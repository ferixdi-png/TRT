"""
KIE API sanity test - deterministic test for one model (WAN 2.6)
"""

import os
import json
import time
import requests
from pathlib import Path
from typing import Optional, Dict, Any

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

def mask_token(token: str) -> str:
    """Mask API token in logs"""
    if not token or len(token) < 8:
        return "***"
    return token[:4] + "..." + token[-4:]

def post_with_retry(path: str, payload: Dict[str, Any], max_retries: int = 3) -> Dict[str, Any]:
    """POST with retry on 5xx errors"""
    for attempt in range(max_retries):
        try:
            r = requests.post(
                BASE + path,
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json=payload,
                timeout=30,
            )
            # Retry on 5xx, fail fast on 4xx
            if r.status_code >= 500 and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"Server error {r.status_code}, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                continue
            
            try:
                return r.json()
            except:
                return {"error": r.text, "status_code": r.status_code}
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"Timeout, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                continue
            return {"error": "Request timeout", "status_code": 0}
        except Exception as e:
            return {"error": str(e), "status_code": 0}
    return {"error": "Max retries exceeded", "status_code": 0}

def get_with_retry(path: str, max_retries: int = 3) -> Dict[str, Any]:
    """GET with retry on 5xx errors"""
    for attempt in range(max_retries):
        try:
            r = requests.get(
                BASE + path,
                headers={"Authorization": f"Bearer {API_KEY}"},
                timeout=30,
            )
            if r.status_code >= 500 and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"Server error {r.status_code}, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                continue
            
            try:
                return r.json()
            except:
                return {"error": r.text, "status_code": r.status_code}
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"Timeout, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                continue
            return {"error": "Request timeout", "status_code": 0}
        except Exception as e:
            return {"error": str(e), "status_code": 0}
    return {"error": "Max retries exceeded", "status_code": 0}

def main():
    model = os.getenv("KIE_MODEL", "wan/2-6-text-to-video")
    prompt = os.getenv("KIE_PROMPT", "A cinematic cat walking in neon Tokyo, 720p, smooth motion.")
    duration = os.getenv("KIE_DURATION", "5")
    resolution = os.getenv("KIE_RESOLUTION", "720p")
    image_url = os.getenv("KIE_IMAGE_URL")
    video_url = os.getenv("KIE_VIDEO_URL")

    input_data = {
        "prompt": prompt,
        "duration": duration,
        "resolution": resolution,
    }

    # Add optional image_urls
    if image_url:
        input_data["image_urls"] = [image_url]
    
    # Add optional video_urls
    if video_url:
        input_data["video_urls"] = [video_url]

    payload = {
        "model": model,
        "input": input_data
    }

    # Log without full prompt
    prompt_preview = prompt[:50] + "..." if len(prompt) > 50 else prompt
    print(f"CREATE_TASK:")
    print(f"  model: {model}")
    print(f"  prompt: {prompt_preview} ({len(prompt)} chars)")
    print(f"  duration: {duration}, resolution: {resolution}")
    if image_url:
        print(f"  image_url: {image_url[:50]}...")
    if video_url:
        print(f"  video_url: {video_url[:50]}...")
    
    resp = post_with_retry("/api/v1/jobs/createTask", payload)
    
    print(f"\nCREATE_RESP:")
    print(f"  HTTP status: {resp.get('status_code', 'N/A')}")
    print(f"  code: {resp.get('code', 'N/A')}")
    print(f"  msg: {resp.get('msg', 'N/A')}")
    
    if resp.get("status_code"):
        print(f"ERROR: HTTP {resp.get('status_code')} - {resp.get('error')}")
        raise SystemExit("Task creation failed")

    if resp.get("code") != 200:
        print(f"\nERROR: Response code is not 200: {resp.get('code')}")
        print(f"Message: {resp.get('msg', 'No message')}")
        raise SystemExit("Task creation failed - check API key and response")

    task_id = resp.get("data", {}).get("taskId")
    if not task_id:
        print(f"\nERROR: No taskId in response")
        print(f"Response structure: {list(resp.keys())}")
        if "data" in resp:
            print(f"Data keys: {list(resp['data'].keys())}")
        raise SystemExit("No taskId in response")

    print(f"  taskId: {task_id}")
    print(f"\nPolling for completion (timeout: 900s, poll: 3s)...")

    start_time = time.time()
    for i in range(300):  # 900s / 3s = 300 iterations
        info = get_with_retry(f"/api/v1/jobs/recordInfo?taskId={task_id}")
        
        if info.get("status_code"):
            print(f"[{i+1}] ERROR: HTTP {info.get('status_code')} - {info.get('error')}")
            time.sleep(3)
            continue
        
        state = info.get("data", {}).get("state")
        elapsed = int(time.time() - start_time)
        print(f"[{i+1}] ({elapsed}s) state: {state}")
        
        if state in ("success", "fail"):
            print(f"\nFINAL_STATE: {state}")
            result_urls = info.get("data", {}).get("resultUrls", [])
            if result_urls:
                print(f"resultUrls: {len(result_urls)} items")
                for idx, url in enumerate(result_urls[:3], 1):
                    print(f"  [{idx}] {url[:80]}...")
            
            if state == "success":
                print("\nSUCCESS: Task completed successfully!")
            else:
                error_msg = info.get("data", {}).get("errorMessage", "Unknown error")
                print(f"\nFAILED: {error_msg}")
            break
        time.sleep(3)
    else:
        print("\nTIMEOUT: Task did not complete in 900 seconds")

if __name__ == "__main__":
    main()
