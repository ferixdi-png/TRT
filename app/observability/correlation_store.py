"""Correlation registry for task_id/job_id/request_id backfill."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

from app.observability.trace import get_correlation_id as get_trace_correlation_id

logger = logging.getLogger(__name__)

CORRELATIONS_FILE = "observability_correlations.json"
_DELIVERY_COMPLETE_STATES = {"delivered", "success", "succeeded", "completed"}


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class CorrelationRecord:
    correlation_id: str
    request_id: Optional[str] = None
    task_id: Optional[str] = None
    job_id: Optional[str] = None
    user_id: Optional[int] = None
    model_id: Optional[str] = None
    updated_at_ms: int = field(default_factory=_now_ms)
    missing_actions: Set[str] = field(default_factory=set)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "request_id": self.request_id,
            "task_id": self.task_id,
            "job_id": self.job_id,
            "user_id": self.user_id,
            "model_id": self.model_id,
            "updated_at_ms": self.updated_at_ms,
            "missing_actions": sorted(self.missing_actions),
        }


_records_by_correlation: Dict[str, CorrelationRecord] = {}
_records_by_request: Dict[str, CorrelationRecord] = {}
_persist_tasks: Set[asyncio.Task[Any]] = set()


def _register_persist_task(task: asyncio.Task[Any]) -> None:
    _persist_tasks.add(task)
    task.add_done_callback(_persist_tasks.discard)


def _get_running_loop() -> Optional[asyncio.AbstractEventLoop]:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _resolve_storage(storage: Optional[Any]) -> Optional[Any]:
    if storage is not None:
        return storage
    from app.storage import get_storage

    try:
        return get_storage()
    except Exception:
        return None


def _normalize_correlation_id(correlation_id: Optional[str], request_id: Optional[str]) -> Optional[str]:
    resolved = correlation_id or request_id or get_trace_correlation_id()
    if not resolved:
        return None
    return str(resolved)


def _get_record(correlation_id: str) -> CorrelationRecord:
    record = _records_by_correlation.get(correlation_id)
    if record:
        return record
    record = CorrelationRecord(correlation_id=correlation_id)
    _records_by_correlation[correlation_id] = record
    return record


def resolve_correlation_ids(
    *,
    correlation_id: Optional[str],
    request_id: Optional[str],
    task_id: Optional[str],
    job_id: Optional[str],
) -> Dict[str, Optional[str]]:
    """Resolve ids from in-memory registry."""
    resolved_corr = _normalize_correlation_id(correlation_id, request_id)
    record: Optional[CorrelationRecord] = None
    if resolved_corr:
        record = _records_by_correlation.get(resolved_corr)
    if not record and request_id:
        record = _records_by_request.get(str(request_id))
        if record:
            resolved_corr = record.correlation_id
    resolved_request_id = str(request_id) if request_id else (record.request_id if record else None)
    resolved_task_id = str(task_id) if task_id else (record.task_id if record else None)
    resolved_job_id = str(job_id) if job_id else (record.job_id if record else None)
    return {
        "correlation_id": resolved_corr,
        "request_id": resolved_request_id,
        "task_id": resolved_task_id,
        "job_id": resolved_job_id,
    }


def _merge_record(
    record: CorrelationRecord,
    *,
    request_id: Optional[str],
    task_id: Optional[str],
    job_id: Optional[str],
    user_id: Optional[int],
    model_id: Optional[str],
    missing_actions: Optional[Set[str]] = None,
) -> tuple[CorrelationRecord, bool]:
    changed = False
    if request_id and record.request_id != request_id:
        record.request_id = request_id
        changed = True
    if task_id and record.task_id != task_id:
        record.task_id = task_id
        changed = True
    if job_id and record.job_id != job_id:
        record.job_id = job_id
        changed = True
    if user_id is not None and record.user_id != user_id:
        record.user_id = int(user_id)
        changed = True
    if model_id and record.model_id != model_id:
        record.model_id = model_id
        changed = True
    if missing_actions:
        before = set(record.missing_actions)
        record.missing_actions.update(missing_actions)
        if record.missing_actions != before:
            changed = True
    if record.task_id and record.job_id and record.missing_actions:
        record.missing_actions.clear()
        changed = True
    if changed:
        record.updated_at_ms = _now_ms()
    return record, changed


async def _persist_record(record: CorrelationRecord, *, storage: Optional[Any], source: Optional[str]) -> None:
    storage_instance = _resolve_storage(storage)
    if not storage_instance or not hasattr(storage_instance, "update_json_file"):
        return

    async def _update_file() -> None:
        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            next_data = dict(data or {})
            payload = dict(next_data.get(record.correlation_id) or {})
            payload.update(record.to_dict())
            if source:
                payload["source"] = source
            next_data[record.correlation_id] = payload
            if record.request_id:
                index_key = f"request:{record.request_id}"
                request_payload = dict(next_data.get(index_key) or {})
                request_payload.update(
                    {
                        "correlation_id": record.correlation_id,
                        "request_id": record.request_id,
                        "task_id": record.task_id,
                        "job_id": record.job_id,
                        "updated_at_ms": record.updated_at_ms,
                    }
                )
                next_data[index_key] = request_payload
            return next_data

        await storage_instance.update_json_file(CORRELATIONS_FILE, updater)

    try:
        await _update_file()
    except Exception as exc:
        logger.debug("correlation_store_persist_failed correlation_id=%s error=%s", record.correlation_id, exc)


async def register_correlation_ids(
    *,
    correlation_id: Optional[str],
    request_id: Optional[str],
    task_id: Optional[str],
    job_id: Optional[str],
    user_id: Optional[int],
    model_id: Optional[str],
    storage: Optional[Any] = None,
    source: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Register known ids and persist them when possible."""
    resolved_corr = _normalize_correlation_id(correlation_id, request_id)
    if not resolved_corr:
        return {"correlation_id": None, "request_id": request_id, "task_id": task_id, "job_id": job_id}
    record = _get_record(resolved_corr)
    record, changed = _merge_record(
        record,
        request_id=str(request_id) if request_id else None,
        task_id=str(task_id) if task_id else None,
        job_id=str(job_id) if job_id else None,
        user_id=user_id,
        model_id=model_id,
    )
    if record.request_id:
        _records_by_request[record.request_id] = record
    if changed:
        await _persist_record(record, storage=storage, source=source)
    return resolve_correlation_ids(
        correlation_id=record.correlation_id,
        request_id=record.request_id,
        task_id=record.task_id,
        job_id=record.job_id,
    )


