from core.logger import get_logger

# Supervisor logs go to the shared system_logs via the _file_handler in core.logger.
# No dedicated log file needed.
logger = get_logger("TradingSupervisorAgent")
