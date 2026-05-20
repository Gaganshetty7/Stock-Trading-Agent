#!/usr/bin/env python3

# =========================================================
# STOCK SETTINGS
# =========================================================
# Shared configuration values used by the pipeline,
# query tool, and indicator processor.
# =========================================================

CACHE_FILE = "tools/market/technical_analysis_tool/stock_cache.json"
LOCK_FILE  = "tools/market/technical_analysis_tool/stock_cache.lock"
REFRESH_SECONDS = 30
MA_PERIOD = 20
