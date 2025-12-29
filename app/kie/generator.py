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
from contextlib import nullcontext

from app.kie.builder import build_payload, load_source_of_truth
from app.kie.validator import ModelContractError
from app.kie.parser import parse_record_info, get_human_readable_error
from app.utils.errors import classify_api_failure, classify_exception
from app.kie.router import is_v4_model, build_category_payload
from app.utils.public_url import get_public_base_url
from app.utils.payload_hash import payload_hash
from app.utils.trace import TraceContext, get_request_id

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

# Test mode flag
TEST_MODE = os.getenv('TEST_MODE', 'false').lower() == 'true'
KIE_STUB = os.getenv('KIE_STUB', 'false').lower() == 'true'
USE_V4_API = os.getenv('KIE_USE_V4', 'false').lower() == 'true'  # Default to V3 (safe)

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
            async def create_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
                """Stub create_task."""
                model = payload.get('model', 'unknown')
                return {
                    'taskId': f"stub_task_{model}",
                    'status': 'waiting'
                }
            
            async def get_record_info(self, task_id: str) -> Dict[str, Any]:
                """Stub get_record_info."""
                # Simulate different states for testing
                if 'text' in task_id or 'test_text' in task_id:
                    return {
                        'state': 'success',
                        'resultJson': json.dumps({
                            'resultUrls': ['https://example.com/result1.txt']
                        })
                    }
                elif 'image' in task_id or 'test_image' in task_id:
                    return {
                        'state': 'success',
                        'resultJson': json.dumps({
                            'resultUrls': ['https://example.com/result1.jpg']
                        })
                    }
                elif 'video' in task_id or 'test_video' in task_id:
                    return {
                        'state': 'success',
                        'resultJson': json.dumps({
                            'resultUrls': ['https://example.com/result1.mp4']
                        })
                    }
                elif 'audio' in task_id or 'test_audio' in task_id:
                    return {
                        'state': 'success',
                        'resultJson': json.dumps({
                            'resultUrls': ['https://example.com/result1.mp3']
                        })
                    }
                elif 'url' in task_id or 'test_url' in task_id:
                    return {
                        'state': 'success',
                        'resultJson': json.dumps({
                            'resultUrls': ['https://example.com/processed.jpg']
                        })
                    }
                elif 'file' in task_id or 'test_file' in task_id:
                    return {
                        'state': 'success',
                        'resultJson': json.dumps({
                            'resultUrls': ['https://example.com/processed_file.pdf']
                        })
                    }
                elif 'fail' in task_id:
                    return {
                        'state': 'fail',
                        'failCode': 'TEST_ERROR',
                        'failMsg': 'Test error message'
                    }
                else:
                    return {'state': 'waiting'}
        
        return StubClient()
    
    async def generate(
        self,
        model_id: str,
        user_inputs: Dict[str, Any],
        progress_callback: Optional[Callable[[str], None]] = None,
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
        ctx = TraceContext(model_id=model_id) if get_request_id() == "-" else nullcontext()
        with ctx:
            ph = payload_hash({"model": model_id, "inputs": user_inputs})
            logger.info(
                "▶️ generation start timeout=%ss inputs=%s",
                timeout,
                list(user_inputs.keys()),
                extra={"stage": "start", "payload_hash": ph, "model_id": model_id},
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
                        extra={"stage": "payload_build", "payload_hash": ph, "model_id": model_id},
                    )
                    payload = build_category_payload(model_id, user_inputs)
                else:
                    logger.info(
                        "Using V3 API for model %s",
                        model_id,
                        extra={"stage": "payload_build", "payload_hash": ph, "model_id": model_id},
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
                        extra={"stage": "payload_built", "payload_hash": ph, "model_id": model_id},
                    )
                except Exception:
                    logger.debug(
                        "payload built (failed to summarize)",
                        exc_info=True,
                        extra={"stage": "payload_built", "payload_hash": ph, "model_id": model_id},
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
                        extra={"stage": "payload_log", "payload_hash": ph, "model_id": model_id},
                    )
                except Exception:
                    logger.debug(
                        "Failed to log full payload",
                        exc_info=True,
                        extra={"stage": "payload_log", "payload_hash": ph, "model_id": model_id},
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
                        extra={"stage": "create_task", "payload_hash": ph, "model_id": model_id},
                    )
                    return {
                        "success": False,
                        "message": "❌ Ошибка API при старте генерации. Попробуйте ещё раз позже.",
                        "result_urls": [],
                        "result_object": None,
                        "error_code": getattr(cls, "code", "API_ERROR"),
                        "error_message": str(e),
                        "task_id": None,
                    }

                logger.info(
                    "Create task response: %s",
                    create_response,
                    extra={"stage": "create_task_response", "payload_hash": ph, "model_id": model_id},
                )

                # Check if response is None or has error
                if create_response is None:
                    err = classify_api_failure("UPSTREAM_NONE", "create_task returned None")
                    logger.error(
                        "%s create_task returned None | %s",
                        err.code,
                        err.debug_reason,
                        extra={"stage": "create_task", "payload_hash": ph, "model_id": model_id},
                    )
                    return {
                        "success": False,
                        "message": "❌ Ошибка API: не получен ответ от сервера",
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
                        extra={"stage": "create_task", "payload_hash": ph, "model_id": model_id},
                    )
                    return {
                        "success": False,
                        "message": f"❌ Ошибка API: {error_msg}",
                        "result_urls": [],
                        "result_object": None,
                        "error_code": "API_CONNECTION_ERROR",
                        "error_message": error_msg,
                        "task_id": None,
                    }

                # Extract taskId from response (can be at top level or in data object)
                task_id = create_response.get("taskId") if isinstance(create_response, dict) else None
                if not task_id and isinstance(create_response, dict) and create_response.get("data"):
                    data = create_response.get("data")
                    if isinstance(data, dict):
                        task_id = data.get("taskId")

                if not task_id:
                    error_code = create_response.get("code") if isinstance(create_response, dict) else None
                    error_msg = (create_response.get("msg", "Unknown error") if isinstance(create_response, dict) else "Unknown error")

                    logger.error(
                        "No taskId in response. Full response: %s",
                        create_response,
                        extra={"stage": "create_task", "payload_hash": ph, "model_id": model_id},
                    )
                    return {
                        "success": False,
                        "message": f"❌ Ошибка API: {error_msg}",
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
                            extra={
                                "stage": "timeout",
                                "payload_hash": ph,
                                "model_id": model_id,
                                "task_id": task_id,
                            },
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
                        extra={"stage": "poll", "payload_hash": ph, "task_id": task_id, "model_id": model_id},
                    )

                    if state == "success":
                        logger.info(
                            "✅ generation success urls=%s",
                            len(parsed.get("result_urls") or []),
                            extra={"stage": "success", "payload_hash": ph, "task_id": task_id, "model_id": model_id},
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
                            extra={"stage": "fail", "payload_hash": ph, "task_id": task_id, "model_id": model_id},
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
                            if progress_callback:
                                progress_percent = parsed.get("progress", 0)
                                eta_seconds = parsed.get("eta")

                                if progress_percent and progress_percent > 0:
                                    bar_length = 10
                                    filled = int(progress_percent / 10)
                                    bar = "█" * filled + "░" * (bar_length - filled)

                                    if eta_seconds:
                                        progress_callback(
                                            f"⏳ <b>Генерация</b>\n\n{bar} {progress_percent}%\nОсталось: ~{eta_seconds} сек"
                                        )
                                    else:
                                        progress_callback(f"⏳ <b>Генерация</b>\n\n{bar} {progress_percent}%")
                                elif eta_seconds:
                                    progress_callback(f"⏳ <b>Генерация...</b>\n\nОсталось: ~{eta_seconds} сек")
                                else:
                                    dots = "." * (int(elapsed) % 4)
                                    progress_callback(f"⏳ <b>Генерация{dots}</b>\n\nПрошло: {int(elapsed)} сек")

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