import asyncio
import json
from core.tool import init_tools
from agents.technical_analyst_agent.agent import TechnicalAnalystAgent
from agents.technical_analyst_agent.schema import TechnicalAnalystInputSchema

async def main():
    print("Initializing tools...")
    init_tools()

    agent = TechnicalAnalystAgent()

    # Validate input through schema before passing to agent
    raw_input = TechnicalAnalystInputSchema(tickers=["TTML", "TMCV.NS", "CHOLAFIN"])
    task = {
        "tickers": raw_input.tickers
    }


    print("\nStarting Technical Analyst Agent...")
    result = await agent.run(task)

    print("\n" + "="*50)
    print("Agent Execution Completed")
    print("="*50)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
