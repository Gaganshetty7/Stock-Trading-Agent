import asyncio
import random
import urllib.parse
import re
import html
import json
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import aiohttp
import feedparser
import pytz
from rapidfuzz import fuzz

from core.logger import get_logger

logger = get_logger("broad_market_rss_fetcher")

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

REQUEST_TIMEOUT        = 8
MAX_SUMMARY_LEN        = 350
MAX_ARTICLES_PER_QUERY = 100
BATCH_CONCURRENCY      = 8
STAGGER_DELAY          = 0.25
MAX_RETRIES            = 1
RETRY_DELAY            = 10
DEDUP_SIMILARITY       = 60

OUTPUT_DIR  = Path("data/rss_output")
OUTPUT_FILE = OUTPUT_DIR / "broad_market_articles.json"

# Sentinel for "no parseable timestamp" — tz-aware so comparisons never blow up
_DT_MIN = datetime.min.replace(tzinfo=timezone.utc)


# ── Query grid ────────────────────────────────────────────────────────────────

# ============================================================
# Broad Market Sweepers
# ============================================================

_BROAD_SWEEPERS = [
    "NSE BSE India stock market today",
    "India stock market news today",
    "India quarterly results today",
    "India corporate earnings today",
    "NSE BSE share price today",
    "India stock market gainers losers",
    "India FII DII activity today",
    "India bulk deal today",
    "India IPO news today",
    "SEBI action India today",
    "RBI policy India today",
    "India market rally today",
    "India 52 week high stocks",
    "India upper circuit stocks",
    "India mutual fund news",
    "India analyst target price",
    "India company earnings guidance",
    "India promoter stake sale",
    "India dividend buyback today",
    "India rights issue today",
    "India takeover open offer",
    "India earnings surprise stocks",
    "India capex expansion company",
    "India company revenue profit",
    "India company order win",
    "India large contract win India",
]



# ============================================================
# High Signal Queries
# Low volume but HIGH market impact.
# Keep even if article count is smaller.
# ============================================================

_HIGH_SIGNAL = [
    "India company merger today",
    "India takeover bid today",
    "India defence order today",
    "India pharma FDA approval",
    "India pharma drug approval",
    "India QIP issue today",
    "India rights issue record date",
    "India buyback record date",
    "India dividend record date",
    "India stake sale today",
    "India insolvency NCLT",
    "India plant shutdown company",
    "India capex expansion",
    "India insider trading SEBI",
    "India acquisition deal today",
]

# ============================================================
# Sector-Specific Semantic Query Mapping
# ============================================================

_SECTOR_EVENT_MAP: dict[str, list[str]] = {

    # ========================================================
    # BANKING
    # ========================================================

    "banking": [
        "results profit",
        "loan growth",
        "bank expansion",
        "bank partnership",
        "target price",
        "RBI policy",
        "bank IPO",
        "bank earnings",
        "bank stocks",
        "credit growth",
    ],

    # ========================================================
    # PHARMA
    # ========================================================

    "pharma": [
        "results profit",
        "FDA approval",
        "drug approval",
        "export order",
        "capacity expansion",
        "licensing deal",
        "target price",
        "pharma earnings",
        "pharma IPO",
        "US market",
    ],

    # ========================================================
    # IT
    # ========================================================

    "IT": [
        "results profit",
        "AI partnership",
        "cloud deal",
        "data center expansion",
        "target price",
        "IT hiring",
        "IT earnings",
        "block deal",
        "digital transformation",
        "software deal",
    ],

    # ========================================================
    # INFRASTRUCTURE
    # ========================================================

    "infrastructure": [
        "EPC order",
        "project win",
        "results profit",
        "construction order",
        "road project",
        "railway project",
        "capacity expansion",
        "target price",
        "infrastructure IPO",
        "government project",
    ],

    # ========================================================
    # ENERGY
    # ========================================================

    "energy": [
        "renewable energy",
        "solar project",
        "wind project",
        "results profit",
        "oil gas",
        "capacity expansion",
        "energy IPO",
        "target price",
        "power project",
        "green energy",
    ],

    # ========================================================
    # FMCG
    # ========================================================

    "FMCG": [
        "results profit",
        "sales growth",
        "consumer demand",
        "capacity expansion",
        "FMCG earnings",
        "distribution expansion",
        "retail growth",
    ],

    # ========================================================
    # METALS
    # ========================================================

    "metals": [
        "steel production",
        "aluminium production",
        "results profit",
        "mining expansion",
        "steel export",
        "capacity expansion",
        "metal stocks",
        "commodity prices",
    ],

    # ========================================================
    # AUTO
    # ========================================================

    "auto": [
        "vehicle sales",
        "EV expansion",
        "results profit",
        "auto exports",
        "manufacturing expansion",
        "target price",
        "auto earnings",
        "car sales",
        "two wheeler sales",
        "auto stocks",
    ],

    # ========================================================
    # TELECOM
    # ========================================================

    "telecom": [
        "5G expansion",
        "spectrum news",
        "telecom earnings",
        "results profit",
        "subscriber growth",
        "telecom IPO",
        "target price",
        "network expansion",
        "broadband growth",
    ],

    # ========================================================
    # CHEMICALS
    # ========================================================

    "chemicals": [
        "specialty chemicals",
        "chemical exports",
        "results profit",
        "capacity expansion",
        "chemical stocks",
        "target price",
        "chemical earnings",
        "export demand",
    ],

    # ========================================================
    # DEFENCE
    # ========================================================

    "defence": [
        "defence order",
        "government contract",
        "results profit",
        "military equipment",
        "manufacturing expansion",
        "defence stocks",
        "target price",
        "Make in India defence",
    ],

    # ========================================================
    # REAL ESTATE
    # ========================================================

    "real estate": [
        "property sales",
        "housing demand",
        "real estate earnings",
        "commercial project",
        "construction expansion",
        "home loan policy",
        "REIT IPO",
        "target price",
        "real estate stocks",
        "property launches",
    ],
}

