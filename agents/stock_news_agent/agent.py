from pathlib import Path
from typing import Any

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
        # Seamlessly extensible: add new tools to this list when needed 
        # (e.g., "write_json", "search_web", "analyze_sentiment")
        # Include `rank_news_payload` but enforce file-based handoff in the skill prompt
        return ["fetch_broad_market_rss", "rank_news_payload"]

    def parse_output(self, final_output: dict[str, Any]) -> Any:
        # Since fetch_broad_market_rss already writes the JSON to disk,
        # we don't need a strict Pydantic model. We simply return the
        # output the LLM provided during the FINISH action.
        return final_output
