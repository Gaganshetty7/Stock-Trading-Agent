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
        return ["trade_strategy"]

    @property
    def output_schema(self) -> Any:
        return None

    def parse_output(self, final_output: dict[str, Any]) -> Any:
        # The schema is validated inside the generate_trade_plans tool.
        # We just return the final agent message here.
        return final_output
