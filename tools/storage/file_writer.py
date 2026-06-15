import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config.settings import OUTPUTS_DIR
from core.logger import get_logger, RUN_TIMESTAMP

logger = get_logger("file_writer")


async def write_json(filename_prefix: str, data: dict | list, overwrite: bool = False) -> str:
    """
    Writes data as a JSON file to the outputs directory.
    If overwrite is False (default), a timestamp is added to the filename.
    If overwrite is True, the file is saved exactly as {filename_prefix}.json.
    Returns the filepath as a string.
    """
    if overwrite:
        filename = f"{filename_prefix}.json"
    else:
        filename = f"{filename_prefix}_{RUN_TIMESTAMP}.json"
    
    filepath = Path(OUTPUTS_DIR) / filename

    filepath.parent.mkdir(parents=True, exist_ok=True)  # ensure outputs dir exists
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    logger.info(f"Output saved → {filepath}")
    return str(filepath)
