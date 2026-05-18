import json
import re
from pathlib import Path

def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def generate_ngrams(words: list[str], max_n: int = 3) -> set[str]:
    ngrams = set()
    length = len(words)
    for n in range(1, max_n + 1):
        for i in range(length - n + 1):
            gram = " ".join(words[i:i + n])
            ngrams.add(gram)
    return ngrams

def map_news_to_tickers(articles: list[dict], alias_lookup: dict) -> dict:
    mapped_news = {}
    for article in articles:
        title = article.get("title", "")
        summary = article.get("summary", "")
        combined_text = f"{title} {summary}"
        normalized_text = normalize(combined_text)
        words = normalized_text.split()
        ngrams = generate_ngrams(words)
        
        matched_tickers = set()
        for gram in ngrams:
            if gram in alias_lookup:
                matched_tickers.add(alias_lookup[gram])
        
        for ticker in matched_tickers:
            if ticker not in mapped_news:
                mapped_news[ticker] = {
                    "ticker": ticker,
                    "company_insights": []
                }
            
            insight = article.copy()
            # Standardize flags
            insight["content_fetched"] = False
            insight["published_date"] = article.get("published")
            mapped_news[ticker]["company_insights"].append(insight)
            
    return mapped_news
