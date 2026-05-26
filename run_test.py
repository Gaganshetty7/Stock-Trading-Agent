import asyncio
import time
import json
from datetime import datetime
from pathlib import Path
import pytz

async def run_pipeline():
    ist = pytz.timezone("Asia/Kolkata")
    start_time = time.perf_counter()

    print("\n" + "=" * 60)
    print("STOCK INTELLIGENCE PIPELINE")
    print("=" * 60)

    # ─────────────── STAGE 1: FETCHING ───────────────
    from tools.web.broad_market_feeds.broad_rss_fetcher import fetch_broad_market_rss
    print("[STAGE 1] Fetching Broad Market News...")
    payload = await fetch_broad_market_rss(max_age_hours=6)
    
    # payload is already saved by fetch_broad_market_rss, no need to save again here

    # ─────────────── STAGE 2: RANKING ───────────────
    from tools.web.ranker.tool import rank_news_payload
    print("[STAGE 2] Running Intraday Signal Extraction...")
    ranked_payload = await rank_news_payload(payload)
    
    # Final Ranker Output (Stage 2)
    ts = datetime.now(ist).strftime("%Y%m%d_%H%M%S")
    output_dir = Path("outputs/ranker")
    output_dir.mkdir(parents=True, exist_ok=True)
    ranked_file = output_dir / f"intraday_signals_{ts}.json"
    
    with open(ranked_file, "w", encoding="utf-8") as f:
        json.dump(ranked_payload, f, indent=2, ensure_ascii=False)
    
    print(f"  Saved Signals: {ranked_file}")

    # ─────────────── STAGE 3: SELECTOR ───────────────
    print("[STAGE 3] Running Dynamic Selector...")
    from tools.web.selector.dynamic_selector import dynamic_threshold_select
    
    signals = ranked_payload["signals"]
    top_stocks = dynamic_threshold_select(signals)

    # ─────────────── SAFE COUNTING & TICKER LISTS ───────────────
    bullish_tickers = [t for t, arts in top_stocks.items() if any(x.get("trend") == "bullish" for x in arts)]
    bearish_tickers = [t for t, arts in top_stocks.items() if any(x.get("trend") == "bearish" for x in arts)]
    sideways_tickers = [t for t, arts in top_stocks.items() if any(x.get("trend") == "sideways" for x in arts)]

    bullish_count = len(bullish_tickers)
    bearish_count = len(bearish_tickers)
    sideways_count = len(sideways_tickers)

    # ─────────────── FINAL OUTPUT (TOP STOCKS) ───────────────
    final_output = {
        "metadata": {
            "input_file": str(ranked_file),
            "total_companies": len(signals),
            "selected_top_stocks": sum(len(v) for v in top_stocks.values()),
            "bullish": bullish_count,
            "bearish": bearish_count,
            "sideways": sideways_count,
            "generated_at": datetime.now(ist).isoformat()
        },
        "top_stocks": top_stocks
    }

    final_file = Path("outputs/top_stocks") / f"top_stocks_{ts}.json"
    final_file.parent.mkdir(parents=True, exist_ok=True)
    with open(final_file, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=2)

    # ─────────────── FINAL SUMMARY ───────────────
    elapsed = time.perf_counter() - start_time

    print("\n" + "=" * 60)
    print(f"PIPELINE COMPLETE IN {elapsed:.2f}s")
    print(f"Top Stocks File: {final_file}")
    print(f"Signals File:    {ranked_file}")
    print("=" * 60 + "\n")



if __name__ == "__main__":
    asyncio.run(run_pipeline())


