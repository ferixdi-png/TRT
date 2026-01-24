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
from app.resilience import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerError

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
        circuit_breaker_enabled: bool = True,
    ) -> None:
        self.api_key = api_key or os.getenv("KIE_API_KEY")
        self.base_url = (base_url or os.getenv("KIE_API_URL", "https://api.kie.ai")).rstrip("/")
        timeout_seconds = timeout or float(os.getenv("KIE_TIMEOUT_SECONDS", "30"))
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.max_retries = int(max_retries or os.getenv("KIE_RETRY_MAX_ATTEMPTS", "3"))
        self.base_delay = float(base_delay or os.getenv("KIE_RETRY_BASE_DELAY", "1.0"))
        self.max_delay = float(max_delay or os.getenv("KIE_RETRY_MAX_DELAY", "60.0"))
        self._session: Optional[aiohttp.ClientSession] = None
        
        # PR-3: Circuit Breaker for KIE API
        self.circuit_breaker_enabled = circuit_breaker_enabled and os.getenv("KIE_CIRCUIT_BREAKER_ENABLED", "true").lower() == "true"
        if self.circuit_breaker_enabled:
            self.circuit_breaker = CircuitBreaker(
                config=CircuitBreakerConfig(
                    failure_threshold=int(os.getenv("KIE_CB_FAILURE_THRESHOLD", "5")),
                    success_threshold=int(os.getenv("KIE_CB_SUCCESS_THRESHOLD", "2")),
                    timeout=float(os.getenv("KIE_CB_TIMEOUT", "60.0")),
                    name="kie_api",
                )
            )
            logger.info(
                "[CIRCUIT_BREAKER] enabled=true name=kie_api failure_threshold=%s timeout=%s",
                self.circuit_breaker.config.failure_threshold,
                self.circuit_breaker.config.timeout,
            )
        else:
            self.circuit_breaker = None
            logger.info("[CIRCUIT_BREAKER] enabled=false")

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
                "❌ Неверный ключ KIE API.\n"
                f"ID: {correlation_id}"
            )
            code = "unauthorized"
        elif status == 402:
            user_message = (
                "💳 Недостаточно средств на KIE аккаунте.\n"
                f"ID: {correlation_id}"
            )
            code = "payment_required"
        elif status == 422:
            user_message = (
                "🧩 Ошибка параметров модели.\n"
                f"Подсказка: {message}\n"
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
        # PR-3: Circuit Breaker wrapper
        if self.circuit_breaker:
            try:
                return await self.circuit_breaker.call(
                    self._request_json_impl,
                    method,
                    path,
                    payload=payload,
                    params=params,
                    correlation_id=correlation_id,
                )
            except CircuitBreakerError as exc:
                # Circuit is OPEN - fast fail with user-friendly message
                logger.warning(
                    "[CIRCUIT_BREAKER] request_rejected method=%s path=%s state=%s",
                    method,
                    path,
                    exc.state.value,
                )
                correlation_id = correlation_id or uuid4().hex[:8]
                return {
                    "ok": False,
                    "status": 503,
                    "error": f"Circuit breaker {exc.state.value}",
                    "user_message": (
                        "⚠️ KIE API временно недоступен из-за множественных сбоев.\n"
                        f"Попробуйте через {int(exc.until - time.monotonic()) if exc.until else 60} сек.\n"
                        f"ID: {correlation_id}"
                    ),
                    "correlation_id": correlation_id,
                    "error_code": "circuit_breaker_open",
                }
        else:
            return await self._request_json_impl(
                method, path, payload=payload, params=params, correlation_id=correlation_id
            )

    async def _request_json_impl(
        self,
        method: str,
        path: str,
        *,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Internal implementation (wrapped by circuit breaker)."""
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
            error_code="KIE_CREATE_REQUEST",
            fix_hint="Создание задачи в KIE API.",
        )

        result = await self._request_json(
            "POST",
            "/api/v1/jobs/createTask",
            payload=payload,
            correlation_id=correlation_id,
        )
        if not result.get("ok"):
            log_structured_event(
                correlation_id=result.get("correlation_id"),
                action="KIE_CREATE",
                action_path="kie_client.create_task",
                model_id=model_id,
                outcome="failed",
                error_code=result.get("error_code") or "KIE_CREATE_FAILED",
                fix_hint="Проверьте параметры и доступность KIE API.",
                param={"status": result.get("status"), "error": result.get("error")},
            )
            return result

        data = result.get("data", {})
        if data.get("code") != 200:
            message = data.get("msg", "Unknown error")
            error = self._classify_error(status=422, message=message, correlation_id=result["correlation_id"])
            log_structured_event(
                correlation_id=error.correlation_id,
                action="KIE_CREATE",
                action_path="kie_client.create_task",
                model_id=model_id,
                outcome="failed",
                error_code=error.code,
                fix_hint="KIE вернул ошибку в payload.",
                param={"status": 422, "message": message},
            )
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
            log_structured_event(
                correlation_id=error.correlation_id,
                action="KIE_CREATE",
                action_path="kie_client.create_task",
                model_id=model_id,
                outcome="failed",
                error_code=error.code,
                fix_hint="KIE ответил без taskId.",
                param={"status": 422},
            )
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
            error_code="KIE_CREATE_OK",
            fix_hint="Задача создана.",
        )
        return {"ok": True, "taskId": task_id, "correlation_id": result["correlation_id"]}

    async def get_task_status(
        self,
        task_id: str,
        correlation_id: Optional[str] = None,
        poll_attempt: Optional[int] = None,
        total_wait_ms: Optional[int] = None,
        retry_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        log_structured_event(
            correlation_id=correlation_id,
            action="KIE_TASK_POLL",
            action_path="kie_client.get_task_status",
            outcome="request",
            error_code="KIE_TASK_POLL_REQUEST",
            fix_hint="Запрос статуса задачи KIE.",
            poll_attempt=poll_attempt,
            total_wait_ms=total_wait_ms,
            retry_count=retry_count,
            param={"task_id": task_id},
        )
        result = await self._request_json(
            "GET",
            "/api/v1/jobs/recordInfo",
            params={"taskId": task_id},
            correlation_id=correlation_id,
        )
        if not result.get("ok"):
            log_structured_event(
                correlation_id=result.get("correlation_id"),
                action="KIE_TASK_POLL",
                action_path="kie_client.get_task_status",
                outcome="failed",
                error_code=result.get("error_code") or "KIE_TASK_POLL_FAILED",
                fix_hint="Проверьте статус задачи и доступность KIE API.",
                param={"status": result.get("status"), "error": result.get("error"), "task_id": task_id},
            )
            return result

        data = result.get("data", {})
        if data.get("code") != 200:
            message = data.get("msg", "Unknown error")
            error = self._classify_error(status=422, message=message, correlation_id=result["correlation_id"])
            log_structured_event(
                correlation_id=error.correlation_id,
                action="KIE_TASK_POLL",
                action_path="kie_client.get_task_status",
                outcome="failed",
                error_code=error.code,
                fix_hint="KIE вернул ошибку по задаче.",
                param={"status": 422, "message": message, "task_id": task_id},
            )
            return {
                "ok": False,
                "status": 422,
                "error": error.message,
                "user_message": error.user_message,
                "correlation_id": error.correlation_id,
                "error_code": error.code,
            }
        task_data = data.get("data", {})
        log_structured_event(
            correlation_id=result.get("correlation_id"),
            action="KIE_TASK_POLL",
            action_path="kie_client.get_task_status",
            outcome="success",
            error_code="KIE_TASK_POLL_OK",
            fix_hint="Статус задачи получен.",
            param={"task_id": task_id, "state": task_data.get("state")},
        )
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
            poll_attempt=poll_attempt,
            poll_latency_ms=result.get("meta", {}).get("latency_ms"),
            total_wait_ms=total_wait_ms,
            task_state=response_payload.get("state"),
            retry_count=retry_count,
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

    async def cancel_task(self, task_id: str, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        log_structured_event(
            correlation_id=correlation_id,
            action="KIE_TASK_CANCEL",
            action_path="kie_client.cancel_task",
            outcome="request",
            error_code="KIE_TASK_CANCEL_REQUEST",
            fix_hint="Запрос отмены задачи KIE.",
            param={"task_id": task_id},
        )
        result = await self._request_json(
            "POST",
            "/api/v1/jobs/cancelTask",
            payload={"taskId": task_id},
            correlation_id=correlation_id,
        )
        if not result.get("ok"):
            log_structured_event(
                correlation_id=result.get("correlation_id"),
                action="KIE_TASK_CANCEL",
                action_path="kie_client.cancel_task",
                outcome="failed",
                error_code=result.get("error_code") or "KIE_TASK_CANCEL_FAILED",
                fix_hint="Проверьте endpoint cancelTask и доступность KIE API.",
                param={"status": result.get("status"), "error": result.get("error"), "task_id": task_id},
            )
            return result
        data = result.get("data", {})
        if isinstance(data, dict) and data.get("code") not in (None, 200):
            message = data.get("msg", "Unknown error")
            error = self._classify_error(status=422, message=message, correlation_id=result["correlation_id"])
            log_structured_event(
                correlation_id=error.correlation_id,
                action="KIE_TASK_CANCEL",
                action_path="kie_client.cancel_task",
                outcome="failed",
                error_code=error.code,
                fix_hint="KIE вернул ошибку при отмене задачи.",
                param={"status": 422, "message": message, "task_id": task_id},
            )
            return {
                "ok": False,
                "status": 422,
                "error": error.message,
                "user_message": error.user_message,
                "correlation_id": error.correlation_id,
                "error_code": error.code,
            }
        log_structured_event(
            correlation_id=result.get("correlation_id"),
            action="KIE_TASK_CANCEL",
            action_path="kie_client.cancel_task",
            outcome="success",
            error_code="KIE_TASK_CANCEL_OK",
            fix_hint="Отмена задачи отправлена.",
            param={"task_id": task_id},
        )
        return {"ok": True, "taskId": task_id, "correlation_id": result.get("correlation_id")}

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
        result = await self._request_json("GET", "/api/v1/chat/credit")
        if not result.get("ok"):
            status = result.get("status")
            if status in (404, 0):
                log_structured_event(
                    correlation_id=result.get("correlation_id"),
                    action="KIE_CREDITS",
                    action_path="kie_client.get_credits",
                    stage="KIE_CREDITS",
                    outcome="endpoint_unavailable",
                    error_code="KIE_CREDITS_ENDPOINT_MISSING",
                    fix_hint="Проверьте endpoint /api/v1/chat/credit или план KIE API.",
                )
                logger.warning(
                    "KIE credits endpoint unavailable (status=%s). Hint: verify KIE API plan or endpoint.",
                    status,
                )
                return {
                    "ok": False,
                    "credits": None,
                    "status": status,
                    "error": result.get("error"),
                    "user_message": f"Баланс KIE недоступен (endpoint {status})",
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
                "user_message": "Баланс KIE недоступен",
                "correlation_id": result.get("correlation_id"),
            }

        data = result.get("data", {})
        credits = None
        if isinstance(data, (int, float)) and not isinstance(data, bool):
            credits = float(data)
        elif isinstance(data, dict):
            nested = data.get("data")
            if isinstance(nested, (int, float)) and not isinstance(nested, bool):
                credits = float(nested)
            else:
                credits = (
                    data.get("credits")
                    or data.get("credit")
                    or (nested.get("credits") if isinstance(nested, dict) else None)
                    or (nested.get("credit") if isinstance(nested, dict) else None)
                )
        if credits is None:
            log_structured_event(
                correlation_id=result.get("correlation_id"),
                action="KIE_CREDITS",
                action_path="kie_client.get_credits",
                stage="KIE_CREDITS",
                outcome="missing_field",
                error_code="KIE_CREDITS_MISSING_FIELD",
                fix_hint="Проверьте схему ответа KIE /api/v1/chat/credit.",
            )
            logger.warning(
                "KIE credits response missing credits field. Hint: confirm API response schema.",
            )
            return {
                "ok": False,
                "credits": None,
                "status": result.get("status"),
                "error": "missing_credits",
                "user_message": "Баланс KIE недоступен",
                "correlation_id": result.get("correlation_id"),
            }
        return {
            "ok": True,
            "credits": credits,
            "status": result.get("status"),
            "correlation_id": result.get("correlation_id"),
        }

    async def get_download_url(
        self,
        source_url: str,
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Resolve a KIE download URL into a direct binary link."""
        payload = {"url": source_url}
        result = await self._request_json(
            "POST",
            "/api/v1/common/download-url",
            payload=payload,
            correlation_id=correlation_id,
        )
        if not result.get("ok"):
            return result
        data = result.get("data", {})
        if isinstance(data, dict):
            url = data.get("url") or data.get("data", {}).get("url")
        else:
            url = None
        if not url:
            return {
                "ok": False,
                "error": "missing_download_url",
                "status": result.get("status"),
                "correlation_id": result.get("correlation_id"),
            }
        return {
            "ok": True,
            "url": url,
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
