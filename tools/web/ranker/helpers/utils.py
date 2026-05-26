import json
import os
import logging
from datetime import datetime
from typing import List, Dict, Optional

# ── Logging Setup ────────────────────────────────────────────────────────────
def setup_ranker_logger():
    log_dir = "logs/ranker_logs"
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"ranker_{timestamp}.log")
    
    logger = logging.getLogger("ranker")
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers
    if not logger.handlers:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(logging.Formatter('%(asctime)s | ranker | %(levelname)s | %(message)s'))
        logger.addHandler(fh)
    
    return logger

# Initialize logger
setup_ranker_logger()
logger = logging.getLogger("ranker")

class QuotaError(Exception):
    """Custom error for 429 rejections."""
    pass

def extract_json_objects(text: str) -> List[Dict]:
    """Robustly extracts JSON snippets from mixed text using bracket counting."""
    results = []
    stack = []
    start_idx = -1

    for i, char in enumerate(text):
        if char == '{':
            if not stack:
                start_idx = i
            stack.append(char)
        elif char == '}':
            if stack:
                stack.pop()
                if not stack:
                    try:
                        results.append(json.loads(text[start_idx:i + 1]))
                    except json.JSONDecodeError:
                        continue
    return results

def robust_json_parser(text: str) -> Optional[Dict]:
    """Finds a valid BatchResponse in LLM output."""
    objs = extract_json_objects(text)
    for obj in objs:
        if "results" in obj:
            return obj
    return None

def truncate(text: str, max_len: int) -> str:
    if not text:
        return ""
    return text[:max_len] + "…" if len(text) > max_len else text
