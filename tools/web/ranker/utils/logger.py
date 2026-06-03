from datetime import datetime
from pathlib import Path
from core.logger import get_logger

# Generate a timestamped log filename for the ranker
_timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
log_file_path = f"logs/ranker/ranker_{_timestamp}.log"

logger = get_logger("ranker", log_file=log_file_path)

