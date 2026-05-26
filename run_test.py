import asyncio
import time
import json
import os
from datetime import datetime
from pathlib import Path
import pytz

async def run_pipeline():
    ist = pytz.timezone("Asia/Kolkata")
    start_time = time.perf_counter()
    
    print("\n" + "=" * 60)
    print("STOCK INTELLIGENCE PIPELINE")
    print("=" * 60)

    # 1. FETCH & MAP STAGE
    print("[STAGE 1] Fetching & Mapping Broad Market News...")
    from tools.web.broad_market_feeds.broad_rss_fetcher import fetch_broad_market_rss
    payload = await fetch_broad_market_rss(max_age_hours=6)

    # 2. INTRADAY SIGNAL EXTRACTION
    print("[STAGE 2] Running Intraday Signal Extraction...")
    from tools.web.ranker.tool import rank_news_payload

    final_payload = await rank_news_payload(payload)
    
    # SAVE FINAL RESULT
    elapsed = round(time.perf_counter() - start_time, 2)
    final_payload["metadata"]["pipeline_time_seconds"] = elapsed

    timestamp = datetime.now(ist).strftime("%Y%m%d_%H%M%S")
    output_dir = Path("outputs/ranker")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"intraday_signals_{timestamp}.json"
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, indent=2, ensure_ascii=False)



    elapsed = time.perf_counter() - start_time
    
    print(f"Saved Signals:    {output_file}")
    print("\n" + "=" * 60)
    print(f"PIPELINE COMPLETE IN {elapsed:.2f}s")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_pipeline())


