import re
from datetime import datetime, time
from zoneinfo import ZoneInfo


def is_market_open() -> bool:
    """Return whether the Indian market is open in IST.

    NSE / BSE trading hours are roughly 09:15–15:30 IST on weekdays.
    """
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    if now.weekday() >= 5:  # Saturday, Sunday
        return False

    market_open = time(9, 15)
    market_close = time(15, 30)
    return market_open <= now.time() <= market_close


def parse_age_to_mins(age: str) -> int:
    """Convert an age string into minutes.

    Supports values like "45 mins", "2 hours", "1.5 hours", "stale", and "N/A".
    """
    if age is None:
        return 999

    text = str(age).strip().lower()
    if not text or text in {"stale", "unknown", "n/a", "na", "none"}:
        return 999

    # Numeric-only age representing minutes
    numeric_match = re.match(r"^\s*(\d+(?:\.\d+)?)\s*$", text)
    if numeric_match:
        return int(float(numeric_match.group(1)))

    hours_match = re.search(r"(\d+(?:\.\d+)?)\s*hour", text)
    if hours_match:
        return int(float(hours_match.group(1)) * 60)

    mins_match = re.search(r"(\d+(?:\.\d+)?)\s*min", text)
    if mins_match:
        return int(float(mins_match.group(1)))

    days_match = re.search(r"(\d+(?:\.\d+)?)\s*day", text)
    if days_match:
        return int(float(days_match.group(1)) * 24 * 60)

    # Fallback: extract first number and interpret as minutes.
    fallback_match = re.search(r"(\d+(?:\.\d+)?)", text)
    if fallback_match:
        return int(float(fallback_match.group(1)))

    return 999
