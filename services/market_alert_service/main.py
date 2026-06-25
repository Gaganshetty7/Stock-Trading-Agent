"""
Market Alert Service — Entry Point
=====================================
Usage:
    python -m services.market_alert_service.main

Environment variables (set in .env):
    DATABASE_URL           — PostgreSQL connection string
    TELEGRAM_BOT_TOKEN     — from @BotFather
    TELEGRAM_CHAT_ID       — your personal or group chat ID
    EMAIL_SENDER           — sending email
    EMAIL_PASSWORD         — app password
    EMAIL_RECEIVER         — receiving email
    ENABLE_EMAIL_ALERTS    — "True" or "False"
    ENABLE_TELEGRAM_ALERTS — "True" or "False"
"""

import logging
import asyncio

from dotenv import load_dotenv

from .core.scheduler import MonitoringScheduler
from .utils.logger import setup_logger
from .config.settings import settings

from .channels.telegram_alert_service.service import TelegramChannel
from .channels.email_alert_service.service import EmailChannel


def main() -> None:
    load_dotenv()
    setup_logger()

    logger = logging.getLogger(__name__)

    # ── Register active channels ────────────────────────────────────────────────
    active_channels = []
    
    if settings.ENABLE_TELEGRAM_ALERTS:
        logger.info("[MAIN] Telegram alerts enabled.")
        active_channels.append(TelegramChannel())
        
    if settings.ENABLE_EMAIL_ALERTS:
        logger.info("[MAIN] Email alerts enabled.")
        active_channels.append(EmailChannel())

    if not active_channels:
        logger.warning("[MAIN] No alert channels enabled. Service will fetch data but won't send notifications.")

    # ── Run — scheduler reads trades from the database (no plan file needed) ──
    try:
        scheduler = MonitoringScheduler(active_channels)
        logger.info("[MAIN] Service startup initialized — scheduler is DB-driven.")
        asyncio.run(scheduler.run())
    except KeyboardInterrupt:
        logger.info("\n[MAIN] Interrupted by user — shutting down.")


if __name__ == "__main__":
    main()
