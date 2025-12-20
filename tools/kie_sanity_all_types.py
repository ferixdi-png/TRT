"""
KIE Sanity Test - tests one model of each model_type.

This script:
1. Loads models from models/kie_models.yaml
2. Groups models by model_type
3. Selects one model per type for testing
4. Generates minimal valid input based on schema
5. Tests createTask + waitTask for each model type
6. Outputs results table: model | model_type | state | ok/fail | time

If any model_type fails, the script exits with error code 1.
"""

import os
import sys
import json
import time
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

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

MODELS_YAML = Path(__file__).parent.parent / "models" / "kie_models.yaml"

def mask_token(token: str) -> str:
    if not token or len(token) < 8:
        return "***"
    return token[:4] + "..." + token[-4:]

def post_with_retry(path: str, payload: Dict[str, Any], max_retries: int = 3) -> Dict[str, Any]:
    for attempt in range(max_retries):
        try:
            r = requests.post(
                BASE + path,
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json=payload,
                timeout=30,
            )
            if r.status_code >= 500 and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"Server error {r.status_code}, retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            try:
                return r.json()
            except:
                return {"error": r.text, "status_code": r.status_code}
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"Timeout, retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            return {"error": "Request timeout", "status_code": 0}
        except Exception as e:
            return {"error": str(e), "status_code": 0}
    return {"error": "Max retries exceeded", "status_code": 0}

def get_with_retry(path: str, max_retries: int = 3) -> Dict[str, Any]:
    for attempt in range(max_retries):
        try:
            r = requests.get(
                BASE + path,
                headers={"Authorization": f"Bearer {API_KEY}"},
                timeout=30,
            )
            if r.status_code >= 500 and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"Server error {r.status_code}, retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            try:
                return r.json()
            except:
                return {"error": r.text, "status_code": r.status_code}
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"Timeout, retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            return {"error": "Request timeout", "status_code": 0}
        except Exception as e:
            return {"error": str(e), "status_code": 0}
    return {"error": "Max retries exceeded", "status_code": 0}

def generate_minimal_input(model_id: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """Generate minimal valid input for a model"""
    input_data = {}
    
    for param_name, param_schema in schema.items():
        is_required = param_schema.get('required', False)
        param_type = param_schema.get('type', 'string')
        
        if not is_required:
            continue  # Skip optional for minimal test
        
        if param_type == 'string':
            min_len = param_schema.get('min', 1)
            input_data[param_name] = 'test' * max(1, min_len // 4)
        elif param_type == 'enum':
            values = param_schema.get('values', [])
            if values:
                input_data[param_name] = values[0]
        elif param_type == 'array':
            item_type = param_schema.get('item_type', 'string')
            if item_type == 'string':
                if 'url' in param_name.lower():
                    # For URLs, use a placeholder (will fail but tests structure)
                    input_data[param_name] = ['https://example.com/test.jpg']
                else:
                    input_data[param_name] = ['test']
    
    return input_data

def test_model(model_id: str, model_type: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """Test a single model"""
    print(f"\nTesting {model_id} ({model_type})...")
    
    input_data = generate_minimal_input(model_id, schema)
    
    payload = {
        "model": model_id,
        "input": input_data
    }
    
    start_time = time.time()
    
    # Create task
    resp = post_with_retry("/api/v1/jobs/createTask", payload)
    
    if resp.get("status_code"):
        return {
            "model": model_id,
            "model_type": model_type,
            "state": "error",
            "ok": False,
            "error": resp.get('error', 'HTTP error'),
            "time": 0
        }
    
    if resp.get("code") != 200:
        return {
            "model": model_id,
            "model_type": model_type,
            "state": "error",
            "ok": False,
            "error": resp.get('msg', 'API error'),
            "time": 0
        }
    
    task_id = resp.get("data", {}).get("taskId")
    if not task_id:
        return {
            "model": model_id,
            "model_type": model_type,
            "state": "error",
            "ok": False,
            "error": "No taskId",
            "time": 0
        }
    
    # Poll for completion (short timeout for sanity test)
    for i in range(100):  # 100 * 3s = 300s max
        info = get_with_retry(f"/api/v1/jobs/recordInfo?taskId={task_id}")
        
        if info.get("status_code"):
            time.sleep(3)
            continue
        
        state = info.get("data", {}).get("state")
        if state in ("success", "fail"):
            elapsed = int(time.time() - start_time)
            return {
                "model": model_id,
                "model_type": model_type,
                "state": state,
                "ok": state == "success",
                "error": info.get("data", {}).get("failMsg") if state == "fail" else None,
                "time": elapsed
            }
        time.sleep(3)
    
    elapsed = int(time.time() - start_time)
    return {
        "model": model_id,
        "model_type": model_type,
        "state": "timeout",
        "ok": False,
        "error": "Timeout",
        "time": elapsed
    }

def main():
    # Load models registry
    if not MODELS_YAML.exists():
        print(f"ERROR: Models registry not found: {MODELS_YAML}")
        sys.exit(1)
    
    with open(MODELS_YAML, 'r', encoding='utf-8') as f:
        registry = yaml.safe_load(f)
    
    models = registry.get('models', {})
    
    # Group by model_type
    models_by_type: Dict[str, List[tuple]] = {}
    for model_id, model_info in models.items():
        model_type = model_info.get('model_type', 'unknown')
        schema = model_info.get('input', {})
        models_by_type.setdefault(model_type, []).append((model_id, schema))
    
    # Test one model of each type
    results = []
    for model_type, model_list in sorted(models_by_type.items()):
        if not model_list:
            continue
        
        # Pick first model of this type
        model_id, schema = model_list[0]
        result = test_model(model_id, model_type, schema)
        results.append(result)
    
    # Print summary table
    print("\n" + "=" * 80)
    print("SANITY TEST RESULTS")
    print("=" * 80)
    print(f"{'Model':<40} {'Type':<20} {'State':<10} {'OK':<5} {'Time':<10}")
    print("-" * 80)
    
    for r in results:
        ok_str = "OK" if r['ok'] else "FAIL"
        time_str = f"{r['time']}s" if r['time'] else "N/A"
        print(f"{r['model']:<40} {r['model_type']:<20} {r['state']:<10} {ok_str:<5} {time_str:<10}")
        if not r['ok'] and r.get('error'):
            print(f"  Error: {r['error']}")
    
    print("-" * 80)
    success_count = sum(1 for r in results if r['ok'])
    total_count = len(results)
    print(f"Total: {success_count}/{total_count} model types passed")
    
    if success_count < total_count:
        print("\nWARNING: Some model types failed!")
        sys.exit(1)
    else:
        print("\nSUCCESS: All model types passed!")

if __name__ == "__main__":
    main()
