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
