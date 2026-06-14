import inspect
from typing import Optional


_ROUTING_TABLE = [
    (
        "supervisors/trading_supervisor",
        "supervisor",
        "TRADING_SUPERVISOR_API_KEY",
    ),
    (
        "tools/trade_brain",
        "trade_strategy",
        "TRADE_STRATEGY_API_KEY",
    ),
    (
        "tools/web/ranker",
        "ranker",
        "NEWS_RANKER_API_KEY",
    ),
]

_DEFAULT_KEY = "GEMINI_API_KEY"


def detect_caller() -> tuple[str, Optional[str], str]:
    """
    Returns:
        (component, worker_name, api_key_name)
    """

    stack = inspect.stack()

    for frame_info in stack:
        path = frame_info.filename.lower()

        # --------------------------------------------------
        # Explicit routing table matches
        # --------------------------------------------------
        for fragment, component, api_key in _ROUTING_TABLE:
            if fragment.lower() in path:
                return component, component, api_key

        # --------------------------------------------------
        # Agent detection by class name
        # --------------------------------------------------
        locals_ = frame_info.frame.f_locals

        if "self" not in locals_:
            continue

        obj = locals_["self"]
        cls_name = obj.__class__.__name__

        # Ignore wrapper itself
        if cls_name == "AutoTrackingLLMWrapper":
            continue

        cls_lower = cls_name.lower()

        # News worker
        if "news" in cls_lower:
            return (
                "agent",
                "WORKER_NEWS",
                _DEFAULT_KEY,
            )

        # Technical worker
        if "technical" in cls_lower:
            return (
                "agent",
                "WORKER_TECH",
                _DEFAULT_KEY,
            )

        # Trade worker
        if "trade" in cls_lower:
            return (
                "agent",
                "WORKER_TRADE_BRAIN",
                _DEFAULT_KEY,
            )

        # Generic agent fallback
        if "agent" in cls_lower:
            return (
                "agent",
                cls_name,
                _DEFAULT_KEY,
            )

    return (
        "unknown",
        "unknown",
        _DEFAULT_KEY,
    )
