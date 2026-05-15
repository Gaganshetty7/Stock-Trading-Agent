"""
article_ranker.py
─────────────────
Batches 5 companies per LLM call.

Speed math (276 companies, 2 keys, 60 effective RPM):
  276 ÷ 6 = 46 calls
  Spaced by 1.0s = 46 seconds total dispatch time  ✓ under 1 minute

Tuning:
  BATCH_SIZE = 6  → optimum for 276 companies within 60 RPM
  BATCH_SIZE = 8  → faster, model starts dropping tickers
  BATCH_SIZE = 10+ → not recommended, output degrades

Setup:
  export GEMINI_KEY_1="AIza..."
  export GEMINI_KEY_2="AIza..."

Usage:
  PYTHONPATH=. python tools/web/article-ranker.py \
      --input  outputs/mapped_news3.json \
      --output outputs/scored_articles.json
"""

import asyncio
import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Any
from dotenv import load_dotenv

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────────

MODEL      = "gemini-3.1-flash-lite"   # 30 RPM/key free tier
BATCH_SIZE = 6                          # companies per LLM call
TOP_N      = 2                          # articles to score per company
LLM_TIMEOUT = 45                        # seconds per batch call
MAX_RETRIES = 3

_KEY_1 = os.environ.get("GEMINI_KEY_1", "")
_KEY_2 = os.environ.get("GEMINI_KEY_2", "")
API_KEYS = [k for k in [_KEY_1, _KEY_2] if k]
if not API_KEYS:
    raise RuntimeError("Set GEMINI_KEY_1 (and optionally GEMINI_KEY_2) env vars")

# One semaphore slot per key — each key handles 1 concurrent batch call
# However, to maximize the 60 RPM we should launch them concurrently.
CONCURRENCY = 15

# ── Filter ───────────────────────────────────────────────────────────────────

def filter_articles(articles: List[Dict]) -> List[Dict]:
    """Pass all articles directly to the LLM (capped to 10 to fit context)."""
    return articles[:10]

# ── Helpers ────────────────────────────────────────────────────────────────────

def load_input(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

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
            "summary":        "",
            "catalyst":       reason,
            "direction":      "NEUTRAL",
            "confidence":     "0/100",
            "reasoning":      reason,
            "impact_summary": reason,
        } for a in articles[:TOP_N]],
    }

# ── Prompt builder ─────────────────────────────────────────────────────────────

