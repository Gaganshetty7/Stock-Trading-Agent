import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict

QUOTA_FILE = Path("logs/api_quota_tracker/quota_usage.json")
QUOTA_COUNT_FILE = Path("logs/api_quota_tracker/quota_counter.txt")


def log_api_usage(key: str, model: str, status: str = "SUCCESS"):
    """Logs a single API request with 12hr timestamp and status."""
    QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%I:%M:%S %p")  # 12hr format
    key_prefix = key[:10] + "..."
    
    # --- Part 1: JSON Log (Detailed) ---
    usage_data = {}
    if QUOTA_FILE.exists():
        try:
            with open(QUOTA_FILE, "r") as f:
                usage_data = json.load(f)
        except:
            usage_data = {}
            
    if date_str not in usage_data:
        usage_data[date_str] = {"requests": [], "summary": {}}
    
    usage_data[date_str]["requests"].append({
        "time": time_str,
        "key": key_prefix,
        "model": model,
        "status": status
    })
    
    summary = usage_data[date_str]["summary"]
    model_key = f"{key_prefix}|{model}|{status}"
    summary[model_key] = summary.get(model_key, 0) + 1
    
    total_calls = sum(ctx for ctx in summary.values())
    remaining = max(0, 1500 - total_calls)
    
    usage_data[date_str]["live_balance"] = {
        "used": total_calls,
        "limit": 1500,
        "remaining": remaining
    }
    
    with open(QUOTA_FILE, "w") as f:
        json.dump(usage_data, f, indent=2)

    # --- Part 2: TXT Counter (Simple Appending) ---
    with open(QUOTA_COUNT_FILE, "a") as f:
        f.write("-" * 60 + "\n")
        f.write(f"[{date_str} {time_str}] CALL: {total_calls} | REMAINING: {remaining}\n")
        f.write(f"STATUS: {status} | MODEL: {model}\n")
        f.write("-" * 60 + "\n\n")

def log_quota_attempt(model: str, status: str = "SKIPPED"):
    """Logs an attempt to use the quota, even if skipped/mocked."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%I:%M:%S %p")
    
    usage = get_today_usage()
    bal = usage.get("live_balance", {})
    rem = bal.get("remaining", "??")
    used = bal.get("used", "??")

    with open(QUOTA_COUNT_FILE, "a") as f:
        f.write("=" * 60 + "\n")
        f.write(f"[{date_str} {time_str}] SESSION ATTEMPT: {status}\n")
        f.write(f"CURRENT USED: {used} | REMAINING: {rem} | MODEL: {model}\n")
        f.write("=" * 60 + "\n\n")


def get_today_usage() -> Dict:
    """Returns usage stats for today."""
    if not QUOTA_FILE.exists():
        return {}
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    with open(QUOTA_FILE, "r") as f:
        usage_data = json.load(f)
        
    return usage_data.get(date_str, {})

DAILY_LIMIT = 1500

def print_usage_report():
    """Prints a human-readable usage report with Used/Remaining balance."""
    if not QUOTA_FILE.exists():
        print("No API usage recorded yet.")
        return
        
    with open(QUOTA_FILE, "r") as f:
        usage_data = json.load(f)
    
    print("\n" + "=" * 55)
    print("API QUOTA USAGE REPORT")
    print("=" * 55)
    
    for date_str, day_data in sorted(usage_data.items()):
        print(f"\n  Date: {date_str}")
        print("-" * 40)
        
        # Summary calculations
        summary = day_data.get("summary", {})
        used = 0
        rejected = 0
        
        for model_key, count in summary.items():
            if "REJECTED_429" in model_key:
                rejected += count
            else:
                used += count
        
        # Balance logic
        remaining = max(0, DAILY_LIMIT - (used + rejected))
        
        print(f"  SUCCESSFUL REQS: {used}")
        print(f"  REJECTED (429):  {rejected}")
        print(f"  DAILY LIMIT:     {DAILY_LIMIT}")
        print(f"  REMAINING:       {remaining}")
        print(f"  ────────────────────────────────")
        
        # Last 10 requests with timestamps
        requests = day_data.get("requests", [])
        if requests:
            print(f"\n  Recent Requests (last 10):")
            for req in requests[-10:]:
                status_icon = "[OK]" if req.get("status") == "SUCCESS" else "[X]"
                print(f"    {req['time']}  |  {status_icon} {req.get('status', '???').ljust(12)}  |  {req['model']}  |  {req['key']}")
    
    print("\n" + "=" * 55)

if __name__ == "__main__":
    print_usage_report()
