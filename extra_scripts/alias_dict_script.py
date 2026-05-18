import json


INPUT_FILE = "resources/aliases.json"
OUTPUT_FILE = "resources/aliases/alias_lookup.json"


def normalize(text: str) -> str:
    return text.strip().lower()


def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        aliases_data = json.load(file)

    alias_lookup = {}

    for ticker, company_data in aliases_data.items():
        aliases = company_data["aliases"]

        for alias in aliases:
            normalized_alias = normalize(alias)

            alias_lookup[normalized_alias] = ticker

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(alias_lookup, file, indent=2, ensure_ascii=False)

    print(f"Created {OUTPUT_FILE} with {len(alias_lookup)} aliases")


if __name__ == "__main__":
    main()
