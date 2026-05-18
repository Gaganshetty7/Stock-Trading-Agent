import os
import glob
import asyncio
import subprocess
from tools.web.broad_market_feeds.broad_rss_fetcher import fetch_broad_market_rss

async def main():
    print("Starting pipeline: Fetching broad market RSS and generating Playwright summaries...")
    res = await fetch_broad_market_rss(max_age_hours=24)
    
    print("\nFetch complete.")
    print(f"Metadata: {res.get('metadata')}")
    
    print("\nStarting pipeline part 2: LLM scoring for market-moving catalysts (Zero Fetch Mode)...")
    latest_file = max(glob.glob("outputs/mapped_news_*.json"), key=os.path.getctime)
    
    ret = subprocess.run([
        ".venv/bin/python3", "tools/web/article-ranker.py", 
        "--input", latest_file, 
        "--no-fetch"
    ])
    
    if ret.returncode == 0:
        print("\nPipeline entirely finished! Check outputs/scored_articles_<timestamp>.json")
    else:
        print("\nError running the ranking script.")

if __name__ == "__main__":
    asyncio.run(main())
