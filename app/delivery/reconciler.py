"""Background reconciler for pending generation results."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from app.config import get_settings
from app.generations.telegram_sender import send_result_file
from app.generations.universal_engine import (
    KIEResultError,
    _validate_result_urls,
    parse_record_info,
)
from app.kie_catalog import get_model
from app.observability.delivery_metrics import metrics_snapshot, record_pending_age
from app.observability.structured_logs import log_structured_event
from app.observability.task_lifecycle import log_task_lifecycle

logger = logging.getLogger(__name__)

PENDING_STATES = {"pending", "queued", "running", "timeout"}
SUCCESS_STATES = {"success", "completed", "succeeded"}
FAILED_STATES = {"failed", "fail", "error", "canceled", "cancelled", "canceled"}


def _delivery_key(user_id: int, task_id: str) -> str:
    return f"{user_id}:{task_id}"


async def _reserve_delivery(
    storage,
    *,
    user_id: int,
    task_id: str,
    job_id: Optional[str],
    model_id: Optional[str],
    request_id: Optional[str],
) -> bool:
    already_delivered = False
    now_iso = datetime.now().isoformat()
    key = _delivery_key(user_id, task_id)

    def updater(data: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal already_delivered
        record = data.get(key, {})
        if record.get("status") == "delivered":
            already_delivered = True
            return data
        attempts = int(record.get("attempts", 0)) + 1
        data[key] = {
            "user_id": user_id,
            "task_id": task_id,
            "job_id": job_id,
            "model_id": model_id,
            "request_id": request_id,
            "status": "delivering",
            "attempts": attempts,
            "created_at": record.get("created_at", now_iso),
            "updated_at": now_iso,
        }
        return data

    await storage.update_json_file("delivery_records.json", updater)
    return already_delivered


async def _finalize_delivery(
    storage,
    *,
    user_id: int,
    task_id: str,
    success: bool,
    error: Optional[str] = None,
    result_urls: Optional[Iterable[str]] = None,
) -> None:
    now_iso = datetime.now().isoformat()
    key = _delivery_key(user_id, task_id)

    def updater(data: Dict[str, Any]) -> Dict[str, Any]:
        record = data.get(key, {})
        record.update(
            {
                "status": "delivered" if success else "failed",
                "updated_at": now_iso,
                "error": error,
                "result_urls": list(result_urls or record.get("result_urls", [])),
            }
        )
        if success:
            record["delivered_at"] = now_iso
        data[key] = record
        return data

    await storage.update_json_file("delivery_records.json", updater)


def _parse_iso_ts(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


async def deliver_job_result(
    bot,
    storage,
    *,
    job: Dict[str, Any],
    status_record: Dict[str, Any],
    notify_user: bool,
    source: str,
) -> bool:
    user_id = job.get("user_id")
    if user_id is None:
        return False
    task_id = job.get("task_id") or job.get("external_task_id") or status_record.get("taskId")
    if not task_id:
        return False
    model_id = job.get("model_id")
    job_id = job.get("job_id") or task_id
    request_id = job.get("request_id")
    prompt_hash = job.get("prompt_hash")

    model_spec = get_model(model_id) if model_id else None
    if not model_spec:
        logger.warning("Missing model spec for delivery: model_id=%s", model_id)
        return False

    base_url = get_settings().kie_result_cdn_base_url
    try:
        job_result = parse_record_info(
            status_record,
            model_spec.output_media_type,
            model_id,
            correlation_id=job.get("request_id"),
            base_url=base_url,
        )
        if job_result.urls:
            await _validate_result_urls(
                job_result.urls,
                media_type=job_result.media_type,
                request_id=request_id or "",
                user_id=user_id,
                model_id=model_id,
                prompt_hash=prompt_hash,
                task_id=task_id,
                job_id=job_id,
            )
    except KIEResultError as exc:
        try:
            await storage.update_job_status(
                job_id,
                "failed",
                error_message=str(exc),
                error_code=getattr(exc, "error_code", "KIE_RESULT_ERROR"),
            )
        except Exception as storage_exc:
            logger.warning("Failed to update job failure: %s", storage_exc)
        log_task_lifecycle(
            state="failed",
            user_id=user_id,
            task_id=task_id,
            job_id=job_id,
            model_id=model_id,
            source=source,
            detail={"reason": "result_validation_failed"},
        )
        return False

    try:
        await storage.update_job_status(
            job_id,
            "completed",
            result_urls=job_result.urls,
        )
    except Exception as storage_exc:
        logger.warning("Failed to update job completion: %s", storage_exc)
    log_task_lifecycle(
        state="done",
        user_id=user_id,
        task_id=task_id,
        job_id=job_id,
        model_id=model_id,
        source=source,
    )

    already_delivered = await _reserve_delivery(
        storage,
        user_id=user_id,
        task_id=task_id,
        job_id=job_id,
        model_id=model_id,
        request_id=request_id,
    )
    if already_delivered:
        return True

    if notify_user:
        try:
            await bot.send_message(
                chat_id=user_id,
                text="✅ Результат готов, отправляю повторно.",
            )
        except Exception:
            pass

    delivered = False
    try:
        delivered = bool(
            await send_result_file(
                bot,
                user_id,
                job_result.media_type,
                job_result.urls,
                job_result.text,
                model_id=model_id,
                gen_type=model_spec.model_mode,
                correlation_id=job.get("request_id"),
                request_id=request_id,
                prompt_hash=prompt_hash,
                params={"prompt": job.get("prompt")} if job.get("prompt") else None,
                model_label=model_spec.name or model_id,
            )
        )
    except Exception as exc:
        log_structured_event(
            correlation_id=job.get("request_id"),
            user_id=user_id,
            chat_id=user_id,
            action="DELIVERY_FAIL",
            action_path=source,
            model_id=model_id,
            stage="TG_DELIVER",
            outcome="failed",
            error_code="TG_DELIVER_EXCEPTION",
            fix_hint=str(exc),
            param={"task_id": task_id},
        )

    await _finalize_delivery(
        storage,
        user_id=user_id,
        task_id=task_id,
        success=delivered,
        error=None if delivered else "delivery_failed",
        result_urls=job_result.urls,
    )
    if delivered:
        log_task_lifecycle(
            state="delivered",
            user_id=user_id,
            task_id=task_id,
            job_id=job_id,
            model_id=model_id,
            source=source,
        )
    return delivered


async def reconcile_pending_results(
    bot,
    storage,
    kie_client,
    *,
    batch_limit: int,
    pending_age_alert_seconds: int,
    queue_tail_alert_threshold: int,
) -> None:
    jobs = await storage.list_jobs_by_status(list(PENDING_STATES), limit=batch_limit)
    if not jobs:
        return

    now_ts = time.time()
    pending_ages = []
    for job in jobs:
        created_ts = _parse_iso_ts(job.get("created_at"))
        if created_ts is None:
            continue
        age = now_ts - created_ts
        pending_ages.append(age)
        record_pending_age(age)

    if pending_ages:
        max_age = max(pending_ages)
        if max_age >= pending_age_alert_seconds:
            logger.warning(
                "PENDING_QUEUE_AGE_ALERT max_age=%s pending_count=%s",
                int(max_age),
                len(jobs),
            )
            log_structured_event(
                action="QUEUE_AGE_ALERT",
                action_path="delivery_reconciler",
                stage="DELIVERY_MONITOR",
                outcome="alert",
                param={"pending_count": len(jobs), "max_age_s": int(max_age)},
            )

    if len(jobs) >= queue_tail_alert_threshold:
        logger.warning(
            "PENDING_QUEUE_TAIL_ALERT pending_count=%s threshold=%s",
            len(jobs),
            queue_tail_alert_threshold,
        )
        log_structured_event(
            action="QUEUE_TAIL_ALERT",
            action_path="delivery_reconciler",
            stage="DELIVERY_MONITOR",
            outcome="alert",
            param={"pending_count": len(jobs), "threshold": queue_tail_alert_threshold},
        )

    for job in jobs:
        task_id = job.get("task_id") or job.get("external_task_id")
        if not task_id:
            continue
        try:
            status = await kie_client.get_task_status(task_id)
        except Exception:
            continue
        if not status.get("ok"):
            continue
        status_state = (status.get("state") or "").lower()
        if status_state in SUCCESS_STATES:
            status["taskId"] = task_id
            await deliver_job_result(
                bot,
                storage,
                job=job,
                status_record=status,
                notify_user=True,
                source="delivery_reconciler",
            )
        elif status_state in FAILED_STATES:
            try:
                await storage.update_job_status(
                    job.get("job_id") or task_id,
                    "failed",
                    error_message=status.get("failMsg"),
                    error_code=status.get("failCode") or "KIE_FAIL_STATE",
                )
            except Exception as storage_exc:
                logger.warning("Failed to update job failure: %s", storage_exc)
            log_task_lifecycle(
                state="failed",
                user_id=job.get("user_id"),
                task_id=task_id,
                job_id=job.get("job_id"),
                model_id=job.get("model_id"),
                source="delivery_reconciler",
                detail={"reason": "provider_failed"},
            )

    snapshot = metrics_snapshot()
    log_structured_event(
        action="DELIVERY_METRICS",
        action_path="delivery_reconciler",
        stage="DELIVERY_MONITOR",
        outcome="observed",
        param=snapshot,
    )


async def run_reconciler_loop(
    bot,
    storage,
    kie_client,
    *,
    interval_seconds: int,
    batch_limit: int,
    pending_age_alert_seconds: int,
    queue_tail_alert_threshold: int,
) -> None:
    while True:
        try:
            await reconcile_pending_results(
                bot,
                storage,
                kie_client,
                batch_limit=batch_limit,
                pending_age_alert_seconds=pending_age_alert_seconds,
                queue_tail_alert_threshold=queue_tail_alert_threshold,
            )
        except Exception as exc:
            logger.error("delivery_reconciler_failed: %s", exc, exc_info=True)
        await asyncio.sleep(interval_seconds)
