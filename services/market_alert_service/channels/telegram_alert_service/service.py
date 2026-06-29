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

        title = "🚨 BUY ZONE REACHED"
        status_text = "Awaiting Confirmation"
        
        run_batch_str = trade.run_batch if trade.run_batch else "N/A"

        return (
            f"{title}\n\n"
            f"Run Batch: {run_batch_str}\n\n"
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

    def _build_exit_message(self, trade: TradeTracking, exit_price: float, alert_type: str, buying_price: float) -> str:
        time_str = datetime.now().strftime("%I:%M %p")
        
        run_batch_str = trade.run_batch if trade.run_batch else "N/A"
        
        diff = exit_price - buying_price
        pct = (diff / buying_price * 100) if buying_price else 0.0
        
        rupee_change = f"+₹{diff:.2f}" if diff >= 0 else f"-₹{abs(diff):.2f}"
        pct_change = f"+{pct:.2f}%" if pct >= 0 else f"-{abs(pct):.2f}%"
        
        if alert_type == "TARGET":
            title = "🎯 TRADE EXITED (TARGET HIT)"
            status_text = "Target Achieved"
        elif alert_type == "STOPLOSS":
            title = "⚠️ TRADE EXITED (STOPLOSS)"
            status_text = "Stoploss Hit"
        elif alert_type == "MARKET_CLOSED":
            title = "🛑 TRADE EXITED (MARKET CLOSE)"
            status_text = "Market Closed"
        else:
            title = "🔔 TRADE EXITED"
            status_text = "Closed"

        return (
            f"{title}\n\n"
            f"Run Batch: {run_batch_str}\n\n"
            f"Stock:\n{trade.symbol}\n\n"
            f"Time:\n{time_str}\n\n"
            f"Buying Price:\n{buying_price}\n\n"
            f"Selling Price:\n{exit_price}\n\n"
            f"Rupee Change:\n{rupee_change}\n\n"
            f"Percentage Change:\n{pct_change}\n\n"
            f"Status:\n{status_text}"
        )

    def send_alert(self, trade: TradeTracking, current_price: float, alert_type: str = "ENTRY", buying_price: float = None) -> Optional[str]:
        bot_token, chat_id = self._get_credentials()

        if not bot_token or not chat_id:
            logger.error(
                "[ALERT] Telegram credentials missing — "
                "set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"
            )
            return None

        if alert_type == "ENTRY":
            message = self._build_message(trade, current_price, alert_type)
        else:
            message = self._build_exit_message(trade, current_price, alert_type, buying_price if buying_price else current_price)
            
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }

        # Attach inline keyboard buttons for ENTRY alerts only
        if alert_type == "ENTRY":
            payload["reply_markup"] = {
                "inline_keyboard": [[
                    {"text": "✅ Confirm", "callback_data": f"confirm:{trade.id}"},
                    {"text": "❌ Reject",  "callback_data": f"reject:{trade.id}"},
                    {"text": "⏰ Snooze",  "callback_data": f"snooze:{trade.id}"},
                ]]
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

    def edit_message_text(self, message_id: str, new_text: str) -> None:
        """Edit an existing Telegram message (e.g. to remove buttons)."""
        bot_token, chat_id = self._get_credentials()
        if not bot_token or not chat_id:
            return
            
        url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
        payload = {
            "chat_id": chat_id,
            "message_id": int(message_id),
            "text": new_text,
            "parse_mode": "Markdown",
            # Omitting reply_markup automatically removes all inline buttons
        }
        try:
            requests.post(url, json=payload, timeout=self._timeout_seconds)
        except Exception as exc:
            logger.error(f"[TELEGRAM] Failed to edit message {message_id}: {exc}")
