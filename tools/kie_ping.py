"""
Minimal KIE API ping test - single POST request
"""

import os
import json
import requests

API_KEY = os.getenv("KIE_API_KEY", "").strip()
if not API_KEY:
    raise SystemExit("ERROR: KIE_API_KEY environment variable not set")
BASE = "https://api.kie.ai"

payload = {
    "model": "wan/2-6-text-to-video",
    "input": {
        "prompt": "A cat walking in Tokyo",
        "duration": "5",
        "resolution": "720p"
    }
}

try:
    r = requests.post(
        f"{BASE}/api/v1/jobs/createTask",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=30
    )
except requests.RequestException as exc:
    raise SystemExit(f"HTTP request failed: {exc}") from exc

print(f"HTTP Status: {r.status_code}")

try:
    resp_json = r.json()
except ValueError as exc:
    raise SystemExit(f"Error parsing JSON: {exc}\nResponse text: {r.text}") from exc

print("Response JSON:")
print(json.dumps(resp_json, indent=2, ensure_ascii=False))

task_id = resp_json.get("data", {}).get("taskId")
if task_id:
    print(f"\nSUCCESS: taskId = {task_id}")
else:
    print("\nWARNING: No taskId in response")


