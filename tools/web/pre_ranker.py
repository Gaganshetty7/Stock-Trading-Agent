import asyncio
import argparse
import json
import os
import re
import time
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# -- Config --
MODEL = "gemini-2.0-flash-lite"
BATCH_SIZE = 10      # Halves request count vs 5
CONCURRENCY = 3      # Safe for 15 RPM free tier
STAGGER_DELAY = 2.0  # seconds between batch dispatches
TIMEOUT = 50         # seconds per call
TOP_N = 2            # articles to keep per company
MIN_CONF = 0.65      # minimum confidence to include article

# -- API Keys setup --
_pool = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 7)]
_main = os.environ.get("GEMINI_API_KEY")
API_KEYS = list(dict.fromkeys(k for k in _pool + [_main] if k))

if not API_KEYS:
    raise RuntimeError("No Gemini API keys found. Set GEMINI_KEY_1..6 or GEMINI_API_KEY")

CLIENT_POOL = [genai.Client(api_key=k) for k in API_KEYS]
print(f"Loaded {len(API_KEYS)} API key(s)")

def normalize_ticker(ticker: str) -> str:
    return re.sub(r'(\.NS|\.BO)$', '', str(ticker).upper().strip())

def robust_json_parser(text: str) -> Optional[Dict]:
    if not text: return None
    clean = text.strip()
    for attempt in [
        lambda t: json.loads(t),
        lambda t: json.loads(t[t.find("{"):t.rfind("}")+1]),
        lambda t: json.loads(re.search(r"\{.*?\}", t, re.DOTALL).group(0)),
    ]:
        try:
            return attempt(clean)
        except:
            continue
    return None

RANK_PROMPT = """You are a senior equity analyst covering Indian equities (NSE/BSE).
TASK: For EACH company below, pick the {top_n} most market-moving articles and score them.
Focus ONLY on news directly about the company — not generic sector roundups.

CONFIDENCE GUIDE:
  0.85-1.0 → hard catalyst with specific number (earnings beat/miss %, ₹ order value, M&A price)
  0.65-0.84 → clear company event but no specific comparative number
  0.40-0.64 → indirect or sector-level news
  <0.40    → generic mention, skip if possible

Return ONLY valid JSON.
Example Format:
{{
  "rankings": [
    {{
      "ticker": "RELIANCE",
      "articles": [
        {{
          "index": 1,
          "score": 8,
          "confidence": 0.95,
          "sentiment": "Bullish",
          "summary": "Reliance reports 15% profit growth led by O2C and retail performance.",
          "catalyst": "Q4 profit beat",
          "reason": "Profit growth of 15% exceeds market expectations."
        }}
      ]
    }}
  ]
}}

Current Time: {current_time}

{content}"""

class QuotaError(Exception):
    pass

async def call_llm(client, prompt: str) -> Optional[str]:
    """Single call logic with transient retry (NOT for 429)."""
    for attempt in range(2):
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                ),
                timeout=TIMEOUT
            )
            return response.text or None
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                raise QuotaError(err)
            if attempt == 0:
                await asyncio.sleep(3)
                continue
    return None

async def run_batch(client, batch: List[Dict], label: str) -> tuple[Dict, bool]:
    """Returns (results_dict, quota_hit)."""
    content = ""
    for comp in batch:
        content += f"\nTICKER: {comp['ticker']}\n"
        for i, art in enumerate(comp["articles"], 1):
            content += f"  {i}. {art.get('title', '').strip()}\n"

    prompt = RANK_PROMPT.format(
        top_n=TOP_N,
        content=content,
        current_time=time.strftime("%Y-%m-%d %H:%M:%S")
    )

    try:
        raw = await call_llm(client, prompt)
    except QuotaError:
        print(f"  [QUOTA] {label} - 429 hit, skipping for later retry")
        return {}, True

    if not raw:
        return {c["ticker"]: [] for c in batch}, False

    parsed = robust_json_parser(raw)
    if not parsed or "rankings" not in parsed:
        return {c["ticker"]: [] for c in batch}, False

    results = {c["ticker"]: [] for c in batch}
    for r in parsed["rankings"]:
        t = normalize_ticker(r.get("ticker", ""))
        if t in results:
            results[t] = r.get("articles", [])
    
    return results, False

