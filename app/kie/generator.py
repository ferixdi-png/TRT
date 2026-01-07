"""
End-to-end generator for Kie.ai models with heartbeat and error handling.
"""
import asyncio
import time
import random
import json
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta
import os

from app.kie.builder import build_payload, load_source_of_truth
from app.kie.validator import ModelContractError
from app.kie.parser import parse_record_info, get_human_readable_error
from app.utils.errors import classify_api_failure, classify_exception
from app.kie.router import is_v4_model, build_category_payload
from app.utils.public_url import get_public_base_url
from app.utils.payload_hash import payload_hash
from app.utils.trace import TraceContext, get_request_id, new_request_id

logger = logging.getLogger(__name__)


# Adaptive polling: reduces API spam during long generations (helps avoid secondary throttling).
def _compute_poll_delay(elapsed_s: float) -> float:
    if elapsed_s < 10:
        base = 2.0
    elif elapsed_s < 30:
        base = 3.0
    elif elapsed_s < 90:
        base = 5.0
    elif elapsed_s < 180:
        base = 7.0
    else:
        base = 9.0

    jitter = random.uniform(-0.25, 0.25)
    return max(1.5, base + jitter)


def _mask_for_logs(value, *, _depth: int = 0):
    """Mask potentially sensitive values in payload logs."""
    if _depth > 6:
        return "..."

    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            ks = str(k).lower()
            if any(x in ks for x in ("token", "api_key", "apikey", "secret", "authorization", "sig")):
                out[k] = "***"
            else:
                out[k] = _mask_for_logs(v, _depth=_depth + 1)
        return out

    if isinstance(value, list):
        return [_mask_for_logs(v, _depth=_depth + 1) for v in value[:50]]

    if isinstance(value, str):
        # Avoid logging huge prompts / base64 blobs
        if len(value) > 500:
            return value[:200] + "..." + value[-60:]
        return value

    return value

# Test mode flag (accept truthy variants like "1"/"true")
def _env_flag(name: str, default: str = 'false') -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "y", "on"}


TEST_MODE = _env_flag('TEST_MODE')
KIE_STUB = _env_flag('KIE_STUB')
USE_V4_API = _env_flag('KIE_USE_V4')  # Default to V3 (safe)

# Import at module level to avoid circular imports and for isinstance check
try:
    from app.kie.client_v4 import KieApiClientV4
except ImportError:
    KieApiClientV4 = None


