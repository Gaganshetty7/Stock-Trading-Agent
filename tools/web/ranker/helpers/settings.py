import os
from math import ceil
from dotenv import load_dotenv

load_dotenv()

# ── Model ─────────────────────────────────────────────────────────────────────
RANKING_MODEL = os.getenv("RANKING_MODEL", )

# ── Confirmed Free Tier Limits ────────────────────────────────────────────────
RPM_HARD_LIMIT = 15
RPD_HARD_LIMIT = 1_500

SAFE_RPM = 14

# ── Orchestration ─────────────────────────────────────────────────────────────
RANKING_BATCH_SIZE   = 10

RANKING_TIMEOUT      = 35
RANKING_MAX_RETRIES  = 1
RANKING_BACKOFF_BASE = 5.0
RETRY_429_WAIT_SECS  = 60

# ── Signal Filtering ──────────────────────────────────────────────────────────
MAX_TITLE_LEN = 120
TOP_N_ARTICLES = 2

MIN_CONFIDENCE = 0.65
MIN_IMPACT     = 0.50

# ── Intraday Weighting ────────────────────────────────────────────────────────
MARKET_CLOSED_MULTIPLIER = 0.85
STALE_DECAY_MULTIPLIER   = 0.70
STALE_THRESHOLD_MINS     = 180

# ── API Key ───────────────────────────────────────────────────────────────────
GEMINI_RANKER_API_KEY = os.getenv("GEMINI_RANKER_API_KEY", "")

if not GEMINI_RANKER_API_KEY:
    raise ValueError("GEMINI_RANKER_API_KEY not set in .env")

GEMINI_KEYS = [GEMINI_RANKER_API_KEY]

# ── Quota Math ────────────────────────────────────────────────────────────────

def quota_summary(total_companies: int = 340) -> dict:
    batches = ceil(total_companies / RANKING_BATCH_SIZE)
    requests_per_run = ceil(batches * 1.1)
    interval_delay = 60.0 / SAFE_RPM
    total_dispatch_time = (batches - 1) * interval_delay
    avg_response = 4.0
    est_total = total_dispatch_time + avg_response
    runs_per_day = RPD_HARD_LIMIT // requests_per_run

    return {
        "model": RANKING_MODEL,
        "rpm_safe": SAFE_RPM,
        "total_companies": total_companies,
        "batches": batches,
        "interval_delay_s": round(interval_delay, 2),
        "requests_per_run": requests_per_run,
        "est_seconds_per_run": round(est_total),
        "est_minutes_per_run": round(est_total / 60, 1),
        "runs_per_day": runs_per_day,
        "quota_used_pct": f"{requests_per_run / RPD_HARD_LIMIT:.1%}",
    }

def print_quota_summary(total_companies: int = 340):
    s = quota_summary(total_companies)

    print("─" * 50)
    print(f"Model:             {s['model']}")
    print(f"Safe RPM:          {s['rpm_safe']}/{RPM_HARD_LIMIT}")
    print(f"Companies:         {s['total_companies']} → {s['batches']} batches")
    print(f"Queue pacing:      {s['interval_delay_s']}s between launches")
    print(f"Requests/run:      {s['requests_per_run']}")
    print(f"Time/run:          ~{s['est_seconds_per_run']}s ({s['est_minutes_per_run']} min)")
    print(f"Runs/day:          {s['runs_per_day']}")
    print(f"Quota used/run:    {s['quota_used_pct']} of daily RPD")
    print("─" * 50)

if __name__ == "__main__":
    print_quota_summary()
