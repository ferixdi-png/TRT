"""
Kie.ai API Client V4 - поддержка новой category-specific архитектуры.
Работает параллельно со старым client для совместимости.
"""
import asyncio
import random
import logging
import os
from typing import Dict, Any, Optional

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

from app.kie.router import (
    get_api_category_for_model,
    get_api_endpoint_for_model,
    get_base_url_for_category,
    load_v4_source_of_truth
)
from .rate_limit import SlidingWindowRateLimiter, RateLimitConfig

logger = logging.getLogger(__name__)

_CREATE_RL = SlidingWindowRateLimiter(
    RateLimitConfig(
        max_requests=int(os.getenv("KIE_CREATE_RL_MAX", "18")),
        per_seconds=float(os.getenv("KIE_CREATE_RL_WINDOW_S", "10")),
        safety_margin=float(os.getenv("KIE_CREATE_RL_MARGIN_S", "0.05")),
    ),
)
_CREATE_SEM = asyncio.Semaphore(int(os.getenv("KIE_CREATE_CONCURRENCY", "8")))



class KieApiClientV4:
    """
    API client для новой архитектуры Kie.ai (v4).
    Поддерживает category-specific endpoints.
    """
    
    def __init__(self, api_key: str | None = None, timeout: int = 30) -> None:
        self.api_key = api_key or os.getenv("KIE_API_KEY")
        if not self.api_key:
            raise ValueError("KIE_API_KEY environment variable is required")
        
        self.timeout = timeout
        self.source_v4 = load_v4_source_of_truth()
        
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    def _make_request(self, url: str, payload: Dict[str, Any]) -> requests.Response:
        """
        Make HTTP request with automatic retry.
        
        Retries on:
        - ConnectionError (network issues)
        - Timeout (slow response)
        
        Does NOT retry on:
        - 4xx errors (client errors - bad request)
        - 5xx errors (server errors - will be handled by caller)
        """
        return requests.post(
            url,
            headers=self._headers(),
            json=payload,
            timeout=self.timeout
        )
    
    async def create_task(self, model_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new generation task.

        Kie enforces a hard per-account limit (documented as 20 new generation requests per 10 seconds).
        Excess returns HTTP 429 and is NOT queued on their side. So we queue locally using:
          - in-process sliding-window rate limiter
          - concurrency semaphore
        """
        endpoint = resolve_v4_endpoint(model_id, KIE_V4_ENDPOINTS)
        if not endpoint:
            return {"state": "fail", "error": f"Unknown model_id: {model_id}"}

        api_category = get_api_category_for_model(model_id)
        adapter = get_v4_payload_adapter(model_id, api_category, endpoint)
        adapted_payload = adapter(payload)

        url = f"{endpoint}/v1/videos/task" if api_category == "video" else f"{endpoint}/api/v1/create"

        max_attempts = int(os.getenv("KIE_CREATE_MAX_ATTEMPTS", "6"))
        base_sleep = float(os.getenv("KIE_CREATE_BASE_SLEEP_S", "1.0"))

        await _CREATE_SEM.acquire()
        try:
            for attempt in range(1, max_attempts + 1):
                await _CREATE_RL.acquire()

                try:
                    response = await asyncio.to_thread(
                        requests.post,
                        url,
                        json=adapted_payload,
                        headers=self._headers(),
                        timeout=self.timeout,
                    )
                except requests.RequestException as e:
                    # network/transient
                    sleep_s = min(20.0, base_sleep * (2 ** (attempt - 1))) * (1.0 + random.random() * 0.25)
                    logger.warning("Kie create_task request exception (attempt %s/%s): %s; sleeping %.2fs", attempt, max_attempts, e, sleep_s)
                    await asyncio.sleep(sleep_s)
                    continue

                # Rate limit: respect Retry-After when possible
                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After") or 10)
                    sleep_s = max(retry_after, 1.0) * (1.0 + random.random() * 0.15)
                    logger.warning("Kie create_task hit 429 (attempt %s/%s). retry_after=%.2fs", attempt, max_attempts, retry_after)
                    await asyncio.sleep(sleep_s)
                    continue

                # Transient upstream failures
                if response.status_code in {500, 502, 503, 504}:
                    sleep_s = min(20.0, base_sleep * (2 ** (attempt - 1))) * (1.0 + random.random() * 0.25)
                    logger.warning("Kie create_task %s (attempt %s/%s). sleeping %.2fs", response.status_code, attempt, max_attempts, sleep_s)
                    await asyncio.sleep(sleep_s)
                    continue

                if response.status_code != 200:
                    return {
                        "state": "fail",
                        "error": f"HTTP {response.status_code}: {response.text[:500]}",
                    }

                try:
                    return response.json()
                except ValueError:
                    return {"state": "fail", "error": "Invalid JSON response from Kie"}

            return {"state": "fail", "error": "Rate-limited / transient errors: exhausted retries"}
        finally:
            _CREATE_SEM.release()

    async def get_record_info(self, task_id: str, model_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get task record info (status checking).
        Этот endpoint все еще универсальный.
        
        Args:
            task_id: Task ID from create_task
        
        Returns:
            Task status and results
        """
        url = "https://api.kie.ai/api/v1/jobs/recordInfo"
        params = {"taskId": task_id}
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await asyncio.to_thread(
                    requests.get,
                    url,
                    headers=self._headers(),
                    params=params,
                    timeout=self.timeout
                )
                
                response.raise_for_status()
                return response.json()
                
            except requests.RequestException as exc:
                logger.warning(f"recordInfo attempt {attempt+1}/{max_retries} failed: {exc}")
                if attempt == max_retries - 1:
                    logger.error(f"Get record info failed: {exc}", exc_info=True)
                    return {"error": str(exc), "state": "fail"}
                await asyncio.sleep(1 * (attempt + 1))
    
    async def poll_task_until_complete(
        self,
        task_id: str,
        max_wait_seconds: int = 300,
        poll_interval: float = 3.0
    ) -> Dict[str, Any]:
        """
        Poll task until completion.
        
        Args:
            task_id: Task ID
            max_wait_seconds: Maximum wait time
            poll_interval: Seconds between polls
        
        Returns:
            Final task data
        """
        start_time = asyncio.get_event_loop().time()
        attempts = 0
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > max_wait_seconds:
                logger.error(f"Task {task_id} timed out after {elapsed:.1f}s")
                return {
                    "error": "Task timeout",
                    "state": "timeout",
                    "taskId": task_id,
                    "elapsed_seconds": elapsed
                }
            
            attempts += 1
            record = await self.get_record_info(task_id)
            
            if 'error' in record:
                return record
            
            state = record.get('state', '').lower()
            logger.info(f"Poll #{attempts} ({elapsed:.1f}s): task {task_id} state={state}")
            
            if state in ['success', 'completed', 'done']:
                logger.info(f"Task {task_id} completed successfully after {elapsed:.1f}s")
                return record
            
            if state in ['fail', 'failed', 'error']:
                logger.error(f"Task {task_id} failed: {record}")
                return record
            
            # Still processing
            await asyncio.sleep(poll_interval)
