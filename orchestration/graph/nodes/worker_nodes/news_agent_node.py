from langchain_core.messages import AIMessage
from orchestration.graph.constants import WORKER_NEWS
from orchestration.graph.state import AgentState

from agents import StockNewsAgent

async def news_agent_node(state: AgentState) -> dict:
    agent = StockNewsAgent()
    # Pass the state history as context so it knows what to do
    task_payload = {"messages": [m.content for m in state.get("messages", [])]}
    result = await agent.run(task=task_payload)
    
    output = result.get("output", "News gathering failed")
    return {"messages": [AIMessage(content=f"Observation from {WORKER_NEWS}:\n{output}", name=WORKER_NEWS)]}
