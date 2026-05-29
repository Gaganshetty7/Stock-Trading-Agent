import asyncio
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Literal
from dataclasses import dataclass, field
import pytz

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import ValidationError


from .api_quota_tracker.quota_tracker import log_api_usage, get_today_usage, log_quota_attempt
from .helpers.settings import (
    RANKING_MODEL,
    RANKING_BATCH_SIZE,

    RANKING_CONCURRENCY,
    RANKING_STAGGER_DELAY,
    RANKING_TIMEOUT,
    RANKING_MAX_RETRIES,
    RANKING_BACKOFF_BASE,
    MAX_TITLE_LEN,
    TOP_N_ARTICLES,
    MIN_CONFIDENCE,
    GEMINI_RANKER_API_KEY,

    MARKET_CLOSED_MULTIPLIER,
    STALE_DECAY_MULTIPLIER,
    STALE_THRESHOLD_MINS
)

# Modular ranker components
from .helpers.schemas import BatchResponse

from .helpers.utils import QuotaError, robust_json_parser, truncate, logger
from .helpers.market_helpers import is_market_open, parse_age_to_mins
from .helpers.prompts import RANK_PROMPT
from .helpers.metrics import PipelineMetrics
from .token_tracker import extract_context_usage
from .token_tracker import log_token_usage

from pathlib import Path


load_dotenv()

# ── Single Client (Protected Key) ─────────────────────────────────────────────
CLIENT = genai.Client(api_key=GEMINI_RANKER_API_KEY)



async def call_llm(prompt: str, metrics: PipelineMetrics) -> Optional[str]:
    """Makes the actual LLM call with exponential backoff for 429s."""


    model = RANKING_MODEL


    attempt = 0
    while attempt <= RANKING_MAX_RETRIES:
        try:
            start = time.time()
            response = await asyncio.wait_for(
                CLIENT.aio.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    ),
                ),
                timeout=RANKING_TIMEOUT,
            )

            usage = getattr(response, "usage_metadata", None)
            if usage:
                stats = extract_context_usage(model, usage)
                log_token_usage(
                    model=model,
                    prompt_tokens=stats["input_tokens"],
                    completion_tokens=stats["output_tokens"],
                    thought_tokens=stats.get("thought_tokens", 0),
                    total_tokens=stats["total_tokens"],
                    context_limit=stats["context_limit"],
                )
                metrics.total_input_tokens += stats["input_tokens"]
                metrics.total_output_tokens += stats["output_tokens"]
                metrics.total_tokens += stats["total_tokens"]


            latency = time.time() - start
            metrics.latencies.append(latency)
            metrics.request_timestamps.append(time.time())

            log_api_usage(GEMINI_RANKER_API_KEY, model, "SUCCESS")
            metrics.api_calls_made += 1
            return response.text

        except Exception as e:
            metrics.api_calls_made += 1
            err_str = str(e)

            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str or "UNAVAILABLE" in err_str:
                log_api_usage(GEMINI_RANKER_API_KEY, model, "REJECTED_429_OR_503")
                if attempt < RANKING_MAX_RETRIES:
                    attempt += 1
                    backoff = RANKING_BACKOFF_BASE * (2 ** (attempt - 1))
                    msg = f"  [API { '503' if '503' in err_str else '429' }] Retrying in {backoff}s... (Attempt {attempt}/{RANKING_MAX_RETRIES})"
                    print(msg)
                    logger.warning(msg)
                    await asyncio.sleep(backoff)
                    continue
                else:
                    msg = f"  [API Error] Model {model} exhausted or unavailable after {RANKING_MAX_RETRIES} retries."
                    print(msg)
                    logger.warning(msg)
                    return None

            if "403" in err_str or "PERMISSION_DENIED" in err_str:
                log_api_usage(GEMINI_RANKER_API_KEY, model, "REJECTED_403_KEY_REVOKED")
                print(f"  [FATAL] API Key revoked/leaked. Get a new key.")
                return None

            print(f"  [LLM Error] {e}")
            return None

    return None


