"""
KIE AI API Client - единый async клиент с retry/backoff
"""

import os
import asyncio
import logging
import random
import time
from uuid import uuid4
from typing import Any, Dict, List, Optional
from datetime import datetime

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

from app.utils.logging_config import get_logger

logger = get_logger(__name__)


class KIEClientError(Exception):
    """Базовый класс для ошибок KIE клиента"""
    pass


class KIENetworkError(KIEClientError):
    """Ошибка сети (retry)"""
    pass


class KIEServerError(KIEClientError):
    """Ошибка сервера 5xx (retry)"""
    pass


class KIERateLimitError(KIEClientError):
    """Rate limit 429 (retry с увеличенной задержкой)"""
    pass


class KIEClientError4xx(KIEClientError):
    """Ошибка клиента 4xx (не retry, кроме 429)"""
    pass


class KIEClient:
    """Единый async клиент для KIE AI API с retry/backoff"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        concurrency_limit: Optional[int] = None,
    ):
        if not AIOHTTP_AVAILABLE:
            raise ImportError("aiohttp is required for KIEClient")
        
        self.api_key = api_key or os.getenv('KIE_API_KEY')
        self.base_url = (base_url or os.getenv('KIE_API_URL', 'https://api.kie.ai')).rstrip('/')
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.concurrency_limit = self._normalize_concurrency_limit(concurrency_limit)
        self._semaphore = asyncio.Semaphore(self.concurrency_limit)
        
        self._session: Optional[aiohttp.ClientSession] = None
    
    def _headers(self, request_id: Optional[str] = None) -> Dict[str, str]:
        """Получить заголовки для запроса"""
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        if request_id:
            headers['X-Request-ID'] = request_id
        return headers

    def _normalize_concurrency_limit(self, concurrency_limit: Optional[int]) -> int:
        if concurrency_limit is None:
            env_limit = os.getenv("KIE_CONCURRENCY_LIMIT")
            if env_limit:
                try:
                    concurrency_limit = int(env_limit)
                except ValueError:
                    logger.warning("[KIE] Invalid KIE_CONCURRENCY_LIMIT=%s, using default=5", env_limit)
                    concurrency_limit = 5
            else:
                concurrency_limit = 5
        if concurrency_limit < 1:
            logger.warning("[KIE] concurrency_limit=%s < 1, using 1", concurrency_limit)
            return 1
        return concurrency_limit

    def _request_meta(self, method: str, path: str) -> Dict[str, str]:
        return {
            "request_id": uuid4().hex,
            "method": method,
            "path": path,
        }
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Получить или создать сессию"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session
    
    async def close(self):
        """Закрыть сессию"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _should_retry(self, status: int, error: Optional[Exception] = None) -> bool:
        """Определить нужно ли retry"""
        if error:
            # Network errors - retry
            if isinstance(error, (aiohttp.ClientError, asyncio.TimeoutError)):
                return True
        
        # 5xx - retry
        if 500 <= status < 600:
            return True
        
        # 429 - retry с увеличенной задержкой
        if status == 429:
            return True
        
        # 4xx (кроме 429) - не retry
        if 400 <= status < 500:
            return False
        
        return False
    
    async def _retry_with_backoff(self, func, *args, request_meta: Optional[Dict[str, str]] = None, **kwargs):
        """Retry с экспоненциальным backoff и jitter"""
        last_error = None
        request_meta = request_meta or {}
        request_id = request_meta.get("request_id", "unknown")
        method = request_meta.get("method", "unknown")
        path = request_meta.get("path", "unknown")
        start_time = time.monotonic()
        
        for attempt in range(self.max_retries + 1):
            try:
                async with self._semaphore:
                    result = await func(*args, **kwargs)
                duration_ms = int((time.monotonic() - start_time) * 1000)
                logger.info(
                    "[KIE] request_ok request_id=%s method=%s path=%s duration_ms=%s attempts=%s",
                    request_id,
                    method,
                    path,
                    duration_ms,
                    attempt + 1,
                )
                return result
            except Exception as e:
                last_error = e
                
                # Определяем статус если это HTTP ошибка
                status = 0
                if isinstance(e, aiohttp.ClientResponseError):
                    status = e.status
                elif hasattr(e, 'status'):
                    status = e.status
                
                # Проверяем нужно ли retry
                if attempt < self.max_retries and self._should_retry(status, e):
                    # Экспоненциальный backoff с jitter
                    delay = min(
                        self.base_delay * (2 ** attempt) + random.uniform(0, 1),
                        self.max_delay
                    )
                    
                    # Увеличенная задержка для 429
                    if status == 429:
                        delay *= 2
                    
                    logger.warning(
                        "[KIE] request_retry request_id=%s method=%s path=%s attempt=%s backoff_s=%.2f error_class=%s error=%s",
                        request_id,
                        method,
                        path,
                        attempt + 1,
                        delay,
                        e.__class__.__name__,
                        e,
                    )
                    await asyncio.sleep(delay)
                else:
                    # Не retry или последняя попытка
                    break
        
        # Все попытки исчерпаны
        logger.error(
            "[KIE] request_failed request_id=%s method=%s path=%s attempts=%s error_class=%s error=%s",
            request_id,
            method,
            path,
            self.max_retries + 1,
            last_error.__class__.__name__ if last_error else "unknown",
            last_error,
        )
        if isinstance(last_error, aiohttp.ClientResponseError):
            status = last_error.status
            if status == 429:
                raise KIERateLimitError(f"Rate limit exceeded: {last_error}")
            elif 500 <= status < 600:
                raise KIEServerError(f"Server error {status}: {last_error}")
            elif 400 <= status < 500:
                raise KIEClientError4xx(f"Client error {status}: {last_error}")
        
        if isinstance(last_error, (aiohttp.ClientError, asyncio.TimeoutError)):
            raise KIENetworkError(f"Network error: {last_error}")
        
        raise KIEClientError(f"Request failed: {last_error}")
    
    async def create_task(
        self,
        model_id: str,
        input_data: Dict[str, Any],
        callback_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Создать задачу генерации
        
        Args:
            model_id: ID модели
            input_data: Входные данные
            callback_url: Опциональный callback URL
        
        Returns:
            {
                'ok': bool,
                'taskId': str (если ok),
                'error': str (если не ok)
            }
        """
        request_meta = self._request_meta("POST", "/api/v1/jobs/createTask")
        if not model_id or not isinstance(input_data, dict):
            logger.warning(
                "[KIE] invalid_input request_id=%s reason=%s",
                request_meta["request_id"],
                "missing_model_id" if not model_id else "input_data_not_dict",
            )
            return {
                'ok': False,
                'error': 'Invalid input parameters'
            }

        if not self.api_key:
            return {
                'ok': False,
                'error': 'KIE_API_KEY not configured'
            }
        
        url = f"{self.base_url}/api/v1/jobs/createTask"
        payload = {
            "model": model_id,
            "input": input_data
        }
        if callback_url:
            payload["callBackUrl"] = callback_url
        
        async def _make_request():
            session = await self._get_session()
            async with session.post(
                url,
                headers=self._headers(request_id=request_meta["request_id"]),
                json=payload,
            ) as resp:
                status = resp.status
                if status == 200:
                    data = await resp.json()
                    task_id = data.get('taskId') or data.get('task_id')
                    if task_id:
                        return {
                            'ok': True,
                            'taskId': task_id
                        }
                    else:
                        return {
                            'ok': False,
                            'error': 'No taskId in response'
                        }
                else:
                    error_text = await resp.text()
                    raise aiohttp.ClientResponseError(
                        request_info=resp.request_info,
                        history=resp.history,
                        status=status,
                        message=error_text
                    )
        
        try:
            return await self._retry_with_backoff(_make_request, request_meta=request_meta)
        except KIEClientError4xx as e:
            return {
                'ok': False,
                'error': str(e)
            }
        except (KIENetworkError, KIEServerError, KIERateLimitError) as e:
            logger.error(f"[KIE] Request failed after retries: {e}")
            return {
                'ok': False,
                'error': str(e)
            }
    
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Получить статус задачи
        
        Args:
            task_id: ID задачи
        
        Returns:
            {
                'ok': bool,
                'state': str ('pending', 'processing', 'completed', 'failed'),
                'resultJson': str (JSON string с результатами),
                'resultUrls': List[str] (если state='completed'),
                'failCode': str (если state='failed'),
                'failMsg': str (если state='failed'),
                'error': str (если ok=False)
            }
        """
        request_meta = self._request_meta("GET", "/api/v1/jobs/recordInfo")
        if not task_id:
            logger.warning(
                "[KIE] invalid_input request_id=%s reason=missing_task_id",
                request_meta["request_id"],
            )
            return {
                'ok': False,
                'state': 'failed',
                'error': 'Task ID is required'
            }

        if not self.api_key:
            return {
                'ok': False,
                'error': 'KIE_API_KEY not configured'
            }
        
        url = f"{self.base_url}/api/v1/jobs/recordInfo"
        params = {"taskId": task_id}
        
        async def _make_request():
            session = await self._get_session()
            async with session.get(
                url,
                headers=self._headers(request_id=request_meta["request_id"]),
                params=params,
            ) as resp:
                status = resp.status
                if status == 200:
                    data = await resp.json()
                    
                    # Парсим resultJson если есть
                    result_urls = []
                    if 'resultJson' in data:
                        import json
                        try:
                            result_json = json.loads(data['resultJson'])
                            if isinstance(result_json, dict):
                                # Ищем URLs в разных форматах
                                if 'urls' in result_json:
                                    result_urls = result_json['urls']
                                elif 'url' in result_json:
                                    result_urls = [result_json['url']]
                                elif 'resultUrls' in result_json:
                                    result_urls = result_json['resultUrls']
                        except json.JSONDecodeError:
                            pass
                    
                    return {
                        'ok': True,
                        'state': data.get('state', 'pending'),
                        'resultJson': data.get('resultJson'),
                        'resultUrls': result_urls or data.get('resultUrls', []),
                        'failCode': data.get('failCode'),
                        'failMsg': data.get('failMsg')
                    }
                else:
                    error_text = await resp.text()
                    raise aiohttp.ClientResponseError(
                        request_info=resp.request_info,
                        history=resp.history,
                        status=status,
                        message=error_text
                    )
        
        try:
            return await self._retry_with_backoff(_make_request, request_meta=request_meta)
        except KIEClientError4xx as e:
            return {
                'ok': False,
                'state': 'failed',
                'error': str(e)
            }
        except (KIENetworkError, KIEServerError, KIERateLimitError) as e:
            logger.error(f"[KIE] Get status failed after retries: {e}")
            return {
                'ok': False,
                'state': 'pending',  # Возможно временная ошибка
                'error': str(e)
            }
    
    async def wait_for_task(
        self,
        task_id: str,
        timeout: int = 900,
        poll_interval: int = 3
    ) -> Dict[str, Any]:
        """
        Ждать завершения задачи с polling
        
        Args:
            task_id: ID задачи
            timeout: Максимальное время ожидания (секунды)
            poll_interval: Интервал polling (секунды)
        
        Returns:
            Результат get_task_status() когда задача завершена
        """
        start_time = asyncio.get_event_loop().time()
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                return {
                    'ok': False,
                    'state': 'timeout',
                    'error': f'Task timeout after {timeout}s'
                }
            
            status = await self.get_task_status(task_id)
            
            if not status.get('ok'):
                # Ошибка получения статуса - продолжаем polling
                await asyncio.sleep(poll_interval)
                continue
            
            state = status.get('state', 'pending')
            
            if state in ('completed', 'failed'):
                return status
            
            # pending или processing - продолжаем polling
            await asyncio.sleep(poll_interval)
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """
        Получить список всех моделей с ценами из market API
        
        Returns:
            List[Dict[str, Any]] - список моделей с информацией и ценами
        """
        request_meta = self._request_meta("GET", "/v1/market/list")
        if not self.api_key:
            logger.warning("KIE_API_KEY not configured, cannot fetch models from API")
            return []
        
        url = f"{self.base_url}/v1/market/list"
        
        async def _make_request():
            session = await self._get_session()
            async with session.get(
                url,
                headers=self._headers(request_id=request_meta["request_id"]),
            ) as resp:
                status = resp.status
                if status == 200:
                    data = await resp.json()
                    # API может вернуть данные в разных форматах
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict):
                        # Может быть обёрнуто в 'data' или 'models'
                        return data.get('data', data.get('models', []))
                    else:
                        logger.warning(f"Unexpected response format from /v1/market/list: {type(data)}")
                        return []
                else:
                    error_text = await resp.text()
                    raise aiohttp.ClientResponseError(
                        request_info=resp.request_info,
                        history=resp.history,
                        status=status,
                        message=error_text
                    )
        
        try:
            return await self._retry_with_backoff(_make_request, request_meta=request_meta)
        except KIEClientError4xx as e:
            logger.error(f"[KIE] Failed to list models (client error): {e}")
            return []
        except (KIENetworkError, KIEServerError, KIERateLimitError) as e:
            logger.error(f"[KIE] Failed to list models after retries: {e}")
            return []


def get_kie_client() -> KIEClient:
    """Получить KIE клиент (singleton)"""
    # TODO: можно добавить singleton если нужно
    return KIEClient()

