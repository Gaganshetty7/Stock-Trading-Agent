from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"

# ── LLM Config ────────────────────────────────────────────────────────────────
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER")
LLM_MODEL: str = os.getenv("LLM_MODEL")
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE",))
MAX_REACT_ITERATIONS: int = int(os.getenv("MAX_REACT_ITERATIONS"))

# ── API Keys ──────────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# ── Role Specific Configs ──────────────────────────────────────────────────────
# Ranker
NEWS_RANKER_LLM_PROVIDER: str = os.getenv("NEWS_RANKER_LLM_PROVIDER")
NEWS_RANKER_MODEL: str = os.getenv("NEWS_RANKER_MODEL")
NEWS_RANKER_LLM_TEMPERATURE: float = float(os.getenv("NEWS_RANKER_LLM_TEMPERATURE", "0"))
NEWS_RANKER_API_KEY: str = os.getenv("NEWS_RANKER_API_KEY", "")

# Trading Supervisor
TRADING_SUPERVISOR_LLM_PROVIDER: str = os.getenv("TRADING_SUPERVISOR_LLM_PROVIDER")
TRADING_SUPERVISOR_MODEL: str = os.getenv("TRADING_SUPERVISOR_MODEL")
TRADING_SUPERVISOR_LLM_TEMPERATURE: float = float(os.getenv("TRADING_SUPERVISOR_LLM_TEMPERATURE", "0"))
TRADING_SUPERVISOR_API_KEY: str = os.getenv("TRADING_SUPERVISOR_API_KEY", "")

# Trade Strategy
TRADE_STRATEGY_LLM_PROVIDER: str = os.getenv("TRADE_STRATEGY_LLM_PROVIDER")
TRADE_STRATEGY_MODEL: str = os.getenv("TRADE_STRATEGY_MODEL")
TRADE_STRATEGY_LLM_TEMPERATURE: float = float(os.getenv("TRADE_STRATEGY_LLM_TEMPERATURE", "0"))
TRADE_STRATEGY_API_KEY: str = os.getenv("TRADE_STRATEGY_API_KEY", "")
