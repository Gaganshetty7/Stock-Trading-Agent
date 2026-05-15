import asyncio
import urllib.parse
import re
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import aiohttp
import feedparser

from core.logger import get_logger
from .queries import FINAL_MASTER_QUERY_LIST
from .text_helpers import (
    IST, _DT_MIN, clean_text, get_headers, 
    get_published_dt, human_age, extract_summary,
    MAX_SUMMARY_LEN
)
import os
import glob
from .deduplication import deduplicate
from .news_mapper import map_news_to_tickers

logger = get_logger("broad_market_rss_fetcher")

# Configuration
REQUEST_TIMEOUT        = 8
MAX_ARTICLES_PER_QUERY = 100
BATCH_CONCURRENCY      = 8
STAGGER_DELAY          = 0.25
MAX_RETRIES            = 1
RETRY_DELAY            = 10

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
                    headers=get_headers(),
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
        raw_title = clean_text(getattr(entry, "title", "") or "")
        summary   = extract_summary(entry)

        source_match = re.search(r"\s*[-–]\s*([A-Z][A-Za-z0-9 &.,']{2,35})$", raw_title)
        title  = raw_title[:source_match.start()].strip() if source_match else raw_title
        source = source_match.group(1).strip() if source_match else ""

        pub_dt    = get_published_dt(entry)
        hours_old = (
            max(0, (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600)
            if pub_dt != _DT_MIN else 9999
        )

        entries.append({
            "title":     title,
            "source":    source,
            "summary":   summary,
            "url":       getattr(entry, "link", "") or "",
            "age":       human_age(pub_dt),
            "age_h":     round(hours_old, 2),
            "published": (
                pub_dt.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")
                if pub_dt != _DT_MIN else "Unknown"
            ),
        })

    logger.debug(f"Query '{query}' → {len(entries)} articles")
    return entries

def _cleanup_legacy_files(outputs_dir: Path) -> None:
    for f in outputs_dir.glob("broad_market_test_report_*.json"):
        try:
            f.unlink()
            logger.info(f"Deleted legacy report: {f.name}")
        except Exception as e:
            logger.warning(f"Failed to delete {f.name}: {e}")
            
    legacy_mapped = outputs_dir / "mapped_news.json"
    if legacy_mapped.exists():
        try:
            legacy_mapped.unlink()
            logger.info(f"Deleted legacy mapped_news: {legacy_mapped.name}")
        except Exception as e:
            logger.warning(f"Failed to delete {legacy_mapped.name}: {e}")

async def fetch_broad_market_rss(max_age_hours: int = 6) -> dict:
    logger.info("=" * 60)
    logger.info("Starting broad market RSS sweep")
    logger.info(f"  Total queries:   {len(FINAL_MASTER_QUERY_LIST)}")
    logger.info(f"  Max per query:   {MAX_ARTICLES_PER_QUERY}")
    logger.info(f"  Max age:         {max_age_hours}h")
    logger.info(f"  Concurrency:     {BATCH_CONCURRENCY}")
    logger.info("=" * 60)

    semaphore    = asyncio.Semaphore(BATCH_CONCURRENCY)
    all_articles: list[dict] = []

    async with aiohttp.ClientSession(trust_env=True) as session:
        tasks = [
            _fetch_query(session, query, semaphore, max_age_hours)
            for query in FINAL_MASTER_QUERY_LIST
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

    unique = deduplicate(filtered)
    logger.info(f"Dedup             — {len(filtered)} → {len(unique)} unique articles")

    # Map to tickers
    alias_file = Path("resources/aliases/alias_lookup.json")
    if alias_file.exists():
        with open(alias_file, "r", encoding="utf-8") as f:
            alias_lookup = json.load(f)
    else:
        logger.warning(f"Alias lookup file not found at {alias_file}, returning empty mapping")
        alias_lookup = {}
        
    mapped_news_data = map_news_to_tickers(unique, alias_lookup)
    logger.info(f"Mapped to {len(mapped_news_data)} unique companies")
    
    timestamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
    outputs_dir = Path("outputs")
    outputs_dir.mkdir(parents=True, exist_ok=True)
    
    _cleanup_legacy_files(outputs_dir)
    
    payload = {
        "metadata": {
            "total_companies": len(mapped_news_data),
            "total_articles": len(unique),
            "generated_at": datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S%z")
        },
        "mapped_news": mapped_news_data
    }
    
    output_file = outputs_dir / f"mapped_news_{timestamp}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        
    logger.info(f"Saved mapped news → {output_file}")
    logger.info("=" * 60)
    return payload
