"""
Async KIE AI client helper.

This module provides a minimal async wrapper around a KIE-style HTTP API.
Configure the API endpoint and API key via environment variables:
- `KIE_API_URL` (default: https://api.kie.ai)
- `KIE_API_KEY` (required for real requests)
- `KIE_TIMEOUT_SECONDS` (default: 30)
- `KIE_RETRY_MAX_ATTEMPTS` (default: 3)
- `KIE_RETRY_BASE_DELAY` (default: 1.0)

The exact endpoints may vary for your KIE deployment; this client keeps
URLs configurable and handles common operations: list models, get model,
invoke model. If no API key is present, methods return helpful messages
instead of raising.
"""
import os
import time
import aiohttp
import asyncio
import logging
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

from app.utils.retry import async_retry
from app.utils.correlation import correlation_tag

logger = logging.getLogger(__name__)

# Load .env if not already loaded
load_dotenv()


class KIEClient:
    def __init__(self):
        self.base_url = os.getenv('KIE_API_URL', 'https://api.kie.ai').rstrip('/')
        self.api_key = os.getenv('KIE_API_KEY')
        self.timeout = int(os.getenv('KIE_TIMEOUT_SECONDS', '30'))
        # Retry parameters from ENV
        self.retry_max_attempts = int(os.getenv('KIE_RETRY_MAX_ATTEMPTS', '3'))
        self.retry_base_delay = float(os.getenv('KIE_RETRY_BASE_DELAY', '1.0'))
        self.retry_max_delay = float(os.getenv('KIE_RETRY_MAX_DELAY', '60.0'))

    def _normalize_exception(self, error: Exception) -> "KIEClientError":
        if isinstance(error, asyncio.TimeoutError):
            return KIEClientError("Request to KIE timed out", user_message="Сервис KIE временно недоступен. Попробуйте позже.")
        if isinstance(error, aiohttp.ClientError):
            return KIEClientError("Network error while contacting KIE", user_message="Не удалось связаться с KIE. Попробуйте позже.")
        return KIEClientError(str(error), user_message="Произошла ошибка KIE. Попробуйте позже.")

    def _headers(self) -> Dict[str, str]:
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        return headers
    
    async def _create_task_internal(self, model_id: str, input_data: Any, callback_url: str = None) -> Dict[str, Any]:
        """Internal method for create_task with retry logic applied."""
        if not self.api_key:
            return {
                'ok': False,
                'error': 'KIE_API_KEY not configured. Set KIE_API_KEY in environment.'
            }
        
        url = f"{self.base_url}/api/v1/jobs/createTask"
        payload = {
            "model": model_id,
            "input": input_data
        }
        if callback_url:
            payload["callBackUrl"] = callback_url
        
        # CRITICAL: Log exact payload being sent to KIE API (for compliance verification)
        import json
        logger.info(f"{correlation_tag()} 📤 KIE API Request: POST {url}")
        logger.info(f"{correlation_tag()} 📤 KIE API Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as s:
                async with s.post(url, headers=self._headers(), json=payload) as resp:
                    text = await resp.text()
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                            if isinstance(data, dict) and data.get('code') == 200:
                                task_id = data.get('data', {}).get('taskId')
                                if task_id:
                                    return {'ok': True, 'taskId': task_id}
                                else:
                                    return {'ok': False, 'error': 'No taskId in response'}
                            else:
                                error_msg = data.get('msg', 'Unknown error')
                                logger.error(f"{correlation_tag()} ❌ KIE API Error (code {data.get('code')}): {error_msg}")
                                logger.error(f"{correlation_tag()} ❌ KIE API Full Response: {json.dumps(data, ensure_ascii=False, indent=2)}")
                                return {'ok': False, 'error': error_msg}
                        except Exception as e:
                            logger.error(f"{correlation_tag()} ❌ Failed to parse KIE API response: {e}, text: {text[:500]}")
                            return {'ok': False, 'error': f'Failed to parse response: {e}'}
                    else:
                        # CRITICAL: Log full error response for debugging 422 and other errors
                        try:
                            error_data = await resp.json()
                            error_msg = error_data.get('msg', text)
                            error_code = error_data.get('code', resp.status)
                            logger.error(f"{correlation_tag()} ❌ KIE API HTTP {resp.status} Error (code {error_code}): {error_msg}")
                            logger.error(f"{correlation_tag()} ❌ KIE API Full Error Response: {json.dumps(error_data, ensure_ascii=False, indent=2)}")
                            
                            # Используем обработчик ошибок для логирования
                            try:
                                from error_handler_providers import get_error_handler
                                handler = get_error_handler()
                                handler.handle_api_error(
                                    status_code=resp.status,
                                    response_data=error_data,
                                    request_details={
                                        "model": model_id,
                                        "payload": payload
                                    }
                                )
                            except ImportError:
                                pass  # Обработчик недоступен
                        except:
                            error_msg = text
                            logger.error(f"{correlation_tag()} ❌ KIE API HTTP {resp.status} Error (raw): {text[:500]}")
                        return {'ok': False, 'status': resp.status, 'error': error_msg}
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise self._normalize_exception(e)
    
    async def _get_task_status_internal(self, task_id: str) -> Dict[str, Any]:
        """Internal method for get_task_status with retry logic applied."""
        if not self.api_key:
            return {
                'ok': False,
                'error': 'KIE_API_KEY not configured. Set KIE_API_KEY in environment.'
            }
        
        url = f"{self.base_url}/api/v1/jobs/recordInfo"
        params = {"taskId": task_id}
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as s:
                async with s.get(url, headers=self._headers(), params=params) as resp:
                    text = await resp.text()
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                            if isinstance(data, dict) and data.get('code') == 200:
                                task_data = data.get('data', {})
                                return {
                                    'ok': True,
                                    'taskId': task_data.get('taskId'),
                                    'state': task_data.get('state'),  # waiting, success, fail
                                    'resultJson': task_data.get('resultJson'),
                                    'resultUrls': task_data.get('resultUrls', []),
                                    'failCode': task_data.get('failCode'),
                                    'failMsg': task_data.get('failMsg'),
                                    'errorMessage': task_data.get('errorMessage'),
                                    'completeTime': task_data.get('completeTime'),
                                    'createTime': task_data.get('createTime')
                                }
                            else:
                                error_msg = data.get('msg', 'Unknown error')
                                return {'ok': False, 'error': error_msg}
                        except Exception as e:
                            logger.error(f"{correlation_tag()} ❌ Failed to parse KIE API response: {e}, text: {text[:500]}")
                            return {'ok': False, 'error': f'Failed to parse response: {e}'}
                    else:
                        try:
                            error_data = await resp.json()
                            error_msg = error_data.get('msg', text)
                        except:
                            error_msg = text
                        return {'ok': False, 'status': resp.status, 'error': error_msg}
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise self._normalize_exception(e)

    async def list_models(self) -> List[Dict[str, Any]]:
        """Return list of models from the KIE API. If API key missing, return []"""
        if not self.api_key:
            return []

        # Проверяем кеш
        try:
            from optimization_cache import get_cached_models, set_cached_models
            cached = get_cached_models()
            if cached is not None:
                logger.debug("✅ Использован кеш для list_models")
                return cached
        except ImportError:
            pass  # Кеш не доступен, продолжаем без него

        # Try different endpoint variations - prioritize /api/v1/ format
        endpoints = [
            (f"{self.base_url}/api/v1/models", "GET"),  # Primary format based on docs
            (f"{self.base_url}/api/v1/chat/models", "GET"),  # Alternative
            (f"{self.base_url}/v1/models", "GET"),
            (f"{self.base_url}/models", "GET"),
            (f"{self.base_url}/api/models", "GET"),
        ]
        
        start_time = time.time()
        last_error = None
        for url, method in endpoints:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as s:
                    if method == "POST":
                        async with s.post(url, headers=self._headers(), json={}) as resp:
                            text = await resp.text()
                            status = resp.status
                    else:
                        async with s.get(url, headers=self._headers()) as resp:
                            text = await resp.text()
                            status = resp.status
                    
                    if status == 200:
                        # Success! Parse response
                        elapsed = time.time() - start_time
                        try:
                            from optimization_helpers import log_api_response_time
                            log_api_response_time(f"KIE API list_models ({url})", elapsed)
                        except ImportError:
                            logger.debug(f"⏱️ list_models заняло {elapsed:.2f}с")
                        
                        try:
                            data = await resp.json()
                            # Check if response is a list or dict with models
                            models = []
                            if isinstance(data, list):
                                models = data
                            elif isinstance(data, dict):
                                # Some APIs return models in a 'data' or 'models' field
                                if 'data' in data:
                                    models = data['data']
                                elif 'models' in data:
                                    models = data['models']
                                elif 'items' in data:
                                    models = data['items']
                                elif 'result' in data:
                                    result = data['result']
                                    if isinstance(result, list):
                                        models = result
                                else:
                                    # Return as single item in list
                                    models = [data]
                            
                            # Сохраняем в кеш
                            try:
                                from optimization_cache import set_cached_models
                                set_cached_models(models)
                            except ImportError:
                                pass  # Кеш не доступен
                            
                            return models
                        except Exception as e:
                            raise RuntimeError(f'Failed to parse response: {e} - Response: {text[:200]}')
                    elif status == 404:
                        # Try next endpoint
                        continue
                    else:
                        # Try to parse error
                        try:
                            error_json = await resp.json()
                            error_msg = str(error_json)
                        except:
                            error_msg = text[:200]
                        last_error = f'Status {status}: {error_msg}'
                        continue
            except aiohttp.ClientError as e:
                last_error = f'Network error: {str(e)}'
                continue
            except Exception as e:
                last_error = f'Error: {str(e)}'
                continue
        
        # All endpoints failed - return empty list instead of raising
        # This allows bot to work even if API is temporarily unavailable
        logger.warning(f'KIE list_models failed on all endpoints. Last error: {last_error}')
        return []

    async def get_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            return None
        # Try different endpoint formats
        endpoints = [
            f"{self.base_url}/api/v1/models/{model_id}",
            f"{self.base_url}/api/v1/chat/models/{model_id}",
            f"{self.base_url}/v1/models/{model_id}",
        ]
        for url in endpoints:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as s:
                    async with s.get(url, headers=self._headers()) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        elif resp.status != 404:
                            # Try next endpoint
                            continue
            except Exception:
                continue
        return None

    async def get_credits(self) -> Dict[str, Any]:
        """Get remaining credits balance. Returns dict with 'ok', 'credits', and optional 'error'."""
        if not self.api_key:
            return {
                'ok': False,
                'error': 'KIE_API_KEY not configured. Set KIE_API_KEY in environment.'
            }
        
        url = f"{self.base_url}/api/v1/chat/credit"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as s:
                async with s.get(url, headers=self._headers()) as resp:
                    text = await resp.text()
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                            # Handle response format: {"code": 200, "msg": "success", "data": 100}
                            if isinstance(data, dict):
                                if data.get('code') == 200:
                                    credits = data.get('data', 0)
                                    return {'ok': True, 'credits': credits}
                                else:
                                    return {'ok': False, 'error': data.get('msg', 'Unknown error')}
                            else:
                                return {'ok': True, 'credits': data if isinstance(data, (int, float)) else 0}
                        except Exception as e:
                            return {'ok': False, 'error': f'Failed to parse response: {e}'}
                    else:
                        try:
                            error_data = await resp.json()
                            error_msg = error_data.get('msg', text)
                        except:
                            error_msg = text
                        return {'ok': False, 'status': resp.status, 'error': error_msg}
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            normalized = self._normalize_exception(e)
            return {'ok': False, 'error': normalized.user_message}
        except Exception as e:
            normalized = self._normalize_exception(e)
            return {'ok': False, 'error': normalized.user_message}

    async def create_task(self, model_id: str, input_data: Any, callback_url: str = None) -> Dict[str, Any]:
        """Create a generation task. Returns task ID for status polling. Uses retry logic for network errors."""
        # Use retry wrapper with instance-specific parameters
        from app.utils.retry import retry_with_backoff
        async def _task():
            return await self._create_task_internal(model_id, input_data, callback_url)
        try:
            return await retry_with_backoff(
                _task,
                max_attempts=self.retry_max_attempts,
                base_delay=self.retry_base_delay,
                max_delay=self.retry_max_delay,
                exceptions=(aiohttp.ClientError, asyncio.TimeoutError, aiohttp.ClientConnectionError, KIEClientError)
            )
        except (aiohttp.ClientError, asyncio.TimeoutError, aiohttp.ClientConnectionError, KIEClientError) as e:
            # After all retries failed, return error dict instead of raising
            normalized = self._normalize_exception(e)
            logger.error(f"❌ KIE API create_task failed after {self.retry_max_attempts} attempts: {e}")
            return {'ok': False, 'error': normalized.user_message}
    
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get task status and results by task ID. Uses retry logic for network errors."""
        # Use retry wrapper with instance-specific parameters
        from app.utils.retry import retry_with_backoff
        async def _get_status():
            return await self._get_task_status_internal(task_id)
        try:
            return await retry_with_backoff(
                _get_status,
                max_attempts=self.retry_max_attempts,
                base_delay=self.retry_base_delay,
                max_delay=self.retry_max_delay,
                exceptions=(aiohttp.ClientError, asyncio.TimeoutError, aiohttp.ClientConnectionError, KIEClientError)
            )
        except (aiohttp.ClientError, asyncio.TimeoutError, aiohttp.ClientConnectionError, KIEClientError) as e:
            # After all retries failed, return error dict instead of raising
            normalized = self._normalize_exception(e)
            logger.error(f"❌ KIE API get_task_status failed after {self.retry_max_attempts} attempts: {e}")
            return {'ok': False, 'error': normalized.user_message}
    
    async def wait_task(self, task_id: str, timeout_s: int = 900, poll_s: int = 3) -> Dict[str, Any]:
        """
        Wait for task completion with polling.
        
        Args:
            task_id: Task ID to wait for
            timeout_s: Maximum wait time in seconds (default 900)
            poll_s: Poll interval in seconds (default 3)
        
        Returns:
            Final task status dict with state, resultUrls (parsed from resultJson), etc.
        
        Raises:
            TimeoutError: If task doesn't complete in timeout
            ValueError: If task fails
        """
        max_iterations = timeout_s // poll_s
        start_time = time.time()
        
        for i in range(max_iterations):
            try:
                result = await self.get_task_status(task_id)
                
                if not result.get('ok'):
                    error = result.get('error', 'Unknown error')
                    logger.warning(f"event=kie.wait_task task_id={task_id} iteration={i+1} error={error}, retrying...")
                    await asyncio.sleep(poll_s)
                    continue
                
                state = result.get('state')
                elapsed = int(time.time() - start_time)
                logger.info(f"event=kie.wait_task task_id={task_id} state={state} elapsed={elapsed}s iteration={i+1}")
                
                if state in ('success', 'fail'):
                    if state == 'success':
                        # Parse resultUrls from resultJson if needed
                        result_urls = result.get('resultUrls', [])
                        if not result_urls and result.get('resultJson'):
                            try:
                                import json
                                result_json_str = result.get('resultJson')
                                if isinstance(result_json_str, str):
                                    result_json = json.loads(result_json_str)
                                    result_urls = result_json.get('resultUrls', [])
                                    result['resultUrls'] = result_urls  # Update in-place
                            except Exception as e:
                                logger.warning(f"event=kie.wait_task task_id={task_id} failed to parse resultJson: {e}")
                        
                        logger.info(f"event=kie.wait_task task_id={task_id} status=success result_urls_count={len(result_urls)}")
                        return result
                    else:
                        error_msg = result.get('failMsg') or result.get('errorMessage', 'Unknown error')
                        fail_code = result.get('failCode')
                        if fail_code:
                            error_msg = f"[{fail_code}] {error_msg}"
                        logger.error(f"event=kie.wait_task task_id={task_id} status=fail error={error_msg}")
                        raise ValueError(f"Task failed: {error_msg}")
                
                await asyncio.sleep(poll_s)
            except ValueError:
                # Task failure - re-raise
                raise
            except Exception as e:
                logger.warning(f"event=kie.wait_task task_id={task_id} iteration={i+1} exception={e}, retrying...")
                await asyncio.sleep(poll_s)
        
        elapsed = int(time.time() - start_time)
        logger.error(f"event=kie.wait_task task_id={task_id} status=timeout elapsed={elapsed}s")
        raise TimeoutError(f"Task {task_id} did not complete in {timeout_s}s")

    async def invoke_model(self, model_id: str, input_data: Any) -> Dict[str, Any]:
        """Invoke a model with given input_data. Returns parsed JSON or error dict."""
        # If API key not set, return a helpful placeholder response
        if not self.api_key:
            return {
                'ok': False,
                'error': 'KIE_API_KEY not configured. Set KIE_API_KEY in environment.'
            }

        # Try different endpoint formats
        endpoints = [
            f"{self.base_url}/api/v1/models/{model_id}/invoke",
            f"{self.base_url}/api/v1/chat/models/{model_id}/invoke",
            f"{self.base_url}/v1/models/{model_id}/invoke",
        ]
        
        payload = {'input': input_data}
        last_error = None
        
        for url in endpoints:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as s:
                    async with s.post(url, headers=self._headers(), json=payload) as resp:
                        text = await resp.text()
                        if resp.status == 200:
                            try:
                                data = await resp.json()
                                # Handle response format: {"code": 200, "msg": "success", "data": {...}}
                                if isinstance(data, dict) and data.get('code') == 200:
                                    return {'ok': True, 'result': data.get('data', data)}
                                return {'ok': True, 'result': data}
                            except Exception:
                                return {'ok': True, 'result': text}
                        elif resp.status == 404:
                            # Try next endpoint
                            continue
                        else:
                            try:
                                error_data = await resp.json()
                                error_msg = error_data.get('msg', text)
                            except:
                                error_msg = text
                            last_error = {'ok': False, 'status': resp.status, 'error': error_msg}
                            if resp.status != 404:
                                # For non-404 errors, return immediately
                                return last_error
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                normalized = self._normalize_exception(e)
                return {'ok': False, 'error': normalized.user_message}
            except Exception as e:
                last_error = {'ok': False, 'error': str(e)}
                continue
        
        # All endpoints failed
        return last_error or {'ok': False, 'error': 'All endpoints returned 404'}


class KIEClientError(Exception):
    def __init__(self, message: str, user_message: str):
        super().__init__(message)
        self.user_message = user_message


# Module-level client for convenience
client = KIEClient()


def get_client() -> KIEClient:
    return client
