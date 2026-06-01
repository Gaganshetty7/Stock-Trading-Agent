import json
import time
from datetime import datetime, timezone
import os
import glob
from typing import Dict, Optional

from .api_quota_tracker.quota_tracker import log_quota_attempt
from .helpers.settings import (
    RANKING_MODEL,
    RANKING_BATCH_SIZE,
    TOP_N_ARTICLES,
    MIN_CONFIDENCE,
    MIN_IMPACT,

    MARKET_CLOSED_MULTIPLIER,
    STALE_DECAY_MULTIPLIER,
    STALE_THRESHOLD_MINS,
)

# Modular ranker components
from .helpers.utils import logger
from .helpers.market_helpers import is_market_open, parse_age_to_mins
from .helpers.metrics import PipelineMetrics
from .llm import run_batch
from .output import save_ranker_output

# ─────────────────────────────────────────────────────────────
# MAIN RANKER
# ─────────────────────────────────────────────────────────────

async def rank_news_payload(payload: Optional[Dict] = None, payload_file: Optional[str] = None, **kwargs) -> Dict:
    pipeline_start = time.time()
    metrics = PipelineMetrics()
    
    logger.info("=" * 60)
    logger.info("Starting Intraday Signal Extraction (Stage 2)")
    logger.debug("[RANKER] Started")

    # 1. Load Payload
    # Allow callers to pass payload fields as kwargs (e.g., metadata=..., mapped_news=...)
    if not payload and kwargs:
        payload = kwargs

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

    def _extract_total_companies(payload_dict):
        metadata = payload_dict.get("metadata", {})
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                return None
        if not isinstance(metadata, dict):
            return None
        total = metadata.get("total_companies") or metadata.get("companies")
        try:
            return int(total)
        except (TypeError, ValueError):
            return None

    def _payload_looks_truncated(m):
        if not isinstance(m, dict):
            return False

        for val in m.values():
            if isinstance(val, str) and val.strip() == "...":
                return True

            if isinstance(val, dict):
                insights = val.get("company_insights")
                if isinstance(insights, list):
                    for item in insights:
                        if isinstance(item, str) and item.strip() == "...":
                            return True
                        if isinstance(item, dict):
                            title = str(item.get("title", "")).strip()
                            if title == "...":
                                return True
        return False

    def _should_fallback_to_file():
        total_companies = _extract_total_companies(payload)
        if total_companies and len(mapped) < total_companies:
            logger.warning(
                "[PAYLOAD] mapped_news contains fewer tickers than metadata.total_companies; "
                "assuming truncated agent handoff."
            )
            return True
        return _payload_looks_truncated(mapped)

    if _should_fallback_to_file():
        logger.warning(
            "[PAYLOAD] detected truncated mapped_news payload; attempting stage-2 file fallback."
        )
        if not payload_file:
            files = glob.glob("outputs/mapped_news_*.json")
            if files:
                payload_file = max(files, key=os.path.getctime)
                logger.info(f"Falling back to latest mapped_news file: {payload_file}")
                try:
                    with open(payload_file, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                    mapped = payload.get("mapped_news", {})
                    if isinstance(mapped, str):
                        try:
                            mapped = json.loads(mapped)
                        except json.JSONDecodeError:
                            return {"error": "Fallback mapped_news is invalid JSON string"}
                    if not isinstance(mapped, dict):
                        return {"error": f"Fallback mapped_news must be dict, got {type(mapped).__name__}"}
                except Exception as e:
                    logger.error(f"Failed to load fallback payload_file {payload_file}: {e}")
                    return {"error": f"Failed to load fallback payload_file: {e}"}
            else:
                logger.error("No fallback mapped_news files found in outputs/")
                return {"error": "Detected truncated payload and no fallback mapped_news file found."}

    # Normalize mapped_news into consistent structure:
    # { ticker: { "company_insights": [ {title, link, published_date, age, ...}, ... ] } }
    def _normalize_mapped(m):
        out = {}
        for ticker, val in m.items():
            # If already in expected shape, keep it
            if isinstance(val, dict) and isinstance(val.get("company_insights"), list):
                out[ticker] = val
                continue

            # If value is a list, it may be list of strings (titles) or list of article dicts
            if isinstance(val, list):
                insights = []
                for item in val:
                    if isinstance(item, str):
                        insights.append({
                            "title": item,
                            "source": None,
                            "link": "",
                            "published_date": "",
                            "age": "stale",
                        })
                    elif isinstance(item, dict):
                        # normalize keys
                        article = dict(item)
                        # prefer 'url' then 'link'
                        if "url" not in article and "link" in article:
                            article["url"] = article.get("link")
                        insights.append(article)
                out[ticker] = {"company_insights": insights}
                continue

            # If value is a single string, treat as single title
            if isinstance(val, str):
                if val == "...":
                    logger.warning(f"[NORMALIZE] {ticker} contains truncated payload")
                    out[ticker] = {"company_insights": []}
                    continue

                out[ticker] = {"company_insights": [{"title": val, "source": None, "link": "", "published_date": "", "age": "stale"}]}
                continue

            # Fallback to empty
            out[ticker] = {"company_insights": []}

        return out

    mapped = _normalize_mapped(mapped)

    # Filter out malformed or truncated insights before ranking
    for ticker, data in mapped.items():
        insights = data.get("company_insights", [])
        insights = [
            x for x in insights
            if isinstance(x, dict)
            and x.get("title")
            and x.get("title") != "..."
            and len(str(x.get("title", "")).strip()) > 20
        ]
        if len(insights) != len(data.get("company_insights", [])):
            logger.warning(f"[FILTER] {ticker} had invalid or truncated company_insights removed")
        data["company_insights"] = insights

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

    # 3. Execution
    for i, batch_tickers in enumerate(batches):
        log_quota_attempt(RANKING_MODEL, "START")
        validated, status = await run_batch(
            batch_tickers=batch_tickers,
            batch_index=i,
            mapped=mapped,
            metrics=metrics,
        )

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
                url_value = signal.get("url") or getattr(article, "url", None)
                if isinstance(url_value, str) and not url_value.strip():
                    url_value = None
                if url_value:
                    signal["url"] = url_value
                elif "url" in signal:
                    signal.pop("url", None)

                published_value = signal.get("published") or getattr(article, "published", None)
                if isinstance(published_value, str) and not published_value.strip():
                    published_value = None
                if published_value:
                    signal["published"] = published_value
                elif "published" in signal:
                    signal.pop("published", None)

                signal["confidence"] = float(signal.get("confidence", 0.0))
                signal["impact_score"] = float(signal.get("impact_score", 0.0))
                
                trend = str(signal.get("trend", "sideways")).lower()
                if trend not in ["bullish", "bearish", "sideways"]:
                    trend = "sideways"
                signal["trend"] = trend

                final_results.append(signal)
                metrics.total_articles_out += 1

    # 4. Finalization
    logger.info("=" * 60)
    logger.info(f"Extraction complete — {len(final_results)} signals found")
    metrics.companies_with_signal = len(set(art["ticker"] for art in final_results))
    metrics.companies_removed = metrics.total_companies - metrics.companies_with_signal

    run_status = "success"
    if metrics.total_companies > 0 and metrics.companies_with_signal == 0:
        run_status = "no_signals_found"

    signals_by_ticker = {}
    for signal in final_results:
        ticker = signal.get("ticker")
        if not ticker:
            continue
        signals_by_ticker.setdefault(ticker, {
            "ticker": ticker,
            "company_insights": [],
        })["company_insights"].append(signal)

    final_result = {
        "metadata": {
            "status": run_status,
            "total_companies_input": metrics.total_companies,
            "companies_with_signal": metrics.companies_with_signal,
            "companies_removed": metrics.companies_removed,
            "total_articles_kept": metrics.total_articles_out,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "signals": signals_by_ticker,
    }

    # 5. Save and Return
    save_ranker_output(
        final_result,
        elapsed_time=time.time() - pipeline_start,
        metrics=metrics,
    )
    return final_result
