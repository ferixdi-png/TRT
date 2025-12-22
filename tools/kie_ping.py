"""
Minimal KIE API ping test - single POST request
"""

import os
import json
import requests

API_KEY = os.getenv("KIE_API_KEY", "4d49a621bc589222a2769978cb725495")
BASE = "https://api.kie.ai"

payload = {
    "model": "wan/2-6-text-to-video",
    "input": {
        "prompt": "A cat walking in Tokyo",
        "duration": "5",
        "resolution": "720p"
    }
}

r = requests.post(
    f"{BASE}/api/v1/jobs/createTask",
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    },
    json=payload,
    timeout=30
)

print(f"HTTP Status: {r.status_code}")

try:
    resp_json = r.json()
    print("Response JSON:")
    print(json.dumps(resp_json, indent=2, ensure_ascii=False))
    
    task_id = resp_json.get("data", {}).get("taskId")
    if task_id:
        print(f"\nSUCCESS: taskId = {task_id}")
    else:
        print(f"\nWARNING: No taskId in response")
except Exception as e:
    print(f"Error parsing JSON: {e}")
    print(f"Response text: {r.text}")



