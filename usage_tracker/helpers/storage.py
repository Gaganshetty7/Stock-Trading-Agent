"""
storage.py
~~~~~~~~~~
Writes THREE daily files on every call:

  logs/usage_tracker/tokens/YYYY-MM-DD.json
  logs/usage_tracker/quota/YYYY-MM-DD.json
  logs/usage_tracker/summary/YYYY-MM-DD.json

Same date → update in place.  New date → new file.
"""

import json
from datetime import datetime
from pathlib import Path

from .models import CallRecord
from core.logger import get_logger

logger = get_logger("usage_tracker", console_output=False)

LOG_BASE            = Path("logs/system_logs/usage_tracker")
DAILY_REQUEST_LIMIT = 500


# ─────────────────────────────────────────────────────────────────────────────
# Public
# ─────────────────────────────────────────────────────────────────────────────

def append_call(record: CallRecord) -> None:
    date_str = datetime.now().strftime("%Y-%m-%d")
    _write_tokens (date_str, record)
    _write_quota  (date_str, record)
    _write_summary(date_str, record)


# ─────────────────────────────────────────────────────────────────────────────
# FILE 1 — tokens/YYYY-MM-DD.json
#
# { date, total_tokens, total_input_tokens, total_output_tokens,
#   by_agent: { <agent>: { tokens, input_tokens, output_tokens,
#                          calls, avg_tokens_per_call } },
#   call_history: [ { timestamp, agent, model, status,
#                     total_tokens, input_tokens, output_tokens,
#                     context_window_used_pct, duration_seconds } ] }
# ─────────────────────────────────────────────────────────────────────────────

def _write_tokens(date_str: str, r: CallRecord) -> None:
    path = _ensure(LOG_BASE / "tokens", date_str)
    d    = _load(path) or {
        "date": date_str,
        "total_tokens": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "by_agent": {},
        "call_history": [],
    }
    ok    = r.status == "SUCCESS"
    agent = r.worker_name or r.component or "unknown"

    if ok:
        d["total_tokens"]       += r.total_tokens
        d["total_input_tokens"] += r.input_tokens
        d["total_output_tokens"]+= r.output_tokens

    a = d["by_agent"].setdefault(agent, {
        "tokens": 0, "input_tokens": 0, "output_tokens": 0,
        "calls": 0, "successful_calls": 0, "avg_tokens_per_call": 0,
    })
    a["calls"] += 1
    if ok:
        a["successful_calls"] = a.get("successful_calls", 0) + 1
        a["tokens"]        += r.total_tokens
        a["input_tokens"]  += r.input_tokens
        a["output_tokens"] += r.output_tokens
    
    succ = a.get("successful_calls", a["calls"])
    a["avg_tokens_per_call"] = a["tokens"] // succ if succ else 0

    d["call_history"].append({
        "timestamp":        r.timestamp,
        "agent":            agent,
        "model":            r.model,
        "status":           r.status,
        "total_tokens":     r.total_tokens,
        "input_tokens":     r.input_tokens,
        "output_tokens":    r.output_tokens,
        "model_context_window": r.context_limit,
        "context_window_used_pct": r.context_window_used_pct,
        "duration_seconds": r.duration_seconds,
    })
    _save(path, d)


# ─────────────────────────────────────────────────────────────────────────────
# FILE 2 — quota/YYYY-MM-DD.json
#
# { date, calls, calls_limit, calls_remaining,
#   successful_calls, failed_calls, rejected_429_calls,
#   by_agent: { <agent>: { calls, failed, rejected_429 } },
#   call_history: [ { timestamp, agent, model, status, duration_seconds } ] }
# ─────────────────────────────────────────────────────────────────────────────

def _write_quota(date_str: str, r: CallRecord) -> None:
    path = _ensure(LOG_BASE / "quota", date_str)
    d    = _load(path) or {
        "date": date_str,
        "calls": 0,
        "calls_limit": DAILY_REQUEST_LIMIT,
        "calls_remaining": DAILY_REQUEST_LIMIT,
        "successful_calls": 0,
        "failed_calls": 0,
        "rejected_429_calls": 0,
        "model_context_window": 0,
        "by_agent": {},
        "call_history": [],
    }
    # Ensure existing data has new fields
    if "model_context_window" not in d:
        d["model_context_window"] = d.pop("avg_context_limit", 0)
    agent = r.worker_name or r.component or "unknown"

    d["calls"] += 1
    if r.status == "SUCCESS":        d["successful_calls"]    += 1
    elif r.status == "FAILED":       d["failed_calls"]        += 1
    elif r.status == "REJECTED_429": d["rejected_429_calls"]  += 1
    d["calls_remaining"] = max(0, DAILY_REQUEST_LIMIT - d["calls"])

    a = d["by_agent"].setdefault(agent, {"calls": 0, "failed": 0, "rejected_429": 0})
    a["calls"] += 1
    if r.status == "FAILED":       a["failed"]       += 1
    if r.status == "REJECTED_429": a["rejected_429"] += 1

    # Update model context window
    prev_calls = d["calls"] - 1
    d["model_context_window"] = int(((d.get("model_context_window", 0) * prev_calls) + r.context_limit) / d["calls"])

    d["call_history"].append({
        "timestamp":        r.timestamp,
        "agent":            agent,
        "model":            r.model,
        "status":           r.status,
        "duration_seconds": r.duration_seconds,
        "model_context_window": r.context_limit,
    })
    _save(path, d)


