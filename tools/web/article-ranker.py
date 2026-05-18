"""
article_ranker.py
─────────────────
Pipeline:
  1. Load input JSON — supports both {ticker:...} and {mapped_news:{ticker:...}} formats
  2. Keyword pre-filter  → keep articles with market signal
  3. Async fetch         → follow Google News redirect → scrape article text (first 1200 chars)
  4. Batch LLM score     → 6 companies per call, LLM ranks + scores using real content
  5. Write output JSON

Speed estimate (285 companies, 2 keys, 60 effective RPM):
  Step 3: fetch ~570 articles concurrently → ~15-25s
  Step 4: 48 batches at 60 RPM → ~48s
  Total: ~60-90s

Setup:
  export GEMINI_KEY_1="AIza..."
  export GEMINI_KEY_2="AIza..."

Dependencies:
  pip install aiohttp beautifulsoup4 langchain-google-genai python-dotenv
"""

import asyncio
import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Any, Optional


from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────────

MODEL             = "gemini-3.1-flash-lite"
BATCH_SIZE        = 10
TOP_N             = 2
LLM_TIMEOUT       = 45
MAX_RETRIES       = 3
FETCH_TIMEOUT     = 8
FETCH_MAX_CHARS   = 800
FETCH_CONCURRENCY = 40
CONCURRENCY       = 15   # concurrent LLM batch calls

_KEY_1 = os.environ.get("GEMINI_KEY_1", "")
_KEY_2 = os.environ.get("GEMINI_KEY_2", "")
API_KEYS = [k for k in [_KEY_1, _KEY_2] if k]
if not API_KEYS:
    raise RuntimeError("Set GEMINI_KEY_1 (and optionally GEMINI_KEY_2) env vars")

# ── Keyword pre-filter ─────────────────────────────────────────────────────────

_SIGNAL_KEYWORDS = {
    "results", "earnings", "profit", "loss", "revenue", "margin", "ebitda",
    "order", "contract", "win", "deal", "merger", "acquisition", "takeover",
    "buyback", "dividend", "stake", "promoter", "fda", "usfda", "dcgi",
    "approval", "sebi", "guidance", "capex", "expansion", "plant", "shutdown",
    "insolvency", "nclt", "ipo", "bulk deal", "block deal", "open offer",
    "rights issue", "qip", "defence", "railway", "q1", "q2", "q3", "q4",
    "fy26", "fy25", "turnover", "fund", "raises", "upgrade", "downgrade",
    "target price", "beat", "miss", "forecast", "outlook", "target",
    "price target", "buy", "sell", "share price", "valuation", "joint venture",
    "manufacturing", "delivery", "production", "capacity", "tender",
}

def filter_articles(articles: List[Dict]) -> List[Dict]:
    """Keep signal articles; send up to TOP_N*3 to LLM so it can pick the best TOP_N."""
    filtered = [a for a in articles if any(
        kw in a.get("title", "").lower() for kw in _SIGNAL_KEYWORDS
    )]
    # If nothing passes filter, send all (avoid skipping companies entirely)
    return (filtered or articles)[:TOP_N * 3]

# ── Input loader ───────────────────────────────────────────────────────────────

def load_input(path: str) -> dict:
    """
    Supports two formats:
      Format A (flat):        {"TICKER": {"company_insights": [...]}, ...}
      Format B (mapped_news): {"metadata": {...}, "mapped_news": {"TICKER": {...}, ...}}
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    # If there's a mapped_news key, use that — otherwise use the root dict
    return raw.get("mapped_news", raw)

# ── Article fetcher ────────────────────────────────────────────────────────────

_FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-IN,en;q=0.9",
}

_BLOCKED_DOMAINS = {
    # Paywalled — returns login wall, not content
    "economictimes.indiatimes.com",
    "livemint.com",
    "business-standard.com",
    "thehindu.com",
    "financialexpress.com",
    "bloomberg.com",
    "reuters.com",
    "wsj.com",
}

def _domain(url: str) -> str:
    m = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1) if m else ""

from browser_summarizer import async_batch_summarize

async def fetch_all_articles(articles_flat: List[Dict]) -> Dict[str, Optional[str]]:
    """Fetch content for all articles concurrently using Playwright. Returns {link: content_or_None}."""
    unique = {a.get("link"): a for a in articles_flat if a.get("link")}
    if not unique:
        return {}

    articles_to_fetch = list(unique.values())
    scraped_results = await async_batch_summarize(articles_to_fetch, max_workers=50, timeout_ms=5000)

    return {res.get("link", ""): res.get("summary", "") for res in scraped_results}

# ── Helpers ────────────────────────────────────────────────────────────────────

def extract_text(content) -> str:
    if isinstance(content, list):
        return "".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    return str(content)

def clean_json(raw: str) -> str:
    return re.sub(r"^```json\s*|^```\s*|```$", "", raw, flags=re.MULTILINE).strip()

def make_llm(key: str) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model=MODEL, google_api_key=key, temperature=0)

def fallback_company(ticker: str, articles: List[Dict], reason: str) -> Dict:
    return {
        "ticker": ticker,
        "articles_scored": 0,
        "scored_articles": [{
            "title":          a.get("title", ""),
            "source":         a.get("source", ""),
            "link":           a.get("link", ""),
            "published_date": a.get("published_date", ""),
            "content_fetched": False,
            "summary":        "",
            "catalyst":       reason,
            "direction":      "NEUTRAL",
            "confidence":     "0/100",
            "reasoning":      reason,
            "impact_summary": reason,
        } for a in articles[:TOP_N]],
    }

# ── Prompt builder ─────────────────────────────────────────────────────────────

def build_batch_prompt(batch: List[Dict], content_map: Dict[str, Optional[str]]) -> str:
    companies_text = ""
    for comp in batch:
        ticker = comp["ticker"]
        articles_text = ""
        for i, a in enumerate(comp["articles"]):
            content = content_map.get(a.get("link", ""))
            if not content and a.get("summary"):
                content = a.get("summary")
            snippet = f"\n     Content: {content}" if content else ""
            articles_text += f"  {i+1}. {a['title']}  [{a.get('published_date','?')}]{snippet}\n"
        companies_text += f"\nTICKER: {ticker}\n{articles_text}"

    return f"""You are a quantitative analyst covering Indian equities (NSE/BSE).

