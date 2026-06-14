from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CallRecord:
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # agent / worker tracking
    component: str = "unknown"
    worker_name: str | None = None
    run_id: str = "no_run"

    # model tracking (from .env)
    model: str = "unknown"

    # execution status
    status: str = "SUCCESS"   # SUCCESS | FAILED | REJECTED_429

    # tokens
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    # context tracking
    context_limit: int = 1
    context_window_used_pct: float = 0.0

    # performance
    duration_seconds: float = 0.0
