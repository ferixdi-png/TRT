"""
KIE AI Gateway Client - single integration point for KIE API.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import uuid4

import aiohttp

from app.utils.logging_config import get_logger
from app.observability.trace import trace_event, url_summary
from app.observability.structured_logs import log_structured_event

logger = get_logger(__name__)


@dataclass(frozen=True)
class KIEError:
    status: int
    code: str
    message: str
    correlation_id: str
    user_message: str


class KIEClient:
    """Async KIE API client with retries/backoff and UX-friendly error taxonomy."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        base_delay: Optional[float] = None,
        max_delay: Optional[float] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("KIE_API_KEY")
        self.base_url = (base_url or os.getenv("KIE_API_URL", "https://api.kie.ai")).rstrip("/")
        timeout_seconds = timeout or float(os.getenv("KIE_TIMEOUT_SECONDS", "30"))
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.max_retries = int(max_retries or os.getenv("KIE_RETRY_MAX_ATTEMPTS", "3"))
        self.base_delay = float(base_delay or os.getenv("KIE_RETRY_BASE_DELAY", "1.0"))
        self.max_delay = float(max_delay or os.getenv("KIE_RETRY_MAX_DELAY", "60.0"))
        self._session: Optional[aiohttp.ClientSession] = None

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    def _headers(self, correlation_id: str) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Request-ID": correlation_id,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _should_retry(self, status: int, error: Optional[BaseException]) -> bool:
        if isinstance(error, (aiohttp.ClientError, asyncio.TimeoutError)):
            return True
        if status in {429}:
            return True
        return 500 <= status < 600

    def _backoff_delay(self, attempt: int, status: int) -> float:
        delay = min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)
        if status == 429:
            delay = min(delay * 2, self.max_delay)
        delay += random.uniform(0, self.base_delay)
        return delay

    def _parse_json(self, payload: str) -> Dict[str, Any]:
        if not payload:
            return {}
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {}

    def _classify_error(
        self,
        status: int,
        message: str,
        correlation_id: str,
    ) -> KIEError:
        if status == 401:
            user_message = (
                "🔒 Авторизация в KIE API не прошла. Проверьте ключ доступа.\n"
                f"ID: {correlation_id}"
            )
            code = "unauthorized"
        elif status == 402:
            user_message = (
                "💳 Недостаточно средств в аккаунте KIE для выполнения запроса.\n"
                f"ID: {correlation_id}"
            )
            code = "payment_required"
        elif status == 422:
            user_message = (
                "🧩 Некорректные параметры запроса. Проверьте введённые данные.\n"
                f"ID: {correlation_id}"
            )
            code = "validation_error"
        elif status == 429:
            user_message = (
                "⏳ Слишком много запросов. Попробуйте чуть позже.\n"
                f"ID: {correlation_id}"
            )
            code = "rate_limited"
        elif 500 <= status < 600:
            user_message = (
                "⚠️ KIE API временно недоступен. Попробуйте ещё раз позже.\n"
                f"ID: {correlation_id}"
            )
            code = "server_error"
        else:
            user_message = (
                "⚠️ Ошибка при обращении к KIE API. Попробуйте ещё раз.\n"
                f"ID: {correlation_id}"
            )
            code = "unknown_error"
        return KIEError(status=status, code=code, message=message, correlation_id=correlation_id, user_message=user_message)

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.api_key:
            correlation_id = correlation_id or uuid4().hex[:8]
            error = self._classify_error(
                status=401,
                message="KIE_API_KEY not configured",
                correlation_id=correlation_id,
            )
            return {"ok": False, "error": error.message, "user_message": error.user_message, "correlation_id": error.correlation_id}

        url = f"{self.base_url}{path}"
        correlation_id = correlation_id or uuid4().hex[:8]
        session = await self._get_session()
        last_error: Optional[BaseException] = None

        for attempt in range(1, self.max_retries + 2):
            start_ts = time.monotonic()
            try:
                async with session.request(
                    method,
                    url,
                    headers=self._headers(correlation_id),
                    json=payload,
                    params=params,
                ) as response:
                    text = await response.text()
                    latency_ms = int((time.monotonic() - start_ts) * 1000)
                    status = response.status
                    logger.info(
                        "[KIE] request method=%s path=%s status=%s attempt=%s latency_ms=%s",
                        method,
                        path,
                        status,
                        attempt,
                        latency_ms,
                    )
                    data = self._parse_json(text)
                    if status in (200, 201):
                        return {
                            "ok": True,
                            "status": status,
                            "data": data,
                            "correlation_id": correlation_id,
                            "meta": {"attempt": attempt, "latency_ms": latency_ms},
                        }
                    last_error = aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=status,
                        message=text,
                    )
                    if attempt <= self.max_retries and self._should_retry(status, last_error):
                        await asyncio.sleep(self._backoff_delay(attempt, status))
                        continue
                    message = data.get("msg") or text or f"HTTP {status}"
                    error = self._classify_error(status=status, message=message, correlation_id=correlation_id)
                    return {
                        "ok": False,
                        "status": status,
                        "error": error.message,
                        "user_message": error.user_message,
                        "correlation_id": error.correlation_id,
                        "error_code": error.code,
                        "meta": {"attempt": attempt, "latency_ms": latency_ms},
                    }
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
                status = 0
                if attempt <= self.max_retries and self._should_retry(status, exc):
                    await asyncio.sleep(self._backoff_delay(attempt, status))
                    continue
                error = self._classify_error(status=0, message=str(exc), correlation_id=correlation_id)
                return {
                    "ok": False,
                    "status": 0,
                    "error": error.message,
                    "user_message": error.user_message,
                    "correlation_id": error.correlation_id,
                    "error_code": error.code,
                    "meta": {"attempt": attempt},
                }

        message = str(last_error) if last_error else "Unknown error"
        error = self._classify_error(status=0, message=message, correlation_id=correlation_id)
        return {
            "ok": False,
            "status": 0,
            "error": error.message,
            "user_message": error.user_message,
            "correlation_id": error.correlation_id,
            "error_code": error.code,
        }

    async def create_task(
        self,
        model_id: str,
        input_data: Dict[str, Any],
        callback_url: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"model": model_id, "input": input_data}
        if callback_url:
            payload["callBackUrl"] = callback_url

        input_keys = list(input_data.keys())
        input_sizes: Dict[str, Any] = {}
        for key, value in input_data.items():
            if isinstance(value, str):
                input_sizes[key] = len(value)
            elif isinstance(value, list):
                input_sizes[key] = len(value)
            elif isinstance(value, dict):
                input_sizes[key] = len(value.keys())
            else:
                input_sizes[key] = type(value).__name__

        trace_event(
            "info",
            correlation_id or "corr-na-na",
            event="TRACE_IN",
            stage="KIE_CREATE",
            action="KIE_CREATE",
            endpoint="/api/v1/jobs/createTask",
            model_id=model_id,
            input_keys=input_keys,
            input_sizes=input_sizes,
            has_callback=bool(callback_url),
        )
        log_structured_event(
            correlation_id=correlation_id,
            action="KIE_CREATE",
            action_path="kie_client.create_task",
            model_id=model_id,
            param={"input_keys": input_keys},
            outcome="request",
        )

        result = await self._request_json(
            "POST",
            "/api/v1/jobs/createTask",
            payload=payload,
            correlation_id=correlation_id,
        )
        if not result.get("ok"):
            return result

        data = result.get("data", {})
        if data.get("code") != 200:
            message = data.get("msg", "Unknown error")
            error = self._classify_error(status=422, message=message, correlation_id=result["correlation_id"])
            return {
                "ok": False,
                "status": 422,
                "error": error.message,
                "user_message": error.user_message,
                "correlation_id": error.correlation_id,
                "error_code": error.code,
            }
        task_id = data.get("data", {}).get("taskId")
        if not task_id:
            error = self._classify_error(status=422, message="No taskId in response", correlation_id=result["correlation_id"])
            return {
                "ok": False,
                "status": 422,
                "error": error.message,
                "user_message": error.user_message,
                "correlation_id": error.correlation_id,
                "error_code": error.code,
            }
        trace_event(
            "info",
            result["correlation_id"],
            event="TRACE_OUT",
            stage="KIE_CREATE",
            action="KIE_CREATE",
            endpoint="/api/v1/jobs/createTask",
            http_status=result.get("status"),
            attempt=result.get("meta", {}).get("attempt"),
            latency_ms=result.get("meta", {}).get("latency_ms"),
            task_id=task_id,
        )
        log_structured_event(
            correlation_id=result.get("correlation_id"),
            action="KIE_CREATE",
            action_path="kie_client.create_task",
            model_id=model_id,
            param={"task_id": task_id},
            outcome="created",
        )
        return {"ok": True, "taskId": task_id, "correlation_id": result["correlation_id"]}

    async def get_task_status(self, task_id: str, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        result = await self._request_json(
            "GET",
            "/api/v1/jobs/recordInfo",
            params={"taskId": task_id},
            correlation_id=correlation_id,
        )
        if not result.get("ok"):
            return result

        data = result.get("data", {})
        if data.get("code") != 200:
            message = data.get("msg", "Unknown error")
            error = self._classify_error(status=422, message=message, correlation_id=result["correlation_id"])
            return {
                "ok": False,
                "status": 422,
                "error": error.message,
                "user_message": error.user_message,
                "correlation_id": error.correlation_id,
                "error_code": error.code,
            }
        task_data = data.get("data", {})
        response_payload = {
            "ok": True,
            "taskId": task_data.get("taskId"),
            "state": task_data.get("state"),
            "resultJson": task_data.get("resultJson"),
            "resultUrls": task_data.get("resultUrls", []),
            "failCode": task_data.get("failCode"),
            "failMsg": task_data.get("failMsg"),
            "errorMessage": task_data.get("errorMessage"),
            "completeTime": task_data.get("completeTime"),
            "createTime": task_data.get("createTime"),
            "correlation_id": result["correlation_id"],
        }
        trace_event(
            "info",
            result["correlation_id"],
            event="TRACE_IN",
            stage="KIE_POLL",
            action="KIE_POLL",
            endpoint="/api/v1/jobs/recordInfo",
            http_status=result.get("status"),
            attempt=result.get("meta", {}).get("attempt"),
            latency_ms=result.get("meta", {}).get("latency_ms"),
            task_id=task_id,
            state=response_payload.get("state"),
            fail_code=response_payload.get("failCode"),
            fail_msg=response_payload.get("failMsg"),
            result_url_summary=url_summary((response_payload.get("resultUrls") or [None])[0]),
        )
        log_structured_event(
            correlation_id=result.get("correlation_id"),
            action="KIE_POLL",
            action_path="kie_client.get_task_status",
            model_id=None,
            param={
                "task_id": task_id,
                "attempt": result.get("meta", {}).get("attempt"),
                "latency_ms": result.get("meta", {}).get("latency_ms"),
            },
            outcome=response_payload.get("state"),
        )
        return response_payload

    async def wait_for_task(
        self,
        task_id: str,
        timeout: int = 900,
        poll_interval: int = 3,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        start_time = asyncio.get_event_loop().time()
        attempt = 0
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                error = self._classify_error(status=408, message="Task timeout", correlation_id=correlation_id or uuid4().hex[:8])
                return {
                    "ok": False,
                    "status": 408,
                    "error": error.message,
                    "user_message": error.user_message,
                    "correlation_id": error.correlation_id,
                    "error_code": error.code,
                }
            attempt += 1
            status = await self.get_task_status(task_id, correlation_id=correlation_id)
            log_structured_event(
                correlation_id=correlation_id,
                action="KIE_POLL",
                action_path="kie_client.wait_for_task",
                param={"attempt": attempt, "elapsed": round(elapsed, 3), "task_id": task_id},
                outcome=status.get("state"),
            )
            if not status.get("ok"):
                await asyncio.sleep(poll_interval)
                continue
            state = status.get("state")
            if state in ("success", "completed", "failed"):
                return status
            await asyncio.sleep(poll_interval)

    async def submit_and_wait(
        self,
        model_id: str,
        input_data: Dict[str, Any],
        callback_url: Optional[str] = None,
        timeout: int = 900,
        poll_interval: int = 3,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        submit = await self.create_task(
            model_id,
            input_data,
            callback_url=callback_url,
            correlation_id=correlation_id,
        )
        if not submit.get("ok"):
            return submit
        return await self.wait_for_task(
            submit["taskId"],
            timeout=timeout,
            poll_interval=poll_interval,
            correlation_id=correlation_id,
        )

    async def list_models(self) -> List[Dict[str, Any]]:
        result = await self._request_json("GET", "/api/v1/models")
        if not result.get("ok"):
            return []
        data = result.get("data", {})
        if isinstance(data, dict) and "data" in data:
            return data.get("data", [])
        if isinstance(data, list):
            return data
        return []

    async def get_credits(self) -> Dict[str, Any]:
        """Best-effort credits check. Returns ok=False with credits=None on unsupported endpoints."""
        result = await self._request_json("GET", "/api/v1/account/balance")
        if not result.get("ok"):
            status = result.get("status")
            if status in (404, 0):
                logger.warning(
                    "KIE credits endpoint unavailable (status=%s). Hint: verify KIE API plan or endpoint.",
                    status,
                )
                return {
                    "ok": False,
                    "credits": None,
                    "status": status,
                    "error": result.get("error"),
                    "correlation_id": result.get("correlation_id"),
                }
            logger.warning(
                "KIE credits request failed (status=%s, error=%s). Hint: check KIE API credentials.",
                status,
                result.get("error"),
            )
            return {
                "ok": False,
                "credits": None,
                "status": status,
                "error": result.get("error"),
                "correlation_id": result.get("correlation_id"),
            }

        data = result.get("data", {})
        if isinstance(data, dict):
            credits = data.get("credits") or data.get("data", {}).get("credits")
        else:
            credits = None
        if credits is None:
            logger.warning(
                "KIE credits response missing credits field. Hint: confirm API response schema.",
            )
            return {
                "ok": False,
                "credits": None,
                "status": result.get("status"),
                "error": "missing_credits",
                "correlation_id": result.get("correlation_id"),
            }
        return {
            "ok": True,
            "credits": credits,
            "status": result.get("status"),
            "correlation_id": result.get("correlation_id"),
        }


_client_instance: Optional[KIEClient] = None


def get_kie_client() -> KIEClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = KIEClient()
    return _client_instance


def get_client() -> KIEClient:
    return get_kie_client()
