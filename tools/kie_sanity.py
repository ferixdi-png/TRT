"""
KIE API sanity test - deterministic test for one model (WAN 2.6)
"""

import os
import json
import time
import requests
from pathlib import Path

# Try to load from .env if exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

BASE = "https://api.kie.ai"
API_KEY = os.getenv("KIE_API_KEY")
if not API_KEY:
    raise SystemExit("ERROR: KIE_API_KEY environment variable not set")

def post(path, payload):
    r = requests.post(
        BASE + path,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=60,
    )
    # Don't raise on errors - return JSON for inspection
    try:
        return r.json()
    except:
        return {"error": r.text, "status_code": r.status_code}

def get(path):
    r = requests.get(
        BASE + path,
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()

def main():
    model = os.getenv("KIE_MODEL", "wan/2-6-text-to-video")
    prompt = os.getenv("KIE_PROMPT", "A cinematic cat walking in neon Tokyo, 720p, smooth motion.")
    duration = os.getenv("KIE_DURATION", "5")
    resolution = os.getenv("KIE_RESOLUTION", "720p")

    payload = {
        "model": model,
        "input": {
            "prompt": prompt,
            "duration": duration,
            "resolution": resolution,
        }
    }

    print("CREATE:", json.dumps(payload, indent=2))
    try:
        resp = post("/api/v1/jobs/createTask", payload)
    except requests.exceptions.HTTPError as e:
        print(f"HTTP ERROR: {e}")
        if hasattr(e.response, 'json'):
            try:
                resp = e.response.json()
                print("CREATE_RESP:", json.dumps(resp, indent=2, ensure_ascii=False))
            except:
                print(f"Response text: {e.response.text}")
        raise SystemExit(f"Request failed: {e}")
    
    print("CREATE_RESP:", json.dumps(resp, indent=2, ensure_ascii=False))

    # Check response structure
    if resp.get("code") != 200:
        print(f"\n⚠️  Response code is not 200: {resp.get('code')}")
        print(f"Message: {resp.get('msg', 'No message')}")
        raise SystemExit("Task creation failed - check API key and response")

    task_id = resp.get("data", {}).get("taskId")
    if not task_id:
        print(f"\n⚠️  No taskId in response")
        print(f"Response structure: {list(resp.keys())}")
        if "data" in resp:
            print(f"Data keys: {list(resp['data'].keys())}")
        raise SystemExit(f"No taskId in response")

    print(f"\nTask ID: {task_id}")
    print("Polling for completion...")

    for i in range(120):
        info = get(f"/api/v1/jobs/recordInfo?taskId={task_id}")
        state = info.get("data", {}).get("state")
        print(f"[{i+1}] STATE: {state}")
        if state in ("success", "fail"):
            print("\nFINAL:", json.dumps(info, ensure_ascii=False, indent=2))
            break
        time.sleep(3)
    else:
        print("TIMEOUT: Task did not complete in 600 seconds")

if __name__ == "__main__":
    main()
