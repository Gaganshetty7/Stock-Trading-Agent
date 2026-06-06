from orchestration.graph.state import AgentState
from supervisors.trading_supervisor.agent import TradingSupervisorAgent
from supervisors.trading_supervisor.logger import logger

async def supervisor_node(state: AgentState) -> dict:
    agent = TradingSupervisorAgent()
    
    current_step = state.get("step_count", 0)
    logger.info(f"[Recursion #{current_step + 1}] Supervisor node invoked.")
    
    # Pass the raw messages directly
    result = await agent.run(messages=state.get("messages", []))
    
    if result["status"] == "completed":
        routing_decision = result["output"]
        next_node = routing_decision.get("next", "FINISH")
        logger.info(f"[Recursion #{current_step + 1}] Routing → {next_node}")
        return {
            "next": next_node,
            "step_count": 1
        }
    else:
        # Fallback on failure
        logger.error(f"[Recursion #{current_step + 1}] Supervisor failed. Forcing FINISH.")
        return {"next": "FINISH", "step_count": 1}
