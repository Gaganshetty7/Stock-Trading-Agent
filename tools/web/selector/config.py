# =========================
# USER CONFIG (EDIT THIS)
# =========================

TOP_N = 10

# 👉 YOU DECIDE THIS
ALLOWED_TRENDS = ["bullish", "bearish"]  
# examples:
# ["bullish"]
# ["bearish"]
# ["bullish", "sideways"]
# ["bullish", "bearish", "sideways"]

CONFIDENCE_LEVELS = [0.98, 0.95, 0.92, 0.90, 0.85]

IMPACT_LEVELS = [0.95, 0.90, 0.80, 0.70, 0.60]

COMBINED_SCORE_WEIGHTS = {
    "impact": 0.7,
    "confidence": 0.3
}
