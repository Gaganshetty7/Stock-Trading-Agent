from pathlib import Path
from core.logger import RUN_TIMESTAMP, get_logger
from config.settings import BASE_DIR

# Ensure logs/ranker directory exists
log_dir = Path(BASE_DIR) / "logs" / "ranker"
log_dir.mkdir(parents=True, exist_ok=True)

# Use the shared IST timestamp from core.logger
log_file_path = f"logs/ranker/ranker_{RUN_TIMESTAMP}.log"

# Get ranker-specific logger without console flooding
logger = get_logger("ranker", log_file=log_file_path)
