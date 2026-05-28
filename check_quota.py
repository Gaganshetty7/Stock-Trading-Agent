import os, asyncio, time
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
_KEY = os.environ.get("GEMINI_KEY_4", "")

async def check():
    if not _KEY:
        print("KEY 4 NOT FOUND")
        return
    client = genai.Client(api_key=_KEY)
    
    # Try multiple models to see which one works and if we get quota info
    models_to_test = ["gemini-1.5-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash-latest"]
    
    for m in models_to_test:
        print(f"Testing {m}...")
        try:
            response = client.models.generate_content(
                model=m,
                contents="test"
            )
            print(f"  SUCCESS: {m}")
        except Exception as e:
            print(f"  FAILED: {m} - {str(e)[:200]}")

if __name__ == "__main__":
    asyncio.run(check())
