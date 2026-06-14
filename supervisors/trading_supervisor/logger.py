from pathlib import Path
from core.logger import RUN_TIMESTAMP, get_logger
from config.settings import BASE_DIR

# Ensure logs/supervisor directory exists
log_dir = Path(BASE_DIR) / "logs" / "supervisor"
log_dir.mkdir(parents=True, exist_ok=True)

# Use the shared IST timestamp from core.logger
log_file_path = log_dir / f"supervisor_{RUN_TIMESTAMP}.log"

# Get supervisor-specific logger without console flooding
logger = get_logger("TradingSupervisorAgent", log_file=log_file_path, console_output=False)
