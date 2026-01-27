"""Correlation registry for task_id/job_id/request_id backfill."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import suppress
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
_persist_debounce_tasks: Dict[str, asyncio.Task[Any]] = {}
_persist_debounce_seconds = float(os.getenv("CORRELATION_STORE_DEBOUNCE_SECONDS", "0.5"))
_flush_interval_seconds = float(os.getenv("CORRELATION_STORE_FLUSH_INTERVAL_SECONDS", "1.0"))
_flush_interval_ms_raw = os.getenv("OBS_FLUSH_INTERVAL_MS", "").strip()
if _flush_interval_ms_raw:
    try:
        _flush_interval_seconds = max(0.01, float(_flush_interval_ms_raw) / 1000)
    except ValueError:
        logger.warning("OBS_FLUSH_INTERVAL_MS invalid: %s", _flush_interval_ms_raw)
_persist_timeout_seconds = float(os.getenv("CORRELATION_STORE_PERSIST_TIMEOUT_SECONDS", "2.5"))
_flush_timeout_log_interval_seconds = float(
    os.getenv("CORRELATION_STORE_FLUSH_TIMEOUT_LOG_INTERVAL_SECONDS", "30.0")
)
_flush_timeout_last_log_ts: Optional[float] = None
_flush_max_records = int(os.getenv("CORRELATION_STORE_FLUSH_MAX_RECORDS", "200"))
_queue_max_records = int(os.getenv("OBS_QUEUE_MAX", "1000"))
_dropped_records_total = 0
_pending_records: Dict[str, CorrelationRecord] = {}
_pending_sources: Dict[str, Optional[str]] = {}
_flush_task: Optional[asyncio.Task[Any]] = None
_pending_storage: Optional[Any] = None
_flush_lock: Optional[asyncio.Lock] = None


def _register_persist_task(task: asyncio.Task[Any]) -> None:
    _persist_tasks.add(task)
    task.add_done_callback(_persist_tasks.discard)


def _register_debounce_task(correlation_id: str, task: asyncio.Task[Any]) -> None:
    _persist_debounce_tasks[correlation_id] = task

    def _cleanup(done_task: asyncio.Task[Any]) -> None:
        if _persist_debounce_tasks.get(correlation_id) is done_task:
            _persist_debounce_tasks.pop(correlation_id, None)

    task.add_done_callback(_cleanup)
    _register_persist_task(task)


def _schedule_debounced_persist(
    *,
    correlation_id: str,
    storage: Optional[Any],
    source: Optional[str],
) -> None:
    loop = _get_running_loop()
    if not loop or not loop.is_running():
        return
    record = _records_by_correlation.get(correlation_id)
    if not record:
        return
    global _dropped_records_total
    if _queue_max_records > 0 and correlation_id not in _pending_records and len(_pending_records) >= _queue_max_records:
        _dropped_records_total += 1
        logger.warning(
            "correlation_store_queue_full dropped_total=%s queue_max=%s correlation_id=%s",
            _dropped_records_total,
            _queue_max_records,
            correlation_id,
        )
        logger.info(
            "METRIC_GAUGE name=correlation_store_dropped_total value=%s queue_max=%s",
            _dropped_records_total,
            _queue_max_records,
        )
        return
    _pending_records[correlation_id] = record
    if source:
        _pending_sources[correlation_id] = source
    global _pending_storage, _flush_task, _flush_lock
    if storage is not None:
        _pending_storage = storage
    if _flush_lock is None:
        _flush_lock = asyncio.Lock()
    if _flush_task and not _flush_task.done():
        return

    async def _flush_pending() -> None:
        if _persist_debounce_seconds > 0:
            await asyncio.sleep(_persist_debounce_seconds)
        while True:
            async with _flush_lock:
                if not _pending_records:
                    return
                batch_keys = list(_pending_records.keys())[:_flush_max_records]
                batch = {key: _pending_records.pop(key) for key in batch_keys}
                batch_sources = {key: _pending_sources.pop(key, None) for key in batch_keys}
                storage_instance = _pending_storage or storage
            try:
                await asyncio.wait_for(
                    _persist_records_batch(batch, storage=storage_instance, sources=batch_sources),
                    timeout=_persist_timeout_seconds,
                )
            except asyncio.TimeoutError:
                global _flush_timeout_last_log_ts
                now = time.monotonic()
                if (
                    _flush_timeout_log_interval_seconds <= 0
                    or _flush_timeout_last_log_ts is None
                    or (now - _flush_timeout_last_log_ts) >= _flush_timeout_log_interval_seconds
                ):
                    _flush_timeout_last_log_ts = now
                    logger.warning(
                        "correlation_store_flush_timeout batch_size=%s timeout_s=%.2f",
                        len(batch),
                        _persist_timeout_seconds,
                    )
                else:
                    logger.debug(
                        "correlation_store_flush_timeout_suppressed batch_size=%s timeout_s=%.2f",
                        len(batch),
                        _persist_timeout_seconds,
                    )
                async with _flush_lock:
                    _pending_records.update(batch)
                    _pending_sources.update(batch_sources)
                await asyncio.sleep(_flush_interval_seconds)
                continue
            if _pending_records:
                await asyncio.sleep(_flush_interval_seconds)
            else:
                return

    _flush_task = loop.create_task(_flush_pending(), name="correlation-store:flush")
    _register_persist_task(_flush_task)

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

        await storage_instance.update_json_file(
            CORRELATIONS_FILE,
            updater,
            lock_mode="pg_try_advisory_xact_lock",
        )

    try:
        await _update_file()
    except Exception as exc:
        logger.debug("correlation_store_persist_failed correlation_id=%s error=%s", record.correlation_id, exc)


async def _persist_records_batch(
    records: Dict[str, CorrelationRecord],
    *,
    storage: Optional[Any],
    sources: Dict[str, Optional[str]],
) -> None:
    if not records:
        return
    from app.utils.fault_injection import maybe_inject_sleep

    await maybe_inject_sleep("TRT_FAULT_INJECT_CORR_FLUSH_SLEEP_MS", label="correlation_store.flush")
    storage_instance = _resolve_storage(storage)
    if not storage_instance or not hasattr(storage_instance, "update_json_file"):
        return

    async def _update_file() -> None:
        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            next_data = dict(data or {})
            for record in records.values():
                payload = dict(next_data.get(record.correlation_id) or {})
                payload.update(record.to_dict())
                source = sources.get(record.correlation_id)
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

        await storage_instance.update_json_file(
            CORRELATIONS_FILE,
            updater,
            lock_mode="pg_try_advisory_xact_lock",
        )

    start_ts = time.monotonic()
    try:
        await _update_file()
    except Exception as exc:
        logger.debug(
            "correlation_store_persist_failed batch_size=%s error=%s",
            len(records),
            exc,
        )
        return
    duration_ms = int((time.monotonic() - start_ts) * 1000)
    logger.info(
        "METRIC_GAUGE name=correlation_store_flush_duration_ms value=%s count=%s",
        duration_ms,
        len(records),
    )


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
        _schedule_debounced_persist(
            correlation_id=record.correlation_id,
            storage=storage,
            source=source,
        )
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
            _schedule_debounced_persist(
                correlation_id=record.correlation_id,
                storage=storage,
                source=source,
            )
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
            _schedule_debounced_persist(
                correlation_id=record.correlation_id,
                storage=storage,
                source="missing_ids",
            )


def is_delivery_complete(status: Optional[str]) -> bool:
    if not status:
        return False
    return str(status).lower() in _DELIVERY_COMPLETE_STATES


def reset_correlation_store() -> None:
    def _cancel_task_safe(task: asyncio.Task[Any]) -> None:
        try:
            loop = task.get_loop()
        except Exception:
            loop = None
        if loop is not None and loop.is_closed():
            return
        with suppress(RuntimeError):
            task.cancel()

    _records_by_correlation.clear()
    _records_by_request.clear()
    for task in list(_persist_tasks):
        _cancel_task_safe(task)
    _persist_tasks.clear()
    for task in list(_persist_debounce_tasks.values()):
        _cancel_task_safe(task)
    _persist_debounce_tasks.clear()
    global _flush_task, _pending_storage
    if _flush_task:
        _cancel_task_safe(_flush_task)
    _flush_task = None
    _pending_storage = None
    _pending_records.clear()
    _pending_sources.clear()
    global _flush_timeout_last_log_ts
    _flush_timeout_last_log_ts = None
