# ============================================================
# Broad Market Sweepers
# ============================================================

_BROAD_SWEEPERS = [
    "NSE BSE India stock market today",
    "India stock market news today",
    "India quarterly results today",
    "India corporate earnings today",
    "NSE BSE share price today",
    "India stock market gainers losers",
    "India FII DII activity today",
    "India bulk deal today",
    "India IPO news today",
    "SEBI action India today",
    "RBI policy India today",
    "India market rally today",
    "India 52 week high stocks",
    "India upper circuit stocks",
    "India mutual fund news",
    "India analyst target price",
    "India company earnings guidance",
    "India promoter stake sale",
    "India dividend buyback today",
    "India rights issue today",
    "India takeover open offer",
    "India earnings surprise stocks",
    "India capex expansion company",
    "India company revenue profit",
    "India company order win",
    "India large contract win India",
]

# ============================================================
# High Signal Queries
# Low volume but HIGH market impact.
# Keep even if article count is smaller.
# ============================================================

_HIGH_SIGNAL = [
    "India company merger today",
    "India takeover bid today",
    "India defence order today",
    "India pharma FDA approval",
    "India pharma drug approval",
    "India QIP issue today",
    "India rights issue record date",
    "India buyback record date",
    "India dividend record date",
    "India stake sale today",
    "India insolvency NCLT",
    "India plant shutdown company",
    "India capex expansion",
    "India insider trading SEBI",
    "India acquisition deal today",
]

# ============================================================
# Sector-Specific Semantic Query Mapping
# ============================================================

_SECTOR_EVENT_MAP: dict[str, list[str]] = {
    "banking": [
        "results profit", "loan growth", "bank expansion", "bank partnership",
        "target price", "RBI policy", "bank IPO", "bank earnings", "bank stocks", "credit growth",
    ],
    "pharma": [
        "results profit", "FDA approval", "drug approval", "export order",
        "capacity expansion", "licensing deal", "target price", "pharma earnings", "pharma IPO", "US market",
    ],
    "IT": [
        "results profit", "AI partnership", "cloud deal", "data center expansion",
        "target price", "IT hiring", "IT earnings", "block deal", "digital transformation", "software deal",
    ],
    "infrastructure": [
        "EPC order", "project win", "results profit", "construction order",
        "road project", "railway project", "capacity expansion", "target price", "infrastructure IPO", "government project",
    ],
    "energy": [
        "renewable energy", "solar project", "wind project", "results profit",
        "oil gas", "capacity expansion", "energy IPO", "target price", "power project", "green energy",
    ],
    "FMCG": [
        "results profit", "sales growth", "consumer demand", "capacity expansion",
        "FMCG earnings", "distribution expansion", "retail growth",
    ],
    "metals": [
        "steel production", "aluminium production", "results profit", "mining expansion",
        "steel export", "capacity expansion", "metal stocks", "commodity prices",
    ],
    "auto": [
        "vehicle sales", "EV expansion", "results profit", "auto exports",
        "manufacturing expansion", "target price", "auto earnings", "car sales", "two wheeler sales", "auto stocks",
    ],
    "telecom": [
        "5G expansion", "spectrum news", "telecom earnings", "results profit",
        "subscriber growth", "telecom IPO", "target price", "network expansion", "broadband growth",
    ],
    "chemicals": [
        "specialty chemicals", "chemical exports", "results profit", "capacity expansion",
        "chemical stocks", "target price", "chemical earnings", "export demand",
    ],
    "defence": [
        "defence order", "government contract", "results profit", "military equipment",
        "manufacturing expansion", "defence stocks", "target price", "Make in India defence",
    ],
    "real estate": [
        "property sales", "housing demand", "real estate earnings", "commercial project",
        "construction expansion", "home loan policy", "REIT IPO", "target price", "real estate stocks", "property launches",
    ],
}

# ============================================================
# Generate Final Sector Queries
# ============================================================

_SECTOR_EVENT_QUERIES = [
    f"India {sector} {event}"
    for sector, events in _SECTOR_EVENT_MAP.items()
    for event in events
]

# ============================================================
# Final Master Query List
# ============================================================

FINAL_MASTER_QUERY_LIST = (
    _BROAD_SWEEPERS
    + _SECTOR_EVENT_QUERIES
    + _HIGH_SIGNAL
)
