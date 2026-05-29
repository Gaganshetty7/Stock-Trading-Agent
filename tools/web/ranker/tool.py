import asyncio
import json
import time
from datetime import datetime, timezone
import os
import glob
from pathlib import Path
from typing import Dict, List, Optional

import pytz
from dotenv import load_dotenv
from google import genai
from google.genai import types

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
    MIN_IMPACT,
    GEMINI_RANKER_API_KEY,

    MARKET_CLOSED_MULTIPLIER,
    STALE_DECAY_MULTIPLIER,
    STALE_THRESHOLD_MINS
)

# Modular ranker components
from .helpers.schemas import ScoredArticle, BatchResponse
from .helpers.utils import QuotaError, robust_json_parser, truncate, logger
from .helpers.market_helpers import is_market_open, parse_age_to_mins
from .helpers.prompts import RANK_PROMPT
from .helpers.metrics import PipelineMetrics
from .token_tracker import extract_context_usage
from .token_tracker import log_token_usage

load_dotenv()

# ─────────────────────────────────────────────────────────────
# GEMINI CLIENT
# ─────────────────────────────────────────────────────────────

CLIENT = genai.Client(api_key=GEMINI_RANKER_API_KEY)

# ─────────────────────────────────────────────────────────────
# OUTPUT SAVER
# ─────────────────────────────────────────────────────────────

