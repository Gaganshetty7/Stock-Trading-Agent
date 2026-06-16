import glob
import json
import os
from typing import Dict, Tuple, Optional
from core.logger import get_logger

logger = get_logger("TradeStrategy")

def load_technicals_payload(file_path: Optional[str] = None) -> Tuple[Dict, str]:
    """
    Locates and loads the JSON technical analysis payload.
    If no file_path is given, defaults to the latest analysis_batch_*.json
    in outputs/TechnicalAnalystAgent/technicals/
    """
    if not file_path:
        files = glob.glob("outputs/TechnicalAnalystAgent/technicals/analysis_batch_*.json")
        if not files:
            raise ValueError("No analysis_batch_*.json found in outputs/TechnicalAnalystAgent/technicals/")
        file_path = max(files, key=os.path.getctime)
        
    logger.info(f"Loading technicals payload from: {file_path}")
    if not os.path.exists(file_path):
        raise ValueError(f"Technical data file not found: {file_path}")
        
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    return data, file_path
