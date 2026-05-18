import re
import html
import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

BASE_HEADERS = {
    "Accept":          "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer":         "https://www.google.com/",
}

MAX_SUMMARY_LEN = 350

# Sentinel for "no parseable timestamp" — tz-aware so comparisons never blow up
_DT_MIN = datetime.min.replace(tzinfo=timezone.utc)

def clean_text(raw: str) -> str:
    text = re.sub(r"<.*?>", "", raw)
    text = html.unescape(text)
    return " ".join(text.split()).strip()

def get_headers() -> dict:
    return {**BASE_HEADERS, "User-Agent": random.choice(USER_AGENTS)}

def get_published_dt(entry) -> datetime:
    """
    Return a tz-aware UTC datetime for the entry.
    Tries three sources in order; falls back to _DT_MIN if all fail.
    """
    # 1. feedparser's pre-parsed time tuple (most reliable when present)
    pp = getattr(entry, "published_parsed", None)
    if pp:
        try:
            return datetime(*pp[:6], tzinfo=timezone.utc)
        except Exception:
            pass

    # 2. Raw published string — handles RFC 2822 and ISO 8601 variants
    raw = getattr(entry, "published", "") or ""
    if raw:
        try:
            dt = parsedate_to_datetime(raw)
            # parsedate_to_datetime may return naive if no tz in string
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except Exception:
            pass

    # 3. updated_parsed as last resort
    up = getattr(entry, "updated_parsed", None)
    if up:
        try:
            return datetime(*up[:6], tzinfo=timezone.utc)
        except Exception:
            pass

    return _DT_MIN

def human_age(pub_dt: datetime) -> str:
    if pub_dt == _DT_MIN:
        return "unknown"
    secs = max(0, (datetime.now(timezone.utc) - pub_dt).total_seconds())
    if secs < 3600:
        return f"{int(secs / 60)}m ago"
    if secs < 86400:
        return f"{int(secs / 3600)}h ago"
    return f"{int(secs / 86400)}d ago"

def extract_summary(entry) -> str:
    raw = getattr(entry, "description", getattr(entry, "summary", "")) or ""
    cleaned = clean_text(raw)
    return cleaned[:MAX_SUMMARY_LEN]