TASK: For EACH of the {len(batch)} companies below, pick the {TOP_N} most market-moving articles and score them.
Where article content is provided, USE IT to cite specific numbers (revenue, order value, %, beat/miss).

RULES:
- Prefer: earnings beat/miss vs estimates, orders with ₹ value, M&A, FDA/regulatory actions
- Avoid: generic roundups, articles where the ticker is a minor mention
- DISCARD LOW QUALITY: If a company has absolutely NO market-moving news (e.g. only generic coverage, minor mentions, or no hard catalysts), DO NOT include that company in your output at all. Only output companies that have at least one valid catalyst.

CONFIDENCE GUIDE:
  85-100 → hard catalyst WITH specific number: earnings % beat/miss, ₹ order value, M&A price known
  60-84  → results/order/regulatory but no specific comparative number
  35-59  → sector news, analyst note, management commentary without hard data
  0-34   → brief mention or generic market roundup

{companies_text}

Return ONLY a JSON object. No markdown. No explanation. Every ticker must appear.
{{
  "companies": [
    {{
      "ticker": "TICKER",
      "scored_articles": [
        {{
          "article_index": <1-based int from the list above>,
          "summary": "<STRICTLY 2 to 3 sentences: what happened and the KEY numbers or facts>",
          "catalyst": "<3-5 words: e.g. Q4 profit beat, ₹500Cr defence order>",
          "direction": "BULLISH" | "BEARISH" | "NEUTRAL",
          "confidence": <int 0-100>,
          "reasoning": "<2-3 sentences citing SPECIFIC data from content or title>",
          "impact_summary": "<1 sentence for a trader: what to act on today>"
        }}
      ]
    }}
  ]
}}"""

# ── Batch LLM call with retry ──────────────────────────────────────────────────

async def run_batch(
    llm,
    batch: List[Dict],
    content_map: Dict[str, Optional[str]],
    batch_label: str,
) -> Dict[str, Dict]:
    prompt = build_batch_prompt(batch, content_map)
    ticker_to_articles = {c["ticker"]: c["articles"] for c in batch}

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = await asyncio.wait_for(
                llm.ainvoke([HumanMessage(content=prompt)]),
                timeout=LLM_TIMEOUT,
            )
            raw = clean_json(extract_text(resp.content).strip())
            parsed = json.loads(raw)
            assert "companies" in parsed

            results = {}
            returned_tickers = set()

            for comp in parsed["companies"]:
                ticker = comp.get("ticker", "").strip()
                if not ticker or ticker not in ticker_to_articles:
                    continue
                returned_tickers.add(ticker)
                articles = ticker_to_articles[ticker]
                scored = []
                for r in comp.get("scored_articles", [])[:TOP_N]:
                    idx = max(0, min(int(r.get("article_index", 1)) - 1, len(articles) - 1))
                    art = articles[idx]
                    conf = r.get("confidence", 0)
                    scored.append({
                        "title":           art.get("title", ""),
                        "source":          art.get("source", ""),
                        "link":            art.get("link", ""),
                        "published_date":  art.get("published_date", ""),
                        "content_fetched": bool(content_map.get(art.get("link", ""))),
                        "summary":         r.get("summary", ""),
                        "catalyst":        r.get("catalyst", ""),
                        "direction":       r.get("direction", "NEUTRAL"),
                        "confidence":      f"{int(conf)}/100",
                        "reasoning":       r.get("reasoning", ""),
                        "impact_summary":  r.get("impact_summary", ""),
                    })
                results[ticker] = {
                    "ticker":          ticker,
                    "articles_scored": len(scored),
                    "scored_articles": scored,
                }

            # Log tickers the model deliberately dropped due to low quality
            for ticker, articles in ticker_to_articles.items():
                if ticker not in returned_tickers:
                    pass  # Deliberately discarded by the LLM


            return results

        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                if attempt >= MAX_RETRIES:
                    break
                m = re.search(r"retry in ([\d.]+)s", err, re.IGNORECASE)
                wait = min(float(m.group(1)) + 2 if m else 10 * (2 ** attempt), 60)
                print(f"  [429] {batch_label} — waiting {wait:.0f}s (attempt {attempt+1})")
                await asyncio.sleep(wait)
            else:
                print(f"  [ERROR] {batch_label}: {err[:120]}")
                if attempt >= MAX_RETRIES:
                    break
                await asyncio.sleep(2)

    print(f"  [FAIL] {batch_label} — all retries exhausted")
    return {
        c["ticker"]: fallback_company(c["ticker"], c["articles"], "Batch failed after retries")
        for c in batch
    }

# ── Main pipeline ──────────────────────────────────────────────────────────────

async def process(input_path: str, output_path: str, no_fetch: bool = False) -> None:
    start = time.time()
    data = load_input(input_path)
    print(f"\nLoaded {len(data)} companies from {input_path}")
    print(f"Model: {MODEL} | Keys: {len(API_KEYS)} | Batch: {BATCH_SIZE}")
    print(f"Effective RPM: {30 * len(API_KEYS)} | LLM Concurrency: {CONCURRENCY}")

    # Step 1: pre-filter
    work = []
    for ticker, company_data in data.items():
        if ticker == "metadata":
            continue
        insights = company_data.get("company_insights", [])
        if not insights:
            continue
        articles = filter_articles(insights)
        if articles:
            work.append({"ticker": ticker, "articles": articles})

    skipped = len(data) - len(work)
    print(f"After filter: {len(work)} companies ({skipped} skipped — no insights)")

    # Step 2: fetch article content
    content_map: Dict[str, Optional[str]] = {}
    if not no_fetch:
        all_articles_flat = [a for comp in work for a in comp["articles"]]
        print(f"\nFetching content for {len(all_articles_flat)} articles...")
        t_fetch = time.time()
        content_map = await fetch_all_articles(all_articles_flat)
        fetched_ok = sum(1 for v in content_map.values() if v)
        print(f"Fetched: {fetched_ok}/{len(content_map)} articles got content ({time.time()-t_fetch:.1f}s)")
    else:
        print("Skipping article fetch (--no-fetch mode)")

    # Step 3: batch LLM scoring
    batches = [work[i:i+BATCH_SIZE] for i in range(0, len(work), BATCH_SIZE)]
    n_calls = len(batches)
    est_secs = (n_calls / (30 * len(API_KEYS))) * 60
    print(f"\nLLM scoring: {n_calls} batches | Est. ~{est_secs:.0f}s")

    llm_pool = [make_llm(k) for k in API_KEYS]
    semaphore = asyncio.Semaphore(CONCURRENCY)
    companies_data: Dict[str, Any] = {}
    done = {"n": 0}

    async def dispatch_batch(i: int, batch: List[Dict]):
        await asyncio.sleep(i * 1.0)  # 1s stagger to spread RPM evenly
        async with semaphore:
            llm = llm_pool[i % len(llm_pool)]
            label = f"{i+1}/{n_calls}"
            result = await run_batch(llm, batch, content_map, label)
            companies_data.update(result)
            done["n"] += len(result)
            tickers = ", ".join(result.keys())
            print(f"  ✓ Batch {i+1}/{n_calls} → {tickers} [{done['n']}/{len(work)}]")

    await asyncio.gather(*[dispatch_batch(i, batch) for i, batch in enumerate(batches)])

    elapsed = time.time() - start
    fetched_count = sum(
        1 for comp in companies_data.values()
        for art in comp.get("scored_articles", [])
        if art.get("content_fetched")
    )

    output_data = {
        "metadata": {
            "input_file":             input_path,
            "model":                  MODEL,
            "batch_size":             BATCH_SIZE,
            "keys_used":              len(API_KEYS),
            "total_companies":        len(data),
            "companies_processed":    len(work),
            "companies_skipped":      skipped,
            "articles_with_content":  fetched_count,
            "llm_calls_total":        n_calls,
            "execution_time_seconds": round(elapsed, 2),
            "execution_time_minutes": round(elapsed / 60, 2),
            "timestamp":              time.time(),
        },
        "companies": companies_data,
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*55}")
    print(f"Done. {len(companies_data)} companies → {output_path}")
    print(f"Articles with content: {fetched_count}")
    print(f"Time: {elapsed:.1f}s ({elapsed/60:.2f} min)")
    print(f"{'='*55}\n")


def main():
    global BATCH_SIZE
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",      default="outputs/mapped_news3.json")
    parser.add_argument("--output",     default=f"outputs/scored_articles_{timestamp}.json")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--no-fetch",   action="store_true",
                        help="Skip article fetching (faster, title-only mode)")
    args = parser.parse_args()
    BATCH_SIZE = args.batch_size
    asyncio.run(process(args.input, args.output, no_fetch=args.no_fetch))


if __name__ == "__main__":
    main()
