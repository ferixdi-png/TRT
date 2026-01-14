"""
Strict KIE AI Client - единственный источник правды для работы с KIE API

Following felores/kie-ai-mcp-server patterns:
- Validate inputs against SOURCE_OF_TRUTH before API calls
- Strict contract: create_task returns task_id (raises on error)
- Idempotent operations with retry/backoff
- Callback URL injection
- Detailed logging for production debugging

CRITICAL: This is the ONLY KIE client in the project.
All other clients (kie_client.py, kie_client_sync.py, etc.) are DEPRECATED.
"""

import os
import asyncio
import logging
import random
import json
from typing import Dict, Any, Optional
from pathlib import Path

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

logger = logging.getLogger(__name__)


class KIEError(Exception):
    """Base KIE error"""
    pass


class KIENetworkError(KIEError):
    """Network/timeout error (retriable)"""
    pass


class KIEServerError(KIEError):
    """5xx server error (retriable)"""
    pass


class KIERateLimitError(KIEError):
    """429 rate limit (retriable with backoff)"""
    pass


class KIEClientError(KIEError):
    """4xx client error (NOT retriable)"""
    pass


class KIEValidationError(KIEError):
    """Input validation failed before API call"""
    pass


def load_source_of_truth() -> Dict[str, Any]:
    """Load KIE_SOURCE_OF_TRUTH.json for validation."""
    sot_path = Path(__file__).parent.parent.parent / "models" / "KIE_SOURCE_OF_TRUTH.json"
    if not sot_path.exists():
        logger.warning(f"SOURCE_OF_TRUTH not found: {sot_path}")
        return {"version": "missing", "models": {}}
    
    with open(sot_path) as f:
        data = json.load(f)
    
    logger.info(f"✅ Loaded SOURCE_OF_TRUTH v{data.get('version')} ({len(data.get('models', {}))} models)")
    return data


