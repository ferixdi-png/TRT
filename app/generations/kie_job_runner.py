"""Unified KIE job runner for all models."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.generations.telegram_sender import deliver_result
from app.generations.universal_engine import JobResult, parse_record_info
from app.kie.kie_client import KIEClient
from app.kie_catalog import ModelSpec


def _get_media_type(model_meta: ModelSpec | Dict[str, Any]) -> str:
    if isinstance(model_meta, ModelSpec):
        return model_meta.output_media_type or "file"
    return model_meta.get("output_media_type") or model_meta.get("media_type") or "file"


async def create_task(
    model_id: str,
    input_payload: Dict[str, Any],
    *,
    correlation_id: Optional[str] = None,
    callback_url: Optional[str] = None,
    client: Optional[KIEClient] = None,
) -> str:
    kie_client = client or KIEClient()
    result = await kie_client.create_task(
        model_id,
        input_payload,
        callback_url=callback_url,
        correlation_id=correlation_id,
    )
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "create_task_failed")
    return result.get("taskId", "")


async def poll_task(
    task_id: str,
    *,
    timeout: int = 900,
    poll_interval: int = 3,
    correlation_id: Optional[str] = None,
    client: Optional[KIEClient] = None,
) -> Dict[str, Any]:
    kie_client = client or KIEClient()
    record = await kie_client.wait_for_task(
        task_id,
        timeout=timeout,
        poll_interval=poll_interval,
        correlation_id=correlation_id,
    )
    record["taskId"] = task_id
    state = record.get("state")
    if state != "success":
        raise RuntimeError(record.get("failMsg") or record.get("errorMessage") or "task_failed")
    return record


def parse_result(
    record: Dict[str, Any],
    model_meta: ModelSpec | Dict[str, Any],
    *,
    correlation_id: Optional[str] = None,
) -> JobResult:
    media_type = _get_media_type(model_meta)
    model_id = model_meta.id if isinstance(model_meta, ModelSpec) else model_meta.get("id", "unknown")
    return parse_record_info(
        record,
        media_type,
        model_id,
        correlation_id=correlation_id,
    )


async def send_result_to_user(
    update: Any,
    context: Any,
    parsed_result: JobResult,
    *,
    correlation_id: Optional[str] = None,
) -> None:
    chat_id = update.effective_chat.id if getattr(update, "effective_chat", None) else None
    if chat_id is None:
        raise RuntimeError("chat_id_missing")
    await deliver_result(
        context.bot,
        chat_id,
        parsed_result.media_type,
        parsed_result.urls,
        parsed_result.text,
        correlation_id=correlation_id,
    )
