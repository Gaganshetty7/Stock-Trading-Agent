import asyncio
import time
import json
import os
import glob
from datetime import datetime
from pathlib import Path
import pytz

async def run_pipeline():
    ist = pytz.timezone("Asia/Kolkata")
    start_time = time.perf_counter()
    
    print("\n" + "="*60)
    print("🚀 STARTING STOCK INTELLIGENCE PIPELINE (Hardened Flow)")
    print("="*60)

    # 1. FETCH & MAP STAGE
    # Based on the current broad_rss_fetcher.py, it does both fetching and mapping.
    print("[STAGE 1] Fetching & Mapping Broad Market News...")
    from tools.web.broad_market_feeds.broad_rss_fetcher import fetch_broad_market_rss
    payload = await fetch_broad_market_rss(max_age_hours=24)
    
    # 2. SELECTION FOR RANKING
    print(f"  ✓ Fetched {payload['metadata']['total_articles']} articles")
    print(f"  ✓ Mapped to {payload['metadata']['total_companies']} companies")

    # 3. RANKING STAGE
    print("[STAGE 2] Running Production-Hardened Pre-Ranker...")
    from tools.web.pre_ranker import rank_news_payload
    final_payload = await rank_news_payload(payload["mapped_news"])
    
    # SAVE FINAL RESULT
    timestamp = datetime.now(ist).strftime("%Y%m%d_%H%M%S")
    output_file = Path("outputs") / f"final_pre_ranked_{timestamp}.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, indent=2, ensure_ascii=False)

    elapsed = time.perf_counter() - start_time
    # Use fallback count to calculate success rate
    input_count = final_payload['metadata']['total_companies_input']
    fallback_count = final_payload['metadata'].get('fallback_used_count', 0)
    success_rate = round(((input_count - fallback_count) / input_count) * 100, 2) if input_count > 0 else 0

    print("\n" + "="*60)
    print(f"✅ PIPELINE COMPLETE IN {elapsed:.2f}s")
    print(f"📊 COMPANIES OUTPUT: {final_payload['metadata']['total_companies_output']}")
    print(f"📈 SUCCESS RATE: {success_rate}%")
    print(f"📂 SAVED TO: {output_file}")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(run_pipeline())
