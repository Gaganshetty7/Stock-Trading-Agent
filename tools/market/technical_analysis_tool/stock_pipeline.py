#!/usr/bin/env python3

# =========================================================
# STOCK PIPELINE SERVER
# =========================================================
# Continuously fetches data for a list of stocks and
# writes results to a shared cache file (stock_cache.json)
# that the query tool reads from.
#
# Usage:
#   python stock_pipeline.py
#   > Enter Stock Ticker List: ['RELIANCE.NS', 'TCS.NS']
#
# The pipeline runs forever. Stop with Ctrl+C.
# =========================================================

import time
import threading
import warnings
import logging
import ast
import os
import sys

# Ensure the project root is on sys.path so absolute imports work
# even when this file is executed directly as a script.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from tools.market.technical_analysis_tool.stock_fetcher import fetch_and_write
from tools.market.technical_analysis_tool.stock_settings import CACHE_FILE, REFRESH_SECONDS

# =========================================================
# SUPPRESS NOISE
# =========================================================

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore")

# =========================================================
# SHARED CACHE PATH
# =========================================================
# Both pipeline and query tool read/write this file.
# Change to an absolute path if running from different dirs.

CACHE_FILE  = "stock_cache.json"
LOCK_FILE   = "stock_cache.lock"

# =========================================================
# CONFIG
# =========================================================

REFRESH_SECONDS =30  # how often to re-fetch all stocks

# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    # ----- input -----
    try:
        raw    = input("Enter Stock Ticker List: ")
        tickers = [t.strip().upper() for t in ast.literal_eval(raw)]
    except Exception:
        print("\nInvalid list format.  Example:  ['RELIANCE.NS', 'TCS.NS']")
        sys.exit(1)

    if not tickers:
        print("No tickers provided.")
        sys.exit(1)

    print(f"\n[PIPELINE] Starting with {len(tickers)} tickers")
    print(f"[PIPELINE] Cache file   : {os.path.abspath(CACHE_FILE)}")
    print(f"[PIPELINE] Refresh every {REFRESH_SECONDS}s")
    print("[PIPELINE] Press Ctrl+C to stop\n")

    cycle_meta = {"count": 0, "last_updated": None, "ok": 0, "failed": 0, "tickers": []}

    # first fetch is blocking so the cache exists before we loop
    fetch_and_write(tickers, cycle_meta)

    # background refresh loop
    def loop():
        while True:
            time.sleep(REFRESH_SECONDS)
            fetch_and_write(tickers, cycle_meta)

    bg = threading.Thread(target=loop, daemon=True)
    bg.start()

    # keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[PIPELINE] Stopped.")
