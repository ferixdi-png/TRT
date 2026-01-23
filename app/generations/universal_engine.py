"""Universal job engine for all KIE models."""
from __future__ import annotations

import json
import logging
import time
import inspect
import asyncio
import os
import random
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.kie.kie_client import KIEClient
from app.observability.trace import trace_event, url_summary, prompt_summary
from app.observability.structured_logs import log_structured_event
from app.observability.request_logger import log_request_event
from app.observability.error_catalog import ERROR_CATALOG
from app.kie_catalog import get_model_map, ModelSpec
from app.kie_contract.payload_builder import build_kie_payload, PayloadBuildError
from app.utils.url_normalizer import normalize_result_urls, ResultUrlNormalizationError
from app.config import get_settings
from app.storage import get_storage
import aiohttp

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobResult:
    task_id: str
    state: str
    media_type: str
    urls: List[str]
    text: Optional[str]
    raw: Dict[str, Any]


class KIEResultError(RuntimeError):
    """Raised when KIE result parsing fails."""

    def __init__(self, message: str, *, error_code: str, fix_hint: str, raw_keys: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.fix_hint = fix_hint
        self.raw_keys = raw_keys or []


class KIEJobFailed(RuntimeError):
    """Raised when KIE task completes with fail state."""

    def __init__(
        self,
        message: str,
        *,
        fail_code: Optional[str],
        fail_msg: Optional[str],
        correlation_id: Optional[str],
        record_info: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.fail_code = fail_code
        self.fail_msg = fail_msg
        self.correlation_id = correlation_id
        self.record_info = record_info or {}


class KIERequestFailed(RuntimeError):
    """Raised when KIE API returns a fatal request error."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        user_message: Optional[str] = None,
        error_code: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.user_message = user_message
        self.error_code = error_code
        self.correlation_id = correlation_id


def _parse_result_json(raw_value: Any) -> Dict[str, Any]:
    if raw_value is None:
        return {}
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str):
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError:
            return {}
    return {}


def _extract_urls(record: Dict[str, Any], result_json: Dict[str, Any]) -> List[str]:
    urls: List[str] = []
    record_urls = record.get("resultUrls") or record.get("resultUrl")
    if isinstance(record_urls, list):
        urls.extend([url for url in record_urls if url])
    elif isinstance(record_urls, str):
        urls.append(record_urls)
    json_urls = result_json.get("resultUrls") or result_json.get("resultUrl") or result_json.get("urls")
    if isinstance(json_urls, list):
        urls.extend([url for url in json_urls if url])
    elif isinstance(json_urls, str):
        urls.append(json_urls)
    return [url for url in urls if url]


def _extract_text(record: Dict[str, Any], result_json: Dict[str, Any]) -> Optional[str]:
    value = (
        record.get("resultText")
        or result_json.get("resultText")
        or result_json.get("resultObject")
        or result_json.get("text")
    )
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except TypeError:
            return str(value)
    if value is None:
        return None
    return str(value)


def _extract_media_hint(record: Dict[str, Any], result_json: Dict[str, Any]) -> Optional[str]:
    raw = (
        result_json.get("mediaType")
        or result_json.get("outputType")
        or result_json.get("output_type")
        or result_json.get("type")
        or record.get("mediaType")
        or record.get("outputType")
        or record.get("output_type")
        or record.get("type")
    )
    if not isinstance(raw, str):
        return None
    normalized = raw.lower()
    if normalized in {"image", "img", "photo", "picture"}:
        return "image"
    if normalized in {"video", "mp4", "mov"}:
        return "video"
    if normalized in {"audio", "voice", "speech"}:
        return "audio"
    if normalized in {"text", "json", "markdown"}:
        return "text"
    if normalized in {"document", "file", "binary"}:
        return "document"
    if "image" in normalized:
        return "image"
    if "video" in normalized:
        return "video"
    if "audio" in normalized or "speech" in normalized:
        return "audio"
    if "text" in normalized:
        return "text"
    return None


def _infer_media_from_urls(urls: List[str], fallback: str) -> str:
    if fallback in {"image", "video", "audio", "text", "document"}:
        return fallback
    for url in urls:
        lower = url.lower()
        if any(lower.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif")):
            return "image"
        if any(lower.endswith(ext) for ext in (".mp4", ".mov", ".webm", ".mkv")):
            return "video"
        if any(lower.endswith(ext) for ext in (".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac")):
            return "audio"
    return "document"


def parse_record_info(
    record: Dict[str, Any],
    media_type: str,
    model_id: str,
    correlation_id: Optional[str] = None,
    duration_ms: Optional[int] = None,
    *,
    base_url: Optional[str] = None,
) -> JobResult:
    result_json = _parse_result_json(record.get("resultJson"))
    urls = _extract_urls(record, result_json)
    if urls:
        try:
            urls = normalize_result_urls(
                urls,
                base_url=base_url,
                record_info=record,
                correlation_id=correlation_id,
                model_id=model_id,
                stage="KIE_PARSE",
            )
        except ResultUrlNormalizationError as exc:
            log_structured_event(
                correlation_id=correlation_id,
                action="KIE_PARSE",
                action_path="universal_engine.parse_record_info",
                model_id=model_id,
                task_id=record.get("taskId"),
                stage="KIE_PARSE",
                outcome="failed",
                error_code="KIE_RESULT_URL_INVALID",
                fix_hint=str(exc),
                duration_ms=duration_ms,
            )
            raise KIEResultError(
                "KIE_RESULT_URL_INVALID",
                error_code="KIE_RESULT_URL_INVALID",
                fix_hint=str(exc),
            ) from exc
    text = _extract_text(record, result_json)

    supported_media = {"image", "video", "audio", "text", "document"}
    media_hint = _extract_media_hint(record, result_json)
    hint_media = media_hint if media_hint in supported_media else (media_type if media_type in supported_media else "")

    if text and not urls:
        resolved_media = "text"
    elif urls:
        fallback_hint = hint_media if hint_media and hint_media != "text" else "document"
        resolved_media = _infer_media_from_urls(urls, fallback_hint)
    else:
        raw_keys = list(record.keys())
        result_keys = list(result_json.keys())
        logger.error(
            "KIE_RESULT_EMPTY model=%s state=%s failCode=%s failMsg=%s record_keys=%s result_keys=%s",
            model_id,
            record.get("state"),
            record.get("failCode"),
            record.get("failMsg"),
            raw_keys,
            result_keys,
        )
        fix_hint = ERROR_CATALOG.get("KIE_RESULT_EMPTY", "Проверьте ответ KIE recordInfo/resultJson.")
        log_structured_event(
            correlation_id=correlation_id,
            action="KIE_PARSE",
            action_path="universal_engine.parse_record_info",
            model_id=model_id,
            task_id=record.get("taskId"),
            stage="KIE_PARSE",
            outcome="failed",
            error_code="KIE_RESULT_EMPTY",
            fix_hint=fix_hint,
            duration_ms=duration_ms,
        )
        raise KIEResultError(
            "KIE_RESULT_EMPTY",
            error_code="KIE_RESULT_EMPTY",
            fix_hint=fix_hint,
            raw_keys=raw_keys + result_keys,
        )

    if resolved_media == "text" and not text:
        fix_hint = ERROR_CATALOG.get("KIE_RESULT_EMPTY", "Проверьте ответ KIE recordInfo/resultJson.")
        log_structured_event(
            correlation_id=correlation_id,
            action="KIE_PARSE",
            action_path="universal_engine.parse_record_info",
            model_id=model_id,
            task_id=record.get("taskId"),
            stage="KIE_PARSE",
            outcome="failed",
            error_code="KIE_RESULT_EMPTY_TEXT",
            fix_hint=fix_hint,
            duration_ms=duration_ms,
        )
        raise KIEResultError(
            "KIE_RESULT_EMPTY_TEXT",
            error_code="KIE_RESULT_EMPTY_TEXT",
            fix_hint=fix_hint,
            raw_keys=list(result_json.keys()),
        )

    job_result = JobResult(
        task_id=record.get("taskId", ""),
        state=record.get("state", ""),
        media_type=resolved_media,
        urls=urls,
        text=text,
        raw=record,
    )
    if correlation_id:
        trace_event(
            "info",
            correlation_id,
            event="TRACE_IN",
            stage="KIE_PARSE",
            action="KIE_PARSE",
            model_id=model_id,
            media_type=resolved_media,
            result_url_summary=url_summary(urls[0]) if urls else None,
            parse_result="ok",
        )
        log_structured_event(
            correlation_id=correlation_id,
            action="KIE_PARSE",
            action_path="universal_engine.parse_record_info",
            model_id=model_id,
            task_id=record.get("taskId"),
            stage="KIE_PARSE",
            outcome="success",
            duration_ms=duration_ms,
        )
    return job_result


def _normalize_kie_state(raw_state: Optional[str]) -> str:
    if not raw_state:
        return "unknown"
    state = raw_state.lower()
    if state in {"success", "completed", "succeeded"}:
        return "succeeded"
    if state in {"failed", "fail", "error"}:
        return "failed"
    if state in {"cancel", "cancelled", "canceled"}:
        return "canceled"
    if state in {"pending", "queued", "waiting", "queuing"}:
        return "queued"
    if state in {"processing", "running", "generating"}:
        return "running"
    return "unknown"


def _guess_media_type_from_url(url: str) -> Optional[str]:
    lower = url.lower()
    if any(lower.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "image"
    if any(lower.endswith(ext) for ext in (".mp4", ".mov", ".webm", ".mkv")):
        return "video"
    if any(lower.endswith(ext) for ext in (".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac")):
        return "audio"
    return None


def _content_type_matches(media_type: Optional[str], content_type: str) -> bool:
    if not content_type:
        return True
    if content_type.startswith("text/html"):
        return False
    if not media_type:
        return True
    if media_type == "image":
        return content_type.startswith("image/")
    if media_type == "video":
        return content_type.startswith("video/")
    if media_type == "audio":
        return content_type.startswith("audio/")
    if media_type == "text":
        return content_type.startswith("text/")
    return True


async def _validate_result_urls(
    urls: List[str],
    *,
    media_type: Optional[str],
    request_id: str,
    user_id: Optional[int],
    model_id: Optional[str],
    prompt_hash: Optional[str],
    task_id: Optional[str],
    job_id: Optional[str],
    timeout_s: float = 12.0,
) -> None:
    if not urls:
        raise KIEResultError(
            "KIE_RESULT_EMPTY",
            error_code="KIE_RESULT_EMPTY",
            fix_hint=ERROR_CATALOG.get("KIE_RESULT_EMPTY", "Empty result URL list."),
        )
    timeout = aiohttp.ClientTimeout(total=timeout_s)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        last_error: Optional[str] = None
        for url in urls:
            try:
                async with session.get(url, allow_redirects=True) as response:
                    content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                    content_length = response.content_length
                    sample = await response.content.read(1024)
                    size_ok = (content_length or len(sample)) > 0
                    if not size_ok:
                        last_error = "empty_payload"
                        continue
                    inferred_media = _guess_media_type_from_url(url)
                    if not _content_type_matches(media_type or inferred_media, content_type):
                        last_error = f"unexpected_content_type:{content_type}"
                        continue
                    log_request_event(
                        request_id=request_id,
                        user_id=user_id,
                        model=model_id,
                        prompt_hash=prompt_hash,
                        task_id=task_id,
                        job_id=job_id,
                        status="result_validated",
                        latency_ms=None,
                        attempt=None,
                        error_code=None,
                        error_msg=None,
                    )
                    return
            except Exception as exc:
                last_error = str(exc)
                continue
        raise KIEResultError(
            "KIE_RESULT_INVALID_CONTENT",
            error_code="KIE_RESULT_INVALID_CONTENT",
            fix_hint=last_error or "Result URL validation failed.",
        )


async def wait_job_result(
    task_id: str,
    model_id: str,
    *,
    client: Any,
    timeout: int,
    max_attempts: int,
    base_delay: float,
    max_delay: float,
    correlation_id: Optional[str],
    request_id: str,
    user_id: Optional[int],
    prompt_hash: Optional[str],
    job_id: Optional[str],
    progress_callback: Optional[Any] = None,
    validate_result_fn: Optional[Any] = None,
    storage: Optional[Any] = None,
    on_timeout: Optional[Any] = None,
) -> Dict[str, Any]:
    start = time.monotonic()
    delay = base_delay
    attempt = 0
    validate_result_fn = validate_result_fn or _validate_result_urls
    while True:
        elapsed = time.monotonic() - start
        if elapsed >= timeout or attempt >= max_attempts:
            log_request_event(
                request_id=request_id,
                user_id=user_id,
                model=model_id,
                prompt_hash=prompt_hash,
                task_id=task_id,
                job_id=job_id,
                status="timeout",
                latency_ms=int(elapsed * 1000),
                attempt=attempt,
                error_code="ERR_KIE_TIMEOUT",
                error_msg="timeout",
            )
            if storage and job_id:
                await storage.update_job_status(
                    job_id,
                    "timeout",
                    error_message="timeout",
                    error_code="ERR_KIE_TIMEOUT",
                )
            if on_timeout:
                await on_timeout()
            raise TimeoutError("ERR_KIE_TIMEOUT")

        attempt += 1
        try:
            if "correlation_id" in inspect.signature(client.get_task_status).parameters:
                record = await client.get_task_status(task_id, correlation_id=correlation_id)
            else:
                record = await client.get_task_status(task_id)
        except Exception as exc:
            log_request_event(
                request_id=request_id,
                user_id=user_id,
                model=model_id,
                prompt_hash=prompt_hash,
                task_id=task_id,
                job_id=job_id,
                status="retry",
                latency_ms=int(elapsed * 1000),
                attempt=attempt,
                error_code="KIE_POLL_EXCEPTION",
                error_msg=str(exc),
            )
            await asyncio.sleep(delay + random.uniform(0, delay * 0.2))
            delay = min(max_delay, delay * 2)
            continue

        record["taskId"] = task_id
        record["elapsed"] = elapsed
        raw_state = record.get("state")
        state = _normalize_kie_state(raw_state)
        log_request_event(
            request_id=request_id,
            user_id=user_id,
            model=model_id,
            prompt_hash=prompt_hash,
            task_id=task_id,
            job_id=job_id,
            status=state,
            latency_ms=int(elapsed * 1000),
            attempt=attempt,
            error_code=None,
            error_msg=None,
        )

        if progress_callback and attempt == 1:
            await progress_callback({"stage": "KIE_POLL", "task_id": task_id, "state": raw_state, "elapsed": elapsed})

        if record.get("ok") is False:
            status = record.get("status")
            if status and status >= 500 or status in {408, 429}:
                await asyncio.sleep(delay + random.uniform(0, delay * 0.2))
                delay = min(max_delay, delay * 2)
                continue
            raise KIERequestFailed(
                record.get("error", "KIE request failed"),
                status=status,
                user_message=record.get("user_message"),
                error_code=record.get("error_code"),
                correlation_id=record.get("correlation_id") or correlation_id,
            )

        if state in {"queued", "running"}:
            if storage and job_id:
                await storage.update_job_status(job_id, state)
            await asyncio.sleep(delay + random.uniform(0, delay * 0.2))
            delay = min(max_delay, delay * 2)
            continue

        if state == "succeeded":
            urls = _extract_urls(record, _parse_result_json(record.get("resultJson")))
            await validate_result_fn(
                urls,
                media_type=None,
                request_id=request_id,
                user_id=user_id,
                model_id=model_id,
                prompt_hash=prompt_hash,
                task_id=task_id,
                job_id=job_id,
            )
            if storage and job_id:
                await storage.update_job_status(job_id, "succeeded", result_urls=urls)
            return record

        if state == "failed":
            fail_code = record.get("failCode")
            fail_msg = record.get("failMsg") or record.get("errorMessage")
            if storage and job_id:
                await storage.update_job_status(
                    job_id,
                    "failed",
                    error_message=fail_msg,
                    error_code=fail_code or "KIE_FAIL_STATE",
                )
            raise KIEJobFailed(
                fail_msg or "Task failed",
                fail_code=fail_code,
                fail_msg=fail_msg,
                correlation_id=correlation_id,
                record_info=record,
            )

        if state == "canceled":
            if storage and job_id:
                await storage.update_job_status(job_id, "canceled", error_message="canceled", error_code="KIE_CANCELED")
            raise KIEJobFailed(
                "Task canceled",
                fail_code="KIE_CANCELED",
                fail_msg="Task canceled",
                correlation_id=correlation_id,
                record_info=record,
            )

        await asyncio.sleep(delay + random.uniform(0, delay * 0.2))
        delay = min(max_delay, delay * 2)


async def run_generation(
    user_id: int,
    model_id: str,
    session_params: Dict[str, Any],
    *,
    timeout: int = 900,
    poll_interval: int = 3,
    correlation_id: Optional[str] = None,
    progress_callback: Optional[Any] = None,
    request_id: Optional[str] = None,
    prompt_hash: Optional[str] = None,
    prompt: Optional[str] = None,
    job_id: Optional[str] = None,
) -> JobResult:
    """Execute the full generation pipeline for any model."""
    catalog = get_model_map()
    spec = catalog.get(model_id)
    if not spec:
        raise ValueError(f"Model '{model_id}' not found in catalog")

    request_id = request_id or str(uuid.uuid4())
    if prompt_hash is None:
        prompt_hash = prompt_summary(prompt or session_params.get("prompt") or session_params.get("text")).get("prompt_hash")

    try:
        payload = build_kie_payload(spec, session_params)
    except PayloadBuildError as exc:
        raise ValueError(str(exc)) from exc

    try:
        from app.integrations.kie_stub import get_kie_client_or_stub

        client: Any = get_kie_client_or_stub()
    except Exception:
        from app.kie.kie_client import get_kie_client

        client = get_kie_client()
    create_start = time.monotonic()
    log_request_event(
        request_id=request_id,
        user_id=user_id,
        model=model_id,
        prompt_hash=prompt_hash,
        task_id=None,
        job_id=job_id,
        status="create_start",
        latency_ms=0,
        attempt=0,
        error_code=None,
        error_msg=None,
    )
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        action="KIE_SUBMIT",
        action_path="universal_engine.run_generation",
        model_id=model_id,
        gen_type=spec.model_mode,
        stage="KIE_SUBMIT",
        waiting_for="KIE_CREATE",
        outcome="start",
    )
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        action="KIE_CREATE",
        action_path="universal_engine.run_generation",
        model_id=model_id,
        gen_type=spec.model_mode,
        stage="KIE_CREATE",
        outcome="start",
    )
    create_fn = getattr(client, "create_task", None)
    if create_fn and "correlation_id" in inspect.signature(create_fn).parameters:
        created = await client.create_task(spec.kie_model, payload["input"], correlation_id=correlation_id)
    else:
        created = await client.create_task(spec.kie_model, payload["input"])
    create_duration_ms = int((time.monotonic() - create_start) * 1000)
    if not created.get("ok"):
        log_request_event(
            request_id=request_id,
            user_id=user_id,
            model=model_id,
            prompt_hash=prompt_hash,
            task_id=None,
            job_id=job_id,
            status="create_failed",
            latency_ms=create_duration_ms,
            attempt=0,
            error_code=created.get("error_code") or "KIE_CREATE_FAILED",
            error_msg=created.get("error"),
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            action="KIE_CREATE",
            action_path="universal_engine.run_generation",
            model_id=model_id,
            gen_type=spec.model_mode,
            stage="KIE_CREATE",
            outcome="failed",
            error_code=created.get("error_code") or "KIE_CREATE_FAILED",
            fix_hint=created.get("user_message"),
            duration_ms=create_duration_ms,
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            action="KIE_SUBMIT",
            action_path="universal_engine.run_generation",
            model_id=model_id,
            gen_type=spec.model_mode,
            stage="KIE_SUBMIT",
            outcome="failed",
            error_code="KIE_CREATE_FAILED",
            duration_ms=create_duration_ms,
        )
        raise KIERequestFailed(
            created.get("error", "create_task_failed"),
            status=created.get("status"),
            user_message=created.get("user_message"),
            error_code=created.get("error_code"),
            correlation_id=created.get("correlation_id") or correlation_id,
        )
    task_id = created.get("taskId")
    log_request_event(
        request_id=request_id,
        user_id=user_id,
        model=model_id,
        prompt_hash=prompt_hash,
        task_id=task_id,
        job_id=job_id,
        status="task_created",
        latency_ms=create_duration_ms,
        attempt=0,
        error_code=None,
        error_msg=None,
    )
    storage = get_storage()
    if storage:
        await storage.add_generation_job(
            user_id=user_id,
            model_id=model_id,
            model_name=spec.name or model_id,
            params=session_params,
            price=0.0,
            task_id=task_id,
            status="queued",
            job_id=job_id,
            request_id=request_id,
            prompt=prompt or session_params.get("prompt") or session_params.get("text"),
            prompt_hash=prompt_hash,
        )
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        action="KIE_CREATE",
        action_path="universal_engine.run_generation",
        model_id=model_id,
        gen_type=spec.model_mode,
        task_id=task_id,
        stage="KIE_CREATE",
        outcome="success",
        duration_ms=create_duration_ms,
    )
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        action="KIE_TASK_CREATED",
        action_path="universal_engine.run_generation",
        model_id=model_id,
        gen_type=spec.model_mode,
        task_id=task_id,
        stage="KIE_CREATE",
        outcome="created",
        duration_ms=create_duration_ms,
    )
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        action="KIE_SUBMIT",
        action_path="universal_engine.run_generation",
        model_id=model_id,
        gen_type=spec.model_mode,
        task_id=task_id,
        stage="KIE_SUBMIT",
        outcome="created",
        duration_ms=create_duration_ms,
    )
    if progress_callback:
        await progress_callback({"stage": "KIE_CREATE", "task_id": task_id})

    poll_start = time.monotonic()
    record = await wait_job_result(
        task_id,
        model_id,
        client=client,
        timeout=timeout,
        max_attempts=int(os.getenv("KIE_POLL_MAX_ATTEMPTS", "80")),
        base_delay=max(1.0, float(poll_interval)),
        max_delay=max(poll_interval, 12),
        correlation_id=correlation_id,
        request_id=request_id,
        user_id=user_id,
        prompt_hash=prompt_hash,
        job_id=job_id,
        progress_callback=progress_callback,
        storage=storage,
    )
    poll_duration_ms = int((time.monotonic() - poll_start) * 1000)
    state = record.get("state")
    if correlation_id:
        trace_event(
            "info",
            correlation_id,
            event="TRACE_IN",
            stage="KIE_DONE",
            action="KIE_DONE",
            task_id=task_id,
            state=state,
            elapsed=record.get("elapsed"),
        )
    if progress_callback:
        await progress_callback({"stage": "KIE_DONE", "task_id": task_id, "state": state})
    if state not in {"success", "completed"}:
        fail_code = record.get("failCode")
        fail_msg = record.get("failMsg") or record.get("errorMessage")
        if correlation_id:
            trace_event(
                "info",
                correlation_id,
                event="TRACE_IN",
                stage="KIE_POLL",
                action="KIE_POLL",
                task_id=task_id,
                state=state,
                fail_code=fail_code,
                fail_msg=fail_msg,
                parse_result="failed",
            )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            action="KIE_POLL",
            action_path="universal_engine.run_generation",
            model_id=model_id,
            gen_type=spec.model_mode,
            task_id=task_id,
            stage="KIE_POLL",
            outcome="failed",
            duration_ms=poll_duration_ms,
            error_code=fail_code or "KIE_FAIL_STATE",
            fix_hint=ERROR_CATALOG.get("KIE_FAIL_STATE"),
            param={"fail_code": fail_code, "fail_msg": fail_msg},
        )
        error_text = fail_msg or "Task failed"
        if fail_code:
            error_text = f"{error_text} (code: {fail_code})"
        raise KIEJobFailed(
            error_text,
            fail_code=fail_code,
            fail_msg=fail_msg,
            correlation_id=correlation_id,
            record_info=record,
        )

    # Notify progress callback that generation is complete and we're preparing result
    if progress_callback:
        await progress_callback({"stage": "KIE_COMPLETE", "task_id": task_id, "state": state})

    parse_start = time.monotonic()
    try:
        base_url = get_settings().kie_result_cdn_base_url
        result = parse_record_info(
            record,
            spec.output_media_type,
            model_id,
            correlation_id=correlation_id,
            base_url=base_url,
        )
        await _validate_result_urls(
            result.urls,
            media_type=result.media_type,
            request_id=request_id,
            user_id=user_id,
            model_id=model_id,
            prompt_hash=prompt_hash,
            task_id=task_id,
            job_id=job_id,
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            action="KIE_PARSE",
            action_path="universal_engine.run_generation",
            model_id=model_id,
            gen_type=spec.model_mode,
            task_id=task_id,
            stage="KIE_PARSE",
            outcome="success",
            duration_ms=int((time.monotonic() - parse_start) * 1000),
        )
        return result
    except Exception:
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            action="KIE_PARSE",
            action_path="universal_engine.run_generation",
            model_id=model_id,
            gen_type=spec.model_mode,
            task_id=task_id,
            stage="KIE_PARSE",
            outcome="failed",
            duration_ms=int((time.monotonic() - parse_start) * 1000),
        )
        raise
