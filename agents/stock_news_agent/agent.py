from typing import Any
from pathlib import Path

from core.base_agent import BaseAgent


class StockNewsAgent(BaseAgent):
    """Agent that sweeps market news, analyzes sentiment, and generates structured signals."""

    @property
    def name(self) -> str:
        return "StockNewsAgent"

    @property
    def skill_path(self) -> str:
        return str(Path(__file__).parent / "skill.md")

    @property
    def tool_names(self) -> list[str]:
        return ["fetch_broad_market_rss", "write_json"]

    def parse_output(self, final_output: dict[str, Any]) -> Any:
        """Parses the final output returned from the LangGraph execution."""
        return final_output
