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

    # ─────────────── STAGE 1 ───────────────
    from tools.web.broad_market_feeds.broad_rss_fetcher import fetch_broad_market_rss

    print("[STAGE 1] Fetching News...")
    payload = await fetch_broad_market_rss(max_age_hours=6)

    print(f"  Articles: {payload['metadata']['total_articles']}")

    # ─────────────── STAGE 2 ───────────────
    from tools.web.ranker.pre_ranker import rank_news_payload

    print("[STAGE 2] Ranking...")
    ranked_payload = await rank_news_payload(payload)

    ts = datetime.now(ist).strftime("%Y%m%d_%H%M%S")

    ranked_file = Path("outputs") / f"signals_{ts}.json"
    ranked_file.parent.mkdir(parents=True, exist_ok=True)

    with open(ranked_file, "w", encoding="utf-8") as f:
        json.dump(ranked_payload, f, indent=2)

    print(f"  Saved: {ranked_file}")

    # ─────────────── STAGE 3 ───────────────
    print("[STAGE 3] Dynamic Selector...")

    from tools.web.selector.dynamic_selector import dynamic_threshold_select

    signals = ranked_payload["signals"]

    top_stocks = dynamic_threshold_select(signals)

    # ─────────────── SAFE COUNTING (FIXED) ───────────────
    bullish = sum(
        1
        for articles in top_stocks.values()
        for x in articles
        if x.get("trend") == "bullish"
    )

    bearish = sum(
        1
        for articles in top_stocks.values()
        for x in articles
        if x.get("trend") == "bearish"
    )

    sideways = sum(
        1
        for articles in top_stocks.values()
        for x in articles
        if x.get("trend") == "sideways"
    )

    # ─────────────── FINAL OUTPUT ───────────────
    final_output = {
        "metadata": {
            "input_file": str(ranked_file),
            "total_companies": len(signals),
            "selected_top_stocks": sum(len(v) for v in top_stocks.values()),
            "bullish": bullish,
            "bearish": bearish,
            "sideways": sideways,
            "generated_at": datetime.now(ist).isoformat()
        },
        "top_stocks": top_stocks
    }

    # ─────────────── SAVE ───────────────
    final_file = Path("outputs") / f"top_stocks_{ts}.json"

    with open(final_file, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=2)

    # ─────────────── SUMMARY ───────────────
    elapsed = time.perf_counter() - start_time

    print("\n" + "=" * 60)
    print(f"DONE IN {elapsed:.2f}s")
    print(f"Top Stocks File: {final_file}")
    print(f"Bullish: {bullish}")
    print(f"Bearish: {bearish}")
    print(f"Sideways: {sideways}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_pipeline())
