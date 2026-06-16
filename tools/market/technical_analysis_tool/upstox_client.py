#!/usr/bin/env python3

"""
Upstox Analytics API Client
----------------------------
Async HTTP client for fetching historical candlestick data from Upstox.
Single-instrument per request; respects rate limits (50 req/sec).
Returns pandas DataFrame matching yfinance output format.
"""

import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import pandas as pd

from config.settings import UPSTOX_TOKEN, UPSTOX_API_BASE_URL
from core.logger import get_logger

logger = get_logger("upstox_client")

IST = timezone(timedelta(hours=5, minutes=30))


class UpstoxClient:
    """Async Upstox API client for historical candle data."""
    
    def __init__(self, token: str, base_url: str = "https://api.upstox.com/v3"):
        self.token = token
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        # Rate limiting: track requests per second
        self.last_request_time = 0
        self.request_lock = asyncio.Lock()

    async def fetch_candles(
        self,
        instrument_key: str,
        interval: str,  # "1", "5", "15"
        days_back: int = 30,
    ) -> Optional[pd.DataFrame]:
        """
        Fetch candlestick data for a single instrument.

        Args:
            instrument_key: Upstox format, e.g., "NSE_EQ|INE002A01018"
            interval: "1", "5", or "15" (minutes)
            days_back: How many days to look back (max 30 for intraday)

        Returns:
            pandas DataFrame with columns: Open, High, Low, Close, Volume
            OR None if request fails
        """
        try:
            # Calculate date range
            to_date = datetime.now(IST).date()
            from_date = to_date - timedelta(days=days_back)

            # Build URL (Upstox maps Arg1 to toDate and Arg2 to fromDate)
            url = (
                f"{self.base_url}/historical-candle/{instrument_key}/minutes/{interval}/"
                f"{to_date.isoformat()}/{from_date.isoformat()}"
            )

            logger.debug(f"Fetching {instrument_key} [{interval}m] from {from_date} to {to_date}")

            # Respect rate limit: 50 req/sec
            await self._rate_limit()

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()

            data = response.json()

            if data.get("status") != "success":
                logger.warning(f"Upstox error for {instrument_key}: {data.get('error', 'Unknown error')}")
                return None

            candles = data.get("data", {}).get("candles", [])
            if not candles:
                logger.warning(f"No candles returned for {instrument_key}")
                return None

            # Transform array format to DataFrame
            df = self._transform_to_dataframe(candles)
            logger.debug(f"Successfully fetched {len(df)} candles for {instrument_key}")
            return df

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error(f"Authentication failed: Check UPSTOX_TOKEN. {e}")
            elif e.response.status_code == 404:
                logger.warning(f"Instrument not found: {instrument_key}")
            elif e.response.status_code == 429:
                logger.warning(f"Rate limit exceeded. Consider reducing request rate.")
            else:
                logger.error(f"HTTP error {e.response.status_code}: {e}")
            return None

        except asyncio.TimeoutError:
            logger.error(f"Request timeout for {instrument_key}")
            return None

        except Exception as e:
            logger.error(f"Unexpected error fetching {instrument_key}: {e}")
            return None

    async def fetch_ltp(self, instrument_key: str) -> Optional[float]:
        """Fetch the latest LTP for a single instrument key."""
        try:
            # Upstox V3 endpoint for LTP takes comma-separated instrument_keys but we fetch one at a time for simplicity and consistency
            url = f"{self.base_url}/market-quote/ltp?instrument_key={instrument_key}"
            
            await self._rate_limit()
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                
            data = response.json()
            if data.get("status") != "success":
                logger.warning(f"Upstox LTP error for {instrument_key}: {data.get('errors', 'Unknown error')}")
                return None
                
            quotes = data.get("data", {})
            if quotes:
                instrument_data = list(quotes.values())[0]
                return float(instrument_data.get("last_price", 0.0))
            return None
            
        except Exception as e:
            logger.error(f"Error fetching LTP for {instrument_key}: {e}")
            return None

    def _transform_to_dataframe(self, candles: list) -> pd.DataFrame:
        """
        Transform Upstox candle array format to pandas DataFrame.
        
        Input candle format: [timestamp, open, high, low, close, volume, openInterest]
        Output: DataFrame with DatetimeIndex and columns: Open, High, Low, Close, Volume
        """
        rows = []
        for candle in candles:
            timestamp_str, open_, high, low, close, volume, oi = candle
            rows.append({
                "Datetime": pd.to_datetime(timestamp_str),
                "Open": float(open_),
                "High": float(high),
                "Low": float(low),
                "Close": float(close),
                "Volume": int(volume),
            })

        df = pd.DataFrame(rows)
        if df.empty:
            return df

        df.set_index("Datetime", inplace=True)
        df.sort_index(ascending=True, inplace=True)
        return df

    async def _rate_limit(self, requests_per_second: float = 50.0):
        """
        Simple rate limiter: ensure we don't exceed requests_per_second.
        """
        async with self.request_lock:
            now = asyncio.get_event_loop().time()
            time_since_last = now - self.last_request_time
            min_interval = 1.0 / requests_per_second

            if time_since_last < min_interval:
                await asyncio.sleep(min_interval - time_since_last)

            self.last_request_time = asyncio.get_event_loop().time()


