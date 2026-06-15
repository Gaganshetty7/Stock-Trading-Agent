import logging
from typing import Dict, List

import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_prices(symbols: List[str]) -> Dict[str, float]:
    """
    Fetch the latest available price for each symbol via yfinance.

    Strategy:
      1. Try ticker.fast_info.last_price  — fastest, real-time during market hours.
      2. Fall back to 1-minute history     — works when fast_info returns None/0.

    Returns a dict of symbol → price.  Symbols that fail are omitted.
    """
    if not symbols:
        return {}

    prices: Dict[str, float] = {}

    for symbol in symbols:
        price: float | None = None

        try:
            ticker = yf.Ticker(symbol)

            # ── Attempt 1: fast_info ─────────────────────────────────────────
            try:
                raw = ticker.fast_info.last_price
                if raw and float(raw) > 0:
                    price = round(float(raw), 2)
            except Exception:
                pass

            # ── Attempt 2: 1-minute history ──────────────────────────────────
            if price is None:
                hist = ticker.history(period="1d", interval="1m")
                if not hist.empty:
                    price = round(float(hist["Close"].iloc[-1]), 2)

        except Exception as exc:
            logger.error(f"[PRICE ERROR] {symbol}: {exc}")
            continue

        if price and price > 0:
            prices[symbol] = price
            logger.debug(f"[PRICE] {symbol:<22} ₹{price}")
        else:
            logger.debug(f"[PRICE] {symbol:<22} — no valid price returned")

    return prices
