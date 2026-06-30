import logging
import os
from datetime import datetime


def setup_logger() -> logging.Logger:
    log_dir = "logs/services/market_alert_service"
    os.makedirs(log_dir, exist_ok=True)

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
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"{log_dir}/market_alert_{timestamp}.log"
    file_fh = logging.FileHandler(log_file)
    file_fh.setFormatter(fmt)
    file_fh.setLevel(logging.DEBUG)
    root.addHandler(file_fh)

    # Silence noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return root
