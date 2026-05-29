import asyncio
from core.tool import init_tools
from agents.technical_analyst_agent import TechnicalAnalystAgent

async def main():
    # Initialise tool registry
    init_tools()

    agent = TechnicalAnalystAgent()
    
    print("Starting technical analysis sweep using TechnicalAnalystAgent...")
    
    # We run the agent with a list of tickers that it should process.
    task = {
        "tickers": ["RELIANCE", "TCS", "INFY"]
    }
    
    try:
        result = await agent.run(task)
        
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