class KieGenerator:
    """Universal generator for Kie.ai models."""
    
    def __init__(self, api_client: Optional[Any] = None):
        """
        Initialize generator.
        
        Args:
            api_client: Optional API client (for dependency injection in tests)
        """
        self.api_client = api_client
        self.source_of_truth = None
        self._heartbeat_interval = 12  # 10-15 seconds, use 12 as middle
        
    def _get_api_client(self):
        """Get API client (real or stub) - V4 or V3."""
        if self.api_client:
            return self.api_client

        if TEST_MODE or KIE_STUB:
            return self._get_stub_client()
        
        # Check if using V4 API (new architecture)
        if USE_V4_API:
            from app.kie.client_v4 import KieApiClientV4
            return KieApiClientV4()
        
        # Fallback to old V3 client (for compatibility)
        from app.api.kie_client import KieApiClient
        return KieApiClient()
    
    def _get_stub_client(self):
        """Get stub client for testing."""

        class StubClient:
            def __init__(self):
                self._poll_counts: Dict[str, int] = {}

            async def create_task(self, *args, callback_url=None, **kwargs) -> Dict[str, Any]:
                """Stub create_task supporting V3 and V4 call signatures."""

                payload: Dict[str, Any] = {}
                model: str = "unknown"

                # V3 style: create_task(payload, callback_url=None, **kwargs)
                if len(args) == 1 and isinstance(args[0], dict):
                    payload = args[0]
                    model = payload.get("model") or payload.get("model_id") or model

                # V4 style: create_task(model_id, payload, **kwargs)
                elif len(args) >= 2:
                    model = str(args[0]) if args[0] is not None else model
                    payload = args[1] if isinstance(args[1], dict) else payload

                elif "payload" in kwargs and isinstance(kwargs.get("payload"), dict):
                    payload = kwargs.get("payload")
                    model = payload.get("model") or payload.get("model_id") or kwargs.get("model_id", model)

                task_id = f"stub_task_{model}"
                self._poll_counts[task_id] = 0

                return {
                    "code": 200,
                    "taskId": task_id,
                    "data": {"taskId": task_id, "status": "waiting"},
                }

            async def get_record_info(self, task_id: str) -> Dict[str, Any]:
                """Stub get_record_info with deterministic polling states."""
                poll_number = self._poll_counts.get(task_id, 0)

                if "fail" in task_id:
                    return {
                        "state": "fail",
                        "failCode": "TEST_ERROR",
                        "failMsg": "Test error message",
                    }

                if poll_number == 0:
                    self._poll_counts[task_id] = 1
                    return {"state": "running"}

                self._poll_counts[task_id] = poll_number + 1
                return {
                    "state": "success",
                    "resultJson": json.dumps(
                        {
                            "mediaUrl": f"https://example.com/{task_id}.mp4",
                            "resultUrls": [f"https://example.com/{task_id}.mp4"],
                        }
                    ),
                }

        return StubClient()
    
    async def generate(
        self,
        model_id: str,
        user_inputs: Dict[str, Any],
        progress_callback: Optional[Callable[[str], None]] = None,
        task_id_callback: Optional[Callable[[str], Any]] = None,
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Generate content using Kie.ai model.
        
        Args:
            model_id: Model identifier
            user_inputs: User inputs (text, url, file, etc.)
            progress_callback: Optional callback for progress updates
            timeout: Maximum wait time in seconds
            
        Returns:
            Result dictionary with:
            - success: bool
            - message: str
            - result_urls: List[str]
            - result_object: Any
            - error_code: Optional[str]
            - error_message: Optional[str]
        """
        request_id = get_request_id()
        if not request_id or request_id == "-":
            request_id = new_request_id()
        ph = payload_hash({"model": model_id, "inputs": user_inputs})

        def _x(stage: str, **kw: Any) -> Dict[str, Any]:
            return {
                "stage": stage,
                "request_id": request_id,
                "model_id": model_id,
                "payload_hash": ph,
                **kw,
            }

        with TraceContext(model_id=model_id, request_id=request_id):
            logger.info(
                "▶️ generation start timeout=%ss inputs=%s",
                timeout,
                list(user_inputs.keys()),
                extra=_x("start"),
            )

            async def _maybe_call_progress(message: str) -> None:
                if not progress_callback:
                    return
                try:
                    res = progress_callback(message)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:
                    logger.debug(
                        "progress callback failed",
                        exc_info=True,
                        extra={"stage": "progress", "payload_hash": ph, "model_id": model_id},
                    )

            async def _maybe_call_task_id(task_id: str) -> None:
                if not task_id_callback:
                    return
                try:
                    res = task_id_callback(task_id)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:
                    logger.debug(
                        "task_id callback failed",
                        exc_info=True,
                        extra={"stage": "create_task", "payload_hash": ph, "model_id": model_id},
                    )

            try:
                # Load source of truth if needed
                if not self.source_of_truth:
                    self.source_of_truth = load_source_of_truth()

                # Check if this is a V4 model (new architecture)
                is_v4 = USE_V4_API and is_v4_model(model_id)

                # Build payload using appropriate builder
                if is_v4:
                    logger.info(
                        "Using V4 API for model %s",
                        model_id,
                        extra=_x("payload_build"),
                    )
                    payload = build_category_payload(model_id, user_inputs)
                else:
                    logger.info(
                        "Using V3 API for model %s",
                        model_id,
                        extra=_x("payload_build"),
                    )
                    payload = build_payload(model_id, user_inputs, self.source_of_truth)

                # Hash the final payload (stronger correlation than user_inputs)
                ph = payload_hash(payload)

                # Log payload summary (once)
                try:
                    _p = dict(payload) if isinstance(payload, dict) else {}
                    _model = _p.get("model") or _p.get("model_id") or model_id
                    _prompt = (_p.get("prompt") or _p.get("input", {}).get("prompt") or "")
                    _prompt_len = len(_prompt) if isinstance(_prompt, str) else 0
                    logger.info(
                        "🧩 payload built model=%s keys=%s prompt_len=%s",
                        _model,
                        list(_p.keys()),
                        _prompt_len,
                        extra=_x("payload_built"),
                    )
                except Exception:
                    logger.debug(
                        "payload built (failed to summarize)",
                        exc_info=True,
                        extra=_x("payload_built"),
                    )

                # Log full payload (masked) for debugging contract issues
                try:
                    masked = _mask_for_logs(payload)
                    s = json.dumps(masked, ensure_ascii=False)
                    if len(s) > 2500:
                        s = s[:2000] + "..." + s[-300:]
                    logger.info(
                        "📤 Kie payload (masked): %s",
                        s,
                        extra=_x("payload_log"),
                    )
                except Exception:
                    logger.debug(
                        "Failed to log full payload",
                        exc_info=True,
                        extra=_x("payload_log"),
                    )

                # Create task
                api_client = self._get_api_client()

                # Some Kie.ai endpoints require callBackUrl even if we also poll for the result.
                base_url = get_public_base_url()
                callback_url = f"{base_url}/kie/callback" if base_url else None
                if not callback_url:
                    logger.warning(
                        "Kie callBackUrl is not set: public base URL is missing (set WEBHOOK_BASE_URL or RENDER_EXTERNAL_URL)",
                        extra={"stage": "callback_url", "payload_hash": ph, "model_id": model_id},
                    )

                # V4 API requires model_id as first argument
                # V3 API (old KieApiClient) only takes payload
                try:
                    if KieApiClientV4 is not None and isinstance(api_client, KieApiClientV4):
                        if callback_url and isinstance(payload, dict):
                            payload = dict(payload)
                            payload.setdefault("callBackUrl", callback_url)
                        create_response = await api_client.create_task(model_id, payload)
                    else:
                        create_response = await api_client.create_task(payload, callback_url=callback_url)
                except Exception as e:
                    cls = classify_exception(e)
                    logger.error(
                        "create_task exception code=%s error=%s",
                        getattr(cls, "code", "EXC"),
                        str(e),
                        exc_info=True,
                        extra={
                            "stage": "create_task",
                            "payload_hash": ph,
                            "model_id": model_id,
                            "request_id": get_request_id(),
                        },
                    )
                    return {
                        "success": False,
                        "message": f"❌ Ошибка API при старте генерации. Код запроса: {get_request_id()}",
                        "user_friendly_message": f"❌ Ошибка API при старте генерации. Код запроса: {get_request_id()}",
                        "result_urls": [],
                        "result_object": None,
                        "error_code": getattr(cls, "code", "API_ERROR"),
                        "error_message": str(e),
                        "task_id": None,
                    }

                logger.info(
                    "Create task response: %s",
                    create_response,
                    extra=_x("create_task_response"),
                )

                # Check if response is None or has error
                if create_response is None:
                    err = classify_api_failure("UPSTREAM_NONE", "create_task returned None")
                    logger.error(
                        "%s create_task returned None | %s",
                        err.code,
                        err.debug_reason,
                        extra={
                            "stage": "create_task",
                            "payload_hash": ph,
                            "model_id": model_id,
                            "request_id": get_request_id(),
                        },
                    )
                    return {
                        "success": False,
                        "message": f"❌ Ошибка API: не получен ответ от сервера. Код запроса: {get_request_id()}",
                        "user_friendly_message": f"❌ Ошибка API: не получен ответ от сервера. Код запроса: {get_request_id()}",
                        "result_urls": [],
                        "result_object": None,
                        "error_code": "NO_RESPONSE",
                        "error_message": "API client returned None",
                        "task_id": None,
                    }

                # Check for error in response (from exception handling)
                if isinstance(create_response, dict) and "error" in create_response:
                    error_msg = create_response.get("error", "Unknown error")
                    logger.error(
                        "API error in create_task: %s",
                        error_msg,
                        extra={
                            "stage": "create_task",
                            "payload_hash": ph,
                            "model_id": model_id,
                            "request_id": get_request_id(),
                        },
                    )
                    return {
                        "success": False,
                        "message": f"❌ Ошибка API: {error_msg}. Код запроса: {get_request_id()}",
                        "user_friendly_message": f"❌ Ошибка API: {error_msg}. Код запроса: {get_request_id()}",
                        "result_urls": [],
                        "result_object": None,
                        "error_code": "API_CONNECTION_ERROR",
                        "error_message": error_msg,
                        "task_id": None,
                    }

                # Extract taskId from response (can be at top level or in data object)
                task_id = create_response.get("taskId") if isinstance(create_response, dict) else None
                upstream_code = create_response.get("code") if isinstance(create_response, dict) else None
                upstream_msg = create_response.get("msg") if isinstance(create_response, dict) else None
                if not task_id and isinstance(create_response, dict) and create_response.get("data"):
                    data = create_response.get("data")
                    if isinstance(data, dict):
                        task_id = data.get("taskId")

                if task_id:
                    await _maybe_call_task_id(task_id)

                if isinstance(create_response, dict) and upstream_code not in (None, 0, 200):
                    logger.error(
                        "Create task failed code=%s msg=%s",
                        upstream_code,
                        upstream_msg,
                        extra={
                            "stage": "create_task",
                            "payload_hash": ph,
                            "model_id": model_id,
                            "request_id": get_request_id(),
                            "upstream_code": upstream_code,
                            "upstream_msg": upstream_msg,
                        },
                    )
                    message = upstream_msg or "Неизвестная ошибка"
                    return {
                        "success": False,
                        "message": f"❌ Ошибка API: {message}. Код запроса: {get_request_id()}",
                        "user_friendly_message": f"❌ Ошибка API: {message}. Код запроса: {get_request_id()}",
                        "result_urls": [],
                        "result_object": None,
                        "error_code": f"API_ERROR_{upstream_code}",
                        "error_message": f"{message}. Response: {create_response}",
                        "task_id": None,
                    }

                if not task_id:
                    error_code = create_response.get("code") if isinstance(create_response, dict) else None
                    error_msg = (create_response.get("msg", "Unknown error") if isinstance(create_response, dict) else "Unknown error")

                    logger.error(
                        "No taskId in response. Full response: %s",
                        create_response,
                        extra={
                            "stage": "create_task",
                            "payload_hash": ph,
                            "model_id": model_id,
                            "request_id": get_request_id(),
                            "upstream_code": error_code,
                            "upstream_msg": error_msg,
                        },
                    )
                    return {
                        "success": False,
                        "message": f"❌ Ошибка API: {error_msg}. Код запроса: {get_request_id()}",
                        "user_friendly_message": f"❌ Ошибка API: {error_msg}. Код запроса: {get_request_id()}",
                        "result_urls": [],
                        "result_object": None,
                        "error_code": f"API_ERROR_{error_code}" if error_code else "NO_TASK_ID",
                        "error_message": f"{error_msg}. Response: {create_response}",
                        "task_id": None,
                    }

                # Wait for completion with heartbeat
                start_time = datetime.now()
                start_ts = time.monotonic()
                last_heartbeat = datetime.now()

                while True:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    if elapsed > timeout:
                        logger.error(
                            "Timeout waiting for task: %ss",
                            timeout,
                            extra=_x("timeout", task_id=task_id),
                        )
                        return {
                            "success": False,
                            "message": f"⏱️ Превышено время ожидания ({timeout} сек)",
                            "result_urls": [],
                            "result_object": None,
                            "error_code": "TIMEOUT",
                            "error_message": f"Task timeout after {timeout} seconds",
                            "task_id": task_id,
                        }

                    # Get record info
                    try:
                        record_info = await api_client.get_record_info(task_id)
                    except Exception as e:
                        cls = classify_exception(e)
                        logger.error(
                            "get_record_info exception code=%s error=%s",
                            getattr(cls, "code", "EXC"),
                            str(e),
                            exc_info=True,
                            extra={
                                "stage": "poll",
                                "payload_hash": ph,
                                "model_id": model_id,
                                "task_id": task_id,
                                "request_id": request_id,
                            },
                        )
                        return {
                            "success": False,
                            "message": "❌ Ошибка API при получении результата. Попробуйте ещё раз позже.",
                            "result_urls": [],
                            "result_object": None,
                            "error_code": getattr(cls, "code", "POLL_ERROR"),
                            "error_message": str(e),
                            "task_id": task_id,
                        }

                    # Normalize data-wrapper format: {"code":200,"data":{"state":...}}
                    if (
                        isinstance(record_info, dict)
                        and isinstance(record_info.get("data"), dict)
                        and "state" not in record_info
                    ):
                        logger.debug(
                            "Normalizing recordInfo from data-wrapper format",
                            extra={"stage": "poll", "payload_hash": ph, "task_id": task_id, "model_id": model_id},
                        )
                        record_info = record_info["data"]

                    parsed = parse_record_info(record_info)
                    state = parsed.get("state")
                    fail_code = parsed.get("error_code")

                    logger.info(
                        "poll state=%s failCode=%s",
                        state,
                        fail_code,
                        extra=_x("poll", task_id=task_id),
                    )

                    if state == "success":
                        logger.info(
                            "✅ generation success urls=%s",
                            len(parsed.get("result_urls") or []),
                            extra=_x("success", task_id=task_id),
                        )
                        return {
                            "success": True,
                            "message": parsed["message"],
                            "result_urls": parsed["result_urls"],
                            "result_object": parsed["result_object"],
                            "error_code": None,
                            "error_message": None,
                            "task_id": task_id,
                        }

                    if state == "fail":
                        human = get_human_readable_error(parsed.get("error_code"), parsed.get("error_message"))
                        logger.warning(
                            "generation failed code=%s msg=%s",
                            parsed.get("error_code"),
                            parsed.get("error_message"),
                            extra=_x("fail", task_id=task_id),
                        )
                        return {
                            "success": False,
                            "message": f"❌ {human}\n\nНажмите /start для возврата в меню.",
                            "result_urls": [],
                            "result_object": None,
                            "error_code": parsed.get("error_code"),
                            "error_message": parsed.get("error_message"),
                            "task_id": task_id,
                        }

                    if state == "waiting":
                        time_since_heartbeat = (datetime.now() - last_heartbeat).total_seconds()
                        if time_since_heartbeat >= self._heartbeat_interval:
                            progress_percent = parsed.get("progress", 0)
                            eta_seconds = parsed.get("eta")

                            if progress_percent and progress_percent > 0:
                                bar_length = 10
                                filled = int(progress_percent / 10)
                                bar = "█" * filled + "░" * (bar_length - filled)

                                if eta_seconds:
                                    await _maybe_call_progress(
                                        f"⏳ <b>Генерация</b>\n\n{bar} {progress_percent}%\nОсталось: ~{eta_seconds} сек"
                                    )
                                else:
                                    await _maybe_call_progress(f"⏳ <b>Генерация</b>\n\n{bar} {progress_percent}%")
                            elif eta_seconds:
                                await _maybe_call_progress(f"⏳ <b>Генерация...</b>\n\nОсталось: ~{eta_seconds} сек")
                            else:
                                dots = "." * (int(elapsed) % 4)
                                await _maybe_call_progress(f"⏳ <b>Генерация{dots}</b>\n\nПрошло: {int(elapsed)} сек")

                            last_heartbeat = datetime.now()

                        delay = _compute_poll_delay(time.monotonic() - start_ts)
                        await asyncio.sleep(delay)
                        continue

                    # Unknown/empty state: keep polling
                    delay = _compute_poll_delay(time.monotonic() - start_ts)
                    await asyncio.sleep(delay)
                    continue

            except (ValueError, ModelContractError) as e:
                logger.error(
                    "Payload/contract validation error: model=%s error=%s",
                    model_id,
                    str(e),
                    extra={"stage": "payload_validation", "payload_hash": ph, "model_id": model_id},
                )
                return {
                    "success": False,
                    "message": f"❌ Ошибка в параметрах: {str(e)}\n\nНажмите /start для возврата в меню.",
                    "result_urls": [],
                    "result_object": None,
                    "error_code": "INVALID_INPUT",
                    "error_message": str(e),
                    "task_id": None,
                }

            except Exception as e:
                cls = classify_exception(e)
                logger.error(
                    "Error in generate code=%s error=%s",
                    getattr(cls, "code", "EXC"),
                    str(e),
                    exc_info=True,
                    extra={"stage": "exception", "payload_hash": ph, "model_id": model_id},
                )
                return {
                    "success": False,
                    "message": f"❌ Произошла ошибка: {str(e)}\n\nНажмите /start для возврата в меню.",
                    "result_urls": [],
                    "result_object": None,
                    "error_code": getattr(cls, "code", "UNKNOWN_ERROR"),
                    "error_message": str(e),
                    "task_id": None,
                }


# Convenience functions
async def generate_from_text(
    model_id: str,
    text: str,
    progress_callback: Optional[Callable[[str], None]] = None,
    **kwargs
) -> Dict[str, Any]:
    """Generate from text input."""
    generator = KieGenerator()
    user_inputs = {'text': text, 'prompt': text, **kwargs}
    return await generator.generate(model_id, user_inputs, progress_callback)


async def generate_from_url(
    model_id: str,
    url: str,
    progress_callback: Optional[Callable[[str], None]] = None,
    **kwargs
) -> Dict[str, Any]:
    """Generate from URL input."""
    generator = KieGenerator()
    user_inputs = {'url': url, **kwargs}
    return await generator.generate(model_id, user_inputs, progress_callback)


async def generate_from_file(
    model_id: str,
    file_id: str,
    progress_callback: Optional[Callable[[str], None]] = None,
    **kwargs
) -> Dict[str, Any]:
    """Generate from file input."""
    generator = KieGenerator()
    user_inputs = {'file': file_id, 'file_id': file_id, **kwargs}
    return await generator.generate(model_id, user_inputs, progress_callback)