class StrictKIEClient:
    """
    Production-ready KIE client with validation and retry logic.
    
    Key features:
    - Pre-validates inputs against SOURCE_OF_TRUTH
    - Exponential backoff with jitter
    - Detailed logging (request/response)
    - Callback URL injection
    - Raises on errors (no silent failures)
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
        validate_inputs: bool = True
    ):
        if not AIOHTTP_AVAILABLE:
            raise ImportError("aiohttp is required for StrictKIEClient")
        
        self.api_key = api_key or os.getenv('KIE_API_KEY')
        if not self.api_key:
            raise ValueError("KIE_API_KEY not configured")
        
        self.base_url = (base_url or os.getenv('KIE_API_URL', 'https://api.kie.ai')).rstrip('/')
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.validate_inputs = validate_inputs
        
        # Load SOURCE_OF_TRUTH for validation
        self.source_of_truth = load_source_of_truth() if validate_inputs else None
        
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session
    
    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _validate_model(self, model_id: str) -> None:
        """Validate model exists in SOURCE_OF_TRUTH."""
        if not self.validate_inputs or not self.source_of_truth:
            return
        
        models = self.source_of_truth.get('models', {})
        if model_id not in models:
            available = list(models.keys())[:10]
            raise KIEValidationError(
                f"Unknown model '{model_id}'. "
                f"Available: {available}... (total {len(models)} models)"
            )
    
    def _validate_inputs(self, model_id: str, input_params: Dict[str, Any]) -> None:
        """
        Validate input parameters against SOURCE_OF_TRUTH schema.
        
        NOTE: Currently basic validation, can be extended to check:
        - Required fields
        - Field types
        - Enum values
        - Ranges
        """
        if not self.validate_inputs or not self.source_of_truth:
            return
        
        models = self.source_of_truth.get('models', {})
        model_spec = models.get(model_id, {})
        schema = model_spec.get('input_schema', {})
        
        # Basic validation: warn about unexpected fields
        expected_fields = set(schema.keys())
        provided_fields = set(input_params.keys())
        unexpected = provided_fields - expected_fields
        
        if unexpected:
            logger.warning(
                f"[KIE_VALIDATION] Unexpected fields for {model_id}: {unexpected}. "
                f"Expected: {expected_fields}"
            )
    
    async def create_task(
        self,
        model_id: str,
        input_params: Dict[str, Any],
        callback_url: Optional[str] = None
    ) -> str:
        """
        Create KIE task with validation and retry.
        
        Args:
            model_id: Model ID (e.g., "wan/2-5-standard-text-to-video")
            input_params: Input parameters dict (validated against SOURCE_OF_TRUTH)
            callback_url: Optional callback URL
        
        Returns:
            task_id (str): KIE task ID for status polling
        
        Raises:
            KIEValidationError: Invalid model or inputs
            KIEClientError: 4xx error (bad request)
            KIEServerError: 5xx error (after retries)
            KIENetworkError: Network/timeout (after retries)
            KIERateLimitError: Rate limit (after retries)
        """
        # PRE-FLIGHT VALIDATION
        self._validate_model(model_id)
        self._validate_inputs(model_id, input_params)
        
        # Build payload
        payload = {
            "model": model_id,
            "input": input_params
        }
        if callback_url:
            payload["callBackUrl"] = callback_url
        
        # Log request (for debugging)
        logger.info(
            f"[KIE_REQUEST] POST /createTask model={model_id} "
            f"inputs={len(input_params)} callback={bool(callback_url)}"
        )
        logger.debug(f"[KIE_PAYLOAD] {json.dumps(payload, ensure_ascii=False)}")
        
        # Execute with retry
        response = await self._request_with_retry(
            method='POST',
            path='/api/v1/jobs/createTask',
            json=payload
        )
        
        # Extract task_id
        if response.get('code') != 200:
            error = response.get('msg', 'Unknown error')
            raise KIEClientError(f"KIE API returned code {response.get('code')}: {error}")
        
        data = response.get('data', {})
        task_id = data.get('taskId')
        
        if not task_id:
            raise KIEClientError(f"No taskId in response: {response}")
        
        logger.info(f"[KIE_RESPONSE] task_id={task_id} model={model_id}")
        return task_id
    
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get task status from KIE API.
        
        Args:
            task_id: KIE task ID
        
        Returns:
            {
                'state': 'waiting' | 'success' | 'fail',
                'resultJson': str (JSON string with resultUrls),
                'failMsg': str (if failed),
                'costTime': int (milliseconds),
                ...
            }
        
        Raises:
            KIEError: If request fails
        """
        logger.debug(f"[KIE_STATUS] task_id={task_id}")
        
        response = await self._request_with_retry(
            method='GET',
            path=f'/api/v1/jobs/recordInfo?taskId={task_id}'
        )
        
        if response.get('code') != 200:
            error = response.get('msg', 'Unknown error')
            raise KIEClientError(f"Failed to get status: {error}")
        
        data = response.get('data', {})
        state = data.get('state', 'unknown')
        
        logger.debug(f"[KIE_STATUS] task_id={task_id} state={state}")
        return data
    
    async def _request_with_retry(
        self,
        method: str,
        path: str,
        json: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Execute HTTP request with exponential backoff retry."""
        url = f"{self.base_url}{path}"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                session = await self._get_session()
                
                if method == 'POST':
                    async with session.post(url, json=json, headers=headers) as resp:
                        response_text = await resp.text()
                        
                        # Try to parse as JSON
                        try:
                            data = await resp.json()
                        except Exception:
                            data = {'raw': response_text, 'status': resp.status}
                        
                        # Handle HTTP errors
                        if resp.status >= 400:
                            if resp.status == 429:
                                raise KIERateLimitError(f"Rate limit: {data}")
                            elif resp.status >= 500:
                                raise KIEServerError(f"Server error {resp.status}: {data}")
                            elif resp.status >= 400:
                                raise KIEClientError(f"Client error {resp.status}: {data}")
                        
                        return data
                
                elif method == 'GET':
                    async with session.get(url, headers=headers) as resp:
                        data = await resp.json()
                        
                        if resp.status >= 400:
                            if resp.status == 429:
                                raise KIERateLimitError(f"Rate limit: {data}")
                            elif resp.status >= 500:
                                raise KIEServerError(f"Server error {resp.status}: {data}")
                            elif resp.status >= 400:
                                raise KIEClientError(f"Client error {resp.status}: {data}")
                        
                        return data
            
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = KIENetworkError(f"Network error: {e}")
            
            except (KIEServerError, KIERateLimitError) as e:
                last_error = e
            
            except KIEClientError as e:
                # 4xx errors - don't retry
                raise
            
            # Retry logic
            if attempt < self.max_retries:
                # Exponential backoff with jitter
                delay = min(
                    (2 ** attempt) + random.uniform(0, 1),
                    60.0  # Max 60 seconds
                )
                
                # Extra delay for rate limit
                if isinstance(last_error, KIERateLimitError):
                    delay *= 2
                
                logger.warning(
                    f"[KIE_RETRY] Attempt {attempt + 1}/{self.max_retries + 1} failed: {last_error}, "
                    f"retrying in {delay:.1f}s"
                )
                await asyncio.sleep(delay)
            else:
                # All retries exhausted
                logger.error(f"[KIE_ERROR] All retries failed: {last_error}")
                raise last_error


# Singleton instance
_client: Optional[StrictKIEClient] = None


def get_kie_client(
    api_key: Optional[str] = None,
    validate_inputs: bool = True
) -> StrictKIEClient:
    """Get singleton KIE client instance."""
    global _client
    if _client is None:
        _client = StrictKIEClient(
            api_key=api_key,
            validate_inputs=validate_inputs
        )
    return _client


async def close_kie_client():
    """Close singleton client (for cleanup)."""
    global _client
    if _client:
        await _client.close()
        _client = None