async def rank_news_payload(mapped_news: Dict) -> Dict:
    start_time = time.time()
    work = [{"ticker": normalize_ticker(t), "articles": data.get("company_insights", [])} 
            for t, data in mapped_news.items() if data.get("company_insights")]

    if not work:
        return {"metadata": {"total_companies_output": 0}, "companies": {}}

    print(f"Ranking {len(work)} companies (Batch Size: {BATCH_SIZE}, Concurrency: {CONCURRENCY})...")
    batches = [work[i:i+BATCH_SIZE] for i in range(0, len(work), BATCH_SIZE)]
    num_batches = len(batches)
    
    results = {}
    skipped_batches = []
    semaphore = asyncio.Semaphore(CONCURRENCY)
    done_count = 0

    async def dispatch(idx, batch):
        nonlocal done_count
        await asyncio.sleep(idx * STAGGER_DELAY)
        async with semaphore:
            client = CLIENT_POOL[idx % len(CLIENT_POOL)]
            label = f"{idx+1}/{num_batches}"
            batch_res, quota_hit = await run_batch(client, batch, label)

            if quota_hit:
                skipped_batches.append((idx, batch))
                return

            results.update(batch_res)
            done_count += len(batch)
            print(f"  ✓ {label} Processed [{done_count}/{len(work)}]")

    await asyncio.gather(*(dispatch(i, b) for i, b in enumerate(batches)))

    # Deferred Retry for 429s
    if skipped_batches:
        print(f"\n{len(skipped_batches)} batches quota-skipped. Cooling down 60s then retrying...")
        await asyncio.sleep(60)
        for i, batch in skipped_batches:
            client = CLIENT_POOL[i % len(CLIENT_POOL)]
            label = f"retry-{i+1}"
            batch_res, quota_hit = await run_batch(client, batch, label)
            if quota_hit:
                print(f"  [QUOTA] {label} - Still exhausted, skipping permanently")
                for c in batch: results[c["ticker"]] = []
            else:
                results.update(batch_res)
                print(f"  ✓ {label} Retry successful")

    # Output Construction
    final_companies = {}
    for ticker, company_data in mapped_news.items():
        norm_t = normalize_ticker(ticker)
        if norm_t not in results: continue
        
        insights = company_data.get("company_insights", [])
        ranked_list = results[norm_t]
        scored = []
        seen_idx = set()

        for r in ranked_list[:TOP_N]:
            try:
                idx = int(float(r.get("index", 1))) - 1
                conf = float(r.get("confidence", 0))
            except: continue

            if idx in seen_idx or not (0 <= idx < len(insights)): continue
            if conf < MIN_CONF: continue
            seen_idx.add(idx)

            orig = insights[idx]
            scored.append({
                "title": orig.get("title", ""),
                "source": orig.get("source", ""),
                "url": orig.get("url") or orig.get("link", ""),
                "published": orig.get("published", ""),
                "summary": r.get("summary", ""),
                "catalyst": r.get("catalyst", ""),
                "sentiment": str(r.get("sentiment", "Neutral")).capitalize(),
                "confidence": f"{int(conf * 100)}/100",
                "score": r.get("score", 0),
                "reason": r.get("reason", "")
            })
        
        if scored:
            final_companies[ticker] = {
                "ticker": norm_t,
                "articles_scored": len(scored),
                "scored_articles": scored
            }

    elapsed = time.time() - start_time
    return {
        "metadata": {
            "total_companies_input": len(mapped_news),
            "total_companies_output": len(final_companies),
            "execution_time_seconds": round(elapsed, 2),
            "execution_time_minutes": round(elapsed / 60, 2),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S")
        },
        "companies": final_companies
    }

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    with open(args.input, "r") as f:
        data = json.load(f)
    
    result = await rank_news_payload(data.get("mapped_news", data))

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2)
    print(f"✅ SUCCESS: {result['metadata']['total_companies_output']} companies ranked in {args.output}")

if __name__ == "__main__":
    asyncio.run(main())