# ─────────────────────────────────────────────────────────────────────────────
# FILE 3 — summary/YYYY-MM-DD.json
#
# { date,
#   totals: { calls, successful_calls, failed_calls, rejected_429_calls,
#             tokens, calls_limit, calls_remaining,
#             tokens_limit, tokens_remaining,
#             processing_seconds, avg_context_window_used_pct,
#             max_tokens_single_call },
#   by_agent: { <agent>: { calls, successful_calls, tokens,
#                          avg_tokens_per_call, processing_seconds,
#                          avg_context_window_used_pct } } }
# ─────────────────────────────────────────────────────────────────────────────

def _write_summary(date_str: str, r: CallRecord) -> None:
    path = _ensure(LOG_BASE / "summary", date_str)
    d    = _load(path) or {
        "date": date_str,
        "totals": {
            "calls": 0, "successful_calls": 0,
            "failed_calls": 0, "rejected_429_calls": 0,
            "tokens": 0,
            "calls_limit": DAILY_REQUEST_LIMIT,
            "calls_remaining": DAILY_REQUEST_LIMIT,
            "processing_seconds": 0.0,
            "avg_context_window_used_pct": 0.0,
            "model_context_window": 0,
            "max_tokens_single_call": 0,
        },
        "by_agent": {},
    }
    # Ensure existing sections have new fields
    t = d["totals"]
    if "model_context_window" not in t: t["model_context_window"] = t.pop("avg_context_limit", 0)
    # Remove old fields
    t.pop("tokens_limit", None)
    t.pop("tokens_remaining", None)
    if "avg_context_window_used_pct" not in t: t["avg_context_window_used_pct"] = 0.0
    ok    = r.status == "SUCCESS"
    agent = r.worker_name or r.component or "unknown"

    t          = d["totals"]
    prev_succ  = t.get("successful_calls", 0)

    t["calls"] += 1
    if r.status == "SUCCESS":        t["successful_calls"]   += 1
    elif r.status == "FAILED":       t["failed_calls"]       += 1
    elif r.status == "REJECTED_429": t["rejected_429_calls"] += 1

    if ok:
        t["tokens"]             += r.total_tokens
        t["processing_seconds"]  = round(t["processing_seconds"] + r.duration_seconds, 2)
        t["max_tokens_single_call"] = max(t["max_tokens_single_call"], r.total_tokens)
        t["avg_context_window_used_pct"]   = round(
            ((t["avg_context_window_used_pct"] * prev_succ) + r.context_window_used_pct) / t["successful_calls"], 2
        )
        t["model_context_window"] = int(((t.get("model_context_window", 0) * prev_succ) + r.context_limit) / t["successful_calls"])
    t["calls_remaining"]  = max(0, DAILY_REQUEST_LIMIT - t["calls"])

    a      = d["by_agent"].setdefault(agent, {
        "calls": 0, "successful_calls": 0, "tokens": 0,
        "avg_tokens_per_call": 0, "processing_seconds": 0.0,
        "avg_context_window_used_pct": 0.0,
        "model_context_window": 0,
    })
    if "model_context_window" not in a: a["model_context_window"] = a.pop("context_limit", 0)
    prev_a_succ = a["successful_calls"]
    a["calls"] += 1
    if ok:
        a["successful_calls"]    += 1
        a["tokens"]              += r.total_tokens
        a["processing_seconds"]   = round(a["processing_seconds"] + r.duration_seconds, 2)
        a["avg_tokens_per_call"]  = a["tokens"] // a["successful_calls"]
        a["avg_context_window_used_pct"] = round(
            ((a["avg_context_window_used_pct"] * prev_a_succ) + r.context_window_used_pct) / a["successful_calls"], 2
        )
        a["model_context_window"] = r.context_limit
    _save(path, d)


# ─────────────────────────────────────────────────────────────────────────────
# Shared I/O
# ─────────────────────────────────────────────────────────────────────────────

# def _ensure(folder: Path, date_str: str) -> Path:
#     # Use .resolve() to turn it into an absolute safe path before creating it
#     target_dir = folder.resolve()
#     target_dir.mkdir(parents=True, exist_ok=True)
#     return target_dir / f"{date_str}.json"
def _ensure(folder: Path, date_str: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{date_str}.json"

def _load(path: Path) -> dict | None:
    if path.exists():
        try:
            with path.open() as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load JSON file {path}: {str(e)}")
    return None

def _save(path: Path, data: dict) -> None:
    with path.open("w") as f:
        json.dump(data, f, indent=2)
