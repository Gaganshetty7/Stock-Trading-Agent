import asyncio
import json
import re
import time
from datetime import timezone

from dotenv import load_dotenv
from google import genai
from google.genai import types

from ..api_quota_tracker.quota_tracker import log_api_usage
from ..config.settings import (
    GEMINI_RANKER_API_KEY,
    RANKING_BACKOFF_BASE,
    RANKING_MAX_RETRIES,
    RANKING_MODEL,
    RANKING_TIMEOUT,
)
from ..token_tracker import extract_context_usage, log_token_usage
from ..utils.json_utils import parse_json_from_text
from ..utils.logger import logger
from .prompts import RANK_PROMPT

load_dotenv()

CLIENT = genai.Client(api_key=GEMINI_RANKER_API_KEY)

# Rolling rate limiter for outbound LLM requests to avoid burst throttling.
# Keeps timestamps of recent requests and only sleeps when the recent
# window already contains RATE_LIMIT requests.
request_times: list[float] = []
request_lock = asyncio.Lock()
RATE_LIMIT = 14
WINDOW_SECONDS = 60


async def call_llm(
    prompt: str,
    metrics,
) -> str | None:

    attempt = 0

    while attempt <= RANKING_MAX_RETRIES:
        try:
            # Rolling rate limiter: prune old timestamps and sleep only when
            # we are about to exceed RATE_LIMIT requests within WINDOW_SECONDS.
            async with request_lock:
                now = time.time()
                # keep only timestamps within the window
                request_times[:] = [t for t in request_times if now - t < WINDOW_SECONDS]
                if len(request_times) >= RATE_LIMIT:
                    sleep_time = WINDOW_SECONDS - (now - request_times[0])
                    if sleep_time > 0:
                        logger.debug(f"[RATE LIMIT] Reached {RATE_LIMIT} in {WINDOW_SECONDS}s — sleeping {sleep_time:.2f}s")
                        await asyncio.sleep(sleep_time)
                # record this request timestamp (we'll append again right before call to be conservative)
                request_times.append(time.time())

            start = time.time()
            response = await asyncio.wait_for(
                CLIENT.aio.models.generate_content(
                    model=RANKING_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                ),
                timeout=RANKING_TIMEOUT,
            )

            usage = getattr(response, "usage_metadata", None)
            if usage:
                stats = extract_context_usage(RANKING_MODEL, usage)
                log_token_usage(
                    model=RANKING_MODEL,
                    prompt_tokens=stats["input_tokens"],
                    completion_tokens=stats["output_tokens"],
                    thought_tokens=stats.get("thought_tokens", 0),
                    total_tokens=stats["total_tokens"],
                    context_limit=stats["context_limit"],
                )

                metrics.total_input_tokens += stats.get("input_tokens", 0) or 0
                metrics.total_output_tokens += stats.get("output_tokens", 0) or 0
                metrics.total_tokens += stats.get("total_tokens", 0) or 0

            latency = time.time() - start
            metrics.latencies.append(latency)
            metrics.request_timestamps.append(time.time())

            log_api_usage(GEMINI_RANKER_API_KEY, RANKING_MODEL, "SUCCESS")
            metrics.api_calls_made += 1
            return response.text

        except Exception as e:
            metrics.api_calls_made += 1
            err_str = str(e)

            if any(x in err_str for x in ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE"]):
                log_api_usage(GEMINI_RANKER_API_KEY, RANKING_MODEL, "REJECTED_429_OR_503")

                if attempt < RANKING_MAX_RETRIES:
                    attempt += 1
                    backoff = RANKING_BACKOFF_BASE * (2 ** (attempt - 1))
                    logger.debug(f"[API RETRY] Waiting {backoff}s...")
                    await asyncio.sleep(backoff)
                    continue
                else:
                    logger.error("[API ERROR] Max retries exhausted")
                    return None

            if "403" in err_str or "PERMISSION_DENIED" in err_str:
                logger.error("[FATAL] API key invalid/revoked")
                return None

            logger.error(f"[LLM ERROR] {e}")
            return None
    return None


async def run_batch(
    batch_tickers: list[str],
    batch_index: int,
    mapped: dict,
    metrics,
) -> tuple[object | None, str]:
    """Run a single batch: build payload, call LLM, parse and validate response."""
    import time as _time
    from datetime import datetime as _datetime
    from ..config.schemas import BatchResponse

    batch_start = _time.time()
    batch_started_at = _datetime.fromtimestamp(batch_start, timezone.utc).isoformat()
    logger.debug(f"[BATCH {batch_index+1}] Starting")

    llm_payload = []
    article_reference = []
    for ticker in batch_tickers:
        insights = mapped.get(ticker, {}).get("company_insights", [])
        for article in insights:
            if not isinstance(article, dict):
                logger.debug(
                    f"[BATCH {batch_index+1}] article type={type(article)} value={article}"
                )

            published = article.get("published_date") or article.get("published")
            age = article.get("age", "stale")
            title = article.get("title", "")
            url = article.get("url") or article.get("link") or None

            article_reference.append({
                "ticker": ticker,
                "title": title,
                "published": published or "",
                "age": age,
                "url": url,
            })

            llm_payload.append({
                "ticker": ticker,
                "title": title,
                "published": published if published else "N/A",
                "age": age,
            })

    if not llm_payload:
        return None, "empty"

    prompt = RANK_PROMPT.replace(
        "{current_time}",
        _datetime.now(timezone.utc).strftime("%I:%M %p UTC"),
    ).replace(
        "{payload}",
        json.dumps(llm_payload, indent=1),
    )

    try:
        initial_latency_count = len(metrics.latencies)
        raw_response = await call_llm(prompt, metrics)
        llm_latency = 0.0
        if len(metrics.latencies) > initial_latency_count:
            llm_latency = metrics.latencies[-1]

        if not raw_response:
            metrics.batch_details.append({
                "batch_id": batch_index + 1,
                "companies_in_batch": len(batch_tickers),
                "articles_in_batch": len(llm_payload),
                "llm_latency_seconds": round(llm_latency, 2),
                "status": "llm_empty",
                "stagger_delay_applied": 0.0,
                "started_at": batch_started_at,
                "finished_at": _datetime.now(timezone.utc).isoformat(),
            })
            return None, "llm_empty"

        parsed = parse_json_from_text(raw_response)
        if not parsed:
            metrics.parse_failures += 1
            logger.error(
                f"[PARSE FAIL] Batch {batch_index+1}\n"
                f"RAW RESPONSE:\n{(raw_response or '')[:3000]}"
            )
            metrics.batch_details.append({
                "batch_id": batch_index + 1,
                "companies_in_batch": len(batch_tickers),
                "articles_in_batch": len(llm_payload),
                "llm_latency_seconds": round(llm_latency, 2),
                "status": "parse_fail",
                "stagger_delay_applied": 0.0,
                "started_at": batch_started_at,
                "finished_at": _datetime.now(timezone.utc).isoformat(),
            })
            return None, "parse_fail"

        # Normalize empty strings to None so Pydantic does not preserve blank URLs.
        if "results" in parsed and isinstance(parsed["results"], list):
            for art in parsed["results"]:
                if "url" in art and isinstance(art["url"], str) and not art["url"].strip():
                    art["url"] = None
                if "published" in art and isinstance(art["published"], str) and not art["published"].strip():
                    art["published"] = None

        # Rescaling Gate: LLM sometimes uses 0-10 instead of 0-1
        if "results" in parsed and isinstance(parsed["results"], list):
            for art in parsed["results"]:
                for key in ["confidence", "impact_score"]:
                    if key in art and isinstance(art[key], (int, float)):
                        val = float(art[key])
                        if val > 1.0:
                            art[key] = round(val / 10.0, 2)
                        else:
                            art[key] = round(val, 2)

        validated = BatchResponse(**parsed)

        def normalize_title(raw: str) -> str:
            text = (raw or "").strip()
            for sep in [" - ", " – ", " | "]:
                if sep in text:
                    text = text.split(sep)[0].strip()
            text = text.lower()
            text = re.sub(r"[^\w\s]", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text

        def titles_match(scored: str, original: str) -> bool:
            scored_norm = normalize_title(scored)
            original_norm = normalize_title(original)
            if not scored_norm or not original_norm:
                return False
            if scored_norm == original_norm:
                return True
            if original_norm.startswith(scored_norm):
                return True
            if scored_norm in original_norm:
                return True
            if original_norm in scored_norm:
                return True
            scored_tokens = set(scored_norm.split())
            original_tokens = set(original_norm.split())
            if scored_tokens and original_tokens:
                overlap = scored_tokens.intersection(original_tokens)
                if len(overlap) >= max(1, int(len(scored_tokens) * 0.7)):
                    return True
            return False

        # Reattach original metadata (url/published) from the source article payload.
        ticker_reference_index = {}
        for ref in article_reference:
            ticker_reference_index.setdefault(ref["ticker"], []).append(ref)

        for scored_article in validated.results:
            if not getattr(scored_article, "url", None):
                matched_ref = None
                for ref in ticker_reference_index.get(scored_article.ticker, []):
                    if ref["url"] and titles_match(scored_article.title, ref["title"]):
                        matched_ref = ref
                        break

                if not matched_ref:
                    refs = [ref for ref in ticker_reference_index.get(scored_article.ticker, []) if ref["url"]]
                    if len(refs) == 1:
                        matched_ref = refs[0]

                if matched_ref:
                    scored_article.url = matched_ref["url"]
                    if not scored_article.published or scored_article.published == "N/A":
                        scored_article.published = matched_ref["published"]

        metrics.success_count += 1
        metrics.batch_details.append({
            "batch_id": batch_index + 1,
            "companies_in_batch": len(batch_tickers),
            "articles_in_batch": len(llm_payload),
            "llm_latency_seconds": round(llm_latency, 2),
            "status": "success",
            "stagger_delay_applied": 0.0,
            "started_at": batch_started_at,
            "finished_at": _datetime.now(timezone.utc).isoformat(),
        })

        batch_time = _time.time() - batch_start
        logger.debug(f"[BATCH {batch_index+1}] Success in {batch_time:.2f}s")
        return validated, "success"

    except Exception as e:
        metrics.failure_count += 1
        logger.error(f"[BATCH {batch_index+1}] ERROR: {e}")
        metrics.batch_details.append({
            "batch_id": batch_index + 1,
            "companies_in_batch": len(batch_tickers),
            "articles_in_batch": len(llm_payload),
            "llm_latency_seconds": 0.0,
            "status": "error",
            "stagger_delay_applied": 0.0,
            "started_at": batch_started_at,
            "finished_at": _datetime.now(timezone.utc).isoformat(),
        })
        return None, "error"
