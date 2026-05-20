#!/usr/bin/env python3

# =========================================================
# STOCK FETCHER MODULE
# =========================================================
# Contains the fetch-and-write pipeline logic used by
# stock_pipeline.py. This module does not contain CLI logic.
# =========================================================

import json
import time
import os

import yfinance as yf
from datetime import datetime
from filelock import FileLock

from tools.market.technical_analysis_tool.stock_indicators import process_stock
from tools.market.technical_analysis_tool.stock_settings import CACHE_FILE, LOCK_FILE, REFRESH_SECONDS


def fetch_and_write(tickers, cycle_meta):
    try:
        start = time.time()
        print("\n[PIPELINE] Fetching all stocks ...")

        all_data_1m = yf.download(
            tickers=tickers, period="1d", interval="1m",
            group_by="ticker", auto_adjust=True,
            progress=False, threads=True
        )

        all_data_5m = yf.download(
            tickers=tickers, period="5d", interval="5m",
            group_by="ticker", auto_adjust=True,
            progress=False, threads=True
        )

        new_cache  = {}
        ok_count   = 0
        err_count  = 0

        for ticker in tickers:
            try:
                data    = all_data_1m[ticker].copy()
                data_5m = all_data_5m[ticker].copy()
                result  = process_stock(ticker, data, data_5m)
            except Exception as e:
                result = {
                    "stock"    : ticker,
                    "status"   : "error",
                    "message"  : str(e),
                    "timestamp": datetime.now().isoformat()
                }

            new_cache[ticker] = result

            if result["status"] == "ok":
                ok_count += 1
            else:
                err_count += 1

        cycle_meta["count"]        += 1
        cycle_meta["last_updated"]  = datetime.now().isoformat()
        cycle_meta["ok"]            = ok_count
        cycle_meta["failed"]        = err_count
        cycle_meta["tickers"]       = tickers

        payload = {
            "meta" : cycle_meta,
            "data" : new_cache
        }

        # ---- atomic write via file lock ----
        lock = FileLock(LOCK_FILE, timeout=10)
        with lock:
            tmp = CACHE_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(payload, f)
            os.replace(tmp, CACHE_FILE)

        elapsed = round(time.time() - start, 2)

        print(f"[PIPELINE] Cycle      : {cycle_meta['count']}")
        print(f"[PIPELINE] Success    : {ok_count}")
        print(f"[PIPELINE] Failed     : {err_count}")
        print(f"[PIPELINE] Time Taken : {elapsed}s")
        print(f"[PIPELINE] Next fetch in {REFRESH_SECONDS}s ...\n")

    except Exception as e:
        print(f"\n[PIPELINE] FETCH ERROR: {e}\n")
