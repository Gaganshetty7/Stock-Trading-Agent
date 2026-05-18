import csv
import json


INPUT_CSV = "resources/EQUITY_L.csv"
OUTPUT_JSON = "outputs/aliases/aliases.json"


REMOVE_SUFFIXES = [
    " limited",
    " ltd",
    " ltd.",
    " limited.",
    " corporation",
    " corp",
    " industries",
    " pvt",
    " plc"
]


def clean_company_name(name: str) -> str:
    cleaned = name.strip()

    lowered = cleaned.lower()

    for suffix in REMOVE_SUFFIXES:
        if lowered.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
            break

    return cleaned


def generate_number_removed_aliases(name: str) -> list[str]:
    words = name.split()

    if not words:
        return []

    first_word = words[0]

    # Only remove if first token is PURELY numeric
    if not first_word.isdigit():
        return []

    remaining_words = words[1:]

    if not remaining_words:
        return []

    alias = " ".join(remaining_words)

    return [
        alias,
        alias.upper().replace(" ", "")
    ]


def generate_aliases(symbol: str, company_name: str) -> list[str]:
    aliases = []

    original_name = company_name.strip()
    cleaned_name = clean_company_name(original_name)
    ticker = symbol.strip().upper()

    aliases.append(original_name)

    if cleaned_name != original_name:
        aliases.append(cleaned_name)

    aliases.append(ticker)

    # Generate aliases like:
    # "20 Microns" -> "Microns", "MICRONS"
    aliases.extend(generate_number_removed_aliases(cleaned_name))

    unique_aliases = []
    seen = set()

    for alias in aliases:
        normalized = alias.lower()

        if normalized not in seen:
            seen.add(normalized)
            unique_aliases.append(alias)

    return unique_aliases


def main():
    result = {}

    with open(INPUT_CSV, "r", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            symbol = row["SYMBOL"].strip()
            company_name = row["NAME OF COMPANY"].strip()

            result[symbol] = {
                "company_name": company_name,
                "aliases": generate_aliases(symbol, company_name)
            }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as json_file:
        json.dump(result, json_file, indent=2, ensure_ascii=False)

    print(f"Created {OUTPUT_JSON} with {len(result)} companies")


if __name__ == "__main__":
    main()
