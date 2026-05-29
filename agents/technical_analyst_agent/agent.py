import os
from typing import Any
from core.base_agent import BaseAgent

class TechnicalAnalystAgent(BaseAgent):
    """
    A specialized agent that acts as a data pipeline node.
    It takes a list of tickers, calls the technical analysis tool, 
    and writes the raw data to disk using the file writer tool.
    """
    
    @property
    def name(self) -> str:
        return "TechnicalAnalystAgent"
        
    @property
    def skill_path(self) -> str:
        return os.path.join(os.path.dirname(__file__), "skill.md")
        
    @property
    def tool_names(self) -> list[str]:
        # Only expose the composite tool to the LLM so it doesn't have to pass massive data
        return ["fetch_and_save_technicals"]
        
    def parse_output(self, final_output: dict[str, Any]) -> Any:
        # Pass the final output straight through without modification
        return final_output
