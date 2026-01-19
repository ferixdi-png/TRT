"""Universal job engine for all KIE models."""
from __future__ import annotations

import json
import logging
import time
import inspect
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.kie.kie_client import KIEClient
from app.observability.trace import trace_event, url_summary
from app.observability.structured_logs import log_structured_event
from app.observability.error_catalog import ERROR_CATALOG
from app.kie_catalog import get_model_map, ModelSpec
from app.kie_contract.payload_builder import build_kie_payload, PayloadBuildError

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
    return (
        record.get("resultText")
        or result_json.get("resultText")
        or result_json.get("resultObject")
        or result_json.get("text")
    )


def _infer_media_from_urls(urls: List[str], fallback: str) -> str:
    if fallback in {"image", "video", "audio", "voice", "text"}:
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
) -> JobResult:
    result_json = _parse_result_json(record.get("resultJson"))
    urls = _extract_urls(record, result_json)
    text = _extract_text(record, result_json)

    supported_media = {"image", "video", "audio", "voice", "file", "text"}
    hint_media = media_type if media_type in supported_media else ""

    if text and not urls:
        resolved_media = "text"
    elif urls:
        fallback_hint = hint_media if hint_media and hint_media != "text" else "document"
        resolved_media = _infer_media_from_urls(urls, fallback_hint)
        if hint_media == "voice" and resolved_media == "audio":
            resolved_media = "voice"
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
            outcome="failed",
            error_code="KIE_RESULT_EMPTY",
            fix_hint=fix_hint,
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
            outcome="failed",
            error_code="KIE_RESULT_EMPTY_TEXT",
            fix_hint=fix_hint,
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
            outcome="success",
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
        client = KIEClient()
    create_fn = getattr(client, "create_task", None)
    if create_fn and "correlation_id" in inspect.signature(create_fn).parameters:
        created = await client.create_task(spec.kie_model, payload["input"], correlation_id=correlation_id)
    else:
        created = await client.create_task(spec.kie_model, payload["input"])
    if not created.get("ok"):
        raise RuntimeError(created.get("error", "create_task_failed"))
    task_id = created.get("taskId")
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        action="KIE_CREATE",
        action_path="universal_engine.run_generation",
        model_id=model_id,
        outcome="created",
    )
    if progress_callback:
        await progress_callback({"stage": "KIE_CREATE", "task_id": task_id})

    start_time = time.time()
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
    record["elapsed"] = time.time() - start_time
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
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        action="KIE_DONE",
        action_path="universal_engine.run_generation",
        model_id=model_id,
        outcome=state,
        duration_ms=int(record.get("elapsed", 0) * 1000),
    )
    if progress_callback:
        await progress_callback({"stage": "KIE_DONE", "task_id": task_id, "state": state})
    if state not in {"success", "completed"}:
        if correlation_id:
            trace_event(
                "info",
                correlation_id,
                event="TRACE_IN",
                stage="KIE_POLL",
                action="KIE_POLL",
                task_id=task_id,
                state=state,
                fail_code=record.get("failCode"),
                fail_msg=record.get("failMsg"),
                parse_result="failed",
            )
        raise RuntimeError(record.get("failMsg") or record.get("errorMessage") or "Task failed")

    return parse_record_info(record, spec.output_media_type, model_id, correlation_id=correlation_id)
