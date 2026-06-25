import logging
import os
from datetime import datetime
from typing import Optional

import requests

from ...core.notification import NotificationChannel
from db.models.trade_tracking import TradeTracking

logger = logging.getLogger(__name__)

class TelegramChannel(NotificationChannel):
    def __init__(self, timeout_seconds: int = 10):
        self._timeout_seconds = timeout_seconds
        self._bot_token: Optional[str] = None
        self._chat_id: Optional[str] = None

    def _get_credentials(self) -> tuple[Optional[str], Optional[str]]:
        if self._bot_token is None:
            self._bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if self._chat_id is None:
            self._chat_id = os.getenv("TELEGRAM_CHAT_ID")
        return self._bot_token, self._chat_id

    def _build_message(self, trade: TradeTracking, current_price: float, alert_type: str) -> str:
        time_str = datetime.now().strftime("%I:%M %p")

        conditions = trade.confirmation_conditions or []
        conditions_block = "\n\n".join(
            f"{i + 1}. {c}" for i, c in enumerate(conditions)
        )

        if alert_type == "ENTRY":
            title = "🚨 BUY ZONE REACHED"
            status_text = "Awaiting Confirmation"
        elif alert_type == "TARGET":
            title = "✅ TARGET 1 HIT!"
            status_text = "Target Achieved"
        elif alert_type == "STOPLOSS":
            title = "⚠️ STOP LOSS HIT!"
            status_text = "Trade Invalidated"
        else:
            title = "🔔 STOCK ALERT"
            status_text = "Update"

        return (
            f"{title}\n\n"
            f"Stock:\n{trade.symbol}\n\n"
            f"Time:\n{time_str}\n\n"
            f"Current Price:\n{current_price}\n\n"
            f"Buy Zone:\n{trade.buy_zone_min} → {trade.buy_zone_max}\n\n"
            f"Stoploss:\n{trade.hard_stoploss}\n\n"
            f"Targets:\n\n"
            f"T1: {trade.target_1}\n\n"
            f"T2: {trade.target_2}\n\n"
            f"T3: {trade.target_3}\n\n"
            f"Confirmation Conditions:\n\n"
            f"{conditions_block}\n\n"
            f"Status:\n{status_text}"
        )

    def send_alert(self, trade: TradeTracking, current_price: float, alert_type: str = "ENTRY") -> Optional[str]:
        bot_token, chat_id = self._get_credentials()

        if not bot_token or not chat_id:
            logger.error(
                "[ALERT] Telegram credentials missing — "
                "set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"
            )
            return None

        message = self._build_message(trade, current_price, alert_type)
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }

        try:
            resp = requests.post(url, json=payload, timeout=self._timeout_seconds)

            if resp.status_code == 200:
                result = resp.json().get("result", {})
                message_id = str(result.get("message_id", ""))
                logger.info(
                    f"[{alert_type} ALERT SENT] {trade.symbol} @ ₹{current_price}  "
                    f"zone=₹{trade.buy_zone_min}→₹{trade.buy_zone_max} via Telegram "
                    f"(msg_id={message_id})"
                )
                return message_id

            logger.error(
                f"[ALERT FAIL] {trade.symbol} via Telegram  "
                f"HTTP {resp.status_code}: {resp.text[:200]}"
            )
            return None

        except requests.exceptions.Timeout:
            logger.error(f"[ALERT FAIL] {trade.symbol} — Telegram request timed out")
            return None

        except Exception as exc:
            logger.error(f"[ALERT FAIL] {trade.symbol} via Telegram — {exc}")
            return None