def build_batch_prompt(batch: List[Dict]) -> str:
    """
    batch = [{"ticker": "RELIANCE", "articles": [{"title":..., "published_date":...}, ...]}, ...]
    """
    companies_text = ""
    for comp in batch:
        ticker = comp["ticker"]
        articles_text = "\n".join(
            f"  {i+1}. {a['title']}  [{a.get('published_date','?')}]"
            for i, a in enumerate(comp["articles"])
        )
        companies_text += f"\nTICKER: {ticker}\n{articles_text}\n"

    return f"""You are a quantitative analyst covering Indian equities (NSE/BSE).

TASK: For EACH of the {len(batch)} companies below, pick the {TOP_N} most market-moving articles and score them.

RULES:
- Prefer: earnings beat/miss vs estimates, orders with ₹ value, M&A, FDA/regulatory actions
- Avoid: generic roundups, articles where the ticker is a minor mention
- You MUST return a result for EVERY ticker listed — do not skip any

CONFIDENCE GUIDE:
  85-100 → hard catalyst with clear direction (earnings beat/miss vs estimates, named ₹ order value, M&A price known)
  60-84  → results without estimate comparison, order win without value, regulatory filing
  35-59  → sector news, analyst note without new data, management commentary
  0-34   → brief mention, generic roundup

{companies_text}

Return ONLY a JSON object. No markdown. No explanation. Every ticker must appear.
{{
  "companies": [
    {{
      "ticker": "TICKER",
      "scored_articles": [
        {{
          "article_index": <1-based int from the list above>,
          "summary": "<2 sentences: what happened and the key number or fact>",
          "catalyst": "<3-5 words: e.g. Q4 profit beat, Defence order win>",
          "direction": "BULLISH" | "BEARISH" | "NEUTRAL",
          "confidence": <int 0-100>,
          "reasoning": "<2-3 sentences citing specific data from the title>",
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
    batch_label: str,
) -> Dict[str, Dict]:
    """
    Returns dict of ticker → scored company dict.
    Falls back gracefully per-company on parse failure.
    """
    prompt = build_batch_prompt(batch)
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
                        "title":          art.get("title", ""),
                        "source":         art.get("source", ""),
                        "link":           art.get("link", ""),
                        "published_date": art.get("published_date", ""),
                        "summary":        r.get("summary", ""),
                        "catalyst":       r.get("catalyst", ""),
                        "direction":      r.get("direction", "NEUTRAL"),
                        "confidence":     f"{int(conf)}/100",
                        "reasoning":      r.get("reasoning", ""),
                        "impact_summary": r.get("impact_summary", ""),
                    })
                results[ticker] = {
                    "ticker":          ticker,
                    "articles_scored": len(scored),
                    "scored_articles": scored,
                }

            # Fill in any tickers the model silently dropped
            for ticker, articles in ticker_to_articles.items():
                if ticker not in returned_tickers:
                    print(f"  [WARN] {batch_label} — model dropped {ticker}, using fallback")
                    results[ticker] = fallback_company(ticker, articles, "Model did not return this ticker")

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

    # All retries exhausted
    print(f"  [FAIL] {batch_label} — all retries exhausted, using fallback for all")
    return {
        c["ticker"]: fallback_company(c["ticker"], c["articles"], "Batch failed after retries")
        for c in batch
    }

# ── Main pipeline ──────────────────────────────────────────────────────────────

async def process(input_path: str, output_path: str) -> None:
    start = time.time()
    data = load_input(input_path)
    print(f"\nLoaded {len(data)} companies from {input_path}")
    print(f"Model: {MODEL} | Keys: {len(API_KEYS)} | Batch size: {BATCH_SIZE}")
    print(f"Effective RPM: {30 * len(API_KEYS)} | Concurrency: {CONCURRENCY}")

    # Pre-filter
    work = []
    for ticker, company_data in data.items():
        insights = company_data.get("company_insights", [])
        if not insights:
            continue
        articles = filter_articles(insights)
        if articles:
            work.append({"ticker": ticker, "articles": articles})

    skipped = len(data) - len(work)
    print(f"After keyword filter: {len(work)} companies ({skipped} skipped)")

    # Chunk into batches
    batches = [work[i:i+BATCH_SIZE] for i in range(0, len(work), BATCH_SIZE)]
    n_calls = len(batches)
    est_secs = (n_calls / (30 * len(API_KEYS))) * 60
    print(f"Batches: {n_calls} | Est. time: ~{est_secs:.0f}s\n")

    # LLM pool — round robin across keys
    llm_pool = [make_llm(k) for k in API_KEYS]
    semaphore = asyncio.Semaphore(CONCURRENCY)
    companies_data: Dict[str, Any] = {}
    done = {"n": 0}

    async def dispatch_batch(i: int, batch: List[Dict]):
        # Stagger the dispatches by 1 second horizontally to perfectly spread 
        # the 46 batches over 46 seconds, guaranteeing no 429 burst limits.
        await asyncio.sleep(i * 1.0)
        async with semaphore:
            llm = llm_pool[i % len(llm_pool)]
            label = f"{i+1}/{n_calls} ({[c['ticker'] for c in batch]})"
            result = await run_batch(llm, batch, label)
            companies_data.update(result)
            done["n"] += len(result)
            tickers = ", ".join(result.keys())
            print(f"  ✓ Batch {i+1}/{n_calls} → {tickers} [{done['n']}/{len(work)} done]")

    await asyncio.gather(*[dispatch_batch(i, batch) for i, batch in enumerate(batches)])

    elapsed = time.time() - start
    output_data = {
        "metadata": {
            "input_file":             input_path,
            "model":                  MODEL,
            "batch_size":             BATCH_SIZE,
            "keys_used":              len(API_KEYS),
            "total_companies":        len(data),
            "companies_processed":    len(work),
            "companies_skipped":      skipped,
            "llm_calls_total":        n_calls,
            "execution_time_seconds": round(elapsed, 2),
            "execution_time_minutes": round(elapsed / 60, 2),
            "concurrency":            CONCURRENCY,
            "timestamp":              time.time(),
        },
        "companies": companies_data,
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*55}")
    print(f"Done. {len(companies_data)} companies → {output_path}")
    print(f"LLM calls: {n_calls} | Time: {elapsed:.1f}s ({elapsed/60:.2f} min)")
    print(f"{'='*55}\n")


def main():
    global BATCH_SIZE
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  default="outputs/mapped_news3.json")
    parser.add_argument("--output", default="outputs/scored_articles.json")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()
    BATCH_SIZE = args.batch_size
    asyncio.run(process(args.input, args.output))


if __name__ == "__main__":
    main()
