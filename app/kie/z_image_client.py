"""
Lightweight Kie.ai client for z-image model.

Official API:
- POST https://api.kie.ai/api/v1/jobs/createTask
  Body: {"model": "z-image", "input": {"prompt": "...", "aspect_ratio": "1:1"}}
  Response: {"code": 200, "data": {"taskId": "..."}}

- GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=...
  Response: {"code": 200, "data": {"status": "SUCCESS", "output": {"image_url": "..."}}}

Aspect ratios: 1:1, 16:9, 9:16, 4:3, 3:4

This client DOES NOT log API keys or secrets.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Kie.ai task statuses."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass
class ZImageResult:
    """Result from z-image generation."""
    task_id: str
    status: TaskStatus
    image_url: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[dict] = None


class ZImageClient:
    """
    Client for Kie.ai z-image model.
    
    Features:
    - Automatic retries with exponential backoff
    - Timeout protection
    - No secret logging
    - Async/await interface
    """
    
    BASE_URL = "https://api.kie.ai/api/v1/jobs"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self.api_key = api_key or os.getenv("KIE_API_KEY", "")
        self.timeout = timeout
        self.max_retries = max_retries
        
        if not self.api_key:
            logger.warning("[KIE] API key not set, operations will fail")
    
    async def create_task(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        callback_url: Optional[str] = None,
    ) -> ZImageResult:
        """
        Create z-image generation task.
        
        Args:
            prompt: Text prompt for image generation
            aspect_ratio: One of: 1:1, 16:9, 9:16, 4:3, 3:4
            callback_url: Optional webhook for completion notification
        
        Returns:
            ZImageResult with task_id and PENDING status
        
        Raises:
            Exception if API call fails after retries
        """
        if not self.api_key:
            raise ValueError("KIE_API_KEY not configured")
        
        # Validate aspect ratio
        valid_ratios = {"1:1", "16:9", "9:16", "4:3", "3:4"}
        if aspect_ratio not in valid_ratios:
            logger.warning(
                "[KIE] Invalid aspect_ratio=%s, using 1:1", 
                aspect_ratio
            )
            aspect_ratio = "1:1"
        
        # Build request
        payload = {
            "model": "z-image",
            "input": {
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
            }
        }
        
        if callback_url:
            payload["callBackUrl"] = callback_url
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        url = f"{self.BASE_URL}/createTask"
        
        # Retry logic
        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await asyncio.wait_for(
                        client.post(url, json=payload, headers=headers),
                        timeout=self.timeout
                    )
                    
                    # Check HTTP status
                    if resp.status_code != 200:
                        raise Exception(
                            f"HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                    
                    # Parse response
                    data = resp.json()
                    
                    # Check API code
                    code = data.get("code")
                    if code != 200:
                        msg = data.get("msg", "Unknown error")
                        raise Exception(f"API error code={code}: {msg}")
                    
                    # Extract task_id
                    task_data = data.get("data", {})
                    task_id = task_data.get("taskId")
                    
                    if not task_id:
                        raise Exception(f"No taskId in response: {data}")
                    
                    logger.info(
                        "[KIE] Created task_id=%s prompt=%s ratio=%s",
                        task_id, prompt[:50], aspect_ratio
                    )
                    
                    return ZImageResult(
                        task_id=task_id,
                        status=TaskStatus.PENDING,
                        raw_response=data,
                    )
            
            except asyncio.TimeoutError:
                last_error = Exception(f"Timeout after {self.timeout}s")
                logger.warning(
                    "[KIE] createTask timeout (attempt %d/%d)",
                    attempt + 1, self.max_retries
                )
            
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "[KIE] createTask failed (attempt %d/%d): %s",
                    attempt + 1, self.max_retries, exc
                )
            
            # Exponential backoff
            if attempt < self.max_retries - 1:
                delay = 2 ** attempt
                await asyncio.sleep(delay)
        
        # All retries exhausted
        raise Exception(f"Failed after {self.max_retries} attempts: {last_error}")
    
    async def get_task_status(self, task_id: str) -> ZImageResult:
        """
        Get task status and result.
        
        Args:
            task_id: Task ID from create_task()
        
        Returns:
            ZImageResult with current status and image_url if SUCCESS
        
        Raises:
            Exception if API call fails after retries
        """
        if not self.api_key:
            raise ValueError("KIE_API_KEY not configured")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        
        url = f"{self.BASE_URL}/recordInfo?taskId={task_id}"
        
        # Retry logic
        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await asyncio.wait_for(
                        client.get(url, headers=headers),
                        timeout=self.timeout
                    )
                    
                    # Check HTTP status
                    if resp.status_code != 200:
                        raise Exception(
                            f"HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                    
                    # Parse response
                    data = resp.json()
                    
                    # Check API code
                    code = data.get("code")
                    if code != 200:
                        msg = data.get("msg", "Unknown error")
                        raise Exception(f"API error code={code}: {msg}")
                    
                    # Extract status and output
                    task_data = data.get("data", {})
                    status_str = task_data.get("status", "UNKNOWN").upper()
                    
                    # Map to enum
                    try:
                        status = TaskStatus(status_str)
                    except ValueError:
                        status = TaskStatus.UNKNOWN
                    
                    # Extract image URL if SUCCESS
                    image_url = None
                    error = None
                    
                    if status == TaskStatus.SUCCESS:
                        output = task_data.get("output", {})
                        image_url = output.get("image_url") or output.get("url")
                    
                    elif status == TaskStatus.FAILED:
                        error = task_data.get("error") or task_data.get("msg")
                    
                    logger.debug(
                        "[KIE] Status task_id=%s: %s",
                        task_id, status.value
                    )
                    
                    return ZImageResult(
                        task_id=task_id,
                        status=status,
                        image_url=image_url,
                        error=error,
                        raw_response=data,
                    )
            
            except asyncio.TimeoutError:
                last_error = Exception(f"Timeout after {self.timeout}s")
                logger.warning(
                    "[KIE] recordInfo timeout (attempt %d/%d)",
                    attempt + 1, self.max_retries
                )
            
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "[KIE] recordInfo failed (attempt %d/%d): %s",
                    attempt + 1, self.max_retries, exc
                )
            
            # Exponential backoff
            if attempt < self.max_retries - 1:
                delay = 2 ** attempt
                await asyncio.sleep(delay)
        
        # All retries exhausted
        raise Exception(f"Failed after {self.max_retries} attempts: {last_error}")
    
    async def poll_until_complete(
        self,
        task_id: str,
        max_wait: float = 300.0,
        poll_interval: float = 3.0,
    ) -> ZImageResult:
        """
        Poll task status until SUCCESS or FAILED.
        
        Args:
            task_id: Task ID from create_task()
            max_wait: Maximum wait time in seconds (default 5 minutes)
            poll_interval: Seconds between polls (default 3s)
        
        Returns:
            ZImageResult with final status
        
        Raises:
            Exception if timeout or API errors
        """
        start_time = time.monotonic()
        
        while True:
            elapsed = time.monotonic() - start_time
            
            if elapsed > max_wait:
                raise Exception(
                    f"Timeout waiting for task_id={task_id} after {max_wait}s"
                )
            
            result = await self.get_task_status(task_id)
            
            if result.status in (TaskStatus.SUCCESS, TaskStatus.FAILED):
                return result
            
            # Still processing, wait and retry
            await asyncio.sleep(poll_interval)


# Global singleton
_client: Optional[ZImageClient] = None


def get_z_image_client() -> ZImageClient:
    """Get or create global z-image client."""
    global _client
    if _client is None:
        _client = ZImageClient()
    return _client
