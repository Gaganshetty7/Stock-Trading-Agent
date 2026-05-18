"""
browser_summarizer.py
=====================

Ultra-fast pooled browser summarizer.

Architecture:
- 4 shared Chromium browsers
- 10 tabs each
- 40 concurrent pages
- Massive speedup
- Lower RAM
- Better stability
"""

import asyncio
import re

from playwright.async_api import async_playwright


# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------

BROWSER_INSTANCES = 4
TABS_PER_BROWSER = 10

TOTAL_CONCURRENT = (
    BROWSER_INSTANCES * TABS_PER_BROWSER
)


# -------------------------------------------------------------------
# CLEANERS
# -------------------------------------------------------------------

def clean_text(text: str) -> str:

    if not text:
        return ""

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# -------------------------------------------------------------------
# EXTRACTION
# -------------------------------------------------------------------

async def extract_article_text(page):

    selectors = [

        "article",
        ".article-content",
        ".post-content",
        ".entry-content",
        ".story-content",
        ".content",
        "main",
        ".main-content",
        "#main-content",
        "body",
    ]

    best = ""

    for sel in selectors:

        try:

            texts = await page.locator(
                sel
            ).all_inner_texts()

            joined = clean_text(
                " ".join(texts)
            )

            if len(joined) > len(best):
                best = joined

        except:
            pass

    return best


# -------------------------------------------------------------------
# SUMMARY
# -------------------------------------------------------------------

def build_summary(text: str):

    text = clean_text(text)

    if not text:
        return ""

    sentences = re.split(
        r"(?<=[.!?])\s+",
        text
    )

    selected = []

    total = 0

    for s in sentences:

        s = s.strip()

        if len(s) < 40:
            continue

        selected.append(s)

        total += len(s)

        if total > 800:
            break

    return clean_text(
        " ".join(selected)
    )


# -------------------------------------------------------------------
# WORKER
# -------------------------------------------------------------------

async def worker(
    browser,
    queue,
    results,
    timeout_ms
):

    while True:

        article = await queue.get()

        if article is None:
            queue.task_done()
            break

        url = article.get("link", "")

        context = None
        page = None

        try:
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            page = await context.new_page()

            await page.goto(
                url,
                wait_until="networkidle",
                timeout=30000
            )

            final_url = page.url

            text = await extract_article_text(
                page
            )

            summary = build_summary(text)

            if not summary:

                summary = article.get(
                    "summary",
                    article.get(
                        "title",
                        ""
                    )
                )

                intelligence_type = (
                    "FALLBACK"
                )

            else:

                intelligence_type = (
                    "DEEP_BROWSER"
                )

            results.append({
                **article,
                "summary": summary,
                "resolved_url": final_url,
                "intelligence_type": intelligence_type,
                "content_fetched": True if intelligence_type == "DEEP_BROWSER" else False
            })
        except:
            results.append({
                **article,
                "summary": article.get("summary", article.get("title", "")),
                "resolved_url": url,
                "intelligence_type": "FALLBACK",
                "content_fetched": False
            })
        finally:
            try:
                if page:
                    await page.close()
                if context:
                    await context.close()
            except:
                pass

            queue.task_done()


# -------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------

def batch_summarize(
    articles,
    max_workers=40,
    timeout_ms=6000
):
    return asyncio.run(async_batch_summarize(articles, max_workers, timeout_ms))

async def async_batch_summarize(
    articles,
    max_workers=40,
    timeout_ms=6000
):

    results = []

    queue = asyncio.Queue()

    for article in articles:
        await queue.put(article)

    async with async_playwright() as p:

        browsers = []

        # Target ~10 tabs per browser for stability/RAM balance
        tabs_per_browser = min(max_workers, 10)
        browser_instances = (max_workers + tabs_per_browser - 1) // tabs_per_browser

        for _ in range(browser_instances):

            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--no-sandbox",
                ]
            )

            browsers.append(browser)

        workers = []

        for browser in browsers:

            for _ in range(tabs_per_browser):

                workers.append(

                    asyncio.create_task(

                        worker(
                            browser,
                            queue,
                            results,
                            timeout_ms
                        )
                    )
                )

        await queue.join()

        for _ in workers:
            await queue.put(None)

        await asyncio.gather(*workers)

        for browser in browsers:

            try:
                await browser.close()
            except:
                pass

    return results
