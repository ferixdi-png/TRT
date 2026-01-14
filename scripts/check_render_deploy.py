#!/usr/bin/env python3
"""
Check Render deploy status via API.
"""

import sys
import os
from pathlib import Path
from typing import Dict, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.render_logs_check import load_render_config


def check_deploy_status(api_key: str, service_id: str) -> Dict:
    """Check latest deploy status."""
    try:
        import requests
    except ImportError:
        try:
            import aiohttp
            import asyncio
        except ImportError:
            return {"error": "Neither requests nor aiohttp available"}
    
    url = f"https://api.render.com/v1/services/{service_id}/deploys"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }
    
    params = {
        "limit": 1  # Latest deploy
    }
    
    try:
        import requests
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            deploys = data if isinstance(data, list) else data.get("deploys", [])
            if deploys:
                latest = deploys[0]
                return {
                    "status": latest.get("status", "unknown"),
                    "created_at": latest.get("createdAt", ""),
                    "finished_at": latest.get("finishedAt", ""),
                    "commit": latest.get("commit", {}).get("id", "") if isinstance(latest.get("commit"), dict) else "",
                }
            return {"error": "No deploys found"}
        else:
            return {"error": f"API returned {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}


def main():
    """Main function."""
    config = load_render_config()
    if not config:
        print("❌ Config not loaded")
        return 1
    
    api_key = config.get("RENDER_API_KEY")
    service_id = config.get("RENDER_SERVICE_ID")
    
    if not api_key or not service_id:
        print("❌ RENDER_API_KEY or RENDER_SERVICE_ID missing")
        return 1
    
    print("🔍 Checking deploy status...")
    status = check_deploy_status(api_key, service_id)
    
    if "error" in status:
        print(f"❌ Error: {status['error']}")
        return 1
    
    print(f"✅ Latest deploy:")
    print(f"  Status: {status.get('status', 'unknown')}")
    print(f"  Created: {status.get('created_at', 'unknown')}")
    print(f"  Finished: {status.get('finished_at', 'unknown')}")
    print(f"  Commit: {status.get('commit', 'unknown')}")
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

