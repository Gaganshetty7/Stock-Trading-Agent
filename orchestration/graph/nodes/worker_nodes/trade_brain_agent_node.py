from langchain_core.messages import AIMessage
from orchestration.graph.constants import WORKER_TRADE_BRAIN
from orchestration.graph.state import AgentState

from agents import TradeBrainAgent

async def trade_brain_agent_node(state: AgentState) -> dict:
    agent = TradeBrainAgent()
    task_payload = {"messages": [m.content for m in state.get("messages", [])]}
    result = await agent.run(task=task_payload)
    
    output = result.get("output", "Trade planning failed")
    return {"messages": [AIMessage(content=f"Observation from {WORKER_TRADE_BRAIN}:\n{output}", name=WORKER_TRADE_BRAIN)]}
