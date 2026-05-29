import asyncio
import json
import pytz
from pathlib import Path
from datetime import datetime
from core.tool import init_tools
from agents.stock_news_agent import StockNewsAgent

async def main():
    # Initialise tool registry
    init_tools()

    agent = StockNewsAgent()
    ist = pytz.timezone("Asia/Kolkata")

    
    print("Starting broad market news sweep using StockNewsAgent...")
    
    # We just run the agent with a generic task since its system prompt 
    # tells it exactly what to do using its available tools.
    task = {"task": "Fetch the latest broad market news and report statistics."}
    
    try:
        result = await agent.run(task)
        
        if result["status"] == "completed":
            print("\n✓ Run completed successfully.")
            print("Agent Final Output:", result["output"])
            timestamp = datetime.now(ist).strftime("%Y%m%d_%H%M%S")
            output_dir = Path("outputs/ranker")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"intraday_signals_{timestamp}.json"
            
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result["output"], f, indent=2, ensure_ascii=False)
            
            print(f"Saved output to: {output_file}")
        else:
            print("\n! Agent run did not complete successfully.")
            print("Status:", result["status"])
            print("Error:", result.get("error"))
            
    except Exception as e:
        print(f"\n! Error running agent: {e}")

if __name__ == "__main__":
    asyncio.run(main())
