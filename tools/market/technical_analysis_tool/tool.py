#!/usr/bin/env python3

"""
Technical Analysis Tool
-----------------------
Batch on-demand technical analysis for a list of NSE stock tickers.

Fetches live OHLCV data from yfinance in a single batch request and returns
full technical indicators immediately. No background pipeline or cache required.

Agent usage (via core registry):
    The agent calls `fetch_and_save_technicals` which internally runs
    `run_technical_analysis` and writes results to disk via `write_json`.

Direct usage (for testing/pipelines):
    from tools.market.technical_analysis_tool import run_technical_analysis
    result = await run_technical_analysis(["RELIANCE", "TCS.NS"])
"""

import warnings
import logging
from datetime import datetime

import yfinance as yf

from tools.market.technical_analysis_tool.helpers.indicators import process_stock
from tools.storage.file_writer import write_json
from core.logger import get_logger

logger = get_logger("TechAnalysis")

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore")


async def run_technical_analysis(tickers: list[str]) -> dict:
    """
    Fetch and analyze a list of NSE stock tickers on demand in a single batch.

    Automatically appends '.NS' suffix to any ticker that is missing it.
    Downloads 1-minute (intraday) and 5-minute OHLCV data from yfinance,
    then computes and returns for each ticker:
      - market_data         : current price, open, high, low, previous close
      - technical_indicators: RSI (1m + 5m), VWAP, MA20, overall trend
      - support_resistance  : S1–S3 and R1–R3 pivot levels
      - volume_analysis     : total volume, last candle, average, strength ratio

    Args:
        tickers: List of NSE stock symbols, e.g. ['RELIANCE', 'TCS.NS', 'HDFCBANK']
                 Missing '.NS' suffixes are added automatically.

    Returns:
        dict — Maps each ticker (with .NS) to its full analysis or an error dict.
    """
    formatted_tickers = []
    for t in tickers:
        clean_t = t.strip().upper()
        if not clean_t.endswith(".NS"):
            clean_t += ".NS"
        formatted_tickers.append(clean_t)

    # Note: Using multi_level_index=False for multiple tickers is not robust in yf.
    # When fetching multiple tickers, it's safer to let yf return the default MultiIndex.
    data_1m = yf.download(
        formatted_tickers, period="1d", interval="1m",
        auto_adjust=True, progress=False
    )
    data_5m = yf.download(
        formatted_tickers, period="5d", interval="5m",
        auto_adjust=True, progress=False
    )
    data_15m = yf.download(
        formatted_tickers, period="5d", interval="15m",
        auto_adjust=True, progress=False
    )

    results = {}
    for ticker in formatted_tickers:
        try:
            if len(formatted_tickers) == 1:
                # Single ticker: yfinance returns flat columns (Close, Open, etc.)
                ticker_1m = data_1m.copy()
                ticker_5m = data_5m.copy()
                ticker_15m = data_15m.copy()
            else:
                # Multiple tickers: yfinance returns MultiIndex (Price, Ticker)
                ticker_1m = data_1m.xs(ticker, axis=1, level=1).copy()
                ticker_5m = data_5m.xs(ticker, axis=1, level=1).copy()
                ticker_15m = data_15m.xs(ticker, axis=1, level=1).copy()

            results[ticker] = process_stock(ticker, ticker_1m, ticker_5m, ticker_15m)
        except Exception as e:
            results[ticker] = {
                "stock": ticker,
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
        tickers: List of NSE stock symbols, e.g. ['RELIANCE', 'TCS.NS', 'HDFCBANK']
                 Missing '.NS' suffixes are added automatically.

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
