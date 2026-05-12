from pathlib import Path
from typing import Any
import re
from datetime import datetime

from core.base_agent import BaseAgent
from agents.news_agent.schema import NewsAgentOutput


class NewsAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "news_agent"

    @property
    def skill_path(self) -> str:
        return str(Path(__file__).parent / "skill.md")

    @property
    def tool_names(self) -> list[str]:
        return ["fetch_rss", "write_json"]

    def parse_output(self, final_output: dict[str, Any]) -> dict[str, Any]:
        # Extract the flat stock->signal mapping from various LLM response shapes
        raw_signals = final_output.get("results") or final_output.get("signals") or final_output

        def _clean_source(s: Any) -> dict:
            """Normalise a single source entry to {title, description, url, published}."""
            if isinstance(s, dict):
                return {
                    "title":       s.get("title", "Unknown")[:300],
                    "description": s.get("description", ""),
                    "url":         s.get("url") or s.get("link", "Unknown"),
                    "published":   s.get("published", "Unknown"),
                }
            if isinstance(s, str):
                return {"title": s[:200], "description": "", "url": "Unknown", "published": "Unknown"}
            return {"title": "Unknown", "description": "", "url": "Unknown", "published": "Unknown"}

        def _source_event_key(source: dict) -> str:
            title = str(source.get("title", "")).lower()
            title = re.sub(r"\d+", "", title)
            title = re.sub(r"[^a-z ]", " ", title)
            return " ".join(title.split())[:140]

        def _published_sort_key(source: dict) -> datetime:
            published = str(source.get("published", ""))
            try:
                return datetime.strptime(published, "%d %b %Y, %I:%M %p IST")
            except Exception:
                return datetime.min

        def _clean_sources(raw: Any) -> list[dict]:
            if not isinstance(raw, list):
                return []
            
            # If the LLM hallucinated a list of strings representing one object:
            if raw and all(isinstance(x, str) for x in raw) and any(x.strip().lower().startswith(("title:", "url:", "link:", "description:")) for x in raw):
                obj = {"title": "Unknown", "description": "", "url": "Unknown", "published": "Unknown"}
                for s in raw:
                    s_str = str(s).strip()
                    s_lower = s_str.lower()
                    if s_lower.startswith("title:"): obj["title"] = s_str[6:].strip()[:300]
                    elif s_lower.startswith("description:"): obj["description"] = s_str[12:].strip()
                    elif s_lower.startswith("url:"): obj["url"] = s_str[4:].strip()
                    elif s_lower.startswith("link:"): obj["url"] = s_str[5:].strip()
                    elif s_lower.startswith("published:"): obj["published"] = s_str[10:].strip()
                return [obj]

            normalized_sources = [_clean_source(s) for s in raw]
            normalized_sources.sort(key=_published_sort_key, reverse=True)

            unique_sources: list[dict] = []
            seen_urls: set[str] = set()
            seen_events: set[str] = set()
            for source in normalized_sources:
                source_url = source.get("url", "")
                if source_url and source_url in seen_urls:
                    continue

                event_key = _source_event_key(source)
                if event_key and event_key in seen_events:
                    continue

                unique_sources.append(source)
                if source_url:
                    seen_urls.add(source_url)
                if event_key:
                    seen_events.add(event_key)

                if len(unique_sources) >= 3:
                    break

            return unique_sources

        def _clean_signal(v: dict) -> dict:
            """Strip legacy/removed top-level fields; ensure sources is a clean list."""
            for f in ("title", "description", "url", "published"):
                v.pop(f, None)
            v["sources"] = _clean_sources(v.get("sources", []))
            return v

        cleaned_output = {}
        if isinstance(raw_signals, list):
            for item in raw_signals:
                if isinstance(item, dict) and "stock" in item:
                    cleaned_output[item["stock"]] = _clean_signal(item)
        elif isinstance(raw_signals, dict):
            for k, v in raw_signals.items():
                if isinstance(v, dict) and ("stock" in v or "direction" in v):
                    cleaned_output[k] = _clean_signal(v)
                elif k == "signals" and isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict) and "stock" in item:
                            cleaned_output[item["stock"]] = _clean_signal(item)

        result = NewsAgentOutput(cleaned_output)
        return result.model_dump()
