#!/usr/bin/env python3
"""
Render log watcher - fetches logs from Render API and updates Desktop report.

Usage:
    python scripts/render_watch.py --minutes 30
    python scripts/render_watch.py --minutes 10

Environment:
    Reads from ~/Desktop/TRT_RENDER.env (Windows: %USERPROFILE%/Desktop/TRT_RENDER.env)
    Required keys: RENDER_API_KEY, RENDER_SERVICE_ID

Output:
    - ~/Desktop/TRT_RENDER_LAST_LOGS.txt (raw logs)
    - ~/Desktop/TRT_REPORT.md (updated with log summary)
"""

import os
import sys
import re
import json
import argparse
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

try:
    import requests
except ImportError:
    print("ERROR: requests library not installed. Run: pip install requests")
    sys.exit(1)

# Desktop path detection
def get_desktop_path() -> Path:
    """Get Desktop path for current OS."""
    if sys.platform == "win32":
        desktop = Path(os.getenv("USERPROFILE", "")) / "Desktop"
    else:
        desktop = Path.home() / "Desktop"
    
    # Fallback if Desktop doesn't exist
    if not desktop.exists():
        desktop = Path.home() / "_desktop"
        desktop.mkdir(exist_ok=True)
        print(f"WARNING: Desktop not found, using fallback: {desktop}")
    
    return desktop


def load_render_env() -> Tuple[str, str]:
    """
    Load RENDER_API_KEY and RENDER_SERVICE_ID from Desktop env file.
    
    Returns:
        (api_key, service_id)
    
    Raises:
        SystemExit if file/key missing with helpful error message.
    """
    desktop = get_desktop_path()
    env_file = desktop / "TRT_RENDER.env"
    
    if not env_file.exists():
        print("=" * 60)
        print("ERROR: TRT_RENDER.env file not found")
        print("=" * 60)
        print(f"Expected location: {env_file}")
        print("")
        print("Create this file with:")
        print("  RENDER_API_KEY=your_api_key_here")
        print("  RENDER_SERVICE_ID=your_service_id_here")
        print("")
        print("How to get keys:")
        print("  1. RENDER_API_KEY: Render Dashboard → Account Settings → API Keys")
        print("  2. RENDER_SERVICE_ID: Render Dashboard → Your Service → Settings → Service ID")
        print("")
        print("See docs/RENDER_LOG_WATCH.md for detailed instructions.")
        sys.exit(1)
    
    # Parse env file
    env_vars = {}
    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
    except Exception as e:
        print(f"ERROR: Failed to read {env_file}: {e}")
        sys.exit(1)
    
    api_key = env_vars.get("RENDER_API_KEY", "").strip()
    service_id = env_vars.get("RENDER_SERVICE_ID", "").strip()
    
    if not api_key:
        print("ERROR: RENDER_API_KEY not found in TRT_RENDER.env")
        sys.exit(1)
    
    if not service_id:
        print("ERROR: RENDER_SERVICE_ID not found in TRT_RENDER.env")
        sys.exit(1)
    
    return api_key, service_id


