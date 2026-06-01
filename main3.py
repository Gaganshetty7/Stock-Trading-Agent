import asyncio
import json
from core.tool import init_tools
from tools.storage.file_writer import write_json
from agents.trade_brain_agent import TradeBrainAgent
from agents.trade_brain_agent.schema import TradePlan

async def main():
    print("Initializing tools...")
    init_tools()

    agent = TradeBrainAgent()

    # Raw technical data
    technical_data = {
      "RELIANCE.NS": {
        "stock": "RELIANCE.NS",
        "timestamp": "2026-05-29T14:24:18.710347+05:30",
        "status": "ok",
        "market_data": {
          "current_price": 1328.4,
          "today_open": 1364.0,
          "today_high": 1368.5,
          "today_low": 1326.3,
          "previous_close": 1328.6
        },
        "technical_indicators": {
          "pivot": 1328.4,
          "MA20": 1328.37,
          "VWAP": 1341.53,
          "RSI_1m": 46.51,
          "RSI_5m": 40.96,
          "trend": "SIDEWAYS"
        },
        "support_resistance": {
          "R1": 1329.4,
          "R2": 1330.4,
          "R3": 1331.4,
          "S1": 1327.4,
          "S2": 1326.4,
          "S3": 1325.4
        },
        "volume_analysis": {
          "today_total_volume": 17435703,
          "last_candle_volume": 25110,
          "average_volume": 24108,
          "volume_strength": 1.04
        },
        "ma_timeframes": {
          "MA20_1m": 1328.37,
          "MA20_5m": 1331.68,
          "MA20_15m": 1339.32
        }
      },
      "TCS.NS": {
        "stock": "TCS.NS",
        "timestamp": "2026-05-29T14:24:18.719344+05:30",
        "status": "ok",
        "market_data": {
          "current_price": 2284.6,
          "today_open": 2310.0,
          "today_high": 2333.6,
          "today_low": 2280.0,
          "previous_close": 2282.9
        },
        "technical_indicators": {
          "pivot": 2283.7,
          "MA20": 2282.6,
          "VWAP": 2307.68,
          "RSI_1m": 57.14,
          "RSI_5m": 43.4,
          "trend": "SIDEWAYS"
        },
        "support_resistance": {
          "R1": 2285.8,
          "R2": 2287.0,
          "R3": 2289.1,
          "S1": 2282.5,
          "S2": 2280.4,
          "S3": 2279.2
        },
        "volume_analysis": {
          "today_total_volume": 3779567,
          "last_candle_volume": 7401,
          "average_volume": 7146,
          "volume_strength": 1.04
        },
        "ma_timeframes": {
          "MA20_1m": 2282.6,
          "MA20_5m": 2286.12,
          "MA20_15m": 2301.38
        }
      },
      "INFY.NS": {
        "stock": "INFY.NS",
        "timestamp": "2026-05-29T14:24:18.728522+05:30",
        "status": "ok",
        "market_data": {
          "current_price": 1190.9,
          "today_open": 1183.6,
          "today_high": 1210.0,
          "today_low": 1180.5,
          "previous_close": 1190.9
        },
        "technical_indicators": {
          "pivot": 1190.13,
          "MA20": 1189.63,
          "VWAP": 1200.35,
          "RSI_1m": 50.7,
          "RSI_5m": 25.27,
          "trend": "SIDEWAYS"
        },
        "support_resistance": {
          "R1": 1192.27,
          "R2": 1193.63,
          "R3": 1195.77,
          "S1": 1188.77,
          "S2": 1186.63,
          "S3": 1185.27
        },
        "volume_analysis": {
          "today_total_volume": 13680001,
          "last_candle_volume": 17575,
          "average_volume": 39501,
          "volume_strength": 0.44
        },
        "ma_timeframes": {
          "MA20_1m": 1189.63,
          "MA20_5m": 1195.67,
          "MA20_15m": 1200.76
        }
      }
    }

    print("\nStarting Trade Brain Agent analysis...")
    final_results = {}

    for symbol, data in technical_data.items():
        print(f"Analyzing {symbol}...")
        
        try:
            result = await agent.run(data)
            if result["status"] == "completed":
                final_results[symbol] = result["output"]
            else:
                print(f"  ! Agent failed for {symbol}: {result.get('error')}")
                final_results[symbol] = {"error": result.get("error")}
        except Exception as e:
            print(f"  ! Exception for {symbol}: {e}")
            final_results[symbol] = {"error": str(e)}

    # Save to disk using tool
    print("\n✓ All runs finished.")
    try:
        filepath = await write_json(
            filename_prefix="trade_strategy/plan",
            data=final_results,
            overwrite=False
        )
        print(f"✓ Saved final multi-stock Trade Plans to: {filepath}")
    except Exception as e:
        print(f"! Failed to write file: {e}")

if __name__ == "__main__":
    asyncio.run(main())
