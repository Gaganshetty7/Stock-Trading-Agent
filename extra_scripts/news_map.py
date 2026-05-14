import json
import re


ARTICLES_FILE = "outputs/broad_market_test_report_20260514_130457.json"
ALIAS_LOOKUP_FILE = "resources/aliases/alias_lookup.json"
OUTPUT_FILE = "outputs/mapped_news.json"


MAX_NGRAM = 3


def normalize(text: str) -> str:
    text = text.lower()

    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def generate_ngrams(words: list[str], max_n: int = MAX_NGRAM) -> set[str]:
    ngrams = set()

    length = len(words)

    for n in range(1, max_n + 1):
        for i in range(length - n + 1):
            gram = " ".join(words[i:i + n])
            ngrams.add(gram)

    return ngrams


def main():
    with open(ARTICLES_FILE, "r", encoding="utf-8") as file:
        articles_data = json.load(file)

    with open(ALIAS_LOOKUP_FILE, "r", encoding="utf-8") as file:
        alias_lookup = json.load(file)

    articles = articles_data["articles"]

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

            mapped_news[ticker]["company_insights"].append({
                "title": article.get("title"),
                "source": article.get("source"),
                "link": article.get("url"),
                "published_date": article.get("published"),
                "age": article.get("age")
            })

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(mapped_news, file, indent=2, ensure_ascii=False)

    print(f"Created {OUTPUT_FILE}")
    print(f"Matched companies: {len(mapped_news)}")


if __name__ == "__main__":
    main()