def fetch_render_logs(api_key: str, service_id: str, minutes: int = 30) -> List[str]:
    """
    Fetch logs from Render API for the last N minutes.
    
    Args:
        api_key: Render API key
        service_id: Render service ID
        minutes: Number of minutes to fetch (default 30)
    
    Returns:
        List of log lines (strings)
    """
    # Render API endpoint for logs
    # https://api.render.com/v1/services/{serviceId}/logs
    url = f"https://api.render.com/v1/services/{service_id}/logs"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    
    # Calculate timestamp for "since" parameter
    since_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    since_timestamp = int(since_time.timestamp())
    
    params = {
        "since": since_timestamp,
        "limit": 1000,  # Max lines per request
    }
    
    all_logs = []
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Render API returns logs in different formats
        # Try to extract log lines
        if isinstance(data, dict):
            # Format: {"logs": [{"message": "...", "timestamp": ...}, ...]}
            if "logs" in data:
                for log_entry in data["logs"]:
                    if isinstance(log_entry, dict):
                        message = log_entry.get("message", "")
                        timestamp = log_entry.get("timestamp", "")
                        if message:
                            all_logs.append(f"[{timestamp}] {message}")
                    elif isinstance(log_entry, str):
                        all_logs.append(log_entry)
            # Format: {"data": "log lines as string"}
            elif "data" in data:
                log_text = data["data"]
                if isinstance(log_text, str):
                    all_logs = log_text.split("\n")
        elif isinstance(data, list):
            # Format: [{"message": "...", ...}, ...]
            for log_entry in data:
                if isinstance(log_entry, dict):
                    message = log_entry.get("message", "")
                    timestamp = log_entry.get("timestamp", "")
                    if message:
                        all_logs.append(f"[{timestamp}] {message}")
                elif isinstance(log_entry, str):
                    all_logs.append(log_entry)
        elif isinstance(data, str):
            # Format: plain text logs
            all_logs = data.split("\n")
        
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to fetch logs from Render API: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response body: {e.response.text[:500]}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected error fetching logs: {e}")
        sys.exit(1)
    
    return all_logs


def parse_log_line(line: str) -> Dict[str, Optional[str]]:
    """
    Parse a log line to extract structured information.
    
    Returns:
        Dict with: cid, update_id, event_name, log_level, message
    """
    result = {
        "cid": None,
        "update_id": None,
        "event_name": None,
        "log_level": None,
        "message": line,
    }
    
    # Extract cid (correlation ID)
    cid_match = re.search(r'cid=([a-zA-Z0-9_-]+)', line)
    if cid_match:
        result["cid"] = cid_match.group(1)
    
    # Extract update_id
    update_id_match = re.search(r'update_id=(\d+)', line)
    if update_id_match:
        result["update_id"] = update_id_match.group(1)
    
    # Extract event names (UPDATE_RECEIVED, CALLBACK_RECEIVED, etc.)
    event_patterns = [
        r'UPDATE_RECEIVED',
        r'CALLBACK_RECEIVED',
        r'CALLBACK_ROUTED',
        r'CALLBACK_ACCEPTED',
        r'CALLBACK_REJECTED',
        r'DISPATCH_OK',
        r'DISPATCH_FAIL',
        r'PASSIVE_REJECT',
        r'UNKNOWN_CALLBACK',
        r'EXCEPTION_CAUGHT',
        r'LOCK.*ACQUIRED',
        r'LOCK.*NOT.*ACQUIRED',
        r'ACTIVE MODE',
        r'PASSIVE MODE',
    ]
    
    for pattern in event_patterns:
        if re.search(pattern, line, re.IGNORECASE):
            result["event_name"] = pattern.replace(r'.*', '').replace('.*', '')
            break
    
    # Extract log level
    if re.search(r'\bERROR\b', line, re.IGNORECASE):
        result["log_level"] = "ERROR"
    elif re.search(r'\bWARNING\b', line, re.IGNORECASE):
        result["log_level"] = "WARNING"
    elif re.search(r'\bINFO\b', line, re.IGNORECASE):
        result["log_level"] = "INFO"
    elif re.search(r'\bDEBUG\b', line, re.IGNORECASE):
        result["log_level"] = "DEBUG"
    
    return result


