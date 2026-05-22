from typing import Dict, List
import json
from pathlib import Path
from datetime import datetime
import pytz


def dynamic_threshold_select(
    signals: Dict,
    top_n: int = 10,
    confidence_levels: List[float] = None,
    impact_levels: List[float] = None,
    allowed_trends: List[str] = None,
):
    """
    Dynamically selects strongest market-moving stocks.

    FLOW:
    1. Try strict thresholds first
    2. Gradually relax thresholds
    3. Always attempt to return top_n stocks
    4. Final fallback fills remaining slots
    """

    # STRICT → RELAXED
    if confidence_levels is None:
        confidence_levels = [0.98, 0.95, 0.92, 0.90, 0.85, 0.80, 0.75]

    if impact_levels is None:
        impact_levels = [0.95, 0.90, 0.85, 0.80, 0.70, 0.60, 0.50, 0.40]

    if allowed_trends is None:
        allowed_trends = ["bullish", "bearish"]

    selected = []
    used_titles = set()

    all_articles = []

    # ─────────────────────────────────────────────
    # Flatten signals
    # ─────────────────────────────────────────────
    for ticker, articles in signals.items():

        for article in articles:

            item = article.copy()
            item["ticker"] = ticker

            confidence = item.get("confidence", 0)
            impact = item.get("impact_score", 0)

            # Weighted combined score
            item["combined_score"] = round(
                (impact * 0.7) + (confidence * 0.3),
                4
            )

            all_articles.append(item)

    # ─────────────────────────────────────────────
    # Sort strongest first
    # ─────────────────────────────────────────────
    all_articles.sort(
        key=lambda x: (
            x.get("combined_score", 0),
            x.get("impact_score", 0),
            x.get("confidence", 0),
        ),
        reverse=True,
    )

    # ─────────────────────────────────────────────
    # Dynamic threshold relaxation
    # ─────────────────────────────────────────────
    for conf in confidence_levels:

        for impact in impact_levels:

            for article in all_articles:

                if len(selected) >= top_n:
                    break

                title = article.get("title", "")

                if title in used_titles:
                    continue

                if article.get("trend") not in allowed_trends:
                    continue

                if article.get("confidence", 0) < conf:
                    continue

                if article.get("impact_score", 0) < impact:
                    continue

                selected.append(article)
                used_titles.add(title)

            if len(selected) >= top_n:
                break

        if len(selected) >= top_n:
            break

    # ─────────────────────────────────────────────
    # Final fallback
    # ─────────────────────────────────────────────
    if len(selected) < top_n:

        for article in all_articles:

            if len(selected) >= top_n:
                break

            title = article.get("title", "")

            if title in used_titles:
                continue

            if article.get("trend") not in allowed_trends:
                continue

            selected.append(article)
            used_titles.add(title)

    return selected[:top_n]


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":

    INPUT_FILE = "/home/vishmitha/news/Stock-Trading-Agent/outputs/signals_20260522_102644.json"

    # CONFIG
    TOP_N = 10

    confidence_levels = [0.98, 0.95, 0.92, 0.90, 0.85, 0.80, 0.75]

    impact_levels = [0.95, 0.90, 0.85, 0.80, 0.70, 0.60, 0.50, 0.40]

    allowed_trends = ["bullish", "bearish"]

    # ─────────────────────────────────────────────
    # Load ranking output
    # ─────────────────────────────────────────────
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)

    signals = payload["signals"]

    # ─────────────────────────────────────────────
    # Run selector
    # ─────────────────────────────────────────────
    top_stocks = dynamic_threshold_select(
        signals=signals,
        top_n=TOP_N,
        confidence_levels=confidence_levels,
        impact_levels=impact_levels,
        allowed_trends=allowed_trends,
    )

    # ─────────────────────────────────────────────
    # Metadata
    # ─────────────────────────────────────────────
    total_input_companies = len(signals)

    bullish_count = sum(
        1 for x in top_stocks
        if x.get("trend") == "bullish"
    )

    bearish_count = sum(
        1 for x in top_stocks
        if x.get("trend") == "bearish"
    )

    neutral_count = sum(
        1 for x in top_stocks
        if x.get("trend") == "neutral"
    )

    final_output = {
        "metadata": {
            "input_file": INPUT_FILE,
            "input_companies": total_input_companies,
            "selected_top_stocks": len(top_stocks),
            "top_n_requested": TOP_N,
            "confidence_levels": confidence_levels,
            "impact_levels": impact_levels,
            "allowed_trends": allowed_trends,
            "bullish_selected": bullish_count,
            "bearish_selected": bearish_count,
            "neutral_selected": neutral_count,
            "generated_at": datetime.now().isoformat(),
        },

        "top_stocks": top_stocks
    }

    # ─────────────────────────────────────────────
    # Save output
    # ─────────────────────────────────────────────
    ist = pytz.timezone("Asia/Kolkata")

    timestamp = datetime.now(ist).strftime("%Y%m%d_%H%M%S")

    output_dir = Path("outputs/top_stocks")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"top_stocks_{timestamp}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 50)
    print("TOP STOCK SELECTION COMPLETE")
    print("=" * 50)
    print(f"Input Companies: {total_input_companies}")
    print(f"Selected Stocks: {len(top_stocks)}")
    print(f"Bullish: {bullish_count}")
    print(f"Bearish: {bearish_count}")
    print(f"Neutral: {neutral_count}")
    print(f"Saved To: {output_file}")
    print("=" * 50 + "\n")
