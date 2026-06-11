import logging
import os
from datetime import datetime
from typing import Optional

import requests

from ..models.tracking_object import TrackingObject

logger = logging.getLogger(__name__)

# ── Config (loaded from environment) ─────────────────────────────────────────
_BOT_TOKEN: Optional[str] = None
_CHAT_ID: Optional[str] = None
_TIMEOUT_SECONDS: int = 10


def _get_credentials() -> tuple[Optional[str], Optional[str]]:
    """Lazy-load credentials from env on first use."""
    global _BOT_TOKEN, _CHAT_ID
    if _BOT_TOKEN is None:
        _BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if _CHAT_ID is None:
        _CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
    return _BOT_TOKEN, _CHAT_ID


# ── Message builder ───────────────────────────────────────────────────────────

def _build_message(obj: TrackingObject, current_price: float) -> str:
    time_str = datetime.now().strftime("%I:%M %p")

    conditions_block = "\n\n".join(
        f"{i + 1}. {c}" for i, c in enumerate(obj.entry_plan.confirmation_conditions)
    )

    return (
        f"🚨 BUY ZONE REACHED\n\n"
        f"Stock:\n{obj.symbol}\n\n"
        f"Time:\n{time_str}\n\n"
        f"Current Price:\n{current_price}\n\n"
        f"Buy Zone:\n{obj.entry_plan.buy_zone.min} → {obj.entry_plan.buy_zone.max}\n\n"
        f"Stoploss:\n{obj.stoploss_plan.hard_stoploss}\n\n"
        f"Targets:\n\n"
        f"T1: {obj.target_plan.target_1}\n\n"
        f"T2: {obj.target_plan.target_2}\n\n"
        f"T3: {obj.target_plan.target_3}\n\n"
        f"Confirmation Conditions:\n\n"
        f"{conditions_block}\n\n"
        f"Status:\nAwaiting Confirmation"
    )


# ── Transport ─────────────────────────────────────────────────────────────────

def send_telegram_alert(obj: TrackingObject, current_price: float) -> bool:
    """
    Build and dispatch a Telegram message.
    Returns True on success, False on any failure.
    Guaranteed to never raise — callers need not wrap in try/except.
    """
    bot_token, chat_id = _get_credentials()

    if not bot_token or not chat_id:
        logger.error(
            "[ALERT] Telegram credentials missing — "
            "set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"
        )
        return False

    message = _build_message(obj, current_price)
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        resp = requests.post(url, json=payload, timeout=_TIMEOUT_SECONDS)

        if resp.status_code == 200:
            logger.info(
                f"[ALERT SENT] {obj.symbol} @ ₹{current_price}  "
                f"zone=₹{obj.entry_plan.buy_zone.min}→₹{obj.entry_plan.buy_zone.max}"
            )
            return True

        logger.error(
            f"[ALERT FAIL] {obj.symbol}  "
            f"HTTP {resp.status_code}: {resp.text[:200]}"
        )
        return False

    except requests.exceptions.Timeout:
        logger.error(f"[ALERT FAIL] {obj.symbol} — Telegram request timed out")
        return False

    except Exception as exc:
        logger.error(f"[ALERT FAIL] {obj.symbol} — {exc}")
        return False
