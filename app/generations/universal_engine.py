"""Universal job engine for all KIE models."""
from __future__ import annotations

import json
import logging
import time
import inspect
import asyncio
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.kie.kie_client import KIEClient
from app.observability.trace import trace_event, url_summary
from app.observability.structured_logs import log_structured_event
from app.observability.error_catalog import ERROR_CATALOG
from app.kie_catalog import get_model_map, ModelSpec
from app.kie_contract.payload_builder import build_kie_payload, PayloadBuildError
from app.utils.url_normalizer import normalize_result_urls, ResultUrlNormalizationError
from app.config import get_settings

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


async def run_generation(
    user_id: int,
    model_id: str,
    session_params: Dict[str, Any],
    *,
    timeout: int = 900,
    poll_interval: int = 3,
    correlation_id: Optional[str] = None,
    progress_callback: Optional[Any] = None,
) -> JobResult:
    """Execute the full generation pipeline for any model."""
    catalog = get_model_map()
    spec = catalog.get(model_id)
    if not spec:
        raise ValueError(f"Model '{model_id}' not found in catalog")

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
    attempt = 0
    poll_delay = poll_interval
    max_poll_delay = max(poll_interval, 12)
    error_attempts = 0
    error_retry_limit = int(os.getenv("KIE_POLL_ERROR_RETRIES", "3"))
    progress_interval = 25
    next_progress_at = poll_start + progress_interval
    get_status_fn = getattr(client, "get_task_status", None)
    record: Dict[str, Any] = {}
    state = None
    while True:
        elapsed = time.monotonic() - poll_start
        if elapsed > timeout:
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                action="KIE_POLL",
                action_path="universal_engine.run_generation",
                model_id=model_id,
                gen_type=spec.model_mode,
                task_id=task_id,
                stage="KIE_POLL",
                outcome="timeout",
                duration_ms=int(elapsed * 1000),
                error_code="ERR_KIE_TIMEOUT",
                fix_hint=ERROR_CATALOG.get("KIE_TIMEOUT"),
                param={"task_id": task_id, "attempt": attempt, "elapsed": round(elapsed, 3)},
            )
            raise TimeoutError("ERR_KIE_TIMEOUT")

        attempt += 1
        if get_status_fn:
            if "correlation_id" in inspect.signature(get_status_fn).parameters:
                record = await client.get_task_status(task_id, correlation_id=correlation_id)
            else:
                record = await client.get_task_status(task_id)
        else:
            wait_fn = getattr(client, "wait_for_task", None)
            if wait_fn and "correlation_id" in inspect.signature(wait_fn).parameters:
                record = await client.wait_for_task(
                    task_id,
                    timeout=timeout,
                    poll_interval=poll_interval,
                    correlation_id=correlation_id,
                )
            else:
                record = await client.wait_for_task(task_id, timeout=timeout, poll_interval=poll_interval)

        record["taskId"] = task_id
        record["elapsed"] = elapsed
        state = record.get("state")
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            action="KIE_POLL",
            action_path="universal_engine.run_generation",
            model_id=model_id,
            gen_type=spec.model_mode,
            task_id=task_id,
            stage="KIE_POLL",
            outcome=state,
            duration_ms=int(elapsed * 1000),
            param={"task_id": task_id, "attempt": attempt, "elapsed": round(elapsed, 3), "poll_delay": poll_delay},
        )
        if progress_callback and elapsed >= next_progress_at:
            await progress_callback(
                {"stage": "KIE_POLL", "task_id": task_id, "state": state, "attempt": attempt, "elapsed": elapsed}
            )
            next_progress_at = time.monotonic() + progress_interval

        if record.get("ok") is False:
            status = record.get("status")
            if status in {401, 402, 422}:
                raise KIERequestFailed(
                    record.get("error", "KIE request failed"),
                    status=status,
                    user_message=record.get("user_message"),
                    error_code=record.get("error_code"),
                    correlation_id=record.get("correlation_id") or correlation_id,
                )
            if status in {429, 500}:
                error_attempts += 1
                log_structured_event(
                    correlation_id=correlation_id,
                    user_id=user_id,
                    action="KIE_POLL",
                    action_path="universal_engine.run_generation",
                    model_id=model_id,
                    gen_type=spec.model_mode,
                    task_id=task_id,
                    stage="KIE_POLL",
                    outcome="retry",
                    error_code=record.get("error_code") or f"KIE_POLL_{status}",
                    fix_hint=record.get("user_message"),
                    param={
                        "status": status,
                        "attempt": error_attempts,
                        "retry_limit": error_retry_limit,
                    },
                )
                if error_attempts > error_retry_limit:
                    raise KIERequestFailed(
                        record.get("error", "KIE request failed"),
                        status=status,
                        user_message=record.get("user_message"),
                        error_code=record.get("error_code"),
                        correlation_id=record.get("correlation_id") or correlation_id,
                    )
                await asyncio.sleep(poll_delay)
                poll_delay = min(max_poll_delay, poll_delay * 1.5)
                continue
            await asyncio.sleep(poll_delay)
            poll_delay = min(max_poll_delay, poll_delay * 1.5)
            continue
        if state in {"success", "completed", "failed"}:
            break

        await asyncio.sleep(poll_delay)
        poll_delay = min(max_poll_delay, poll_delay * 1.5)

    poll_duration_ms = int((time.monotonic() - poll_start) * 1000)
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