# ============================================================
# Generate Final Sector Queries
# ============================================================

_SECTOR_EVENT_QUERIES = [
    f"India {sector} {event}"
    for sector, events in _SECTOR_EVENT_MAP.items()
    for event in events
]

# ============================================================
# Final Master Query List
# ============================================================

ALL_QUERIES = (
    _BROAD_SWEEPERS
    + _SECTOR_EVENT_QUERIES
    + _HIGH_SIGNAL
)
# ── Text helpers ──────────────────────────────────────────────────────────────

def _clean_text(raw: str) -> str:
    text = re.sub(r"<.*?>", "", raw)
    text = html.unescape(text)
    return " ".join(text.split()).strip()


def _get_headers() -> dict:
    return {**BASE_HEADERS, "User-Agent": random.choice(USER_AGENTS)}


def _get_published_dt(entry) -> datetime:
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


def _human_age(pub_dt: datetime) -> str:
    if pub_dt == _DT_MIN:
        return "unknown"
    secs = max(0, (datetime.now(timezone.utc) - pub_dt).total_seconds())
    if secs < 3600:
        return f"{int(secs / 60)}m ago"
    if secs < 86400:
        return f"{int(secs / 3600)}h ago"
    return f"{int(secs / 86400)}d ago"


def _extract_summary(entry) -> str:
    raw = getattr(entry, "description", getattr(entry, "summary", "")) or ""
    cleaned = _clean_text(raw)
    return cleaned[:MAX_SUMMARY_LEN]


# ── Single query fetch ────────────────────────────────────────────────────────

