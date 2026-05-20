#!/usr/bin/env python3

# =========================================================
# STOCK QUERY TOOL
# =========================================================
# Reads real-time data written by stock_pipeline.py.
# Both files must point to the same CACHE_FILE path.
#
# Usage:
#   python stock_query.py              # interactive mode
#   python stock_query.py RELIANCE.NS  # one-shot query
#   python stock_query.py status
#   python stock_query.py list
# =========================================================

import json
import sys
import os

from datetime import datetime
from filelock import FileLock

# Ensure the project root is on sys.path so absolute imports work
# even when this file is executed directly as a script.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from tools.market.technical_analysis_tool.stock_settings import CACHE_FILE, LOCK_FILE

# =========================================================
# MUST MATCH stock_pipeline.py
# =========================================================

# =========================================================
# READ CACHE (thread-safe)
# =========================================================

def read_cache():
    if not os.path.exists(CACHE_FILE):
        return None, None

    lock = FileLock(LOCK_FILE, timeout=5)
    try:
        with lock:
            with open(CACHE_FILE, "r") as f:
                payload = json.load(f)
        return payload.get("meta", {}), payload.get("data", {})
    except Exception as e:
        print(f"[ERROR] Could not read cache: {e}")
        return None, None

# =========================================================
# QUERY A SINGLE TICKER
# =========================================================

def query(ticker, data):
    key = ticker.strip().upper()

    # try exact match first, then .NS suffix fallback
    if key in data:
        result = data[key]

    elif not key.endswith(".NS") and (key + ".NS") in data:
        result = data[key + ".NS"]
        print(f"[INFO] Matched as {key}.NS\n")

    else:
        pipeline_tickers = list(data.keys())
        print(f"\n  '{key}' is NOT in the pipeline.")
        print(f"    The pipeline is currently tracking {len(pipeline_tickers)} stock(s).")
        if pipeline_tickers:
            sample = pipeline_tickers[:10]
            print(f"    Sample tickers : {sample}")
            if len(pipeline_tickers) > 10:
                print(f"    ... and {len(pipeline_tickers) - 10} more  (use 'list' to see all)")
        print()
        return

    print(json.dumps(result, indent=4))

    # human-readable freshness note
    ts = result.get("timestamp")
    if ts:
        try:
            age = (datetime.now() - datetime.fromisoformat(ts)).total_seconds()
            print(f"\n[INFO] Data age: {int(age)}s ago  ({ts})")
        except Exception:
            pass

# =========================================================
# STATUS
# =========================================================

def show_status(meta):
    print(json.dumps({
        "pipeline_cycle"  : meta.get("count"),
        "last_updated"    : meta.get("last_updated"),
        "ok_stocks"       : meta.get("ok"),
        "failed_stocks"   : meta.get("failed"),
        "total_tickers"   : len(meta.get("tickers", []))
    }, indent=4))

# =========================================================
# LIST
# =========================================================

def show_list(data):
    ok_list  = [t for t, v in data.items() if v.get("status") == "ok"]
    err_list = [t for t, v in data.items() if v.get("status") != "ok"]
    print(json.dumps({"ok": ok_list, "failed": err_list}, indent=4))

# =========================================================
# HANDLE A COMMAND
# =========================================================

def handle(cmd):
    meta, data = read_cache()

    if meta is None:
        print(f"\n[ERROR] Cache file '{CACHE_FILE}' not found.")
        print("        Make sure stock_pipeline.py is running first.\n")
        return

    cmd = cmd.strip()

    if cmd.lower() == "status":
        show_status(meta)

    elif cmd.lower() == "list":
        show_list(data)

    elif cmd:
        query(cmd, data)

# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    # one-shot mode:  python stock_query.py RELIANCE.NS
    if len(sys.argv) > 1:
        handle(" ".join(sys.argv[1:]))
        sys.exit(0)

    # interactive mode
    print("\n Stock Query Tool")
    print(" Pipeline cache :", os.path.abspath(CACHE_FILE))
    print()
    print(" Commands:")
    print("   RELIANCE          → query (auto-appends .NS if needed)")
    print("   RELIANCE.NS       → query exact")
    print("   list              → show all tracked tickers")
    print("   status            → pipeline health")
    print("   exit              → quit")
    print()

    while True:
        try:
            user_input = input("Query> ").strip()

            if not user_input:
                continue

            if user_input.lower() == "exit":
                print("Goodbye.")
                break

            handle(user_input)

        except KeyboardInterrupt:
            print("\nStopped.")
            break
