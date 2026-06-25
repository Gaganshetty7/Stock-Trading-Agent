import logging
import asyncio
from datetime import datetime
from typing import List, Optional

from db.database import SessionLocal
from db.models.trade_tracking import TradeTracking, TrackingStatus, TradeEventType
from db.repositories.trade_tracking import TradeTrackingRepository
from .market_data_service import fetch_prices
from .notification import NotificationChannel

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS: int = 60
EXPIRY_MINUTES: int = 60


class MonitoringScheduler:
    """
    DB-backed scheduler that queries PostgreSQL for active/tracking trades
    each tick, evaluates live market prices, and broadcasts alerts through
    registered notification channels.  All state mutations are persisted
    atomically via TradeTrackingRepository.
    """

    def __init__(self, channels: List[NotificationChannel]) -> None:
        self.channels = channels
        self.repo = TradeTrackingRepository()
        self._tick_count: int = 0

    async def run(self) -> None:
        self._print_banner()

        while True:
            trade_count = await self._run_tick()

            if trade_count == 0:
                logger.info("[SCHEDULER] No active/tracking trades remaining — service sleeping.")

            logger.debug(f"[SLEEP] {TICK_INTERVAL_SECONDS}s until next tick ({trade_count} monitored)")
            await asyncio.sleep(TICK_INTERVAL_SECONDS)

    async def _run_tick(self) -> int:
        """
        Execute a single monitoring tick.
        Returns the number of trades that were evaluated.
        """
        self._tick_count += 1
        now_str = datetime.now().strftime("%H:%M:%S")

        with SessionLocal() as db:
            try:
                trades: List[TradeTracking] = self.repo.get_active_and_tracking_trades(db)

                if not trades:
                    logger.debug(f"[TICK #{self._tick_count}] {now_str} — 0 trades to monitor")
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

                # ── Step 4: Commit all state mutations ───────────────────────
                db.commit()
                return len(trades)

            except Exception as exc:
                logger.error(f"[TICK ERROR] Unexpected error during tick #{self._tick_count}: {exc}", exc_info=True)
                db.rollback()
                return 0

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
