import os
from dotenv import load_dotenv

load_dotenv()

# ── Ranking LLM Config ────────────────────────────────────────────────────────
# Specific model identifier for the ranking/filtering stage
NEWS_RANKER_MODEL = os.getenv("NEWS_RANKER_MODEL")

# -- Orchestration Parameters --
RANKING_BATCH_SIZE = 10

RANKING_CONCURRENCY = 1

RANKING_STAGGER_DELAY = 1.5     # Increased from 0.5 to proactively avoid 429s

RANKING_MAX_RETRIES = 3        # Local retries per batch
RANKING_BACKOFF_BASE = 5.0    # Initial backoff in seconds

RANKING_TIMEOUT = 25

# -- Data Constraints --
MAX_TITLE_LEN = 160            # Truncate long titles before sending to LLM
TOP_N_ARTICLES = 2             # Max articles to keep per company
MIN_CONFIDENCE = 0.75          # Minimum confidence (0.0-1.0) to keep an article
MIN_IMPACT = 0.55            # Minimum impact score (0.0-1.0) to keep an article

# -- Intraday Weighting Multipliers --
MARKET_CLOSED_MULTIPLIER = 0.85  # Penalty if outside IST trading hours
STALE_DECAY_MULTIPLIER = 0.70    # Penalty if news is > 3h old
STALE_THRESHOLD_MINS = 180       # 3 hours

# ── API Key Management ────────────────────────────────────────────────────────
# Single key for ranking - friend's key, must be protected
NEWS_RANKER_API_KEY = os.getenv("NEWS_RANKER_API_KEY", "")
if not NEWS_RANKER_API_KEY:
    raise ValueError("NEWS_RANKER_API_KEY not found in .env — add it there, never hardcode it")

