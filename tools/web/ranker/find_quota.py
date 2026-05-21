import os, asyncio
from dotenv import load_dotenv
from google import genai

load_dotenv()
_KEY = os.getenv("GEMINI_RANKING_KEY", "")

async def check():
    client = genai.Client(api_key=_KEY)
    models = client.models.list()
    for m in models:
        try:
            # Simple small test
            client.models.generate_content(model=m.name, contents="hi")
            print(f"!!! QUOTA AVAILABLE: {m.name}")
            return
        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e):
                continue
            # print(f"Skipping {m.name}: {e}")

if __name__ == "__main__":
    asyncio.run(check())