def save_ranker_output(
    output_data: Dict,
    output_subdir: str = "outputs/ranker",
    elapsed_time: Optional[float] = None,
) -> str:
    """
    Save final ranker output to JSON.
    """
    ist = pytz.timezone("Asia/Kolkata")
    timestamp = datetime.now(ist).strftime("%Y%m%d_%H%M%S")

    output_dir = Path(output_subdir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"intraday_signals_{timestamp}.json"

    if elapsed_time is not None:
        output_data.setdefault("metadata", {})
        output_data["metadata"]["pipeline_time_seconds"] = round(elapsed_time, 2)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved ranker output → {output_file}")
    logger.info("=" * 60)
    return str(output_file)

# ─────────────────────────────────────────────────────────────
# LLM CALL
# ─────────────────────────────────────────────────────────────

async def call_llm(
    prompt: str,
    metrics: PipelineMetrics,
) -> Optional[str]:

    attempt = 0

    while attempt <= RANKING_MAX_RETRIES:
        try:
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

                metrics.total_input_tokens += stats["input_tokens"]
                metrics.total_output_tokens += stats["output_tokens"]
                metrics.total_tokens += stats["total_tokens"]

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

            # Check for 403/Key revoked
            if "403" in err_str or "PERMISSION_DENIED" in err_str:
                logger.error("[FATAL] API key invalid/revoked")
                return None

            logger.error(f"[LLM ERROR] {e}")
            return None
    return None

# ─────────────────────────────────────────────────────────────
# MAIN RANKER
# ─────────────────────────────────────────────────────────────

async def rank_news_payload(payload: Optional[Dict] = None, payload_file: Optional[str] = None) -> Dict:
    pipeline_start = time.time()
    metrics = PipelineMetrics()
    
    logger.info("=" * 60)
    logger.info("Starting Intraday Signal Extraction (Stage 2)")
    logger.debug("[RANKER] Started")

    # 1. Load Payload
    # If no payload or file provided, or if specifically requested, find the latest mapped news
    if not payload and not payload_file:
        logger.info("No payload provided. Searching for latest mapped news in outputs/...")
        files = glob.glob("outputs/mapped_news_*.json")
        if files:
            payload_file = max(files, key=os.path.getctime)
            logger.info(f"Auto-discovered latest payload: {payload_file}")
        else:
            logger.error("No mapped news files found in outputs/")
            return {"error": "No payload provided and no mapped_news_*.json found in outputs/"}

    if payload_file:
        try:
            with open(payload_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
            logger.info(f"Loaded payload from file: {payload_file}")
        except Exception as e:
            logger.error(f"Failed to load payload_file {payload_file}: {e}")
            return {"error": f"Failed to load payload_file: {e}"}

    # Validation
    if payload is None:
        return {"error": "No payload or payload_file provided to rank_news_payload"}

    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return {"error": "rank_news_payload received invalid JSON string"}

    if not isinstance(payload, dict):
        return {"error": f"Expected dict payload, got {type(payload).__name__}"}

    mapped = payload.get("mapped_news", {})
    if isinstance(mapped, str):
        try:
            mapped = json.loads(mapped)
        except json.JSONDecodeError:
            return {"error": "mapped_news is invalid JSON string"}

    if not isinstance(mapped, dict):
        return {"error": f"mapped_news must be dict, got {type(mapped).__name__}"}

    all_tickers = list(mapped.keys())
    metrics.total_companies = len(all_tickers)
    metrics.total_articles_in = sum(len(mapped[t].get("company_insights", [])) for t in all_tickers)

    logger.info(f"  Companies input: {metrics.total_companies}")
    logger.info(f"  Articles input:  {metrics.total_articles_in}")
    logger.info("=" * 60)

    logger.debug(f"[RANKER] Companies={metrics.total_companies}")

    # 2. Batching
    batches = [all_tickers[i : i + RANKING_BATCH_SIZE] for i in range(0, len(all_tickers), RANKING_BATCH_SIZE)]
    final_results = []

    async def run_batch(batch_tickers: List[str], batch_index: int):
        batch_start = time.time()
        logger.debug(f"[BATCH {batch_index+1}] Starting")

        llm_payload = []
        for ticker in batch_tickers:
            insights = mapped.get(ticker, {}).get("company_insights", [])
            for article in insights:
                llm_payload.append({
                    "ticker": ticker,
                    "title": article.get("title", ""),
                    "published": article.get("published_date", "N/A"),
                    "age": article.get("age", "stale"),
                })

        if not llm_payload:
            return None, None, "empty"

        prompt = RANK_PROMPT.replace(
            "{current_time}",
            datetime.now(timezone.utc).strftime("%I:%M %p UTC"),
        ).replace(
            "{payload}",
            json.dumps(llm_payload, indent=1),
        )

        try:
            raw_response = await call_llm(prompt, metrics)
            if not raw_response:
                return None, None, "llm_empty"

            parsed = robust_json_parser(raw_response)
            if not parsed:
                metrics.parse_failures += 1
                return None, None, "parse_fail"

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
            metrics.success_count += 1
            
            batch_time = time.time() - batch_start
            logger.debug(f"[BATCH {batch_index+1}] Success in {batch_time:.2f}s")
            return raw_response, validated, "success"

        except Exception as e:
            metrics.failure_count += 1
            logger.error(f"[BATCH {batch_index+1}] ERROR: {e}")
            return None, None, "error"

    # 3. Execution
    for i, batch_tickers in enumerate(batches):
        log_quota_attempt(RANKING_MODEL, "START")
        raw, validated, status = await run_batch(batch_tickers, i)

        if status != "success" or not validated:
            continue

        market_open = is_market_open()
        valid_articles = []

        for article in validated.results:
            if not market_open:
                article.confidence *= MARKET_CLOSED_MULTIPLIER
            
            age_mins = parse_age_to_mins(article.age)
            if age_mins > STALE_THRESHOLD_MINS:
                article.confidence *= STALE_DECAY_MULTIPLIER

            article.confidence = round(article.confidence, 2)
            article.impact_score = round(article.impact_score, 2)

            if article.confidence >= MIN_CONFIDENCE and article.impact_score >= MIN_IMPACT:
                valid_articles.append(article)

        grouped = {}
        for article in valid_articles:
            grouped.setdefault(article.ticker, []).append(article)

        for ticker, articles in grouped.items():
            articles.sort(key=lambda x: (x.impact_score, x.confidence), reverse=True)
            for article in articles[:TOP_N_ARTICLES]:
                signal = article.model_dump()
                signal["confidence"] = float(signal.get("confidence", 0.0))
                signal["impact_score"] = float(signal.get("impact_score", 0.0))
                
                trend = str(signal.get("trend", "sideways")).lower()
                if trend not in ["bullish", "bearish", "sideways"]:
                    trend = "sideways"
                signal["trend"] = trend

                final_results.append(signal)
                metrics.total_articles_out += 1

        if i < len(batches) - 1:
            pass

    # 4. Finalization
    logger.info("=" * 60)
    logger.info(f"Extraction complete — {len(final_results)} signals found")
    metrics.companies_with_signal = len(set(art["ticker"] for art in final_results))
    metrics.companies_removed = metrics.total_companies - metrics.companies_with_signal

    run_status = "success"
    if metrics.quota_skipped > 0:
        run_status = "denied (quota hits)" if metrics.companies_with_signal == 0 else "partial (quota hits)"
    elif metrics.total_companies > 0 and metrics.companies_with_signal == 0:
        run_status = "no_signals_found"

    final_result = {
        "metadata": {
            "status": run_status,
            "total_companies_input": metrics.total_companies,
            "companies_with_signal": metrics.companies_with_signal,
            "companies_removed": metrics.companies_removed,
            "total_articles_kept": metrics.total_articles_out,
            "quota_skips": metrics.quota_skipped,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "results": final_results,
    }

    # 5. Save and Return
    save_ranker_output(final_result, elapsed_time=time.time() - pipeline_start)
    return final_result
