#!/usr/bin/env python3

"""
Symbol Resolver
---------------
Resolves NSE trading symbols (e.g., "RELIANCE") to Upstox instrument_keys
(e.g., "NSE_EQ|INE002A01018").

Downloads and caches the Upstox instrument master file locally.
Refreshes cache daily (Upstox updates ~6 AM IST).
"""

import json
import gzip
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from config.settings import OUTPUTS_DIR
from core.logger import get_logger

logger = get_logger("symbol_resolver")

IST = timezone(timedelta(hours=5, minutes=30))

# Cache file path
CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "resources"
CACHE_FILE = CACHE_DIR / "upstox_instruments_master.json"
CACHE_TTL_HOURS = 24

# Upstox official master file URL
UPSTOX_INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"


class SymbolResolver:
    """Resolves NSE symbols to Upstox instrument_keys with caching."""

    def __init__(self):
        self.lookup_dict = None  # {trading_symbol: instrument_key}
        self.instruments_data = None  # Full instrument records

    async def initialize(self) -> bool:
        """
        Load or download instrument master file.
        Returns True if successful, False otherwise.
        """
        try:
            # Check cache first
            if CACHE_FILE.exists():
                cache_age = datetime.now() - datetime.fromtimestamp(CACHE_FILE.stat().st_mtime)
                if cache_age < timedelta(hours=CACHE_TTL_HOURS):
                    logger.info(f"Loading instruments from cache (age: {cache_age.seconds}s)")
                    return self._load_from_cache()

            # Cache missing or stale, download fresh
            logger.info("Downloading fresh instrument master from Upstox...")
            return await self._download_and_cache()

        except Exception as e:
            logger.error(f"Failed to initialize symbol resolver: {e}")
            return False

    def resolve(self, trading_symbol: str) -> Optional[str]:
        """
        Resolve a trading symbol to Upstox instrument_key.

        Args:
            trading_symbol: NSE symbol, e.g., "RELIANCE", "TCS", "SBIN"

        Returns:
            Upstox instrument_key (e.g., "NSE_EQ|INE002A01018") or None if not found
        """
        if self.lookup_dict is None:
            logger.error("Symbol resolver not initialized. Call initialize() first.")
            return None

        # Normalize to uppercase
        symbol = trading_symbol.upper() if trading_symbol else ""

        instrument_key = self.lookup_dict.get(symbol)
        if instrument_key is None:
            logger.warning(f"Symbol not found: {symbol}")
            return None

        logger.debug(f"Resolved {symbol} → {instrument_key}")
        return instrument_key

    def _load_from_cache(self) -> bool:
        """Load cached instrument data from disk."""
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                self.instruments_data = json.load(f)

            # Build lookup dict
            self.lookup_dict = {}
            for record in self.instruments_data:
                trading_symbol = record.get("trading_symbol", "")
                instrument_key = record.get("instrument_key", "")
                if trading_symbol and instrument_key:
                    self.lookup_dict[trading_symbol] = instrument_key

            logger.info(f"Loaded {len(self.lookup_dict)} instruments from cache")
            return True

        except Exception as e:
            logger.error(f"Failed to load from cache: {e}")
            return False

    async def _download_and_cache(self) -> bool:
        """Download instrument master from Upstox and cache locally."""
        try:
            # Download gzip file
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(UPSTOX_INSTRUMENTS_URL)
                response.raise_for_status()
                logger.debug(f"Downloaded {len(response.content)} bytes")

            # Decompress gzip
            json_data = json.loads(gzip.decompress(response.content).decode("utf-8"))

            # Expect array of instrument records
            if isinstance(json_data, list):
                self.instruments_data = json_data
            elif isinstance(json_data, dict) and "data" in json_data:
                self.instruments_data = json_data["data"]
            else:
                logger.error("Unexpected JSON structure from Upstox")
                return False

            # Build lookup dict
            self.lookup_dict = {}
            for record in self.instruments_data:
                trading_symbol = record.get("trading_symbol", "")
                instrument_key = record.get("instrument_key", "")
                if trading_symbol and instrument_key:
                    self.lookup_dict[trading_symbol] = instrument_key

            logger.info(f"Built lookup dict with {len(self.lookup_dict)} symbols")

            # Save to cache
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.instruments_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Cached {len(self.instruments_data)} instruments to {CACHE_FILE}")

            return True

        except httpx.HTTPError as e:
            logger.error(f"HTTP error downloading instruments: {e}")
            return False
        except Exception as e:
            logger.error(f"Error downloading/caching instruments: {e}")
            return False


# Global singleton instance
_resolver: Optional[SymbolResolver] = None


async def get_resolver() -> SymbolResolver:
    """Get or create global symbol resolver instance."""
    global _resolver
    if _resolver is None:
        _resolver = SymbolResolver()
        await _resolver.initialize()
    return _resolver


async def resolve_symbol(trading_symbol: str) -> Optional[str]:
    """
    Convenience function: resolve a single symbol.
    
    Args:
        trading_symbol: NSE symbol, e.g., "RELIANCE"

    Returns:
        Upstox instrument_key or None
    """
    resolver = await get_resolver()
    return resolver.resolve(trading_symbol)


async def resolve_symbols_batch(trading_symbols: list[str]) -> dict[str, Optional[str]]:
    """
    Resolve multiple symbols to instrument_keys.

    Args:
        trading_symbols: List of NSE symbols

    Returns:
        dict: {symbol: instrument_key or None}
    """
    resolver = await get_resolver()
    return {symbol: resolver.resolve(symbol) for symbol in trading_symbols}
