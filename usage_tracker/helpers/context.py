from typing import Dict

MODEL_CONTEXT_LIMITS: Dict[str, int] = {
    "gemini-3.1-flash-lite": 1_048_576,
}

_DEFAULT_LIMIT = 128_000


def context_used_pct(model: str, total_tokens: int) -> tuple[int, float]:
    """Return (context_limit, usage_percent) for the given model."""
    limit = MODEL_CONTEXT_LIMITS.get(model, _DEFAULT_LIMIT)
    pct = round((total_tokens / limit) * 100, 2) if limit else 0.0
    return limit, pct
