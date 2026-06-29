"""
Telegram Bot Callback Listener
================================
Long-polls the Telegram Bot API for inline keyboard callback queries
(Confirm / Reject / Snooze) and performs atomic DB state transitions.

This module uses the raw Telegram Bot API via httpx — no python-telegram-bot
dependency required.
"""

import logging
import os
from datetime import datetime, timedelta

import httpx
import pytz

from db.database import SessionLocal
from db.models.trade_tracking import TradeTracking, TrackingStatus, TradeEventType
from db.repositories.trade_tracking import TradeTrackingRepository
from services.market_alert_service.core.market_data_service import fetch_prices

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")
SNOOZE_MINUTES = 5
POLL_TIMEOUT = 30  # Telegram long-poll timeout in seconds


class TelegramBotListener:
    """
    Listens for inline keyboard button presses on buy-zone-hit alerts
    and transitions trade state in PostgreSQL accordingly.

    Shares a mutable ``snoozed_trades`` dict with the scheduler so that
    snooze expiry can be evaluated during the tick loop.
    """

    def __init__(self, snoozed_trades: dict[int, datetime]) -> None:
        self._snoozed_trades = snoozed_trades
        self._offset: int = 0  # Telegram update offset for deduplication
        self._repo = TradeTrackingRepository()

        self._bot_token: str | None = None
        self._chat_id: str | None = None

    def _get_bot_token(self) -> str | None:
        if self._bot_token is None:
            self._bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        return self._bot_token

    async def run(self) -> None:
        """Infinite long-poll loop — runs as a parallel coroutine alongside the scheduler."""
        token = self._get_bot_token()
        if not token:
            logger.warning("[BOT LISTENER] TELEGRAM_BOT_TOKEN not set — callback listener disabled.")
            return

        logger.info("[BOT LISTENER] Started — listening for inline button callbacks.")
        url = f"https://api.telegram.org/bot{token}/getUpdates"

        async with httpx.AsyncClient(timeout=POLL_TIMEOUT + 10) as http:
            while True:
                try:
                    params = {
                        "offset": self._offset,
                        "timeout": POLL_TIMEOUT,
                        "allowed_updates": '["callback_query"]',
                    }
                    resp = await http.get(url, params=params)
                    resp.raise_for_status()

                    data = resp.json()
                    if not data.get("ok"):
                        logger.warning(f"[BOT LISTENER] Telegram API error: {data}")
                        continue

                    for update in data.get("result", []):
                        self._offset = update["update_id"] + 1
                        callback = update.get("callback_query")
                        if callback:
                            await self._handle_callback(http, token, callback)

                except httpx.ReadTimeout:
                    # Normal — long-poll timed out with no updates
                    continue
                except Exception as exc:
                    logger.error(f"[BOT LISTENER] Poll error: {exc}", exc_info=True)
                    # Brief backoff before retrying
                    import asyncio
                    await asyncio.sleep(3)

    async def _handle_callback(self, http: httpx.AsyncClient, token: str, callback: dict) -> None:
        """Process a single callback_query from a button press."""
        callback_id = callback.get("id")
        callback_data = callback.get("data", "")
        message = callback.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")
        original_text = message.get("text", "")

        # Parse callback_data: "confirm:42", "reject:42", "snooze:42"
        parts = callback_data.split(":", 1)
        if len(parts) != 2:
            await self._answer_callback(http, token, callback_id, "Invalid action.")
            return

        action, trade_id_str = parts
        try:
            trade_id = int(trade_id_str)
        except ValueError:
            await self._answer_callback(http, token, callback_id, "Invalid trade ID.")
            return

        if action not in ("confirm", "reject", "snooze"):
            await self._answer_callback(http, token, callback_id, "Unknown action.")
            return

        # ── DB transaction ──────────────────────────────────────────────────
        now_ist = datetime.now(IST)
        time_str = now_ist.strftime("%I:%M %p")

        with SessionLocal() as db:
            try:
                trade = db.query(TradeTracking).filter(TradeTracking.id == trade_id).first()

                if not trade:
                    await self._answer_callback(http, token, callback_id, "Trade not found.")
                    return

                if trade.status != TrackingStatus.BUY_ZONE_HIT:
                    await self._answer_callback(http, token, callback_id, "Trade already processed.")
                    return

                if action == "confirm":
                    # Check live price to prevent late confirmations
                    try:
                        prices = await fetch_prices([trade.symbol])
                        current_price = prices.get(trade.symbol)
                    except Exception as exc:
                        logger.error(f"[BOT LISTENER] fetch_prices failed during confirm: {exc}")
                        current_price = None

                    if current_price is None:
                        # Fallback: API failed. Revert to tracking.
                        self._repo.update_trade_status(
                            db=db,
                            trade_id=trade_id,
                            new_status=TrackingStatus.TRACKING,
                            event_type=TradeEventType.IGNORED,
                            event_message=f"Confirmation failed at {time_str} (API error). Reverted to tracking.",
                            alert_sent=True,
                        )
                        db.commit()
                        suffix = f"\n\n⚠️ Confirmation failed: Live price fetch failed. Reverted to Tracking."
                        toast = "API failed! Reverting."
                        logger.warning(f"[CALLBACK] {trade.symbol} CONFIRM FAILED (API Error) → TRACKING")
                        
                    elif not (trade.buy_zone_min <= current_price <= trade.buy_zone_max):
                        # Fallback: Price left zone. Revert to tracking.
                        self._repo.update_trade_status(
                            db=db,
                            trade_id=trade_id,
                            new_status=TrackingStatus.TRACKING,
                            event_type=TradeEventType.IGNORED,
                            event_message=f"Confirmation failed at {time_str} (Price ₹{current_price} outside zone). Reverted to tracking.",
                            alert_sent=True,
                        )
                        db.commit()
                        suffix = f"\n\n⚠️ Confirmation failed: Price (₹{current_price}) moved outside Buy Zone. Reverted to Tracking."
                        toast = "Price left zone! Reverting."
                        logger.info(f"[CALLBACK] {trade.symbol} CONFIRM REJECTED (Out of zone) → TRACKING")
                        
                    else:
                        # Success: Price is valid.
                        self._repo.update_trade_status(
                            db=db,
                            trade_id=trade_id,
                            new_status=TrackingStatus.ACTIVE,
                            event_type=TradeEventType.ACTIVATED,
                            event_message=f"Confirmed by user at {time_str} (Price ₹{current_price}).",
                            alert_sent=True,
                        )
                        # Also explicitly record the execution price so P&L math is perfect
                        self._repo.record_execution(db=db, trade_id=trade_id, entry_price=current_price)
                        db.commit()
                        suffix = f"\n\n✅ Confirmed at {time_str} (Price: ₹{current_price})"
                        toast = "Trade activated!"
                        logger.info(f"[CALLBACK] {trade.symbol} CONFIRMED → ACTIVE @ ₹{current_price}")

                elif action == "reject":
                    self._repo.update_trade_status(
                        db=db,
                        trade_id=trade_id,
                        new_status=TrackingStatus.IGNORED,
                        event_type=TradeEventType.IGNORED,
                        event_message=f"Rejected by user at {time_str}.",
                        alert_sent=True,
                    )
                    db.commit()
                    suffix = f"\n\n❌ Rejected at {time_str}"
                    toast = "Trade rejected."
                    logger.info(f"[CALLBACK] {trade.symbol} REJECTED → IGNORED")

                elif action == "snooze":
                    self._repo.update_trade_status(
                        db=db,
                        trade_id=trade_id,
                        new_status=TrackingStatus.SNOOZED,
                        event_type=TradeEventType.BUY_ZONE_HIT,
                        event_message=f"Snoozed by user at {time_str} for {SNOOZE_MINUTES} min.",
                        alert_sent=True,
                    )
                    db.commit()
                    self._snoozed_trades[trade_id] = now_ist + timedelta(minutes=SNOOZE_MINUTES)
                    suffix = f"\n\n⏰ Snoozed for {SNOOZE_MINUTES} min at {time_str}"
                    toast = f"Snoozed for {SNOOZE_MINUTES} minutes."
                    logger.info(f"[CALLBACK] {trade.symbol} SNOOZED for {SNOOZE_MINUTES}m")

            except Exception as exc:
                db.rollback()
                logger.error(f"[CALLBACK ERROR] Failed to process {action}:{trade_id} — {exc}", exc_info=True)
                await self._answer_callback(http, token, callback_id, "Server error. Try again.")
                return

        # ── Update Telegram UI ──────────────────────────────────────────────
        await self._answer_callback(http, token, callback_id, toast)

        # Edit the original message: append status suffix and remove buttons
        if chat_id and message_id:
            await self._edit_message(http, token, chat_id, message_id, original_text + suffix)

    async def _answer_callback(self, http: httpx.AsyncClient, token: str, callback_id: str, text: str) -> None:
        """Acknowledge the callback query (dismisses the loading spinner)."""
        try:
            url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
            await http.post(url, json={"callback_query_id": callback_id, "text": text})
        except Exception as exc:
            logger.debug(f"[BOT LISTENER] answerCallbackQuery failed: {exc}")

    async def _edit_message(self, http: httpx.AsyncClient, token: str, chat_id: int, message_id: int, new_text: str) -> None:
        """Edit the original alert message to show the action taken and remove buttons."""
        try:
            url = f"https://api.telegram.org/bot{token}/editMessageText"
            await http.post(url, json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": new_text,
                # No reply_markup → buttons are removed
            })
        except Exception as exc:
            logger.debug(f"[BOT LISTENER] editMessageText failed: {exc}")
