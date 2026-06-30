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
import urllib.parse

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
        interval: str,  # "1m", "5m", "15m", or "1d"
        days_back: int = 30,
        max_retries: int = 3,
    ) -> Optional[pd.DataFrame]:
        """
        Fetch candlestick data for a single instrument.

        For intraday intervals ("1m", "5m", "15m"), it fetches both historical
        and current intraday (live today's) candles and combines them.
        For daily interval ("1d"), it fetches historical candles.

        Args:
            instrument_key: Upstox format, e.g., "NSE_EQ|INE002A01018"
            interval: "1m", "5m", "15m", or "1d"
            days_back: How many days to look back
            max_retries: Extra attempts with incremented days_back on empty results

        Returns:
            pandas DataFrame with columns: Open, High, Low, Close, Volume
            OR None if request fails
        """
        quoted_key = urllib.parse.quote(instrument_key)
        
        # 1. Fetch historical data
        hist_df = None
        for attempt in range(max_retries + 1):
            current_days_back = days_back + attempt
            try:
                to_date = datetime.now(IST).date()
                from_date = to_date - timedelta(days=current_days_back)

                if interval == "1d":
                    url = (
                        f"{self.base_url}/historical-candle/{quoted_key}/days/1/"
                        f"{to_date.isoformat()}/{from_date.isoformat()}"
                    )
                else:
                    upstox_interval = interval.replace("m", "")
                    url = (
                        f"{self.base_url}/historical-candle/{quoted_key}/minutes/{upstox_interval}/"
                        f"{to_date.isoformat()}/{from_date.isoformat()}"
                    )

                logger.debug(f"Fetching historical {instrument_key} [{interval}] from {from_date} to {to_date}")
                await self._rate_limit()

                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(url, headers=self.headers)
                    response.raise_for_status()

                data = response.json()
                if data.get("status") != "success":
                    logger.warning(f"Upstox historical error for {instrument_key}: {data.get('error', 'Unknown error')}")
                    return None

                candles = data.get("data", {}).get("candles", [])
                if not candles:
                    if attempt < max_retries:
                        logger.info(
                            f"No historical candles for {instrument_key} [{interval}] with "
                            f"days_back={current_days_back}, expanding to {current_days_back + 1}"
                        )
                        continue
                    logger.warning(
                        f"No historical candles returned for {instrument_key} [{interval}] "
                        f"after {max_retries + 1} attempts"
                    )
                else:
                    hist_df = self._transform_to_dataframe(candles)
                break

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error {e.response.status_code} fetching historical {instrument_key}: {e}")
                return None
            except asyncio.TimeoutError:
                logger.error(f"Request timeout for historical {instrument_key}")
                return None
            except Exception as e:
                logger.error(f"Unexpected error fetching historical {instrument_key}: {e}")
                return None

        # 2. Fetch intraday data if interval is not 1d
        intra_df = None
        if interval != "1d":
            try:
                upstox_interval = interval.replace("m", "")
                url = f"{self.base_url}/historical-candle/intraday/{quoted_key}/minutes/{upstox_interval}"
                
                logger.debug(f"Fetching intraday {instrument_key} [{interval}]")
                await self._rate_limit()

                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(url, headers=self.headers)
                    response.raise_for_status()
                    
                data = response.json()
                if data.get("status") == "success":
                    candles = data.get("data", {}).get("candles", [])
                    if candles:
                        intra_df = self._transform_to_dataframe(candles)
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error {e.response.status_code} fetching intraday {instrument_key}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error fetching intraday {instrument_key}: {e}")

        # 3. Combine DataFrames
        if hist_df is None and intra_df is None:
            return None
        
        dfs_to_concat = []
        if hist_df is not None and not hist_df.empty:
            dfs_to_concat.append(hist_df)
        if intra_df is not None and not intra_df.empty:
            dfs_to_concat.append(intra_df)
            
        if not dfs_to_concat:
            return None
            
        combined_df = pd.concat(dfs_to_concat)
        combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
        combined_df.sort_index(ascending=True, inplace=True)
        
        logger.debug(f"Successfully fetched {len(combined_df)} combined candles for {instrument_key}")
        return combined_df

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
    Fetch candlestick data for multiple instruments concurrently.

    Args:
        instrument_keys: List of Upstox instrument keys, e.g., ["NSE_EQ|INE002A01018", ...]
        intervals: List of intervals, e.g., ["1m", "5m", "15m", "1d"]

    Returns:
        dict: {
            "instrument_key": {
                "1m": DataFrame,  # 1-minute data
                "5m": DataFrame,  # 5-minute data
                "15m": DataFrame, # 15-minute data
                "1d": DataFrame,  # Daily data
            },
            ...
        }
    """
    if intervals is None:
        intervals = ["1m", "5m", "15m", "1d"]

    client = UpstoxClient(UPSTOX_TOKEN, UPSTOX_API_BASE_URL)

    # Build (key, interval, days_back) descriptors
    job_descriptors = []
    for instrument_key in instrument_keys:
        for interval in intervals:
            if interval == "1d":
                days_back = 10
            elif interval == "1m":
                days_back = 1
            else:
                days_back = 5
            job_descriptors.append((instrument_key, interval, days_back))

    # Fire all coroutines concurrently via asyncio.gather
    coros = [
        client.fetch_candles(key, interval, days_back)
        for key, interval, days_back in job_descriptors
    ]
    outcomes = await asyncio.gather(*coros, return_exceptions=True)

    # Collate results
    results = {}
    for (instrument_key, interval, _), outcome in zip(job_descriptors, outcomes):
        if instrument_key not in results:
            results[instrument_key] = {}

        if isinstance(outcome, Exception):
            logger.error(f"Error fetching {instrument_key} [{interval}]: {outcome}")
            results[instrument_key][interval] = None
        else:
            results[instrument_key][interval] = outcome

    return results

async def fetch_ltp_batch(instrument_keys: list[str]) -> dict:
    """
    Fetch LTP for multiple instruments in a single batched API call.

    The Upstox V3 ``/market-quote/ltp`` endpoint accepts comma-separated
    instrument_keys, so we collapse all requested symbols into one HTTP
    request instead of making N sequential round-trips.

    Args:
        instrument_keys: List of Upstox instrument keys,
            e.g. ["NSE_EQ|INE002A01018", "NSE_EQ|INE009A01021"]

    Returns:
        dict mapping each instrument_key to its LTP (float), or None
        on per-key failure.  Example::

            {"NSE_EQ|INE002A01018": 1432.50, "NSE_EQ|INE009A01021": None}
    """
    if not instrument_keys:
        return {}

    client = UpstoxClient(UPSTOX_TOKEN, UPSTOX_API_BASE_URL)
    results: dict = {key: None for key in instrument_keys}

    try:
        keys_csv = ",".join(instrument_keys)
        url = f"{client.base_url}/market-quote/ltp?instrument_key={keys_csv}"

        await client._rate_limit()

        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.get(url, headers=client.headers)
            response.raise_for_status()

        data = response.json()
        if data.get("status") != "success":
            logger.warning(f"Upstox batch LTP error: {data.get('errors', 'Unknown error')}")
            return results

        quotes = data.get("data", {})
        for api_key, instrument_data in quotes.items():
            matched_key = instrument_data.get("instrument_token")
            if matched_key and matched_key in results:
                ltp = instrument_data.get("last_price")
                if ltp is not None:
                    results[matched_key] = float(ltp)
            else:
                logger.debug(f"Unmatched LTP key from API response: {api_key}, token: {matched_key}")

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching batch LTP: {e.response.status_code} — {e}")
    except Exception as e:
        logger.error(f"Error fetching batch LTP: {e}")

    return results