def register_ids(
    *,
    correlation_id: Optional[str],
    request_id: Optional[str],
    task_id: Optional[str],
    job_id: Optional[str],
    user_id: Optional[int],
    model_id: Optional[str],
    storage: Optional[Any] = None,
    source: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Sync helper that updates memory and schedules persistence when possible."""
    resolved_corr = _normalize_correlation_id(correlation_id, request_id)
    if not resolved_corr:
        return {"correlation_id": None, "request_id": request_id, "task_id": task_id, "job_id": job_id}
    record = _get_record(resolved_corr)
    record, changed = _merge_record(
        record,
        request_id=str(request_id) if request_id else None,
        task_id=str(task_id) if task_id else None,
        job_id=str(job_id) if job_id else None,
        user_id=user_id,
        model_id=model_id,
    )
    if record.request_id:
        _records_by_request[record.request_id] = record
    if changed:
        loop = _get_running_loop()
        if loop and loop.is_running():
            task = loop.create_task(
                _persist_record(record, storage=storage, source=source),
                name=f"correlation-store:{record.correlation_id}",
            )
            _register_persist_task(task)
    return resolve_correlation_ids(
        correlation_id=record.correlation_id,
        request_id=record.request_id,
        task_id=record.task_id,
        job_id=record.job_id,
    )


def note_missing_ids(
    *,
    correlation_id: Optional[str],
    request_id: Optional[str],
    action: Optional[str],
    stage: Optional[str],
    missing_ids: Set[str],
    reason: str,
    storage: Optional[Any] = None,
) -> None:
    """Record that an event was emitted without full ids."""
    resolved_corr = _normalize_correlation_id(correlation_id, request_id)
    if not resolved_corr or not action:
        return
    missing_tag = ",".join(sorted(missing_ids))
    action_tag = f"{action}:{stage or 'na'}:{missing_tag}:{reason}"
    record = _get_record(resolved_corr)
    record, changed = _merge_record(
        record,
        request_id=str(request_id) if request_id else None,
        task_id=None,
        job_id=None,
        user_id=record.user_id,
        model_id=record.model_id,
        missing_actions={action_tag},
    )
    if record.request_id:
        _records_by_request[record.request_id] = record
    if changed:
        loop = _get_running_loop()
        if loop and loop.is_running():
            task = loop.create_task(
                _persist_record(record, storage=storage, source="missing_ids"),
                name=f"correlation-missing:{record.correlation_id}",
            )
            _register_persist_task(task)


def is_delivery_complete(status: Optional[str]) -> bool:
    if not status:
        return False
    return str(status).lower() in _DELIVERY_COMPLETE_STATES


def reset_correlation_store() -> None:
    _records_by_correlation.clear()
    _records_by_request.clear()
    for task in list(_persist_tasks):
        task.cancel()
    _persist_tasks.clear()
