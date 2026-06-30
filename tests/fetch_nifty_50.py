import asyncio
import json
from tools.market.technical_analysis_tool.tool import run_technical_analysis

async def main():
    print("Fetching real-time data for NIFTY 50...")
    
    # Fetch data for NIFTY 50. run_technical_analysis returns both market_context and tickers.
    data = await run_technical_analysis(["NIFTY 50"])
    
    if "market_context" in data and "NIFTY_50" in data["market_context"]:
        # Wrap it in the NIFTY_50 key as requested in your template
        nifty_data = {"NIFTY_50": data["market_context"]["NIFTY_50"]}
        print("\n=== NIFTY 50 DATA ===")
        print(json.dumps(nifty_data, indent=2))
    else:
        print("Failed to fetch NIFTY 50 data. Raw output:")
        print(json.dumps(data, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
