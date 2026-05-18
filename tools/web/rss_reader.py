import asyncio
import random
import urllib.parse
import re
import html
import time
from datetime import datetime, timezone

import aiohttp
import feedparser
import pytz

from core.logger import get_logger

logger = get_logger("rss_reader")

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

REQUEST_TIMEOUT = 8
MAX_SUMMARY_LEN = 250
MAX_ARTICLES_PER_QUERY = 10
BATCH_SIZE = 100
BATCH_CONCURRENCY = 8
STAGGER_DELAY = 0.15
MAX_RETRIES = 2
RETRY_DELAY = 1.5
MAX_BACKOFF_SECONDS = 12

LAST_FETCH_DIAGNOSTICS: dict[str, int | float] = {}

_NOISE_KEYWORDS = [
    "cricket", "ipl match", "bollywood", "celebrity gossip", "recipe",
    "fashion week", "horoscope", "astrology forecast", "travel guide",
    "fitness tips", "beauty tips", "movie review", "film review",
    "web series review", "ott release", "wedding", "relationship advice",
    "diet plan", "health tips",
]

_MARKET_KEYWORDS = [
    "nifty", "sensex", "nse", "bse", "stock", "share", "equity", "rbi",
    "sebi", "ipo", "fii", "dii", "rupee", "inr", "earning", "result",
    "revenue", "profit", "loss", "quarter", "sector", "index", "fund",
    "futures", "options", "commodity", "crude", "gold", "silver", "dividend",
    "buyback", "bonus", "merger", "acquisition", "demerger", "listing",
    "analyst", "target price", "upgrade", "downgrade", "bulk deal",
    "block deal", "circuit", "derivative", "market cap", "valuation",
    "asm", "f&o", "mou", "contract", "order", "allot", "disclosure",
    "guidance", "agreement", "partnership", "tender", "bid", "capacity",
    "expansion", "plant", "unit", "sanction", "approval", "nod",
]


# ── Text helpers ──────────────────────────────────────────────────────────────

def clean_text(raw: str) -> str:
    text = re.sub(r"<.*?>", "", raw)
    text = html.unescape(text)
    return " ".join(text.split()).strip()