def analyze_logs(logs: List[str]) -> Dict:
    """
    Analyze logs and extract statistics.
    
    Returns:
        Dict with counts, top errors, etc.
    """
    stats = {
        "total_lines": len(logs),
        "errors": 0,
        "warnings": 0,
        "exceptions": 0,
        "unknown_callbacks": 0,
        "dispatch_ok": 0,
        "dispatch_fail": 0,
        "passive_reject": 0,
        "lock_acquired": 0,
        "lock_not_acquired": 0,
        "top_errors": [],
        "events_by_cid": defaultdict(list),
    }
    
    error_lines = []
    
    for line in logs:
        parsed = parse_log_line(line)
        
        # Count log levels
        if parsed["log_level"] == "ERROR":
            stats["errors"] += 1
            error_lines.append(line)
        elif parsed["log_level"] == "WARNING":
            stats["warnings"] += 1
        
        # Count exceptions
        if "Exception" in line or "Traceback" in line or "Error:" in line:
            stats["exceptions"] += 1
            if line not in error_lines:
                error_lines.append(line)
        
        # Count specific events
        event = parsed["event_name"]
        if event:
            if "UNKNOWN_CALLBACK" in event:
                stats["unknown_callbacks"] += 1
            elif "DISPATCH_OK" in event:
                stats["dispatch_ok"] += 1
            elif "DISPATCH_FAIL" in event:
                stats["dispatch_fail"] += 1
            elif "PASSIVE_REJECT" in event:
                stats["passive_reject"] += 1
            elif "LOCK" in event and "ACQUIRED" in event:
                stats["lock_acquired"] += 1
            elif "LOCK" in event and "NOT" in event:
                stats["lock_not_acquired"] += 1
        
        # Group events by CID
        if parsed["cid"]:
            stats["events_by_cid"][parsed["cid"]].append({
                "event": event,
                "update_id": parsed["update_id"],
                "line": line[:200],  # Truncate for storage
            })
    
    # Top 10 errors (most recent)
    stats["top_errors"] = error_lines[-10:] if len(error_lines) > 10 else error_lines
    
    return stats


def compute_logs_hash(logs: List[str]) -> str:
    """Compute hash of logs for change detection."""
    content = "\n".join(logs)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def load_previous_run_info(desktop: Path) -> Dict:
    """Load previous run info from Desktop for comparison."""
    info_file = desktop / "TRT_RENDER_LAST_RUN.json"
    
    if not info_file.exists():
        return {
            "hash": None,
            "timestamp": None,
            "stats": {},
        }
    
    try:
        with open(info_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "hash": None,
            "timestamp": None,
            "stats": {},
        }


def save_run_info(desktop: Path, logs: List[str], stats: Dict):
    """Save current run info for next comparison."""
    info_file = desktop / "TRT_RENDER_LAST_RUN.json"
    
    run_info = {
        "hash": compute_logs_hash(logs),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
    }
    
    try:
        with open(info_file, "w", encoding="utf-8") as f:
            json.dump(run_info, f, indent=2)
    except Exception as e:
        print(f"WARNING: Failed to save run info: {e}")


def detect_changes(current_stats: Dict, previous_stats: Dict) -> List[str]:
    """Detect changes since previous run."""
    changes = []
    
    if not previous_stats:
        changes.append("First run - no previous data to compare")
        return changes
    
    # Compare counts
    for key in ["errors", "warnings", "exceptions", "unknown_callbacks", 
                "dispatch_ok", "dispatch_fail", "passive_reject"]:
        current = current_stats.get(key, 0)
        previous = previous_stats.get(key, 0)
        if current != previous:
            delta = current - previous
            sign = "+" if delta > 0 else ""
            changes.append(f"{key}: {previous} → {current} ({sign}{delta})")
    
    return changes


