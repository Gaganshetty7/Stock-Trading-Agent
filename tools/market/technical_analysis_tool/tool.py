#!/usr/bin/env python3

"""
Technical Analysis Tool
-----------------------
Batch on-demand technical analysis for a list of NSE stock tickers.

Fetches live OHLCV data from Upstox Analytics API in a single batch request and returns
full technical indicators immediately. No background pipeline or cache required.

Agent usage (via core registry):
    The agent calls `fetch_and_save_technicals` which internally runs
    `run_technical_analysis` and writes results to disk via `write_json`.

Direct usage (for testing/pipelines):
    from tools.market.technical_analysis_tool import run_technical_analysis
    result = await run_technical_analysis(["RELIANCE", "TCS"])
"""

import logging
from datetime import datetime
import asyncio

from tools.market.technical_analysis_tool.upstox_client import UpstoxClient, fetch_upstox_batch, fetch_ltp_batch
from tools.market.technical_analysis_tool.helpers.symbol_resolver import resolve_symbols_batch
from tools.market.technical_analysis_tool.helpers.indicators import process_stock
from tools.storage.file_writer import write_json
from core.logger import get_logger

logger = get_logger("TechAnalysis")
from config.settings import UPSTOX_TOKEN, UPSTOX_API_BASE_URL

logger = logging.getLogger(__name__)


async def run_technical_analysis(tickers: list[str]) -> dict:
    """
    Fetch and analyze a list of NSE stock tickers on demand in a single batch.

    Normalizes tickers to uppercase.
    Fetches 1-minute, 5-minute, and 15-minute OHLCV data from Upstox Analytics API,
    then computes and returns for each ticker:
      - market_data         : current price, open, high, low, previous close
      - technical_indicators: RSI (1m + 5m), VWAP, MA20, overall trend
      - support_resistance  : S1–S3 and R1–R3 pivot levels
      - volume_analysis     : total volume, last candle, average, strength ratio

    Args:
        tickers: List of NSE stock symbols, e.g. ['RELIANCE', 'TCS', 'HDFCBANK']

    Returns:
        dict — Maps each ticker to its full analysis or an error dict.
    """
    # Normalize tickers to uppercase
    clean_tickers = []
    for t in tickers:
        clean_t = t.strip().upper()
        if clean_t:
            clean_tickers.append(clean_t)

    if not clean_tickers:
        return {}

    # Resolve symbols to Upstox instrument keys
    symbol_mapping = await resolve_symbols_batch(clean_tickers)

    # Filter out unresolved symbols
    resolvable_tickers = [t for t in clean_tickers if symbol_mapping.get(t)]
    if not resolvable_tickers:
        logger.error(f"Could not resolve any symbols from {clean_tickers}")
        return {t: {"stock": t, "status": "error", "message": "Symbol not found"} 
                for t in clean_tickers}

    # Fetch candles and LTP from Upstox (1m, 5m, 15m)
    instrument_keys = [symbol_mapping[t] for t in resolvable_tickers]
    upstox_data_task = asyncio.create_task(fetch_upstox_batch(instrument_keys, intervals=["1", "5", "15"]))
    ltp_data_task = asyncio.create_task(fetch_ltp_batch(instrument_keys))
    upstox_data, ltp_data = await asyncio.gather(upstox_data_task, ltp_data_task)

    # Process each ticker
    results = {}
    for ticker in clean_tickers:
        output_ticker = ticker
        
        try:
            instrument_key = symbol_mapping.get(ticker)
            if not instrument_key:
                results[output_ticker] = {
                    "stock": output_ticker,
                    "status": "error",
                    "message": "Symbol resolution failed",
                    "timestamp": datetime.now().isoformat()
                }
                continue

            # Get DataFrames for each interval
            ticker_data = upstox_data.get(instrument_key, {})
            data_1m = ticker_data.get("1")
            data_5m = ticker_data.get("5")
            data_15m = ticker_data.get("15")

            # Validate data availability
            if data_1m is None or data_5m is None or data_15m is None:
                results[output_ticker] = {
                    "stock": output_ticker,
                    "status": "error",
                    "message": "Failed to fetch candle data from Upstox",
                    "timestamp": datetime.now().isoformat()
                }
                continue

            # Pass to indicator processor
            ltp = ltp_data.get(instrument_key)
            results[output_ticker] = process_stock(output_ticker, data_1m, data_5m, data_15m, ltp=ltp)

        except Exception as e:
            results[output_ticker] = {
                "stock": output_ticker,
                "status": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            }

    return results


async def fetch_and_save_technicals(tickers: list[str]) -> dict:
    """
    Composite tool: fetches technical analysis for a list of tickers and
    saves the raw output directly to disk in a single atomic step.

    This is the primary tool exposed to the TechnicalAnalystAgent. It avoids
    forcing the LLM to copy-paste massive JSON payloads between tool calls
    (which causes truncation and data loss in the ReAct loop).

    Args:
        tickers: List of NSE stock symbols, e.g. ['RELIANCE', 'TCS', 'HDFCBANK']

    Returns:
        dict — Contains status, file_path, and list of tickers_processed.
    """
    logger.info(f"Fetching on-demand technicals for {len(tickers)} tickers...")
    data = await run_technical_analysis(tickers)
    filepath = await write_json(filename_prefix="technicals/analysis_batch", data=data)
    logger.info(f"Technicals batch saved to: {filepath}")

    return {
        "status": "success",
        "message": f"Successfully fetched technicals for {len(tickers)} tickers and saved to disk.",
        "file_path": filepath,
        "tickers_processed": list(data.keys())
    }