def normalize(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", s).lower()


def normalize_loose(s: str) -> str:
    s = s.lower()
    s = re.sub(r"(limited|ltd|inc|corporation|corp|plc|company)", "", s)
    return re.sub(r"[^a-z0-9]", "", s).strip()


def normalize_event_title(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\b(q[1-4]|fy\d{2}|fy\d{4}|today|tomorrow|live|update)\b", "", s)
    s = re.sub(r"\d+", "", s)
    s = re.sub(r"[^a-z ]", " ", s)
    return " ".join(s.split())


def get_published_dt(entry) -> datetime:
    pp = getattr(entry, "published_parsed", None)
    if pp:
        try:
            return datetime(*pp[:6])
        except Exception:
            pass
    return datetime.min


def human_age(pub_dt: datetime) -> str:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if pub_dt == datetime.min:
        return "unknown"
    secs = (now - pub_dt).total_seconds()
    if secs < 3600:
        return f"{int(secs / 60)}m ago"
    if secs < 86400:
        return f"{int(secs / 3600)}h ago"
    return f"{int(secs / 86400)}d ago"


def extract_summary(entry, raw_title: str) -> str:
    raw = getattr(entry, "summary", "") or ""
    cleaned = clean_text(raw)
    cleaned = re.sub(r"\s*[-–]\s*[A-Z][A-Za-z0-9 &.,']{2,35}$", "", cleaned).strip()
    if normalize(cleaned).startswith(normalize(raw_title)[:40]):
        tail = cleaned[len(raw_title):].strip(" -:|/–")
        if len(tail) >= 30:
            return tail[:MAX_SUMMARY_LEN]
        cleaned = ""
    if len(cleaned) >= 30:
        return cleaned[:MAX_SUMMARY_LEN]
    return re.sub(r"\s*[-–|]\s*[A-Z][A-Za-z0-9 &.,']{2,35}$", "", raw_title).strip()[:MAX_SUMMARY_LEN]


def _derive_aliases(stock: str) -> set[str]:
    aliases: set[str] = set()
    aliases.add(normalize(stock))
    stripped = re.sub(
        r"\b(limited|ltd|ltd\.|inc|inc\.|corp|corporation|plc|company|india)\b",
        "",
        stock,
        flags=re.IGNORECASE,
    ).strip()
    aliases.add(normalize(stripped))
    if "(" in stock and ")" in stock:
        paren = re.findall(r"\((.*?)\)", stock)
        for p in paren:
            aliases.add(normalize(p))
    for token in re.split(r"[\s&\-/.,]+", stripped):
        t = normalize(token)
        if len(t) >= 4:
            aliases.add(t)
    aliases.discard("")
    return aliases


def is_noise(title: str, summary: str, stock: str, aliases: set[str] | None = None) -> bool:
    text = normalize(title) + " " + normalize(summary)
    aliases = aliases or _derive_aliases(stock)
    if any(kw in text for kw in _NOISE_KEYWORDS):
        return True
    if any(a in text for a in aliases):
        return False
    if any(kw in text for kw in _MARKET_KEYWORDS):
        return False
    return True


def get_headers() -> dict:
    return {**BASE_HEADERS, "User-Agent": random.choice(USER_AGENTS)}


# ── Query builder ─────────────────────────────────────────────────────────────

def build_queries(stocks: list[str]) -> list[tuple[str, str]]:
    trigger_keywords = (
        "earnings OR results OR profit OR loss OR order OR contract OR deal OR "
        "acquisition OR merger OR dividend OR buyback OR bonus OR "
        "NSE OR BSE OR share OR stock"
    )
    queries = []
    for stock in stocks:
        short_name = re.sub(
            r"(Limited|LTD|LTD\.|Inc\.|Corp\.|Corporation|PLC|Company)",
            "", stock, flags=re.IGNORECASE
        ).strip()
        company_query = f'"{short_name}" ({trigger_keywords})'
        company_query_loose = f'{short_name} ({trigger_keywords})'
        corporate_query = (
            f'"{short_name}" (announcement OR filing OR guidance OR approval OR '
            "regulatory OR tender OR partnership OR expansion)"
        )
        queries.append((stock, company_query))
        queries.append((stock, company_query_loose))
        queries.append((stock, corporate_query))
    return queries


# ── Single fetch ──────────────────────────────────────────────────────────────

async def fetch_single(
    session: aiohttp.ClientSession,
    stock: str,
    query: str,
    semaphore: asyncio.Semaphore,
) -> tuple[list[dict], dict[str, int]]:
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"

    aliases = _derive_aliases(stock)
    metrics = {
        "requests_total": 0,
        "status_200": 0,
        "status_429": 0,
        "status_503": 0,
        "status_other": 0,
        "exceptions": 0,
        "retries": 0,
    }

    async with semaphore:
        for attempt in range(MAX_RETRIES + 1):
            metrics["requests_total"] += 1
            try:
                async with session.get(
                    url,
                    headers=get_headers(),
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ) as resp:
                    if resp.status == 200:
                        metrics["status_200"] += 1
                        content = await resp.read()
                        break

                    if resp.status in [429, 503]:
                        if resp.status == 429:
                            metrics["status_429"] += 1
                        else:
                            metrics["status_503"] += 1
                        if attempt >= MAX_RETRIES:
                            return [], metrics
                        metrics["retries"] += 1
                        wait = min(RETRY_DELAY * (2 ** attempt) + random.uniform(0.1, 0.9), MAX_BACKOFF_SECONDS)
                        logger.warning(f"HTTP {resp.status} for {query}. Retrying in {wait:.2f}s... (Attempt {attempt+1}/{MAX_RETRIES + 1})")
                        await asyncio.sleep(wait)
                        continue

                    metrics["status_other"] += 1
                    logger.error(f"HTTP {resp.status} for query: {query}")
                    return [], metrics
            except Exception as e:
                metrics["exceptions"] += 1
                if attempt >= MAX_RETRIES:
                    logger.error(f"Fetch failed for {query} after {MAX_RETRIES + 1} attempts: {e}")
                    return [], metrics
                metrics["retries"] += 1
                wait = min(RETRY_DELAY * (2 ** attempt) + random.uniform(0.1, 0.9), MAX_BACKOFF_SECONDS)
                await asyncio.sleep(wait)
        else:
            return [], metrics

    feed = feedparser.parse(content)
    entries = []

    for entry in feed.entries[:MAX_ARTICLES_PER_QUERY]:
        raw_title = clean_text(getattr(entry, "title", "") or "")
        summary = extract_summary(entry, raw_title)

        if is_noise(raw_title, summary, stock, aliases=aliases):
            continue

        source_match = re.search(r"\s*[-–]\s*([A-Z][A-Za-z0-9 &.,']{2,35})$", raw_title)
        title = raw_title[:source_match.start()].strip() if source_match else raw_title
        source = source_match.group(1).strip() if source_match else ""

        pub_dt = get_published_dt(entry)
        hours_old = (
            (datetime.now(timezone.utc).replace(tzinfo=None) - pub_dt).total_seconds() / 3600
            if pub_dt != datetime.min else 9999
        )

        entries.append({
            "title": title,
            "source": source,
            "summary": summary,
            "link": getattr(entry, "link", "") or "",
            "age": human_age(pub_dt),
            "age_h": round(hours_old, 2),
            "target_stock": stock,
            "published": (
                pub_dt.replace(tzinfo=timezone.utc)
                .astimezone(IST)
                .strftime("%d %b %Y, %I:%M %p IST")
                if pub_dt != datetime.min else "Unknown"
            ),
        })

    return entries, metrics


# ── Batch fetcher ─────────────────────────────────────────────────────────────

async def fetch_all(queries: list[tuple[str, str]]) -> list[dict]:
    all_articles = []
    semaphore = asyncio.Semaphore(BATCH_CONCURRENCY)
    started_at = time.perf_counter()
    diagnostics = {
        "queries_total": len(queries),
        "requests_total": 0,
        "status_200": 0,
        "status_429": 0,
        "status_503": 0,
        "status_other": 0,
        "exceptions": 0,
        "retries": 0,
    }

    async with aiohttp.ClientSession(trust_env=True) as session:
        tasks = []
        for i, (stock, query) in enumerate(queries):
            tasks.append(fetch_single(session, stock, query, semaphore))
            if i > 0 and i % BATCH_CONCURRENCY == 0:
                await asyncio.sleep(STAGGER_DELAY)

        logger.info(f"Launched {len(queries)} tasks with concurrency {BATCH_CONCURRENCY} and stagger {STAGGER_DELAY}s")
        results = await asyncio.gather(*tasks)

        for articles, metrics in results:
            all_articles.extend(articles)
            for key in diagnostics:
                if key == "queries_total":
                    continue
                diagnostics[key] += metrics.get(key, 0)

    elapsed = max(time.perf_counter() - started_at, 0.001)
    diagnostics["elapsed_seconds"] = round(elapsed, 3)
    diagnostics["requests_per_second"] = round(diagnostics["requests_total"] / elapsed, 2)
    diagnostics["articles_raw"] = len(all_articles)
    global LAST_FETCH_DIAGNOSTICS
    LAST_FETCH_DIAGNOSTICS = diagnostics
    logger.info(
        "Fetch diagnostics: "
        f"req={diagnostics['requests_total']} ok={diagnostics['status_200']} "
        f"429={diagnostics['status_429']} 503={diagnostics['status_503']} "
        f"retry={diagnostics['retries']} rps={diagnostics['requests_per_second']}"
    )

    return all_articles


# ── Deduplication ─────────────────────────────────────────────────────────────

def deduplicate(articles: list[dict]) -> list[dict]:
    seen_fp = set()
    seen_urls = set()
    unique = []
    for art in articles:
        url = art.get("link", "")
        if url and url in seen_urls:
            continue

        fp = (
            f"{normalize_loose(art['target_stock'])}_"
            f"{normalize_event_title(art['title'])[:120]}"
        )
        if fp in seen_fp:
            continue

        seen_fp.add(fp)
        if url:
            seen_urls.add(url)
        unique.append(art)
    return unique


# ── Main tool function ────────────────────────────────────────────────────────

async def fetch_rss(stocks: list[str], max_age_hours: int = 48) -> list[dict]:
    queries = build_queries(stocks)
    logger.info(f"Starting fetch: {len(queries)} queries for {len(stocks)} stocks")

    all_articles = await fetch_all(queries)
    all_articles.sort(key=lambda x: x["age_h"])

    unique = deduplicate(all_articles)
    filtered = [a for a in unique if a["age_h"] <= max_age_hours]

    logger.info(f"Done: {len(all_articles)} raw → {len(unique)} unique → {len(filtered)} final")
    return filtered
