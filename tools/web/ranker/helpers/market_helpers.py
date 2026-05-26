import re
import pytz
from datetime import datetime

def is_market_open() -> bool:
    """Checks if current time is within Indian Market hours (09:15 - 15:30 IST)."""
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    
    # Check weekday (0-4 are Monday-Friday)
    if now.weekday() > 4:
        return False
        
    start_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
    end_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    return start_time <= now <= end_time

def parse_age_to_mins(age_str: str) -> int:
    """Converts age strings like '2h ago', '15m ago' into integer minutes."""
    if not age_str:
        return 0
    
    age_str = age_str.lower().strip()
    
    # Match patterns like '2h ago', '15m ago', '30 min ago'
    match = re.search(r'(\d+)\s*(h|m|min)', age_str)
    if not match:
        return 0
        
    value = int(match.group(1))
    unit = match.group(2)
    
    if unit == 'h':
        return value * 60
    return value
