import os
from dotenv import load_dotenv

load_dotenv()

# Set this to true to interrupt graph before TradeBrainWorker executes
HUMAN_IN_THE_LOOP: bool = os.getenv("HUMAN_IN_THE_LOOP", "False").lower() == "true"
