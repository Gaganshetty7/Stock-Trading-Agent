from typing import Dict, List
from tools.web.selector.config import TOP_N, ALLOWED_TRENDS


def dynamic_threshold_select(signals: Dict, top_n: int = TOP_N):
    """
    Input:
        signals = ranked_payload["signals"]

    Output:
        {
            "DBL": [ {...}, {...} ],
            "HAPPYFORGE": [ {...} ]
        }
    """

    all_articles = []

    # ─────────────── FLATTEN ───────────────
    for ticker, articles in signals.items():
        for article in articles:

            confidence = article.get("confidence", 0)
            impact = article.get("impact_score", 0)

            article["ticker"] = ticker

            article["combined_score"] = round(
                (impact * 0.7) + (confidence * 0.3),
                4
            )

            all_articles.append(article)

    # ─────────────── SORT ───────────────
    all_articles.sort(
        key=lambda x: x["combined_score"],
        reverse=True
    )

    # ─────────────── SELECT TOP N ───────────────
    selected = []
    used_titles = set()

    for article in all_articles:

        if len(selected) >= top_n:
            break

        if article.get("trend") not in ALLOWED_TRENDS:
            continue

        if article["title"] in used_titles:
            continue

        selected.append(article)
        used_titles.add(article["title"])

    # ─────────────── GROUP BY TICKER (IMPORTANT FIX) ───────────────
    result = {}

    for item in selected:
        ticker = item["ticker"]

        if ticker not in result:
            result[ticker] = []

        result[ticker].append(item)

    return result
