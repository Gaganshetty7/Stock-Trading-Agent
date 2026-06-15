import logging
import os
from datetime import datetime
from core.logger import RUN_TIMESTAMP

def setup_logger() -> logging.Logger:
    os.makedirs("logs", exist_ok=True)

    root = logging.getLogger()
    # Capture everything at DEBUG level in the root
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Console (INFO and above only) ────────────────────────────────────────
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.setLevel(logging.INFO)
    root.addHandler(console)

    # ── Full service file log (DEBUG and above) ──────────────────────────────
    os.makedirs("logs/services/buy-zone-alert-service", exist_ok=True)
    log_file = f"logs/services/buy-zone-alert-service/bz_alert_{RUN_TIMESTAMP}.log"
    file_fh = logging.FileHandler(log_file)
    file_fh.setFormatter(fmt)
    file_fh.setLevel(logging.DEBUG)
    root.addHandler(file_fh)

    # Silence noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)

    return root