async def rank_news_payload(payload: Dict) -> Dict:
    """Main entry point: Batches mapped news and extracts tradable signals."""
    metrics = PipelineMetrics()

    # Guard: agent may pass the observation as a JSON string
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return {"error": "rank_news_payload received an unparseable string payload"}

    if not isinstance(payload, dict):
        return {"error": f"rank_news_payload expected a dict, got {type(payload).__name__}"}

    mapped = payload.get("mapped_news", {})



    if not isinstance(mapped, dict):
        return {"error": f"mapped_news must be dict, got {type(mapped).__name__}"}

    all_tickers = list(mapped.keys())
    # Calculate total articles and sort tickers by news presence
    metrics.total_companies = len(all_tickers)
    tickers_with_news = []
    tickers_without_news = []
    
    for t in all_tickers:
        article_count = len(mapped[t].get("company_insights", []))
        metrics.total_articles_in += article_count
        if article_count > 0:
            tickers_with_news.append(t)
        else:
            tickers_without_news.append(t)
            
    # Sort for optimal batching (news-first)
    all_tickers = tickers_with_news + tickers_without_news

    # Batching logic
    batches = [all_tickers[i:i + RANKING_BATCH_SIZE] for i in range(0, len(all_tickers), RANKING_BATCH_SIZE)]

    final_output = {}

    async def run_batch(batch_tickers: List[str], i: int, data_source: Dict, m: PipelineMetrics):
        batch_start = time.time()
        # Format input for LLM
        truncated_payload = []
        for t in batch_tickers:
            company_data = data_source.get(t, {})
            insights = company_data.get("company_insights", [])
            
            for art in insights:  # Send all headlines, LLM will decide
                truncated_payload.append({
                    "ticker": t,
                    "title": truncate(art['title'], MAX_TITLE_LEN),
                    "published": art.get('published_date', 'N/A'),
                    "age": art.get('age', 'stale')
                })

        if not truncated_payload:
            return None, None, "skipped (no recent news)"

        prompt = RANK_PROMPT.format(
            current_time=datetime.now(timezone.utc).strftime("%I:%M %p UTC"),
            payload=json.dumps(truncated_payload, indent=1)
        )

        status = "unknown"
        try:
            raw_response = await call_llm(prompt, m)
            if not raw_response:
                status = "error (LLM empty)"
                return None, None, status
            
            clean_json = robust_json_parser(raw_response)
            if not clean_json:
                m.parse_failures += 1
                status = "parse_fail"
                return None, None, status

            validated = BatchResponse(**clean_json)
            m.success_count += 1
            status = "success"
            return raw_response, validated, status
            
        except QuotaError:
            m.quota_skipped += 1
            status = "quota_skipped"
            return None, None, status
        except Exception as e:
            m.failure_count += 1
            print(f"  [Batch {i+1} Error] {e}")
            status = f"error: {str(e)[:50]}"
            return None, None, status
        finally:
            batch_latency = time.time() - batch_start
            m.batch_details.append({
                "batch_id": i + 1,
                "companies_in_batch": len(batch_tickers),
                "articles_in_batch": len(truncated_payload),
                "llm_latency_seconds": round(batch_latency, 2),
                "status": status,
                "stagger_delay_applied": RANKING_STAGGER_DELAY,
                "started_at": datetime.fromtimestamp(batch_start).isoformat(),
                "finished_at": datetime.now().isoformat(),
            })

    # Sequential execution (Protected Key)
    msg_start = f"Starting Signal Extraction for {metrics.total_companies} companies..."
    logger.info(msg_start)
    
    msg_model = f"Model: {RANKING_MODEL} | Batch Size: {RANKING_BATCH_SIZE}"
    logger.info(msg_model)

    for i, batch_tickers in enumerate(batches):

        log_quota_attempt(RANKING_MODEL, "START")
        ts, validated, status = await run_batch(batch_tickers, i, mapped, metrics)

        # Print live quota status
        usage = get_today_usage()
        bal = usage.get("live_balance", {})
        rem = bal.get("remaining", "??")
        status_char = "success" if status == "success" else "FAILED"
        msg_batch = f"Batch {i+1} Status: {status_char} | Remaining Quota: {rem}"
        logger.info(msg_batch)

        if status == "success" and validated:
            market_open = is_market_open()
            for article in validated.results:
                tk = article.ticker
                
                # Apply multipliers (Market session & Freshness Decay)
                if not market_open:
                    article.confidence *= MARKET_CLOSED_MULTIPLIER
                
                age_mins = parse_age_to_mins(article.age)
                if age_mins > STALE_THRESHOLD_MINS:
                    article.confidence *= STALE_DECAY_MULTIPLIER
                
                # Round to exactly 2 decimal places
                article.confidence = round(article.confidence, 2)
                article.impact_score = round(article.impact_score, 2)

                # Final filtering
                if article.confidence >= MIN_CONFIDENCE and article.impact_score >= 0.4:
                    # RE-ASSOCIATE URL AND PUBLISHED
                    if tk in mapped and "company_insights" in mapped[tk]:
                        for original in mapped[tk]["company_insights"]:
                            clean_search = article.title.strip("…").strip()
                            if clean_search in original["title"]:
                                article.url = original.get("link")
                                article.published = original.get("published_date")
                                break

                    if tk not in final_output:
                        final_output[tk] = []
                    
                    if len(final_output[tk]) < TOP_N_ARTICLES:
                        final_output[tk].append(article.model_dump())
                        metrics.total_articles_out += 1
        elif status == "quota_skipped":
            # This status correctly tracks batches that failed even after retries
            metrics.quota_skipped += 1

        if i < len(batches) - 1:
            await asyncio.sleep(RANKING_STAGGER_DELAY)
            metrics.total_stagger_wait_seconds += RANKING_STAGGER_DELAY

    # ─────────────────────────────────────────────
    metrics.companies_with_signal = len(final_output)
    metrics.companies_removed = metrics.total_companies - metrics.companies_with_signal
    
    run_status = "success"
    if metrics.quota_skipped > 0:
        run_status = "denied (quota hits)" if metrics.companies_with_signal == 0 else "partial (quota hits)"
    elif metrics.total_companies > 0 and metrics.companies_with_signal == 0:
        run_status = "no_signals_found"



    # ─────────────────────────────────────────────
    # RETURN FINAL RESULT
    # ─────────────────────────────────────────────
    return {
        "metadata": {
            "status": run_status,
            "total_companies_input": metrics.total_companies,
            "companies_with_signal": metrics.companies_with_signal,
            "companies_removed": metrics.companies_removed,
            "total_articles_kept": metrics.total_articles_out,
            "quota_skips": metrics.quota_skipped,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "signals": final_output,
    }
