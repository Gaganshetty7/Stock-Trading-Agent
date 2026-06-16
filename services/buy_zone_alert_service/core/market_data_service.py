import logging
from typing import Dict, List

from tools.market.technical_analysis_tool.upstox_client import fetch_ltp_batch
from tools.market.technical_analysis_tool.helpers.symbol_resolver import resolve_symbols_batch

logger = logging.getLogger(__name__)


async def fetch_prices(symbols: List[str]) -> Dict[str, float]:
    """
    Fetch the latest real-time LTP for each symbol via Upstox API.
    
    Returns a dict of ticker → price.
    """
    if not symbols:
        return {}

    try:
        # 1. Resolve tickers to Upstox instrument keys (e.g. RELIANCE -> NSE_EQ|...)
        symbol_mapping = await resolve_symbols_batch(symbols)
        
        # 2. Extract key list for Upstox call
        resolvable_symbols = [s for s in symbols if symbol_mapping.get(s)]
        instrument_keys = [symbol_mapping[s] for s in resolvable_symbols]
        
        if not instrument_keys:
            logger.warning(f"[MARKET DATA] No symbols could be resolved: {symbols}")
            return {}

        # 3. Fetch LTP batch from Upstox
        ltp_data = await fetch_ltp_batch(instrument_keys)
        
        # 4. Map back to original tickers
        prices: Dict[str, float] = {}
        # Invert mapping to go from instrument_key -> ticker
        key_to_ticker = {v: k for k, v in symbol_mapping.items()}
        
        for key, ltp in ltp_data.items():
            if ltp is not None:
                ticker = key_to_ticker.get(key)
                if ticker:
                    prices[ticker] = round(float(ltp), 2)
                    logger.debug(f"[UPSTOX PRICE] {ticker:<15} ₹{ltp}")

        return prices

    except Exception as exc:
        logger.error(f"[MARKET DATA ERROR] Failed to fetch Upstox prices: {exc}")
        return {}
