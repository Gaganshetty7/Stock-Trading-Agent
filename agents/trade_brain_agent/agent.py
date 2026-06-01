from pathlib import Path
from typing import Any

from core.base_agent import BaseAgent
from agents.trade_brain_agent.schema import TradePlan


class TradeBrainAgent(BaseAgent):
    """
    Institutional-style intraday trade reasoning agent.

    Consumes structured technical market data (price, indicators,
    support/resistance, volume, etc.) and produces actionable trade
    plans with entry, stoploss, target, and confidence scoring.
    """

    @property
    def name(self) -> str:
        return "trade_brain_agent"

    @property
    def skill_path(self) -> str:
        return str(Path(__file__).parent / "skill.md")

    @property
    def tool_names(self) -> list[str]:
        return []

    def parse_output(self, final_output: dict[str, Any]) -> Any:
        """
        Validate the LLM's final output against the TradePlan schema.
        Raises an error if validation fails to prevent silent failures.
        """
        try:
            return TradePlan(**final_output).model_dump()
        except Exception as e:
            self.logger.error(f"Failed to validate TradePlan schema. Error: {e}")
            self.logger.error(f"Raw output was: {final_output}")
            raise ValueError(f"LLM output did not match TradePlan schema: {e}")
