from datetime import datetime
from pathlib import Path
from core.logger import get_logger
from config.settings import BASE_DIR

# Ensure logs/ranker directory exists
log_dir = Path(BASE_DIR) / "logs" / "ranker"
log_dir.mkdir(parents=True, exist_ok=True)

# Generate a timestamped log filename for the ranker
_timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
log_file_path = f"logs/ranker/ranker_{_timestamp}.log"

# Get ranker-specific logger without console flooding
logger = get_logger("ranker", log_file=log_file_path)
