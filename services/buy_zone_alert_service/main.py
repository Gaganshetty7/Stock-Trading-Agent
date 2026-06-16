"""
Buy Zone Alert Service — Entry Point
=====================================
Usage:
    python main.py

Environment variables (set in .env):
    TELEGRAM_BOT_TOKEN   — from @BotFather
    TELEGRAM_CHAT_ID     — your personal or group chat ID
"""

import glob
import logging
import os
import sys
import asyncio

from dotenv import load_dotenv

from .core.scheduler import MonitoringScheduler
from .core.plan_loader import load_plan
from .utils.logger import setup_logger


def find_latest_plan() -> str:
    """
    Auto-discover the most recent plan file from the outputs directory.
    Files are named plan_YYYYMMDD_HHMMSS.json so alphabetical == chronological.
    """
    # Assuming main.py is run from trading-agent/services/buy_zone_alert_service
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    plans_dir = os.path.join(base_dir, "outputs", "trade_strategy")
    
    pattern = os.path.join(plans_dir, "plan_*.json")
    matches = sorted(glob.glob(pattern))

    if not matches:
        raise FileNotFoundError(f"No plan files found matching '{pattern}'.")

    latest = matches[-1]
    logging.getLogger(__name__).info(f"[MAIN] Auto-selected plan: {os.path.basename(latest)}")
    return latest


def main() -> None:
    load_dotenv()
    setup_logger()

    logger = logging.getLogger(__name__)

    # ── Resolve plan path ─────────────────────────────────────────────────────
    try:
        plan_path = find_latest_plan()
    except FileNotFoundError as exc:
        logger.error(str(exc))
        sys.exit(1)

    # ── Load & filter ─────────────────────────────────────────────────────────
    try:
        watchlist_data = load_plan(plan_path)
    except FileNotFoundError:
        logger.error(f"[MAIN] Plan file not found: {plan_path}")
        sys.exit(1)
    except Exception as exc:
        logger.error(f"[MAIN] Failed to load plan: {exc}")
        sys.exit(1)

    if not watchlist_data:
        logger.warning("[MAIN] No trackable stocks found in plan — nothing to monitor.")
        sys.exit(0)

    # ── Run ───────────────────────────────────────────────────────────────────
    try:
        scheduler = MonitoringScheduler(watchlist_data)
        logger.info("[MAIN] Service startup initialized.")
        asyncio.run(scheduler.run())
    except KeyboardInterrupt:
        logger.info("\n[MAIN] Interrupted by user — shutting down.")
        logger.info(f"[MAIN] Final watchlist state: {len(scheduler.watchlist)} active tracking.")


if __name__ == "__main__":
    main()
