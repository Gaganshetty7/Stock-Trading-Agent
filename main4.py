import asyncio
from langchain_core.messages import HumanMessage
from core.tool import init_tools
from orchestration.graph.builder import build_graph

async def main():
    # Initialise tool registry
    init_tools()

    print("Building the Trading Supervisor Graph...")
    graph = build_graph()
    
    print("\nStarting the Multi-Agent Trading Pipeline...")
    
    # We start the graph with an initial task request for the Supervisor
    initial_state = {
        "messages": [HumanMessage(content="Start the daily trading analysis pipeline. Fetch news to get top tickers, run technicals on them, and then generate trade plans.")],
        "step_count": 0
    }
    
    # Provide a generous recursion limit, but cap it to prevent infinite loops burning credits
    config = {"recursion_limit": 20} 
    
    try:
        interrupted = False
        # Stream the graph execution to watch the progress in real time
        async for event in graph.astream(initial_state, config=config):
            for node_name, state_update in event.items():
                # Detect human-in-the-loop interrupt
                if node_name == "__interrupt__":
                    interrupted = True
                    print(f"\n{'='*40}")
                    print(f"    ⏸  HUMAN-IN-THE-LOOP INTERRUPT")
                    print(f"{'='*40}")
                    print(f"\n Pipeline paused before TradeBrainWorker.")
                    print(f" Reason: HUMAN_IN_THE_LOOP is enabled in orchestration/config.py")
                    print(f" To resume, implement graph.astream(None, config) or set HUMAN_IN_THE_LOOP=false")
                    continue

                print(f"\n{'='*40}")
                print(f"         NODE: {node_name}")
                print(f"{'='*40}")
                
                # If a worker returned a new message (observation), print it
                if "messages" in state_update and state_update["messages"]:
                    last_message = state_update["messages"][-1]
                    print(f"\n[OUTPUT from {last_message.name or 'Worker'}]:")
                    print(last_message.content)
                
                # If the supervisor made a routing decision, print it
                if "next" in state_update:
                    route = state_update["next"]
                    print(f"\n[SUPERVISOR DECISION] -> Routing to: {route}")
        
        if interrupted:
            print("\n⏸  Pipeline halted — awaiting human approval to continue.")
        else:
            print("\n Full Multi-Agent Pipeline completed successfully.")
            
    except Exception as e:
        print(f"\n Error running workflow: {e}")

if __name__ == "__main__":
    asyncio.run(main())
