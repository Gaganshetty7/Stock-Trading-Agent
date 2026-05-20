import asyncio
from core.tool import init_tools
from agents.stock_news_agent.agent import StockNewsAgent


async def main():
    print("Initializing tools...")
    init_tools()

    print("Instantiating StockNewsAgent...")
    agent = StockNewsAgent()

    task = {
        "task": "Sweep the broad market RSS feeds for the last 6 hours, map articles to company tickers, and save the mapped results to outputs."
    }

    print(f"Running agent on task: {task['task']}")
    response = await agent.run(task)

    print("\n--- Agent Execution Complete ---")
    print(f"Status: {response.get('status')}")
    if response.get("status") == "completed":
        output = response.get("output", {})
        print("Success! Final output summary:")
        if "metadata" in output:
            print(f"Metadata: {output['metadata']}")
    else:
        print(f"Error: {response.get('error')}")


if __name__ == "__main__":
    asyncio.run(main())
