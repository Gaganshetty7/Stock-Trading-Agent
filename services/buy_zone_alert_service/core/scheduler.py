import logging
import time
from datetime import datetime
from typing import Dict

from ..models.tracking_object import TrackingObject
from .market_data_service import fetch_prices
from .notification_service import send_telegram_alert

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS: int = 60
EXPIRY_MINUTES: int = 90


class MonitoringScheduler:
    """
    Single scheduler that maintains the watchlist dict and runs the loop.
    Evaluates all active stocks per tick.
    """

    def __init__(self, watchlist: Dict[str, TrackingObject]) -> None:
        self.watchlist = watchlist
        self._tick_count: int = 0

    def run(self) -> None:
        self._print_banner()

        while True:
            if not self.watchlist:
                logger.info("[SCHEDULER] No active stocks remaining — service complete.")
                break

            self._run_tick()

            if not self.watchlist:
                logger.info("[SCHEDULER] All stocks resolved — service complete.")
                break

            logger.debug(f"[SLEEP] {TICK_INTERVAL_SECONDS}s until next tick ({len(self.watchlist)} active)")
            time.sleep(TICK_INTERVAL_SECONDS)

    def _run_tick(self) -> None:
        self._tick_count += 1
        now_str = datetime.now().strftime("%H:%M:%S")

        logger.debug(f"[TICK #{self._tick_count}] {now_str} — {len(self.watchlist)} stock(s) active")

        # ── Step 1: Expiry check ──────────────────────────────────────────────
        expired = []
        for symbol, obj in self.watchlist.items():
            if obj.elapsed_minutes() > EXPIRY_MINUTES:
                logger.debug(f"[EXPIRED] {symbol} elapsed={obj.elapsed_minutes():.1f}m")
                expired.append(symbol)

        for symbol in expired:
            self.watchlist[symbol].status = "EXPIRED"
            del self.watchlist[symbol]

        if not self.watchlist:
            logger.debug("[TICK] All remaining stocks expired this tick.")
            return

        # ── Step 2: Fetch prices ──────────────────────────────────────────────
        symbols = list(self.watchlist.keys())
        logger.debug(f"[FETCH] Requesting prices for: {', '.join(symbols)}")
        prices = fetch_prices(symbols)

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
                success = send_telegram_alert(obj, current_price)
                if success:
                    obj.status = "ALERTED"
                    obj.alert_sent = True
                    to_remove.append(symbol)
                else:
                    logger.warning(
                        f"[RETRY PENDING] Alert failed for {obj.symbol}  "
                        f"— will retry on next tick if still in zone"
                    )
        
        for symbol in to_remove:
            del self.watchlist[symbol]

    def _print_banner(self) -> None:
        lines = [
            "╔══════════════════════════════════════════════╗",
            "║        BUY ZONE ALERT SERVICE — LIVE         ║",
            "╚══════════════════════════════════════════════╝",
            f"  Tracking  : {len(self.watchlist)} stock(s)",
            f"  Tick every: {TICK_INTERVAL_SECONDS}s",
            f"  Expiry at : {EXPIRY_MINUTES} minutes",
            "  ─────────────────────────────────────────────",
        ]
        for sym, obj in self.watchlist.items():
            lines.append(
                f"  {sym:<22} zone=₹{obj.entry_plan.buy_zone.min}→₹{obj.entry_plan.buy_zone.max}"
            )
        lines.append("  ─────────────────────────────────────────────")
        logger.info("\n" + "\n".join(lines))
