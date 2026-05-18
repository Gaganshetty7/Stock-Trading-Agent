import asyncio
import time
import json
import os
from datetime import datetime
from pathlib import Path
import pytz

from core.tool import init_tools, get_tool

async def run_pipeline():
    ist = pytz.timezone("Asia/Kolkata")
    start_time = time.perf_counter()
    
    print("\n" + "="*60)
    print("🚀 STARTING STOCK INTELLIGENCE PIPELINE")
    print("="*60)

    # 1. FETCH STAGE
    print("[STAGE 1] Fetching Broad Market RSS News...")
    from tools.web.broad_market_feeds.broad_rss_fetcher import fetch_broad_market_rss
    articles = await fetch_broad_market_rss(max_age_hours=24)
    print(f"  ✓ Fetched {len(articles)} unique articles")

    # 2. MAPPING STAGE
    print("[STAGE 2] Mapping News to Tickers...")
    from tools.web.broad_market_feeds.news_mapper import map_news_to_tickers
    
    alias_file = Path("resources/aliases/alias_lookup.json")
    with open(alias_file, "r", encoding="utf-8") as f:
        alias_lookup = json.load(f)
        
    mapped_data = map_news_to_tickers(articles, alias_lookup)
    print(f"  ✓ Mapped to {len(mapped_data)} companies")

    # 3. RANKING STAGE
    print("[STAGE 3] Running LLM Pre-Ranker (High-Fidelity Filter)...")
    from tools.web.pre_ranker import rank_news_payload
    final_payload = await rank_news_payload(mapped_data)
    
    # SAVE FINAL RESULT
    timestamp = datetime.now(ist).strftime("%Y%m%d_%H%M%S")
    output_file = Path("outputs") / f"pre_ranked_articles_{timestamp}.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, indent=2, ensure_ascii=False)

    elapsed = time.perf_counter() - start_time
    print("\n" + "="*60)
    print(f"✅ PIPELINE COMPLETE IN {elapsed:.2f}s")
    print(f"📊 COMPANIES OUTPUT: {final_payload['metadata']['total_companies_output']}")
    print(f"📂 SAVED TO: {output_file}")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(run_pipeline())
