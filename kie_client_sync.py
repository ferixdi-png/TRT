"""
Synchronous KIE API client - unified interface for all KIE operations
"""

import os
import json
import time
import logging
import requests
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to load from .env if exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


def mask_token(token: str) -> str:
    """Mask API token in logs"""
    if not token or len(token) < 8:
        return "***"
    return token[:4] + "..." + token[-4:]


class KieClient:
    """Synchronous KIE API client"""
    
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = (base_url or os.getenv("KIE_API_URL", "https://api.kie.ai")).rstrip("/")
        self.api_key = api_key or os.getenv("KIE_API_KEY")
        if not self.api_key:
            raise ValueError("KIE_API_KEY must be set (environment variable or parameter)")
        self.timeout = int(os.getenv("KIE_TIMEOUT_SECONDS", "30"))
    
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None, max_retries: int = 3) -> Dict[str, Any]:
        """Internal request method with retry logic"""
        url = f"{self.base_url}{path}"
        
        for attempt in range(max_retries):
            try:
                if method == "POST":
                    r = requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
                else:
                    r = requests.get(url, headers=self._headers(), timeout=self.timeout)
                
                # Retry on 5xx, fail fast on 4xx
                if r.status_code >= 500 and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"Server error {r.status_code}, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                
                try:
                    resp_data = r.json()
                    # Log without secrets
                    logger.debug(f"KIE {method} {path}: status={r.status_code}, code={resp_data.get('code')}")
                    return resp_data
                except:
                    return {"error": r.text, "status_code": r.status_code, "http_status": r.status_code}
                    
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"Timeout, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                return {"error": "Request timeout", "status_code": 0, "http_status": 0}
            except Exception as e:
                logger.error(f"Request exception: {e}", exc_info=True)
                return {"error": str(e), "status_code": 0, "http_status": 0}
        
        return {"error": "Max retries exceeded", "status_code": 0, "http_status": 0}
    
    def create_task(self, model: str, input_data: Dict[str, Any], callback_url: Optional[str] = None) -> str:
        """
        Create a task and return task_id.
        
        Args:
            model: Model ID (e.g., "wan/2-6-text-to-video")
            input_data: Input parameters dict
            callback_url: Optional callback URL
        
        Returns:
            task_id (str)
        
        Raises:
            ValueError: If request fails or no taskId in response
        """
        payload = {
            "model": model,
            "input": input_data
        }
        if callback_url:
            payload["callBackUrl"] = callback_url
        
        # Log without full prompt
        prompt_preview = input_data.get("prompt", "")[:50] + "..." if len(input_data.get("prompt", "")) > 50 else input_data.get("prompt", "")
        logger.info(f"event=kie.create_task model={model} prompt_len={len(input_data.get('prompt', ''))}")
        
        resp = self._request("POST", "/api/v1/jobs/createTask", payload)
        
        if resp.get("status_code") or resp.get("http_status"):
            error_msg = resp.get("error", "Unknown error")
            logger.error(f"event=kie.create_task model={model} status=error error={error_msg}")
            raise ValueError(f"HTTP error: {error_msg}")
        
        code = resp.get("code")
        if code != 200:
            msg = resp.get("msg", "Unknown error")
            logger.error(f"event=kie.create_task model={model} status=error code={code} msg={msg}")
            raise ValueError(f"API error {code}: {msg}")
        
        task_id = resp.get("data", {}).get("taskId")
        if not task_id:
            logger.error(f"event=kie.create_task model={model} status=error error=no_task_id")
            raise ValueError("No taskId in response")
        
        logger.info(f"event=kie.create_task model={model} status=success task_id={task_id}")
        return task_id
    
    def get_task(self, task_id: str) -> Dict[str, Any]:
        """
        Get task status and data.
        
        Args:
            task_id: Task ID
        
        Returns:
            Response dict with data.state, data.resultUrls, etc.
        
        Raises:
            ValueError: If request fails
        """
        resp = self._request("GET", f"/api/v1/jobs/recordInfo?taskId={task_id}")
        
        if resp.get("status_code") or resp.get("http_status"):
            error_msg = resp.get("error", "Unknown error")
            logger.error(f"event=kie.get_task task_id={task_id} status=error error={error_msg}")
            raise ValueError(f"HTTP error: {error_msg}")
        
        code = resp.get("code")
        if code != 200:
            msg = resp.get("msg", "Unknown error")
            logger.error(f"event=kie.get_task task_id={task_id} status=error code={code} msg={msg}")
            raise ValueError(f"API error {code}: {msg}")
        
        state = resp.get("data", {}).get("state")
        logger.debug(f"event=kie.get_task task_id={task_id} state={state}")
        return resp
    
    def wait_task(self, task_id: str, timeout_s: int = 900, poll_s: int = 3) -> Dict[str, Any]:
        """
        Wait for task completion.
        
        Args:
            task_id: Task ID
            timeout_s: Maximum wait time in seconds (default 900)
            poll_s: Poll interval in seconds (default 3)
        
        Returns:
            Final response dict with data.state, data.resultUrls
        
        Raises:
            TimeoutError: If task doesn't complete in timeout
            ValueError: If task fails or request error
        """
        max_iterations = timeout_s // poll_s
        start_time = time.time()
        
        for i in range(max_iterations):
            try:
                resp = self.get_task(task_id)
                state = resp.get("data", {}).get("state")
                elapsed = int(time.time() - start_time)
                logger.info(f"event=kie.poll task_id={task_id} state={state} elapsed={elapsed}s iteration={i+1}")
                
                if state in ("success", "fail"):
                    if state == "success":
                        result_urls = resp.get("data", {}).get("resultUrls", [])
                        logger.info(f"event=kie.poll task_id={task_id} status=success result_urls_count={len(result_urls)}")
                        return resp
                    else:
                        error_msg = resp.get("data", {}).get("errorMessage", "Unknown error")
                        logger.error(f"event=kie.poll task_id={task_id} status=fail error={error_msg}")
                        raise ValueError(f"Task failed: {error_msg}")
                
                time.sleep(poll_s)
            except ValueError as e:
                # If it's a task failure (fail state), re-raise
                if "Task failed" in str(e):
                    raise
                # Otherwise, retry on request errors
                logger.warning(f"event=kie.poll task_id={task_id} iteration={i+1} error={e}, retrying...")
                time.sleep(poll_s)
        
        elapsed = int(time.time() - start_time)
        logger.error(f"event=kie.poll task_id={task_id} status=timeout elapsed={elapsed}s")
        raise TimeoutError(f"Task {task_id} did not complete in {timeout_s}s")


# Self-check
if __name__ == "__main__":
    try:
        from kie_client_sync import KieClient
        print("✅ kie_client_sync imported successfully")
    except Exception as e:
        print(f"❌ Import error: {e}")
