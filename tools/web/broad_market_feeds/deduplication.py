from rapidfuzz import fuzz

DEDUP_SIMILARITY = 60

def deduplicate(articles: list[dict]) -> list[dict]:
    seen_urls:   set[str]   = set()
    seen_titles: list[str]  = []
    unique:      list[dict] = []

    for art in articles:
        if art["url"] and art["url"] in seen_urls:
            continue
        if any(
            fuzz.token_set_ratio(art["title"], t) >= DEDUP_SIMILARITY
            for t in seen_titles
        ):
            continue
        if art["url"]:
            seen_urls.add(art["url"])
        seen_titles.append(art["title"])
        unique.append(art)

    return unique
