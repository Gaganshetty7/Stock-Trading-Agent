import asyncio
import argparse
import json
import os
import re
import time
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# -- Config --
MODEL = "gemini-1.5-flash-8b"
BATCH_SIZE = 15
CONCURRENCY = 10
MAX_RETRIES = 3

API_KEY = os.environ.get("GEMINI_API_KEY", "")

if not API_KEY:
    raise RuntimeError("Set GEMINI_API_KEY env var")

def make_llm():
    return ChatGoogleGenerativeAI(model=MODEL, google_api_key=API_KEY)

def clean_json(text: str) -> str:
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'\s*```', '', text)
    return text.strip()

RANK_PROMPT = """Analyze these Indian stock market news items for a high-frequency trading bot.
Your goal is to identify news that will move the stock price in the NEXT 5-15 MINUTES.

CRITERIA:
1. Market Moving: Focus on Earnings (beats/misses), mega orders (>₹500cr), M&A, USFDA approvals, or CEO change.
2. Priced In Check: Use the 'Time Ago' provided.
   - < 15 mins: High priority (likely not fully priced in).
   - 15-60 mins: Medium priority (partially priced in).
   - > 60 mins: Low priority (usually already reflected in price unless massive surprise).
3. Noise: Ignore generic analyst target price changes (unless major upgrade/downgrade), general sector talk, or standard marketing news.

Rank each article from 0 to 10:
- 10: Just hit the tape (<5m old) AND massive catalyst (e.g. Q4 results beat).
- 7-9: High impact within last 30m.
- 5-6: Significant but 1h+ old or slightly less impactful catalyst.
- 0-4: Noise, education, or stale news.

Return ONLY a JSON object in this format:
{{
  "rankings": [
    {{
      "ticker": "TICKER",
      "articles": [
        {{ "index": 1, "score": 8 }},
        ...
      ]
    }}
  ]
}}

Articles:
{content}
"""

async def run_rank_batch(llm, batch: List[Dict], batch_label: str) -> List[Dict]:
    content = ""
    for comp in batch:
        content += f"\nTicker: {comp['ticker']}\n"
        for i, art in enumerate(comp["articles"], 1):
            title = art.get("title", "")
            age = art.get("age", "")
            content += f"  {i}. {title} | Time Ago: {age}\n"

    prompt = RANK_PROMPT.format(content=content)

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = await asyncio.wait_for(
                llm.ainvoke([HumanMessage(content=prompt)]),
                timeout=45,
            )
            text = resp.content
            if isinstance(text, list):
                text = "".join([p.get("text", "") if isinstance(p, dict) else str(p) for p in text])
            
            raw = clean_json(text).strip()
            parsed = json.loads(raw)
            return parsed.get("rankings", [])
        except Exception as e:
            if attempt >= MAX_RETRIES:
                print(f"  [FAIL] {batch_label}: {str(e)[:100]}")
                break
            await asyncio.sleep(5 * (2**attempt))
    return []

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    with open(args.input, "r") as f:
        data = json.load(f)
    
    # Handle both nested and flat mapped news
    if "mapped_news" in data:
        mapped_news = data["mapped_news"]
    elif any(isinstance(v, dict) and "company_insights" in v for v in data.values()):
        mapped_news = data
    else:
        print("Error: Input JSON does not seem to contain mapped news with company_insights.")
        return
    
async def rank_news_payload(mapped_news: Dict) -> Dict:
    work = []
    SCORE_THRESHOLD = 5

    for ticker, comp_data in mapped_news.items():
        insights = comp_data.get("company_insights", [])
        if not insights: continue
        
        # Latest 2 articles
        insights.sort(key=lambda x: x.get("age_h", 9999))
        insights = insights[:2]
        comp_data["company_insights"] = insights
        work.append({"ticker": ticker, "articles": insights})

    if not work:
        return {
            "metadata": {
                "total_companies_input": len(mapped_news),
                "total_companies_output": 0,
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")
            },
            "mapped_news": {}
        }

    print(f"Ranking {len(work)} companies (top 2 latest articles each)...")
    
    batches = [work[i:i+BATCH_SIZE] for i in range(0, len(work), BATCH_SIZE)]
    llm = make_llm()
    semaphore = asyncio.Semaphore(CONCURRENCY)
    output_rankings = {}

    async def dispatch(i, batch):
        async with semaphore:
            res = await run_rank_batch(llm, batch, f"Batch {i+1}")
            for r in res:
                output_rankings[r["ticker"]] = r["articles"]
            print(f"  ✓ Processed batch {i+1}/{len(batches)}")

    await asyncio.gather(*(dispatch(i, b) for i, b in enumerate(batches)))

    # Assemble final output and FILTER by score
    final_mapped_news = {}
    KEEP_FIELDS = {"title", "source", "link", "published_date", "age"}

    for ticker, comp_data in mapped_news.items():
        ranks = output_rankings.get(ticker, [])
        insights = comp_data.get("company_insights", [])
        
        has_market_moving = False
        refined_insights = []

        # Map scores to articles
        for r in ranks:
            idx = r.get("index", 1) - 1
            if 0 <= idx < len(insights):
                score = r.get("score", 0)
                art = insights[idx]
                
                if score >= SCORE_THRESHOLD:
                    # Filter to only keep desired fields
                    trimmed_art = {k: v for k, v in art.items() if k in KEEP_FIELDS}
                    refined_insights.append(trimmed_art)
                    has_market_moving = True

        if has_market_moving:
            comp_data["company_insights"] = refined_insights
            final_mapped_news[ticker] = comp_data

    return {
        "metadata": {
            "total_companies_input": len(mapped_news),
            "total_companies_output": len(final_mapped_news),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        },
        "mapped_news": final_mapped_news
    }

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    with open(args.input, "r") as f:
        data = json.load(f)
    
    # Handle both nested and flat mapped news
    if "mapped_news" in data:
        mapped_news = data["mapped_news"]
    elif any(isinstance(v, dict) and "company_insights" in v for v in data.values()):
        mapped_news = data
    else:
        print("Error: Input JSON does not seem to contain mapped news with company_insights.")
        return
    
    final_payload = await rank_news_payload(mapped_news)

    with open(args.output, "w") as f:
        json.dump(final_payload, f, indent=2, ensure_ascii=False)
    
    print(f"\nDone. Saved high-fidelity results ({final_payload['metadata']['total_companies_output']} companies) → {args.output}")

if __name__ == "__main__":
    asyncio.run(main())
