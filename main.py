import asyncio
import json
import random
from datetime import datetime
from pathlib import Path
import time

from core.tool import init_tools
from agents.news_agent.agent import NewsAgent


def load_stocks() -> list[str]:
    path = Path(__file__).parent / "resources" / "master_stock_list.json"
    if not path.exists():
        return []
    with open(path, "r") as f:
        data = json.load(f)
    return [item["name"] for item in data]


async def main():
    run_start_utc = datetime.utcnow()
    run_start_ts = time.perf_counter()

    # Initialise tool registry
    init_tools()

    stocks = load_stocks()
    if not stocks:
        print("No stocks found in master list.")
        return

    agent = NewsAgent()
    consolidated_results = {}

    BATCH_SIZE = 50
    print(f"Starting news analysis for {len(stocks)} stocks in batches of {BATCH_SIZE}...")

    for i in range(0, len(stocks), BATCH_SIZE):
        batch = stocks[i:i + BATCH_SIZE]
        print(f"[{i+1} to {min(i+BATCH_SIZE, len(stocks))}/{len(stocks)}] Processing batch...")

        try:
            result = await agent.run({
                "stocks": batch,
                "max_age_hours": 48,
            })

            if result["status"] == "completed":
                # Merge flat results (stock -> signal)
                consolidated_results.update(result["output"])
            else:
                print(f"  ! Agent failed for batch: {result.get('error')}")

        except Exception as e:
            print(f"  ! Error processing batch: {e}")

        # Evade rate limits: Sleep between batches
        if i + BATCH_SIZE < len(stocks):
            delay = 3 + random.uniform(2, 4)
            await asyncio.sleep(delay)

    # Save final consolidated report with timestamp
    # To revert to a single persistent file, change 'filename' to "market_analysis_report.json"
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"market_analysis_report_{timestamp}.json"
    output_path = Path(__file__).parent / "outputs" / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    run_end_utc = datetime.utcnow()
    elapsed_seconds = round(time.perf_counter() - run_start_ts, 2)
    total_requested_stocks = len(stocks)
    total_companies_returned = len(consolidated_results)
    total_companies_with_sources = sum(
        1 for signal in consolidated_results.values()
        if isinstance(signal, dict) and signal.get("sources")
    )
    total_companies_without_sources = max(total_requested_stocks - total_companies_with_sources, 0)
    extraction_rate = round(
        (total_companies_with_sources / total_requested_stocks) if total_requested_stocks else 0.0,
        4,
    )

    output_payload = {
        "metadata": {
            "generated_at_utc": run_end_utc.isoformat() + "Z",
            "run_started_at_utc": run_start_utc.isoformat() + "Z",
            "run_finished_at_utc": run_end_utc.isoformat() + "Z",
            "run_duration_seconds": elapsed_seconds,
            "batch_size": BATCH_SIZE,
            "max_age_hours": 48,
            "total_companies_requested": total_requested_stocks,
            "total_companies_returned": total_companies_returned,
            "total_companies_with_sources": total_companies_with_sources,
            "total_companies_without_sources": total_companies_without_sources,
            "extraction_rate": extraction_rate,
        },
        "signals": consolidated_results,
    }

    with open(output_path, "w") as f:
        json.dump(output_payload, f, indent=2, default=str)

    print(f"\n✓ Done — Consolidated report saved to {output_path}")
    print(f"✓ Total stocks returned: {len(consolidated_results)}")
    print(f"✓ Stocks with >=1 sources: {total_companies_with_sources}")


if __name__ == "__main__":
    asyncio.run(main())
