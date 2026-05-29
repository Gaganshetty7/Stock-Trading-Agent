from pathlib import Path
from typing import Any
import re

from core.base_agent import BaseAgent


class StockNewsAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "stock_news_agent"

    @property
    def skill_path(self) -> str:
        return str(Path(__file__).parent / "skill.md")

    @property
    def tool_names(self) -> list[str]:
        return ["fetch_broad_market_rss", "rank_news_payload"]

    def parse_output(self, final_output: dict[str, Any]) -> Any:
        # Return as is for minimalism, aligning with the pattern in run_test.py
        return final_output



