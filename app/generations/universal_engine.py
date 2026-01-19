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


def parse_record_info(
    record: Dict[str, Any],
    media_type: str,
    model_id: str,
    correlation_id: Optional[str] = None,
) -> JobResult:
    result_json = _parse_result_json(record.get("resultJson"))
    urls: List[str] = []
    text: Optional[str] = None

    if media_type in {"image", "video", "audio", "voice", "file"}:
        urls = result_json.get("resultUrls") or []
        if not urls and result_json.get("resultUrl"):
            urls = [result_json.get("resultUrl")]
        if not urls:
            logger.error(
                "KIE_RESULT_EMPTY model=%s state=%s failCode=%s failMsg=%s keys=%s",
                model_id,
                record.get("state"),
                record.get("failCode"),
                record.get("failMsg"),
                list(result_json.keys()),
            )
            raise KIEResultError("KIE_RESULT_EMPTY")
    elif media_type == "text":
        text = result_json.get("resultObject") or result_json.get("text") or record.get("resultText")
        if not text:
            logger.error(
                "KIE_RESULT_EMPTY_TEXT model=%s state=%s failCode=%s failMsg=%s keys=%s",
                model_id,
                record.get("state"),
                record.get("failCode"),
                record.get("failMsg"),
                list(result_json.keys()),
            )
            raise KIEResultError("KIE_RESULT_EMPTY_TEXT")
    else:
        raise KIEResultError(f"Unsupported media_type: {media_type}")

    job_result = JobResult(
        task_id=record.get("taskId", ""),
        state=record.get("state", ""),
        media_type=media_type,
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
            media_type=media_type,
            result_url_summary=url_summary(urls[0]) if urls else None,
            parse_result="ok",
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
    if state != "success":
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
