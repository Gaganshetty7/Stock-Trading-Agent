import asyncio
from core.tool import init_tools
from agents.stock_news_agent import StockNewsAgent

async def main():
    # Initialise tool registry
    init_tools()

    agent = StockNewsAgent()
    
    print("Starting broad market news sweep using StockNewsAgent...")
    
    try:
        result = await agent.run()
        
        if result["status"] == "completed":
            print("\n✓ Run completed successfully.")
            print("Agent Final Output:", result["output"])
        else:
            print("\n! Agent run did not complete successfully.")
            print("Status:", result["status"])
            print("Error:", result.get("error"))
            
    except Exception as e:
        print(f"\n! Error running agent: {e}")

if __name__ == "__main__":
    asyncio.run(main())
