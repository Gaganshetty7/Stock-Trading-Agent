from langchain_core.tools import BaseTool
from tools.storage.file_writer import write_json
from tools.web.broad_market_feeds.broad_rss_fetcher import fetch_broad_market_rss

# ── Registry ──────────────────────────────────────────────────────────────────
_TOOLS: dict[str, BaseTool] = {}


def init_tools() -> None:
    """Initializes and registers all native LangChain tools."""
    _TOOLS["write_json"] = write_json
    _TOOLS["fetch_broad_market_rss"] = fetch_broad_market_rss


def get_tool(name: str) -> BaseTool:
    """Fetches a registered LangChain BaseTool by name."""
    if name not in _TOOLS:
        raise KeyError(f"Tool '{name}' not found. Available: {list(_TOOLS.keys())}")
    return _TOOLS[name]


def get_tools_by_names(names: list[str]) -> list[BaseTool]:
    """Returns a list of BaseTool objects matching the provided names."""
    return [get_tool(name) for name in names]


def describe_tools(names: list[str]) -> str:
    """Returns tool descriptions for prompt injection into agent system prompt."""
    lines = []
    for name in names:
        if name in _TOOLS:
            tool = _TOOLS[name]
            lines.append(f"- **{tool.name}**: {tool.description}")
    return "\n".join(lines)