def update_desktop_report(desktop: Path, service_id: str, stats: Dict, changes: List[str], minutes: int):
    """Update TRT_REPORT.md on Desktop with log summary."""
    report_file = desktop / "TRT_REPORT.md"
    
    # Read existing report or create new
    if report_file.exists():
        try:
            with open(report_file, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"WARNING: Failed to read existing report: {e}")
            content = "# TRT Reliability + Growth Report\n\n"
    else:
        content = "# TRT Reliability + Growth Report\n\n"
    
    # Generate log summary section
    now = datetime.now(timezone.utc)
    summary_section = f"""
## RENDER LOGS SUMMARY

**Date/Time**: {now.strftime("%Y-%m-%d %H:%M:%S UTC")}  
**Service ID**: `{service_id}`  
**Time Window**: Last {minutes} minutes

### Summary Counts

- **Total Log Lines**: {stats['total_lines']}
- **Errors**: {stats['errors']}
- **Warnings**: {stats['warnings']}
- **Exceptions**: {stats['exceptions']}
- **Unknown Callbacks**: {stats['unknown_callbacks']}
- **DISPATCH_OK**: {stats['dispatch_ok']}
- **DISPATCH_FAIL**: {stats['dispatch_fail']}
- **PASSIVE_REJECT**: {stats['passive_reject']}
- **LOCK Acquired**: {stats['lock_acquired']}
- **LOCK NOT Acquired**: {stats['lock_not_acquired']}

### Changes Since Previous Run

"""
    
    if changes:
        for change in changes:
            summary_section += f"- {change}\n"
    else:
        summary_section += "- No significant changes detected\n"
    
    summary_section += "\n### Top 10 Recent Errors\n\n"
    
    if stats['top_errors']:
        for i, error in enumerate(stats['top_errors'], 1):
            # Truncate long errors
            error_display = error[:300] + "..." if len(error) > 300 else error
            summary_section += f"{i}. `{error_display}`\n\n"
    else:
        summary_section += "No errors found in this time window.\n\n"
    
    summary_section += "---\n\n"
    
    # Insert at the beginning (after title if exists)
    if content.startswith("# TRT"):
        # Find first "---" or end of first section
        insert_pos = content.find("\n---\n")
        if insert_pos == -1:
            insert_pos = content.find("\n\n## ")
            if insert_pos == -1:
                insert_pos = len(content)
        
        content = content[:insert_pos] + summary_section + content[insert_pos:]
    else:
        content = summary_section + content
    
    # Write updated report
    try:
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ Updated {report_file}")
    except Exception as e:
        print(f"ERROR: Failed to write report: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Fetch and analyze Render logs")
    parser.add_argument(
        "--minutes",
        type=int,
        default=30,
        help="Number of minutes to fetch (default: 30)"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Render Log Watcher")
    print("=" * 60)
    print("")
    
    # Load API keys
    print("Loading Render API credentials...")
    try:
        api_key, service_id = load_render_env()
        print(f"✅ Loaded credentials (service_id: {service_id[:8]}...)")
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR: Failed to load credentials: {e}")
        sys.exit(1)
    
    # Fetch logs
    print(f"Fetching logs for last {args.minutes} minutes...")
    try:
        logs = fetch_render_logs(api_key, service_id, args.minutes)
        print(f"✅ Fetched {len(logs)} log lines")
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR: Failed to fetch logs: {e}")
        sys.exit(1)
    
    # Analyze logs
    print("Analyzing logs...")
    stats = analyze_logs(logs)
    print(f"✅ Found {stats['errors']} errors, {stats['warnings']} warnings")
    
    # Save raw logs
    desktop = get_desktop_path()
    logs_file = desktop / "TRT_RENDER_LAST_LOGS.txt"
    try:
        with open(logs_file, "w", encoding="utf-8") as f:
            f.write("\n".join(logs))
        print(f"✅ Saved raw logs to {logs_file}")
    except Exception as e:
        print(f"WARNING: Failed to save raw logs: {e}")
    
    # Load previous run for comparison
    previous_info = load_previous_run_info(desktop)
    changes = detect_changes(stats, previous_info.get("stats", {}))
    
    # Update report
    print("Updating Desktop report...")
    update_desktop_report(desktop, service_id, stats, changes, args.minutes)
    
    # Save run info for next comparison
    save_run_info(desktop, logs, stats)
    
    print("")
    print("=" * 60)
    print("✅ Done!")
    print("=" * 60)
    print(f"Report updated: {desktop / 'TRT_REPORT.md'}")
    print(f"Raw logs saved: {logs_file}")


if __name__ == "__main__":
    main()

