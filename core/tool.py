from typing import Any, Callable, Coroutine

AsyncTool = Callable[..., Coroutine[Any, Any, Any]]

# ── Registry ──────────────────────────────────────────────────────────────────
_TOOLS: dict[str, dict] = {}


def register_tool(name: str, fn: AsyncTool, description: str) -> None:
    """Registers a tool safely. Prevents duplicate registration."""
    if name in _TOOLS:
        return
    _TOOLS[name] = {"fn": fn, "description": description}


def get_tool(name: str) -> AsyncTool:
    """Fetches a registered tool by name."""
    if name not in _TOOLS:
        raise KeyError(f"Tool '{name}' not found. Available: {list(_TOOLS.keys())}")
    return _TOOLS[name]["fn"]


def describe_tools(names: list[str]) -> str:
    """Returns tool descriptions for prompt injection into agent system prompt."""
    lines = []
    for name in names:
        if name in _TOOLS:
            lines.append(f"- **{name}**: {_TOOLS[name]['description']}")
    return "\n".join(lines)


# ── Tool Initialization ───────────────────────────────────────────────────────
from tools.storage.file_writer import write_json
from tools.web.broad_market_feeds.broad_rss_fetcher import fetch_broad_market_rss
from tools.web.ranker.tool import rank_news_payload
from tools.web.selector.tool import dynamic_threshold_select


def init_tools() -> None:
    """Call this ONCE at application startup."""
    register_tool(
        "write_json",
        write_json,
        "Writes structured data as a JSON file to the outputs directory. "
        "Input: filename_prefix (str), data (dict | list), overwrite (bool, default False). "
        "Set overwrite=True to maintain a single file per stock.",
    )
    register_tool(
        "fetch_broad_market_rss",
        fetch_broad_market_rss,
        "Performs a comprehensive sweep of the Indian stock market (NSE/BSE) using a "
        "wide query grid covering sectors, corporate events, and high-signal news. "
        "Input: max_age_hours (int, default 72). Returns a deduplicated list of articles.",
    )
    register_tool(
        "rank_news_payload",
        rank_news_payload,
        "Processes a large collection of raw market news articles to extract high-confidence "
        "intraday signals. Filters news for market relevance, impact, and freshness. "
        "Input: payload (dict) containing 'mapped_news' tree. Returns structured tradable signals.",
    )
    register_tool(
        "dynamic_threshold_select",
        dynamic_threshold_select,
        "Applies a dynamic scoring threshold and ranking logic to select the top N most "
        "impactful signals from the ranked dataset. Combines impact and confidence scores. "
        "Input: signals (dict), top_n (int, default 5). Returns a filtered subset of top signals.",
    )
