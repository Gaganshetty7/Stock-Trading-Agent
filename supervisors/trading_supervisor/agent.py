import os
from typing import List, Dict, Any
from langchain_core.messages import SystemMessage, BaseMessage
from core.llm import get_llm
from config.settings import (
    TRADING_SUPERVISOR_LLM_PROVIDER,
    TRADING_SUPERVISOR_MODEL,
    TRADING_SUPERVISOR_LLM_TEMPERATURE,
    TRADING_SUPERVISOR_API_KEY
)
from .schemas import SupervisorRoutingSchema
from .logger import logger

class TradingSupervisorAgent:
    """
    A standalone supervisor that uses structured output for one-shot routing.
    Does not inherit from BaseAgent to avoid ReAct loop conflicts.
    """

    def __init__(self):
        self.logger = logger

        # Use supervisor-specific LLM configuration
        self.llm = get_llm(
            provider=TRADING_SUPERVISOR_LLM_PROVIDER,
            model=TRADING_SUPERVISOR_MODEL,
            temperature=TRADING_SUPERVISOR_LLM_TEMPERATURE,
            api_key=TRADING_SUPERVISOR_API_KEY
        )
        
        # Generic enforcement using the exact same style as BaseAgent's run() method
        self.structured_llm = self.llm.with_structured_output(SupervisorRoutingSchema)
        
    def _build_system_prompt(self) -> str:
        """Builds the system prompt just like BaseAgent, but strictly for routing."""
        skill_path = os.path.join(os.path.dirname(__file__), "skill.md")
        with open(skill_path, "r") as f:
            skill = f.read()
            
        return skill
            
    async def run(self, messages: List[BaseMessage]) -> Dict[str, Any]:
        """Takes the graph message history and returns a routing decision."""
        self.logger.info("--- Supervisor Run Started ---")
        self.logger.info(f"Input message history contains {len(messages)} messages.")
        
        system_prompt = self._build_system_prompt()
        full_messages = [SystemMessage(content=system_prompt)] + list(messages)
        
        # Make the one-shot structured output call
        try:
            self.logger.info("Invoking LLM for structured routing decision...")
            response = await self.structured_llm.ainvoke(full_messages)
            
            self.logger.info(f"Supervisor Decision: next = {response.next}")
            self.logger.info(f"Supervisor Reasoning: {response.reasoning}")
            self.logger.info("--- Supervisor Run Completed ---")
            
            return {
                "status": "completed",
                "output": {
                    "reasoning": response.reasoning,
                    "next": response.next
                }
            }
        except Exception as e:
            self.logger.error(f"Supervisor error during execution: {str(e)}")
            self.logger.info("--- Supervisor Run Failed ---")
            return {"status": "error", "error": str(e), "output": {"next": "FINISH"}}