async def _fetch_query(
    session: aiohttp.ClientSession,
    query: str,
    semaphore: asyncio.Semaphore,
    max_age_hours: int,
) -> list[dict]:
    days = max(1, max_age_hours // 24)
    after_date = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).strftime("%Y-%m-%d")
    restricted = f"{query} when:{days}d after:{after_date}"
    encoded = urllib.parse.quote(restricted)
    url = (
        f"https://news.google.com/rss/search"
        f"?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(
                    url,
                    headers=_get_headers(),
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        break
                    if resp.status in [429, 503]:
                        wait = RETRY_DELAY * (2 ** attempt)
                        logger.warning(
                            f"HTTP {resp.status} for '{query}'. "
                            f"Retrying in {wait}s... (attempt {attempt + 1}/{MAX_RETRIES})"
                        )
                        await asyncio.sleep(wait)
                        continue
                    logger.error(f"HTTP {resp.status} for query: '{query}'")
                    return []
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    logger.error(f"Fetch failed for '{query}' after {MAX_RETRIES} attempts: {e}")
                    return []
                await asyncio.sleep(RETRY_DELAY)
        else:
            return []

    feed    = feedparser.parse(content)
    entries = []

    for entry in feed.entries[:MAX_ARTICLES_PER_QUERY]:
        raw_title = _clean_text(getattr(entry, "title", "") or "")
        summary   = _extract_summary(entry)

        source_match = re.search(r"\s*[-–]\s*([A-Z][A-Za-z0-9 &.,']{2,35})$", raw_title)
        title  = raw_title[:source_match.start()].strip() if source_match else raw_title
        source = source_match.group(1).strip() if source_match else ""

        pub_dt    = _get_published_dt(entry)
        hours_old = (
            max(0, (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600)
            if pub_dt != _DT_MIN else 9999
        )

        entries.append({
            "title":     title,
            "source":    source,
            "summary":   summary,
            "url":       getattr(entry, "link", "") or "",
            "age":       _human_age(pub_dt),
            "age_h":     round(hours_old, 2),
            "published": (
                pub_dt.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")
                if pub_dt != _DT_MIN else "Unknown"
            ),
        })

    logger.debug(f"Query '{query}' → {len(entries)} articles")
    return entries


# ── Deduplication ─────────────────────────────────────────────────────────────

def _deduplicate(articles: list[dict]) -> list[dict]:
    seen_urls:   set[str]   = set()
    seen_titles: list[str]  = []
    unique:      list[dict] = []

    for art in articles:
        if art["url"] and art["url"] in seen_urls:
            continue
        if any(
            fuzz.token_set_ratio(art["title"], t) >= DEDUP_SIMILARITY
            for t in seen_titles
        ):
            continue
        if art["url"]:
            seen_urls.add(art["url"])
        seen_titles.append(art["title"])
        unique.append(art)

    return unique


# ── Output ────────────────────────────────────────────────────────────────────

def _save_output(articles: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at_ist": datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S%z"),
        "total_articles": len(articles),
        "articles":       articles,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved {len(articles)} articles → {OUTPUT_FILE}")


# ── Main tool function ────────────────────────────────────────────────────────

async def fetch_broad_market_rss(max_age_hours: int = 6) -> list[dict]:
    logger.info("=" * 60)
    logger.info("Starting broad market RSS sweep")
    logger.info(f"  Total queries:   {len(ALL_QUERIES)}")
    logger.info(f"  Sweepers:        {len(_BROAD_SWEEPERS)}")
    logger.info(f"  Sector x Event:  {len(_SECTOR_EVENT_QUERIES)}")
    logger.info(f"  High signal:     {len(_HIGH_SIGNAL)}")
    logger.info(f"  Max per query:   {MAX_ARTICLES_PER_QUERY}")
    logger.info(f"  Max age:         {max_age_hours}h")
    logger.info(f"  Concurrency:     {BATCH_CONCURRENCY}")
    logger.info("=" * 60)

    semaphore    = asyncio.Semaphore(BATCH_CONCURRENCY)
    all_articles: list[dict] = []

    async with aiohttp.ClientSession(trust_env=True) as session:
        tasks = [
            _fetch_query(session, query, semaphore, max_age_hours)
            for query in ALL_QUERIES
        ]
        results = await asyncio.gather(*tasks)

        for i, batch in enumerate(results):
            if i > 0 and i % BATCH_CONCURRENCY == 0:
                await asyncio.sleep(STAGGER_DELAY)
            all_articles.extend(batch)

    logger.info(f"Fetch complete    — {len(all_articles)} raw articles")

    all_articles.sort(key=lambda x: x["age_h"])

    no_timestamp = sum(1 for a in all_articles if a["age_h"] == 9999)
    genuinely_old = sum(
        1 for a in all_articles
        if a["age_h"] != 9999 and a["age_h"] > max_age_hours
    )
    logger.info(
        f"Timestamp stats   — {no_timestamp} unparseable, "
        f"{genuinely_old} genuinely older than {max_age_hours}h"
    )

    filtered = [a for a in all_articles if a["age_h"] <= max_age_hours]
    logger.info(f"Age filter        — {len(all_articles)} → {len(filtered)} (within {max_age_hours}h)")

    unique = _deduplicate(filtered)
    logger.info(f"Dedup             — {len(filtered)} → {len(unique)} unique articles")

    _save_output(unique)

    logger.info("=" * 60)
    return unique
