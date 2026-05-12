import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from core.tool import get_tool, init_tools


async def test_broad_fetch(max_age_hours: int = 48) -> None:
    run_start_utc = datetime.now(timezone.utc)
    run_start_ts = time.perf_counter()

    init_tools()
    fetch_tool = get_tool("fetch_rss")

    print(f"[TEST2] Running broad RSS fetch with max_age_hours={max_age_hours}")
    articles = await fetch_tool(max_age_hours=max_age_hours)

    run_end_utc = datetime.now(timezone.utc)
    elapsed_seconds = round(time.perf_counter() - run_start_ts, 2)

    payload = {
        "metadata": {
            "generated_at_utc":      run_end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "run_started_at_utc":    run_start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "run_finished_at_utc":   run_end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "run_duration_seconds":  elapsed_seconds,
            "max_age_hours":         max_age_hours,
            "total_articles":        len(articles),
        },
        "articles": articles,
    }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = Path("outputs") / f"broad_market_test_report_{timestamp}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"[TEST2] Done in {elapsed_seconds}s")
    print(f"[TEST2] Articles fetched: {len(articles)}")
    print(f"[TEST2] Saved test payload to: {output_path}")
    print("[TEST2] First 3 article titles:")
    for idx, article in enumerate(articles[:3], start=1):
        print(f"  {idx}. {article.get('title', 'Unknown')}")


if __name__ == "__main__":
    asyncio.run(test_broad_fetch())