import logging
from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme
from rich.panel import Panel
from pathlib import Path
from rich.text import Text
from typing import Optional, Union
from config.settings import BASE_DIR
from datetime import datetime

# ── Theme ─────────────────────────────────────────────────────────────────────
_theme = Theme({
    "thought":     "cyan",
    "action":      "yellow",
    "observation": "green",
    "error":       "bold red",
    "signal":      "bold magenta",
    "info":        "white",
})

console = Console(theme=_theme)

# ── Shared log format ─────────────────────────────────────────────────────────
_LOG_FMT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"

# ── Run log file (one per run, shared across all loggers) ─────────────────────
_log_dir = Path(BASE_DIR) / "logs" / "system_logs"
_log_dir.mkdir(parents=True, exist_ok=True)  # ensure directory exists before opening file
_run_log_file = _log_dir / f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.log"
_file_handler = logging.FileHandler(_run_log_file, encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(_LOG_FMT))


# ── Logger factory ────────────────────────────────────────────────────────────
def get_logger(
    name: str,
    log_file: Optional[Union[str, Path]] = None,
    console_output: bool = False,
    shared_log: bool = True,
) -> logging.Logger:
    """Create or retrieve a named logger.

    Args:
        name:            Logger name (e.g. "ranker", "agent").
        log_file:        Optional path to a dedicated log file for this logger.
                         Parent directories are created automatically.
        console_output:  If False, suppresses Rich console output.
                         Useful for noisy tools where you only want file logs.
        shared_log:      If True, attaches the shared run log file. Set False to exclude.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        # ── Rich console handler (optional) ───────────────────────────────
        if console_output:
            handler = RichHandler(
                console=console,
                show_time=True,
                show_path=False,
                markup=True,
                rich_tracebacks=True,
            )
            logger.addHandler(handler)

        # ── Shared run log (optional) ───────────────────────────────────────
        if shared_log:
            logger.addHandler(_file_handler)

        # ── Dedicated log file (optional) ─────────────────────────────────
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            dedicated_fh = logging.FileHandler(log_path, encoding="utf-8")
            dedicated_fh.setLevel(logging.DEBUG)
            dedicated_fh.setFormatter(logging.Formatter(_LOG_FMT))
            logger.addHandler(dedicated_fh)
        
        if not logger.handlers:
            logger.addHandler(logging.NullHandler())

        logger.setLevel(logging.DEBUG)
        logger.propagate = False
    return logger


# ── ReAct step printers ───────────────────────────────────────────────────────
# Shared logger for ReAct helpers — wired to _file_handler so every step is
# captured on disk. console.print() handles the rich terminal output separately.
_agent_logger = logging.getLogger("REACT_STEP")
if not _agent_logger.handlers:
    _agent_logger.addHandler(_file_handler)
    _agent_logger.setLevel(logging.DEBUG)
    _agent_logger.propagate = False


def log_thought(agent_name: str, thought: str) -> None:
    console.print(f"\n[thought] [{agent_name}] THOUGHT:[/thought] {thought}")
    _agent_logger.debug("[%s] THOUGHT: %s", agent_name, thought)


def log_action(agent_name: str, tool: str, inputs: dict) -> None:
    console.print(f"[action] [{agent_name}] ACTION:[/action] [bold]{tool}[/bold] → {inputs}")
    _agent_logger.debug("[%s] ACTION: %s | inputs: %s", agent_name, tool, inputs)


def log_observation(agent_name: str, observation: str) -> None:
    obs = observation if len(observation) < 300 else observation[:300] + "..."
    console.print(f"[observation] [{agent_name}] OBSERVATION:[/observation] {obs}")
    _agent_logger.debug("[%s] OBSERVATION: %s", agent_name, observation)  # full, untruncated


def log_error(agent_name: str, error: str) -> None:
    console.print(f"[error] [{agent_name}] ERROR:[/error] {error}")
    _agent_logger.error("[%s] ERROR: %s", agent_name, error)


def log_signal(agent_name: str, message: str) -> None:
    console.print(Panel(
        Text(message, style="signal"),
        title=f"[bold magenta] {agent_name} SIGNAL[/bold magenta]",
        border_style="magenta",
    ))
    _agent_logger.info("[%s] SIGNAL: %s", agent_name, message)


def log_info(agent_name: str, message: str) -> None:
    console.print(f"[info]ℹ   [{agent_name}][/info] {message}")
    _agent_logger.info("[%s] %s", agent_name, message)