async def fetch_upstox_batch(
    instrument_keys: list[str],
    intervals: list[str] = None,
) -> dict:
    """
    Fetch candlestick data for multiple instruments in parallel.

    Args:
        instrument_keys: List of Upstox instrument keys, e.g., ["NSE_EQ|INE002A01018", ...]
        intervals: List of intervals, e.g., ["1", "5", "15"]

    Returns:
        dict: {
            "instrument_key": {
                "1": DataFrame,  # 1-minute data
                "5": DataFrame,  # 5-minute data
                "15": DataFrame, # 15-minute data
            },
            ...
        }
    """
    if intervals is None:
        intervals = ["1", "5", "15"]

    client = UpstoxClient(UPSTOX_TOKEN, UPSTOX_API_BASE_URL)
    results = {}

    # Create tasks: one per (instrument, interval) pair
    tasks = []
    for instrument_key in instrument_keys:
        for interval in intervals:
            # Match yfinance lookback: 1m → 1 day, 5m → 5 days, 15m → 5 days
            # We use days_back=1 for 1m to ensure we have enough data even at market open
            days_back = 1 if interval == "1" else 5
            tasks.append((instrument_key, interval, client.fetch_candles(instrument_key, interval, days_back)))

    # Execute all tasks concurrently (respects per-request rate limiting)
    for instrument_key, interval, task in tasks:
        try:
            df = await task
            if instrument_key not in results:
                results[instrument_key] = {}
            results[instrument_key][interval] = df
        except Exception as e:
            logger.error(f"Error fetching {instrument_key} [{interval}m]: {e}")
            if instrument_key not in results:
                results[instrument_key] = {}
            results[instrument_key][interval] = None

    return results

async def fetch_ltp_batch(instrument_keys: list[str]) -> dict:
    """
    Fetch LTP for multiple instruments in parallel.
    Args:
        instrument_keys: List of Upstox instrument keys.
    Returns:
        dict: {"instrument_key": float(ltp), ...}
    """
    client = UpstoxClient(UPSTOX_TOKEN, UPSTOX_API_BASE_URL)
    results = {}
    
    tasks = []
    for instrument_key in instrument_keys:
        tasks.append((instrument_key, client.fetch_ltp(instrument_key)))
        
    for instrument_key, task in tasks:
        try:
            ltp = await task
            results[instrument_key] = ltp
        except Exception as e:
            logger.error(f"Error fetching LTP for {instrument_key}: {e}")
            results[instrument_key] = None
            
    return results
