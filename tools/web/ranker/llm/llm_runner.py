import asyncio
import json
import time
import re
from datetime import datetime, timezone, timedelta

from core.llm import get_llm
from config.settings import NEWS_RANKER_API_KEY, NEWS_RANKER_LLM_PROVIDER
from ..config.settings import (
    NEWS_RANKER_MODEL,
    RANKING_TIMEOUT,
    RANKING_BACKOFF_BASE,
    RANKING_MAX_RETRIES,
)

from ..utils.json_parser import parse_json_from_text
from ..utils.logger import logger
from .prompts import RANK_PROMPT


# -----------------------------
# LLM INIT
# -----------------------------
LLM = get_llm(
    provider=NEWS_RANKER_LLM_PROVIDER,
    model=NEWS_RANKER_MODEL,
    temperature=0,
    api_key=NEWS_RANKER_API_KEY,
)


# -----------------------------
# RATE LIMIT STATE
# -----------------------------
request_times = []
request_lock = asyncio.Lock()
RATE_LIMIT = 14
WINDOW_SECONDS = 60


# -----------------------------
# RESPONSE NORMALIZER (FIX CORE ISSUE)
# -----------------------------
def extract_llm_text(response) -> str:
    """
    Normalizes different LLM response formats into a raw string.
    Fixes your current failure:
    [{'type': 'text', 'text': '...'}]
    """

    # Case 1: LangChain / Gemini structured output
    if isinstance(response, list):
        try:
            return response[0].get("text", "")
        except Exception:
            return str(response)

    # Case 2: Normal LangChain AIMessage
    if hasattr(response, "content"):
        return response.content or ""

    # Case 3: fallback
    return str(response)


# -----------------------------
# LLM CALL WITH RETRY + RATE LIMIT
# -----------------------------
async def call_llm(prompt: str, metrics) -> str | None:
    attempt = 0

    while attempt <= RANKING_MAX_RETRIES:
        try:
            async with request_lock:
                now = time.time()

                # clean old timestamps
                request_times[:] = [
                    t for t in request_times if now - t < WINDOW_SECONDS
                ]

                # rate limit sleep
                if len(request_times) >= RATE_LIMIT:
                    sleep_time = WINDOW_SECONDS - (now - request_times[0])
                    if sleep_time > 0:
                        logger.debug(
                            f"[RATE LIMIT] Sleeping {sleep_time:.2f}s"
                        )
                        await asyncio.sleep(sleep_time)

                request_times.append(time.time())

            start = time.time()

            response = await asyncio.wait_for(
                LLM.ainvoke(prompt),
                timeout=RANKING_TIMEOUT,
            )

            latency = time.time() - start
            metrics.latencies.append(latency)
            metrics.request_timestamps.append(time.time())
            metrics.api_calls_made += 1

            return extract_llm_text(response)

        except Exception as e:
            metrics.api_calls_made += 1
            err_type = e.__class__.__name__
            err_msg = str(e)
            
            # Shorten/clean up nested JSON errors if present
            if len(err_msg) > 200:
                import re
                message_match = re.search(r"['\"]message['\"]:\s*['\"]([^'\"]+)['\"]", err_msg)
                if message_match:
                    err_msg = message_match.group(1)
                else:
                    err_msg = f"{err_msg[:200]}..."
            
            err = f"{err_type}: {err_msg}" if err_msg else err_type

            # retryable errors
            if any(x in err for x in ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE"]):
                if attempt < RANKING_MAX_RETRIES:
                    attempt += 1
                    backoff = RANKING_BACKOFF_BASE * (2 ** (attempt - 1))

                    logger.debug(f"[RETRY] attempt={attempt}, sleep={backoff}s ({err})")
                    await asyncio.sleep(backoff)
                    continue

                logger.error(f"[LLM ERROR] Max retries exhausted. Last error: {err}")
                return None

            if "403" in err or "PERMISSION_DENIED" in err:
                logger.error(f"[FATAL] Invalid API key: {err}")
                return None

            logger.error(f"[LLM ERROR] {err}")
            return None

    return None


# -----------------------------
# BATCH RUNNER
# -----------------------------
async def run_batch(batch_tickers, batch_index, mapped, metrics):
    """
    Runs ranker batch safely with:
    - correct payload building
    - safe LLM response extraction
    - robust JSON parsing
    - metadata reattachment
    """

    from ..config.schemas import BatchResponse

    start_time = time.time()
    batch_started_at = datetime.now(timezone.utc).isoformat()

    logger.debug(f"[BATCH {batch_index+1}] Starting")

    llm_payload = []
    article_reference = []

    # -------------------------
    # BUILD INPUT PAYLOAD
    # -------------------------
    for ticker in batch_tickers:
        insights = mapped.get(ticker, {}).get("company_insights", [])

        for article in insights:
            title = article.get("title", "")
            published = article.get("published_date") or article.get("published")
            age = article.get("age", "stale")
            url = article.get("url") or article.get("link")

            article_reference.append({
                "ticker": ticker,
                "title": title,
                "published": published,
                "age": age,
                "url": url,
            })

            llm_payload.append({
                "ticker": ticker,
                "title": title,
                "published": published or "N/A",
                "age": age,
            })

    if not llm_payload:
        return None, "empty"

    # -------------------------
    # PROMPT BUILD
    # -------------------------
    prompt = RANK_PROMPT.replace(
        "{current_time}",
        datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%I:%M %p IST"),
    ).replace(
        "{payload}",
        json.dumps(llm_payload, indent=2),
    )

    try:
        initial_len = len(metrics.latencies)

        raw_response = await call_llm(prompt, metrics)

        llm_latency = 0.0
        if len(metrics.latencies) > initial_len:
            llm_latency = metrics.latencies[-1]

        if not raw_response:
            return None, "llm_empty"

        # -------------------------
        # FIX: if still structured garbage
        # -------------------------
        if isinstance(raw_response, list):
            raw_response = raw_response[0].get("text", "")

        # -------------------------
        # JSON PARSE
        # -------------------------
        parsed = parse_json_from_text(raw_response)

        if not parsed:
            metrics.parse_failures += 1
            logger.error(f"[PARSE FAIL]\n{raw_response[:2000]}")
            return None, "parse_fail"

        # -------------------------
        # NORMALIZE CLEANUP
        # -------------------------
        if isinstance(parsed.get("results"), list):
            for r in parsed["results"]:
                if isinstance(r.get("url"), str) and not r["url"].strip():
                    r["url"] = None

                for key in ["confidence", "impact_score"]:
                    if key in r and isinstance(r[key], (int, float)):
                        r[key] = round(min(float(r[key]), 1.0), 2)

        validated = BatchResponse(**parsed)

        # -------------------------
        # METRICS UPDATE
        # -------------------------
        metrics.success_count += 1
        metrics.batch_details.append({
            "batch_id": batch_index + 1,
            "companies_in_batch": len(batch_tickers),
            "articles_in_batch": len(llm_payload),
            "llm_latency_seconds": round(llm_latency, 2),
            "status": "success",
            "started_at": batch_started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })

        logger.debug(
            f"[BATCH {batch_index+1}] Success in {time.time() - start_time:.2f}s"
        )

        return validated, "success"

    except Exception as e:
        metrics.failure_count += 1
        logger.error(f"[BATCH ERROR] {e}")

        return None, "error"
