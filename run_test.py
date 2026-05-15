import asyncio
from tools.web.broad_market_feeds.broad_rss_fetcher import fetch_broad_market_rss

async def main():
    print("Starting test...")
    # This invokes the tool, which now handles fetching, mapping, cleanup, and saving.
    res = await fetch_broad_market_rss(max_age_hours=24)
    
    print("\nTest complete.")
    print(f"Metadata: {res.get('metadata')}")
    print(f"Mapped news for {res['metadata']['total_companies']} companies.")

if __name__ == "__main__":
    asyncio.run(main())
