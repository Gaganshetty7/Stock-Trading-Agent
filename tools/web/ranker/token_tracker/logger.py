import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

LOG_FILE = Path("logs/token_usage.jsonl")


def log_token_usage(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    thought_tokens: int = 0,
    context_limit: int = 1_000_000,
):
    """
    Append FULL token + context usage to file
    """

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    remaining = max(context_limit - total_tokens, 0)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "input_tokens": prompt_tokens,
        "output_tokens": completion_tokens,
        "thought_tokens": thought_tokens,
        "total_tokens": total_tokens,
        "context_limit": context_limit,
        "remaining_tokens": remaining,
    }

    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
