# tools/token_tracker/context_window.py

from typing import Dict, Any

# You can expand this per model later
MODEL_CONTEXT_LIMITS = {
    "gemini-flash-latest": 1_000_000,
}


def extract_context_usage(model: str, usage: Any) -> Dict:
    """
    Extracts full token breakdown from Gemini usage_metadata
    and calculates remaining context window.
    """

    if not usage:
        return {
            "model": model,
            "input_tokens": 0,
            "output_tokens": 0,
            "thought_tokens": 0,
            "total_tokens": 0,
            "context_limit": MODEL_CONTEXT_LIMITS.get(model, 1_000_000),
            "remaining_tokens": MODEL_CONTEXT_LIMITS.get(model, 1_000_000),
        }

    # ── Core tokens ─────────────────────────────
    input_tokens = getattr(usage, "prompt_token_count", 0)
    output_tokens = getattr(usage, "candidates_token_count", 0)
    thought_tokens = getattr(usage, "thoughts_token_count", 0)

    # Some SDK versions already include everything in total
    api_total = getattr(usage, "total_token_count", None)

    # Recompute safe total (more accurate for debugging)
    computed_total = input_tokens + output_tokens + thought_tokens

    total_tokens = api_total if api_total is not None else computed_total

    # ── Context limit ───────────────────────────
    limit = MODEL_CONTEXT_LIMITS.get(model, 1_000_000)

    remaining = limit - total_tokens
    if remaining < 0:
        remaining = 0

    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "thought_tokens": thought_tokens,
        "total_tokens": total_tokens,
        "context_limit": limit,
        "remaining_tokens": remaining,
    }
