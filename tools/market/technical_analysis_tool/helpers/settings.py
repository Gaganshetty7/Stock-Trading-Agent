#!/usr/bin/env python3

# =========================================================
# SETTINGS
# =========================================================
# Shared configuration values for the technical analysis tool.
# =========================================================

import os

MA_PERIOD = 20
SYMBOL_RESOLVER_SEGMENT: str = os.getenv("SYMBOL_RESOLVER_SEGMENT", "NSE_EQ")
