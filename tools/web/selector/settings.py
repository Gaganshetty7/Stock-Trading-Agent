# =========================
# USER CONFIG (EDIT THIS)
# =========================

TOP_N_ARTICLES = 10

# YOU DECIDE THIS bullish/bearish/sideways
ALLOWED_TRENDS = ["bullish"]  

# PROGRESSIVE THRESHOLD CONFIG
# The system will start at (1.0, 1.0) and decrease by STEP 
# until it hits MIN_CONFIDENCE and MIN_IMPACT.
MIN_CONFIDENCE = 0.75
MIN_IMPACT = 0.75
STEP = 0.05

COMBINED_SCORE_WEIGHTS = {
    "impact": 0.7,
    "confidence": 0.3
}
