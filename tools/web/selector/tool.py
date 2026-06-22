import glob
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, List

from config.settings import OUTPUTS_DIR
from tools.storage.file_writer import write_json
from tools.web.selector.settings import TOP_N_ARTICLES, ALLOWED_TRENDS, MIN_CONFIDENCE, MIN_IMPACT, STEP, COMBINED_SCORE_WEIGHTS
from core.logger import get_logger

logger = get_logger("selector")


# ─────────────── LOCAL HELPERS ───────────────

async def _write_text(filename_prefix: str, content: str, extension: str = "txt") -> str:
    """
    Local helper to write plain text since file_writer is JSON-only.
    Maintains IST timestamping and output directory logic.
    """
    IST = timezone(timedelta(hours=5, minutes=30))
    timestamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{timestamp}.{extension}"
    
    filepath = Path(OUTPUTS_DIR) / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return str(filepath)


# ─────────────── SIGNAL LOADER ───────────────

def _load_signals(signals_file: Optional[str] = None) -> Dict:
    """
    Load the ranker's intraday_signals file.
    If no path is given, auto-discovers the latest one in outputs/ranker/.
    """
    if not signals_file:
        files = glob.glob("outputs/StockNewsAgent/ranker/intraday_signals_*.json")
        if files:
            signals_file = max(files, key=os.path.getctime)
            logger.info(f"Auto-discovered latest signals file: {signals_file}")
        else:
            raise ValueError(
                "No signals_file provided and no intraday_signals_*.json found in outputs/ranker/"
            )

    with open(signals_file, "r", encoding="utf-8") as f:
        payload = json.load(f)
        logger.info(f"Loaded {len(payload.get('signals', {}))} raw ticker signals from {signals_file}")

    # Unwrap the ranker schema:
    # payload["signals"] = { ticker: { "ticker": ..., "company_insights": [...] } }
    raw_signals = payload.get("signals", {})
    signals: Dict = {}
    for ticker, data in raw_signals.items():
        articles = data.get("company_insights", [])
        if articles:
            signals[ticker] = articles

    if not signals:
        raise ValueError(f"No valid signals found in: {signals_file}")

    return signals, signals_file


# ─────────────── SELECTION CORE ───────────────

def _dynamic_threshold_select(signals: Dict, top_n: int = TOP_N_ARTICLES) -> Dict:
    """
    Progressively expands the candidate pool using tiered thresholds until top_n unique tickers found.
    Combined score is computed ONLY on articles that pass the threshold filter.
    """
    all_articles = []

    # ─────────────── FLATTEN (no scoring yet) ───────────────
    for ticker, articles in signals.items():
        for article in articles:
            article["ticker"] = ticker
            all_articles.append(article)

    # ─────────────── PROGRESSIVE THRESHOLD FILTER ───────────────
    pool_articles: List[Dict] = []
    
    # Generate thresholds dynamically from 1.0 down to mins
    curr_threshold = 1.0
    while True:
        min_conf = max(curr_threshold, MIN_CONFIDENCE)
        min_imp = max(curr_threshold, MIN_IMPACT)
        
        current_pool = []
        unique_tickers_in_pool = set()
        used_titles: set = set()

        for article in all_articles:
            if article.get("trend") not in ALLOWED_TRENDS:
                continue
            if article.get("confidence", 0) < min_conf or article.get("impact_score", 0) < min_imp:
                continue
            if article["title"] in used_titles:
                continue

            current_pool.append(article)
            unique_tickers_in_pool.add(article["ticker"])
            used_titles.add(article["title"])

        if len(unique_tickers_in_pool) >= top_n:
            pool_articles = current_pool
            break
            
        # Stop if we have reached the absolute minimum thresholds
        if curr_threshold <= MIN_CONFIDENCE and curr_threshold <= MIN_IMPACT:
            pool_articles = current_pool # Fallback to last pool
            break
            
        curr_threshold = round(curr_threshold - STEP, 2)

    # ─────────────── SCORE ONLY CANDIDATES (pool) ───────────────
    for article in pool_articles:
        article["combined_score"] = round(
            (article.get("impact_score", 0) * COMBINED_SCORE_WEIGHTS["impact"])
            + (article.get("confidence", 0) * COMBINED_SCORE_WEIGHTS["confidence"]),
            4
        )

    pool_articles.sort(key=lambda x: x["combined_score"], reverse=True)

    # ─────────────── SELECT TOP N UNIQUE TICKERS ───────────────
    selected_tickers_ordered: List[str] = []
    seen_tickers: set = set()
    for article in pool_articles:
        if len(seen_tickers) >= top_n:
            break
        if article["ticker"] not in seen_tickers:
            seen_tickers.add(article["ticker"])
            selected_tickers_ordered.append(article["ticker"])

    def group_by_ticker(items: List[Dict]) -> Dict:
        result: Dict = {}
        for item in items:
            result.setdefault(item["ticker"], []).append(item)
        return result

    return {
        "candidate_pool": group_by_ticker(pool_articles),
        "selected_tickers": selected_tickers_ordered,
        "total_candidates": len(pool_articles)
    }




# ─────────────── PUBLIC TOOL FUNCTION ───────────────

async def select_top_stocks(signals_file: Optional[str] = None) -> Dict:
    """
    Stage 3: Dynamic Threshold Stock Selector.

    Loads the latest intraday_signals file (or uses the provided path),
    runs the tiered selection algorithm, and saves:
        - outputs/candidate_pool/candidate_pool_<ts>.json  (all articles at the selection boundary)
        - outputs/top_tickers/top_tickers_<ts>.json        (raw list of top ticker symbols)

    Returns a summary dict with the saved file paths.
    """
    signals, source_file = _load_signals(signals_file)

    result = _dynamic_threshold_select(signals)

    candidate_pool = result["candidate_pool"]
    selected_tickers = result["selected_tickers"]
    total_candidates = result["total_candidates"]

    # ── Save candidate pool (with metadata) ──
    pool_payload = {
        "metadata": {
            "input_file": source_file,
            "total_companies": len(signals),
            "total_candidates": total_candidates,
        },
        "candidate_pool": candidate_pool,
    }
    pool_file = await write_json("StockNewsAgent/selector/candidate_pool/candidate_pool", pool_payload)

    # ── Save top tickers (plain text, no brackets) ──
    tickers_str = ", ".join(selected_tickers)
    tickers_file = await _write_text("StockNewsAgent/selector/top_tickers/top_tickers", tickers_str)

    logger.info(f"Selection complete: {len(selected_tickers)} tickers selected ({', '.join(selected_tickers[:3])}{'...' if len(selected_tickers) > 3 else ''})")
    return {
        "status": "success",
        "selected_tickers": selected_tickers
    }
