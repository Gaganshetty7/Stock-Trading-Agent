import glob
import json
import os
from typing import Dict

from ..utils.logger import logger


def load_payload(payload_file=None):
    if not payload_file:
        files = glob.glob("outputs/StockNewsAgent/rss_fetcher/mapped_news_*.json")
        if files:
            payload_file = max(files, key=os.path.getctime)
        else:
            raise ValueError("No payload_file provided and no mapped_news_*.json found in outputs/")

    try:
        with open(payload_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
        logger.info(f"Loaded payload from file: {payload_file}")
    except Exception as e:
        raise ValueError(f"Failed to load payload_file: {e}")

    if not isinstance(payload, dict):
        raise ValueError(f"Expected dict payload from file, got {type(payload).__name__}")

    mapped = payload.get("mapped_news", {})
    if isinstance(mapped, str):
        try:
            mapped = json.loads(mapped)
        except json.JSONDecodeError:
            raise ValueError("mapped_news is invalid JSON string")

    if not isinstance(mapped, dict):
        raise ValueError(f"mapped_news must be dict, got {type(mapped).__name__}")

    return payload, mapped, payload_file


def normalize_mapped(mapped: Dict) -> Dict:
    out = {}
    for ticker, val in mapped.items():
        if isinstance(val, dict) and isinstance(val.get("company_insights"), list):
            out[ticker] = val
            continue

        if isinstance(val, list):
            insights = []
            for item in val:
                if isinstance(item, str):
                    insights.append({
                        "title": item,
                        "source": None,
                        "url": "",
                        "published_date": "",
                        "age": "stale",
                    })
                elif isinstance(item, dict):
                    article = dict(item)
                    if "url" not in article and "link" in article:
                        article["url"] = article.get("link")
                    insights.append(article)
            out[ticker] = {"company_insights": insights}
            continue

        if isinstance(val, str):
            if val == "...":
                logger.warning(f"[NORMALIZE] {ticker} contains truncated payload")
                out[ticker] = {"company_insights": []}
                continue

            out[ticker] = {"company_insights": [{"title": val, "source": None, "url": "", "published_date": "", "age": "stale"}]}
            continue

        out[ticker] = {"company_insights": []}

    return out


def filter_insights(mapped: Dict) -> Dict:
    for ticker, data in list(mapped.items()):
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
    return mapped
