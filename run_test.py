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
    print("🚀 STOCK INTELLIGENCE PIPELINE")
    print("=" * 60)

    # 1. FETCH & MAP STAGE
    print("[STAGE 1] Fetching & Mapping Broad Market News...")
    from tools.web.broad_market_feeds.broad_rss_fetcher import fetch_broad_market_rss
    payload = await fetch_broad_market_rss(max_age_hours=6)
    
    print(f"  ✓ Fetched {payload['metadata']['total_articles']} articles")
    print(f"  ✓ Mapped to {payload['metadata']['total_companies']} companies")

    # 2. INTRADAY SIGNAL EXTRACTION
    print("[STAGE 2] Running Intraday Signal Extraction...")
    from tools.web.broad_market_feeds.ranker.pre_ranker import rank_news_payload
    final_payload = await rank_news_payload(payload)
    
    # SAVE FINAL RESULT
    timestamp = datetime.now(ist).strftime("%Y%m%d_%H%M%S")
    output_file = Path("outputs") / f"signals_{timestamp}.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, indent=2, ensure_ascii=False)

    elapsed = time.perf_counter() - start_time
    
    meta = final_payload["metadata"]
    signals = final_payload["signals"]
    
    print("\n" + "=" * 60)
    print(f"✅ PIPELINE COMPLETE IN {elapsed:.2f}s")
    print(f"📊 Companies with signals: {meta['companies_with_signal']}")
    print(f"🗑️  Companies removed (noise): {meta['companies_removed']}")
    print(f"📰 Total articles kept: {meta['total_articles_kept']}")
    print(f"📂 Saved to: {output_file}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_pipeline())
