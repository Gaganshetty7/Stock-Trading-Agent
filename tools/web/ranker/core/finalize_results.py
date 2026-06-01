from datetime import datetime, timezone
from typing import Dict, List

from ..utils.logger import logger
from .metrics import PipelineMetrics


def finalize_results(final_results: List[Dict], metrics: PipelineMetrics) -> Dict:
    logger.info("=" * 60)
    logger.info(f"Extraction complete — {len(final_results)} signals found")

    companies_with_signal = len(set(art["ticker"] for art in final_results if art.get("ticker")))
    total_companies = metrics.total_companies
    companies_removed = total_companies - companies_with_signal

    run_status = "success"
    if total_companies > 0 and companies_with_signal == 0:
        run_status = "no_signals_found"

    signals_by_ticker: Dict[str, Dict] = {}
    for signal in final_results:
        ticker = signal.get("ticker")
        if not ticker:
            continue
        signals_by_ticker.setdefault(ticker, {"ticker": ticker, "company_insights": []})["company_insights"].append(signal)

    return {
        "metadata": {
            "status": run_status,
            "total_companies_input": total_companies,
            "companies_with_signal": companies_with_signal,
            "companies_removed": companies_removed,
            "total_articles_kept": metrics.total_articles_out,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "signals": signals_by_ticker,
    }
