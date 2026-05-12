import asyncio
import json
import random
from datetime import datetime
from pathlib import Path
import time
from core.tool import init_tools
from agents.news_agent.agent import NewsAgent


async def test():
    run_start_utc = datetime.utcnow()
    run_start_ts = time.perf_counter()

    init_tools()
    agent = NewsAgent()

    stocks = [
        "Gabriel",
        "CIPLA",
        "bergepaint"
    ]

    # This will hold the consolidated results across all stocks (flat dict)
    consolidated_results = {}

    print(f"\n[TEST] Starting rate-limited processing of {len(stocks)} stocks...")

    for i, stock in enumerate(stocks):
        print(f"\n[TEST] ({i+1}/{len(stocks)}) Processing: {stock}")

        try:
            result = await agent.run({
                "stocks": [stock],
                "max_age_hours": 48,
            })

            if result["status"] == "completed":
                output = result["output"]
                # Merge the flat stock-to-signal mapping into our consolidated object
                consolidated_results.update(output)
            else:
                print(f"[ERROR] Agent failed for {stock}: {result.get('error')}")

        except Exception as e:
            print(f"[ERROR] Exception during processing of {stock}: {e}")

        # RESTORED: CRITICAL rate limit evasion sleep between stocks
        if i < len(stocks) - 1:
            delay = 5 + random.uniform(2, 5)
            print(f"[TEST] Sleeping for {delay:.2f}s to evade rate limits...")
            await asyncio.sleep(delay)

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
            "max_age_hours": 48,
            "total_companies_requested": total_requested_stocks,
            "total_companies_returned": total_companies_returned,
            "total_companies_with_sources": total_companies_with_sources,
            "total_companies_without_sources": total_companies_without_sources,
            "extraction_rate": extraction_rate,
        },
        "signals": consolidated_results,
    }

    print("\n\n===== FINAL CONSOLIDATED RESULT =====")
    print(json.dumps(output_payload, indent=2, default=str))
    
    # Save the final consolidated result with a timestamp
    # To revert to a single persistent file, change 'filename' to "market_analysis_report.json"
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"market_analysis_report_{timestamp}.json"
    output_path = Path("outputs") / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(output_payload, f, indent=2, default=str)
    print(f"\n[TEST] Final report saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(test())
