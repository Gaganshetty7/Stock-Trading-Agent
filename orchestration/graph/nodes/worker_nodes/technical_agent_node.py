from langchain_core.messages import AIMessage
from orchestration.graph.constants import WORKER_TECH
from orchestration.graph.state import AgentState

from agents import TechnicalAnalystAgent

async def technical_agent_node(state: AgentState) -> dict:
    agent = TechnicalAnalystAgent()
    task_payload = {"messages": [m.content for m in state.get("messages", [])]}
    result = await agent.run(task=task_payload)
    
    output = result.get("output", "Technical analysis failed")
    return {"messages": [AIMessage(content=f"Observation from {WORKER_TECH}:\n{output}", name=WORKER_TECH)]}
