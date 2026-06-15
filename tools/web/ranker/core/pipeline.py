import time
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple


from ..config.settings import (
    MARKET_CLOSED_MULTIPLIER,
    MIN_CONFIDENCE,
    MIN_IMPACT,
    RANKING_BATCH_SIZE,
    NEWS_RANKER_MODEL,
    STALE_DECAY_MULTIPLIER,
    STALE_THRESHOLD_MINS,
    TOP_N_ARTICLES,
)
from ..llm import run_batch
from ..utils.logger import logger
from ..utils.market_helpers import is_market_open, parse_age_to_mins
from .finalize_results import finalize_results
from .metrics import PipelineMetrics
from .payload import (
    filter_insights,
    load_payload,
    normalize_mapped,
)


def create_batches(all_tickers: list[str], batch_size: int) -> list[list[str]]:
    return [all_tickers[i : i + batch_size] for i in range(0, len(all_tickers), batch_size)]


async def execute_ranker_pipeline(
    payload_file: Optional[str] = None,
) -> Tuple[Dict, PipelineMetrics]:
    pipeline_start = time.time()
    metrics = PipelineMetrics()

    try:
        payload, mapped, payload_file = load_payload(payload_file)
    except ValueError as e:
        logger.error(str(e))
        return {"error": str(e)}, metrics

    mapped = normalize_mapped(mapped)
    mapped = filter_insights(mapped)

    all_tickers = list(mapped.keys())
    metrics.total_companies = len(all_tickers)
    metrics.total_articles_in = sum(len(mapped[t].get("company_insights", [])) for t in all_tickers)

    batches = create_batches(all_tickers, RANKING_BATCH_SIZE)
    final_results = []

    for i, batch_tickers in enumerate(batches):
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

        grouped: dict[str, list] = {}
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

    final_result = finalize_results(final_results, metrics)
    final_result["metadata"]["pipeline_time_seconds"] = round(time.time() - pipeline_start, 2)

    return final_result, metrics
