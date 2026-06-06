from datetime import datetime
from pathlib import Path
from core.logger import get_logger
from config.settings import BASE_DIR

# Ensure logs/supervisor directory exists
log_dir = Path(BASE_DIR) / "logs" / "supervisor"
log_dir.mkdir(parents=True, exist_ok=True)

# Generate a timestamped log filename for the supervisor
_timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
log_file_path = log_dir / f"supervisor_{_timestamp}.log"

# Get supervisor-specific logger without console flooding
logger = get_logger("TradingSupervisorAgent", log_file=log_file_path, console_output=False)
