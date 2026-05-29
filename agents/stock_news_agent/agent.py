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
        return ["fetch_broad_market_rss", "rank_news_payload"]

    def parse_output(self, final_output: dict[str, Any]) -> Any:
        """
        Final verification gate to ensure strict schema compliance.
        Maps 'signals' to 'results' if needed, enforces float types, 
        and strictly maps trend literals to bullish/bearish/sideways.
        """
        if not isinstance(final_output, dict):
            return final_output

        # Remap 'signals' to 'results' if LLM hallucinated the key
        if "signals" in final_output and "results" not in final_output:
            final_output["results"] = final_output.pop("signals")

        if "results" in final_output:
            for s in final_output["results"]:
                # Ensure float types
                try:
                    s["confidence"] = float(s.get("confidence", 0.0))
                except (ValueError, TypeError):
                    s["confidence"] = 0.5
                    
                try:
                    s["impact_score"] = float(s.get("impact_score", 0.0))
                except (ValueError, TypeError):
                    s["impact_score"] = 0.5
                
                # Strictly enforce Trend literal: "bullish", "bearish", "sideways"
                t = str(s.get("trend", "sideways")).lower()
                if t in ["bullish", "bearish", "sideways"]:
                    s["trend"] = t
                else:
                    s["trend"] = "sideways"
                
        return final_output
