from rapidfuzz import fuzz

DEDUP_SIMILARITY = 60

def deduplicate(articles: list[dict]) -> list[dict]:
    seen_urls:   set[str]   = set()
    seen_titles: list[str]  = []
    unique:      list[dict] = []

    for art in articles:
        link = art.get("link", "")
        if link and link in seen_urls:
            continue
        if any(
            fuzz.token_set_ratio(art["title"], t) >= DEDUP_SIMILARITY
            for t in seen_titles
        ):
            continue
        if link:
            seen_urls.add(link)
        seen_titles.append(art["title"])
        unique.append(art)

    return unique
