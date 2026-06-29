import logging
import asyncio
from datetime import datetime
from typing import List, Optional

import pytz

from db.database import SessionLocal
from db.models.trade_tracking import TradeTracking, TrackingStatus, TradeEventType
from db.repositories.trade_tracking import TradeTrackingRepository
from .market_data_service import fetch_prices
from .notification import NotificationChannel

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS: int = 60
EXPIRY_MINUTES: int = 60

IST = pytz.timezone("Asia/Kolkata")
MARKET_CLOSE_HOUR: int = 15
MARKET_CLOSE_MINUTE: int = 30


class MonitoringScheduler:
    """
    DB-backed scheduler that queries PostgreSQL for active/tracking trades
    each tick, evaluates live market prices, and broadcasts alerts through
    registered notification channels.  All state mutations are persisted
    atomically via TradeTrackingRepository.

    The scheduler also embeds the Telegram bot callback listener as a
    parallel coroutine and handles snooze re-evaluation + market close.
    """

    def __init__(self, channels: List[NotificationChannel], telegram_enabled: bool = False) -> None:
        self.channels = channels
        self.repo = TradeTrackingRepository()
        self._tick_count: int = 0
        self._telegram_enabled = telegram_enabled

        # Shared with TelegramBotListener — maps trade_id → snooze expiry time (IST)
        self._snoozed_trades: dict[int, datetime] = {}

    async def run(self) -> None:
        self._print_banner()

        tasks = [self._tick_loop()]

        if self._telegram_enabled:
            from ..channels.telegram_alert_service.bot_listener import TelegramBotListener
            listener = TelegramBotListener(self._snoozed_trades)
            tasks.append(listener.run())
            logger.info("[SCHEDULER] Telegram bot listener enabled — running alongside tick loop.")

        await asyncio.gather(*tasks)

    async def _tick_loop(self) -> None:
        """Main monitoring loop — runs forever until market close."""
        while True:
            result = await self._run_tick()

            if result == -1:
                # Market close signal — stop the loop
                logger.info("[SCHEDULER] Market closed — stopping tick loop.")
                return

            if result == 0:
                logger.info("[SCHEDULER] No active/tracking trades remaining — service sleeping.")

            logger.debug(f"[SLEEP] {TICK_INTERVAL_SECONDS}s until next tick ({result} monitored)")
            await asyncio.sleep(TICK_INTERVAL_SECONDS)

    async def _run_tick(self) -> int:
        """
        Execute a single monitoring tick.
        Returns the number of trades evaluated, or -1 to signal market close.
        """
        self._tick_count += 1
        now_ist = datetime.now(IST)
        now_str = now_ist.strftime("%H:%M:%S")

        with SessionLocal() as db:
            try:
                # ── Step 0: Market close check ────────────────────────────────
                if self._is_market_closed(now_ist):
                    await self._close_all_trades(db)
                    return -1

                trades: List[TradeTracking] = self.repo.get_active_and_tracking_trades(db)

                if not trades:
                    logger.debug(f"[TICK #{self._tick_count}] {now_str} — 0 trades to monitor")
                    # Still process snoozed trades even if no TRACKING/ACTIVE
                    await self._process_snoozed_trades(db, {})
                    db.commit()
                    return 0

                logger.debug(f"[TICK #{self._tick_count}] {now_str} — {len(trades)} trade(s) active")

                # ── Step 1: Expiry check (only TRACKING trades) ──────────────
                for trade in trades:
                    if trade.status == TrackingStatus.TRACKING:
                        elapsed = (datetime.now(trade.created_at.tzinfo) - trade.created_at).total_seconds() / 60
                        if elapsed > EXPIRY_MINUTES:
                            logger.debug(f"[EXPIRED] {trade.symbol} elapsed={elapsed:.1f}m")
                            self.repo.update_trade_status(
                                db=db,
                                trade_id=trade.id,
                                new_status=TrackingStatus.EXPIRED,
                                event_type=TradeEventType.EXPIRED,
                                event_message=f"Trade expired after {elapsed:.1f} minutes without entering buy zone.",
                            )

                # Refresh the list after expiry processing
                trades = self.repo.get_active_and_tracking_trades(db)

                if not trades:
                    logger.debug("[TICK] All remaining trades expired this tick.")
                    await self._process_snoozed_trades(db, {})
                    db.commit()
                    return 0

                # ── Step 2: Fetch live prices ────────────────────────────────
                symbols = list(set(t.symbol for t in trades))
                logger.debug(f"[FETCH] Requesting prices for: {', '.join(symbols)}")
                prices = await fetch_prices(symbols)

                if not prices:
                    logger.debug("[FETCH] No prices returned this tick — will retry next tick.")
                    db.commit()
                    return len(trades)

                # ── Step 3: Evaluate each trade ──────────────────────────────
                for trade in trades:
                    current_price = prices.get(trade.symbol)
                    if current_price is None:
                        logger.debug(f"[SKIP] {trade.symbol} — price unavailable this tick")
                        continue

                    # Phase A: TRACKING — waiting for buy zone entry
                    if trade.status == TrackingStatus.TRACKING:
                        in_zone = trade.buy_zone_min <= current_price <= trade.buy_zone_max
                        status_icon = "✅" if in_zone else "⏳"

                        logger.debug(
                            f"{status_icon} {trade.symbol:<22} ₹{current_price:<10}  "
                            f"zone=₹{trade.buy_zone_min}→₹{trade.buy_zone_max}  "
                            f"{'IN ZONE' if in_zone else 'outside'}"
                        )

                        if in_zone:
                            logger.debug(
                                f"[ZONE HIT] {trade.symbol} — ₹{current_price} is inside "
                                f"₹{trade.buy_zone_min}→₹{trade.buy_zone_max}"
                            )
                            message_id = self._broadcast_alert(trade, current_price, "ENTRY")
                            if message_id is not None:
                                self.repo.mark_buy_zone_hit(db, trade.id, message_id)
                            else:
                                logger.warning(
                                    f"[RETRY PENDING] Alert failed for {trade.symbol} on all channels  "
                                    f"— will retry on next tick if still in zone"
                                )

                    # Phase B: ACTIVE — monitoring for target or stoploss
                    elif trade.status == TrackingStatus.ACTIVE:
                        # Check Stoploss
                        if current_price <= trade.hard_stoploss:
                            logger.debug(f"[STOP LOSS HIT] {trade.symbol} — ₹{current_price} <= ₹{trade.hard_stoploss}")
                            message_id = self._broadcast_alert(trade, current_price, "STOPLOSS")
                            if message_id is not None:
                                self.repo.update_trade_status(
                                    db=db,
                                    trade_id=trade.id,
                                    new_status=TrackingStatus.STOPLOSS_HIT,
                                    event_type=TradeEventType.STOPLOSS_HIT,
                                    event_message=f"Hard stoploss hit at ₹{current_price}.",
                                    event_details={"hit_price": current_price, "stoploss_level": trade.hard_stoploss},
                                    alert_sent=True,
                                )
                            else:
                                logger.warning(
                                    f"[RETRY PENDING] Stoploss alert failed for {trade.symbol} "
                                    f"— will retry next tick"
                                )

                        # Check Target 1
                        elif current_price >= trade.target_1:
                            logger.debug(f"[TARGET 1 HIT] {trade.symbol} — ₹{current_price} >= ₹{trade.target_1}")
                            message_id = self._broadcast_alert(trade, current_price, "TARGET")
                            if message_id is not None:
                                self.repo.update_trade_status(
                                    db=db,
                                    trade_id=trade.id,
                                    new_status=TrackingStatus.TARGET_1_HIT,
                                    event_type=TradeEventType.TARGET_1_HIT,
                                    event_message=f"Target 1 hit at ₹{current_price}.",
                                    event_details={"hit_price": current_price, "target_level": 1, "target_value": trade.target_1},
                                    alert_sent=True,
                                )
                            else:
                                logger.warning(
                                    f"[RETRY PENDING] Target alert failed for {trade.symbol} "
                                    f"— will retry next tick"
                                )
                        else:
                            logger.debug(
                                f"🔵 {trade.symbol:<22} ₹{current_price:<10}  "
                                f"ACTIVE (SL: ₹{trade.hard_stoploss}, T1: ₹{trade.target_1})"
                            )

                # ── Step 3.5: Snooze re-evaluation ───────────────────────────
                await self._process_snoozed_trades(db, prices)

                # ── Step 4: Commit all state mutations ───────────────────────
                db.commit()
                return len(trades)

            except Exception as exc:
                logger.error(f"[TICK ERROR] Unexpected error during tick #{self._tick_count}: {exc}", exc_info=True)
                db.rollback()
                return 0

    # ── Snooze Re-evaluation ─────────────────────────────────────────────────

    async def _process_snoozed_trades(self, db, prices: dict) -> None:
        """
        Check snoozed trades whose timer has expired.
        - Price still in zone → re-alert (SNOOZED → BUY_ZONE_HIT)
        - Price left zone → revert (SNOOZED → TRACKING)
        """
        now_ist = datetime.now(IST)
        expired_snoozes = {
            tid: expiry for tid, expiry in self._snoozed_trades.items()
            if now_ist >= expiry
        }

        if not expired_snoozes:
            return

        trade_ids = list(expired_snoozes.keys())
        snoozed_trades = self.repo.get_trades_by_ids(db, trade_ids)

        # Fetch prices for snoozed symbols if not already available
        snoozed_symbols = [t.symbol for t in snoozed_trades if t.symbol not in prices]
        if snoozed_symbols:
            extra_prices = await fetch_prices(list(set(snoozed_symbols)))
            prices.update(extra_prices)

        for trade in snoozed_trades:
            # Skip if no longer snoozed (user may have acted via another path)
            if trade.status != TrackingStatus.SNOOZED:
                self._snoozed_trades.pop(trade.id, None)
                continue

            current_price = prices.get(trade.symbol)
            if current_price is None:
                logger.debug(f"[SNOOZE] {trade.symbol} — price unavailable, will retry next tick")
                continue

            in_zone = trade.buy_zone_min <= current_price <= trade.buy_zone_max

            if in_zone:
                # Price still in zone → re-alert
                logger.info(f"[SNOOZE EXPIRED] {trade.symbol} — ₹{current_price} still in zone, re-alerting")
                message_id = self._broadcast_alert(trade, current_price, "ENTRY")
                if message_id is not None:
                    self.repo.update_trade_status(
                        db=db,
                        trade_id=trade.id,
                        new_status=TrackingStatus.BUY_ZONE_HIT,
                        event_type=TradeEventType.BUY_ZONE_HIT,
                        event_message=f"Snooze expired — price ₹{current_price} still in buy zone. Re-alerted.",
                        telegram_message_id=message_id,
                        alert_sent=True,
                    )
                    self._snoozed_trades.pop(trade.id, None)
                else:
                    logger.warning(f"[SNOOZE] Re-alert failed for {trade.symbol} — will retry next tick")
            else:
                # Price left zone → revert to TRACKING
                logger.info(
                    f"[SNOOZE EXPIRED] {trade.symbol} — ₹{current_price} left zone "
                    f"₹{trade.buy_zone_min}→₹{trade.buy_zone_max}. Reverting to TRACKING."
                )
                self.repo.update_trade_status(
                    db=db,
                    trade_id=trade.id,
                    new_status=TrackingStatus.TRACKING,
                    event_type=TradeEventType.BUY_ZONE_HIT,
                    event_message=f"Snooze expired — price ₹{current_price} outside buy zone. Reverted to tracking.",
                )
                self._snoozed_trades.pop(trade.id, None)

    # ── Market Close ─────────────────────────────────────────────────────────

    def _is_market_closed(self, now_ist: datetime) -> bool:
        """Check if current IST time is at or past market close (15:30)."""
        return (now_ist.hour > MARKET_CLOSE_HOUR or
                (now_ist.hour == MARKET_CLOSE_HOUR and now_ist.minute >= MARKET_CLOSE_MINUTE))

    async def _close_all_trades(self, db) -> None:
        """Force-close all non-terminal trades at market close."""
        open_trades = self.repo.get_all_non_terminal_trades(db)

        if not open_trades:
            logger.info("[MARKET CLOSE] No open trades to close.")
            db.commit()
            return

        for trade in open_trades:
            self.repo.update_trade_status(
                db=db,
                trade_id=trade.id,
                new_status=TrackingStatus.MARKET_CLOSED,
                event_type=TradeEventType.MARKET_CLOSED,
                event_message=f"Market closed at 15:30 IST. Trade force-closed from {trade.status.value}.",
                event_details={"previous_status": trade.status.value},
            )
            logger.info(f"[MARKET CLOSE] {trade.symbol} ({trade.status.value} → MARKET_CLOSED)")

        db.commit()

        # Send a single summary Telegram message (direct API call, not per-trade)
        symbols = [t.symbol for t in open_trades]
        summary = (
            f"🔔 Market Closed — 15:30 IST\n\n"
            f"{len(open_trades)} trade(s) force-closed:\n"
            + "\n".join(f"  • {s}" for s in symbols)
        )
        self._send_telegram_text(summary)

        # Clear any pending snoozes
        self._snoozed_trades.clear()

        logger.info(f"[MARKET CLOSE] {len(open_trades)} trade(s) force-closed. Service stopping.")

    # ── Broadcast ────────────────────────────────────────────────────────────

    def _send_telegram_text(self, text: str) -> None:
        """Send a raw text message to Telegram (for summaries, not per-trade alerts)."""
        import os
        import requests as req
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not bot_token or not chat_id:
            logger.debug("[TELEGRAM] Credentials not set — skipping summary message.")
            return
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            req.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
        except Exception as exc:
            logger.error(f"[TELEGRAM] Failed to send summary: {exc}")

    def _broadcast_alert(self, trade: TradeTracking, current_price: float, alert_type: str) -> Optional[str]:
        """
        Send alert to all configured channels.
        Returns the message_id from the first channel that succeeds,
        or None if all channels failed (or if no channels configured).
        """
        if not self.channels:
            logger.warning("No notification channels configured to broadcast alert.")
            return "no_channel"  # Sentinel — don't block state transitions when no channels exist

        first_message_id: Optional[str] = None
        for channel in self.channels:
            try:
                result = channel.send_alert(trade, current_price, alert_type)
                if result is not None and first_message_id is None:
                    first_message_id = result
            except Exception as exc:
                logger.error(f"[CHANNEL ERROR] {channel.__class__.__name__} failed for {trade.symbol}: {exc}")

        return first_message_id

    # ── Banner ───────────────────────────────────────────────────────────────

    def _print_banner(self) -> None:
        with SessionLocal() as db:
            trades = self.repo.get_active_and_tracking_trades(db)

        lines = [
            "╔══════════════════════════════════════════════╗",
            "║       MARKET ALERT SERVICE — LIVE            ║",
            "╚══════════════════════════════════════════════╝",
            f"  Tracking  : {len(trades)} trade(s) in database",
            f"  Tick every: {TICK_INTERVAL_SECONDS}s",
            f"  Expiry at : {EXPIRY_MINUTES} minutes",
            f"  Mkt close : {MARKET_CLOSE_HOUR}:{MARKET_CLOSE_MINUTE:02d} IST",
            f"  Channels  : {len(self.channels)} active",
            "  ─────────────────────────────────────────────",
        ]
        for trade in trades:
            lines.append(
                f"  {trade.symbol:<22} zone=₹{trade.buy_zone_min}→₹{trade.buy_zone_max}  "
                f"status={trade.status.value}"
            )
        lines.append("  ─────────────────────────────────────────────")
        logger.info("\n" + "\n".join(lines))
