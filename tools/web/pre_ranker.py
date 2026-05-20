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
BATCH_SIZE = 5
CONCURRENCY = 3
STAGGER_DELAY = 1.5
TIMEOUT = 45
RETRIES = 2

# API Keys setup
_POOL = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 7)]
_MAIN = os.environ.get("GEMINI_API_KEY")
API_KEYS = list(set([k for k in _POOL + [_MAIN] if k]))

if not API_KEYS:
    raise RuntimeError("No Gemini API keys found (GEMINI_KEY_1-6 or GEMINI_API_KEY)")

CLIENT_POOL = [genai.Client(api_key=k) for k in API_KEYS]
SEMAPHORE = asyncio.Semaphore(CONCURRENCY)

def normalize_ticker(ticker: str) -> str:
    """Standardize ticker names."""
    return re.sub(r'(\.NS|\.BO)$', '', str(ticker).upper().strip())

def robust_json_parser(text: str) -> Optional[Dict]:
    """Safer JSON extraction and parsing."""
    if not text: return None
    clean = text.strip()
    
    # 1. Direct parse attempt
    try:
        return json.loads(clean)
    except:
        pass
        
    # 2. Find outermost braces
    try:
        start = clean.find('{')
        end = clean.rfind('}')
        if start != -1 and end != -1:
            return json.loads(clean[start:end+1])
    except:
        pass
        
    # 3. Last resort: non-greedy regex (for single-line/simple JSONs)
    try:
        match = re.search(r'\{.*?\}', clean, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except:
        pass
    return None

RANK_PROMPT = """Analyze these Indian stock market news articles for significant DIRECT MARKET-MOVING impact on the SPECIFIC TICKER mentioned.
Rank each for potential price movement (0-10) and determine sentiment (Bullish/Bearish/Neutral).
Focus strictly on news specifically about the company (e.g., earnings, deals, legal issues) rather than generic sector updates.

Return ONLY valid JSON with "rankings" list of objects.
Example Format:
{{
  "rankings": [
    {{
      "ticker": "RELIANCE",
      "articles": [
        {{ "index": 1, "score": 8, "confidence": 0.95, "sentiment": "Bullish", "reason": "Reliance announces record profits and massive expansion in green energy." }}
      ]
    }}
  ]
}}

Confidence should be a float between 0 and 1.
"reason" should be a 1-sentence explanation of why this news moves the SPECIFIC stock price.

Current Time: {current_time}

Articles:
{content}"""

async def run_rank_batch(client, batch: List[Dict]) -> List[Dict]:
    content = ""
    for comp in batch:
        content += f"\nTICKER: {comp['ticker']}\n"
        for i, art in enumerate(comp["articles"], 1):
            content += f"  {i}. {art.get('title', '').strip()}\n"

    prompt = RANK_PROMPT.format(
        content=content,
        current_time=time.strftime("%Y-%m-%d %H:%M:%S")
    )

    for attempt in range(RETRIES + 1):
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                ),
                timeout=TIMEOUT
            )
            
            parsed = robust_json_parser(response.text or "")
            if parsed and "rankings" in parsed:
                return parsed["rankings"]
        except Exception as e:
            if attempt == RETRIES:
                print(f"  [ERROR] Batch processing failed after {RETRIES+1} attempts: {str(e)[:100]}")
            else:
                await asyncio.sleep(1 * (attempt+1))
    
    # Fallback with marker
    return [
        {
            "ticker": comp["ticker"], 
            "fallback": True,
            "articles": [{"index": j+1, "score": 2, "confidence": 0.0, "sentiment": "Neutral", "reason": "Fallback used after failure"} 
                         for j in range(len(comp["articles"]))]
        } 
        for comp in batch
    ]

async def rank_news_payload(mapped_news: Dict) -> Dict:
    work = [{"ticker": t, "articles": data.get("company_insights", [])[:2]} 
            for t, data in mapped_news.items() if data.get("company_insights")]

    if not work:
        return {"metadata": {"total_companies_output": 0}, "mapped_news": {}}

    print(f"Ranking {len(work)} companies...")
    start_time = time.time()
    batches = [work[i:i+BATCH_SIZE] for i in range(0, len(work), BATCH_SIZE)]
    output_rankings = {}
    metrics = {"failed_batches": 0, "fallback_used_count": 0}

    async def dispatch(idx, batch):
        b_start = time.time()
        # Spread the load: Add a stagger delay based on batch index
        if idx > 0:
            await asyncio.sleep(idx * STAGGER_DELAY)
            
        async with SEMAPHORE:
            client = CLIENT_POOL[idx % len(CLIENT_POOL)]
            res = await run_rank_batch(client, batch)
            
            b_took = round(time.time() - b_start, 2)
            print(f"  [BATCH] Processed {len(batch)} companies in {b_took}s")
            
            for r in res:
                ticker = normalize_ticker(r.get("ticker", ""))
                if r.get("fallback"):
                    metrics["fallback_used_count"] += 1
                output_rankings[ticker] = r.get("articles", [])

    await asyncio.gather(*(dispatch(i, b) for i, b in enumerate(batches)))

    final_mapped = {}
    for ticker, data in mapped_news.items():
        norm_t = normalize_ticker(ticker)
        if norm_t in output_rankings:
            insights = data.get("company_insights", [])
            ranked_articles = []
            seen_indexes = set()
            
            for r_art in output_rankings[norm_t]:
                try:
                    idx_val = r_art.get("index", 1)
                    idx = int(float(idx_val)) - 1
                    conf = float(r_art.get("confidence", 0))
                except (ValueError, TypeError):
                    continue

                if idx in seen_indexes: 
                    continue
                seen_indexes.add(idx)
                    
                # Production Rule: Only include high-confidence (>= 0.75) articles
                if conf < 0.75:
                    continue
                    
                if 0 <= idx < len(insights):
                    orig = insights[idx]
                    # Only include requested fields, handle url/link legacy
                    item = {
                        "title": orig.get("title", ""),
                        "source": orig.get("source", ""),
                        "url": orig.get("url") or orig.get("link", ""),
                        "age": orig.get("age", ""),
                        "published": orig.get("published", ""),
                        "confidence": conf,
                        "sentiment": str(r_art.get("sentiment", "Neutral")).capitalize()
                    }
                    ranked_articles.append(item)
            if ranked_articles:
                final_mapped[ticker] = {"company_insights": ranked_articles}

    execution_time = round(time.time() - start_time, 2)
    return {
        "metadata": {
            "total_companies_input": len(mapped_news),
            "total_companies_output": len(final_mapped),
            "execution_time_seconds": execution_time,
            "fallback_used_count": metrics["fallback_used_count"],
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")
        },
        "mapped_news": final_mapped
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
