import logging
import asyncio
from datetime import datetime
from typing import Dict, List

from ..models.tracking_object import TrackingObject, TrackingStatus
from .market_data_service import fetch_prices
from .notification import NotificationChannel

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS: int = 60
EXPIRY_MINUTES: int = 60


class MonitoringScheduler:
    """
    Single scheduler that maintains the watchlist dict and runs the loop.
    Evaluates all active stocks per tick and broadcasts events to channels.
    """

    def __init__(self, watchlist: Dict[str, TrackingObject], channels: List[NotificationChannel]) -> None:
        self.watchlist = watchlist
        self.channels = channels
        self._tick_count: int = 0

    async def run(self) -> None:
        self._print_banner()

        while True:
            if not self.watchlist:
                logger.info("[SCHEDULER] No active stocks remaining — service complete.")
                break

            await self._run_tick()

            if not self.watchlist:
                logger.info("[SCHEDULER] All stocks resolved — service complete.")
                break

            logger.debug(f"[SLEEP] {TICK_INTERVAL_SECONDS}s until next tick ({len(self.watchlist)} active)")
            await asyncio.sleep(TICK_INTERVAL_SECONDS)

    async def _run_tick(self) -> None:
        self._tick_count += 1
        now_str = datetime.now().strftime("%H:%M:%S")

        logger.debug(f"[TICK #{self._tick_count}] {now_str} — {len(self.watchlist)} stock(s) active")

        # ── Step 1: Expiry check (Only for un-entered tracking state) ─────────
        expired = []
        for symbol, obj in self.watchlist.items():
            if obj.status == TrackingStatus.TRACKING and obj.elapsed_minutes() > EXPIRY_MINUTES:
                logger.debug(f"[EXPIRED] {symbol} elapsed={obj.elapsed_minutes():.1f}m")
                expired.append(symbol)

        for symbol in expired:
            self.watchlist[symbol].status = TrackingStatus.EXPIRED
            del self.watchlist[symbol]

        if not self.watchlist:
            logger.debug("[TICK] All remaining stocks expired this tick.")
            return

        # ── Step 2: Fetch prices ──────────────────────────────────────────────
        symbols = list(self.watchlist.keys())
        logger.debug(f"[FETCH] Requesting prices for: {', '.join(symbols)}")
        prices = await fetch_prices(symbols)

        if not prices:
            logger.debug("[FETCH] No prices returned this tick — will retry next tick.")
            return

        # ── Step 3: Evaluate each active stock ────────────────────────────────
        to_remove = []
        for symbol, obj in self.watchlist.items():
            current_price = prices.get(symbol)
            if current_price is None:
                logger.debug(f"[SKIP] {symbol} — price unavailable this tick")
                continue

            # Phase A: Waiting for entry
            if obj.status == TrackingStatus.TRACKING:
                in_zone = obj.entry_plan.buy_zone.min <= current_price <= obj.entry_plan.buy_zone.max
                status_icon = "✅" if in_zone else "⏳"

                logger.debug(
                    f"{status_icon} {symbol:<22} ₹{current_price:<10}  "
                    f"zone=₹{obj.entry_plan.buy_zone.min}→₹{obj.entry_plan.buy_zone.max}  "
                    f"{'IN ZONE' if in_zone else 'outside'}"
                )

                if in_zone:
                    logger.debug(
                        f"[ZONE HIT] {obj.symbol} — ₹{current_price} is inside "
                        f"₹{obj.entry_plan.buy_zone.min}→₹{obj.entry_plan.buy_zone.max}"
                    )
                    success = self._broadcast_alert(obj, current_price, "ENTRY")
                    if success:
                        obj.status = TrackingStatus.ACTIVE
                        obj.alert_sent = True
                        obj.entry_price = current_price
                        # We DONT remove it because we want to track target/stoploss now
                    else:
                        logger.warning(
                            f"[RETRY PENDING] Alert failed for {obj.symbol} on all channels  "
                            f"— will retry on next tick if still in zone"
                        )
            
            # Phase B: Entered trade, waiting for target or stoploss
            elif obj.status == TrackingStatus.ACTIVE:
                # Check Stoploss
                if current_price <= obj.stoploss_plan.hard_stoploss:
                    logger.debug(f"[STOP LOSS HIT] {obj.symbol} — ₹{current_price} <= ₹{obj.stoploss_plan.hard_stoploss}")
                    success = self._broadcast_alert(obj, current_price, "STOPLOSS")
                    if success:
                        obj.status = TrackingStatus.STOPLOSS_HIT
                        to_remove.append(symbol)
                        
                # Check Target 1
                elif current_price >= obj.target_plan.target_1:
                    logger.debug(f"[TARGET 1 HIT] {obj.symbol} — ₹{current_price} >= ₹{obj.target_plan.target_1}")
                    success = self._broadcast_alert(obj, current_price, "TARGET")
                    if success:
                        obj.status = TrackingStatus.TARGET_HIT
                        to_remove.append(symbol)
                else:
                    logger.debug(f"🔵 {symbol:<22} ₹{current_price:<10}  ACTIVE (SL: ₹{obj.stoploss_plan.hard_stoploss}, T1: ₹{obj.target_plan.target_1})")

        for symbol in to_remove:
            del self.watchlist[symbol]

    def _broadcast_alert(self, obj: TrackingObject, current_price: float, alert_type: str) -> bool:
        """
        Send alert to all configured channels.
        Returns True if at least one channel successfully sent the alert.
        Returns False if all channels failed (or if no channels configured).
        """
        if not self.channels:
            logger.warning("No notification channels configured to broadcast alert.")
            return True # Consider "sent" if there are no channels, to avoid endless retrying

        success = False
        for channel in self.channels:
            if channel.send_alert(obj, current_price, alert_type):
                success = True
                
        return success

    def _print_banner(self) -> None:
        lines = [
            "╔══════════════════════════════════════════════╗",
            "║       MARKET ALERT SERVICE — LIVE            ║",
            "╚══════════════════════════════════════════════╝",
            f"  Tracking  : {len(self.watchlist)} stock(s)",
            f"  Tick every: {TICK_INTERVAL_SECONDS}s",
            f"  Expiry at : {EXPIRY_MINUTES} minutes",
            f"  Channels  : {len(self.channels)} active",
            "  ─────────────────────────────────────────────",
        ]
        for sym, obj in self.watchlist.items():
            lines.append(
                f"  {sym:<22} zone=₹{obj.entry_plan.buy_zone.min}→₹{obj.entry_plan.buy_zone.max}"
            )
        lines.append("  ─────────────────────────────────────────────")
        logger.info("\n" + "\n".join(lines))
