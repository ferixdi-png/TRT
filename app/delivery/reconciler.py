"""Background reconciler for pending generation results."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, Optional

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

PENDING_STATES = {"pending", "queued", "running", "timeout", "delivery_pending"}
SUCCESS_STATES = {"success", "completed", "succeeded"}
FAILED_STATES = {"failed", "fail", "error", "canceled", "cancelled", "canceled"}
DELIVERY_POLL_TIMEOUT_SECONDS = int(os.getenv("DELIVERY_POLL_TIMEOUT_SECONDS", "300"))
DELIVERY_RECONCILER_MAX_BACKOFF_SECONDS = int(os.getenv("DELIVERY_RECONCILER_MAX_BACKOFF_SECONDS", "60"))


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
    chat_id: Optional[int],
    message_id: Optional[int],
    sku_id: Optional[str],
    price: Optional[float],
    is_free: Optional[bool],
    is_admin_user: Optional[bool],
) -> bool:
    already_delivered = False
    now_iso = datetime.now().isoformat()
    key = _delivery_key(user_id, task_id)

    def updater(data: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal already_delivered
        next_data = dict(data or {})
        record_raw = next_data.get(key, {})
        record = dict(record_raw) if isinstance(record_raw, dict) else {}
        if record.get("status") == "delivered":
            already_delivered = True
            return next_data
        attempts = int(record.get("attempts", 0)) + 1
        record.update(
            {
                "user_id": user_id,
                "task_id": task_id,
                "job_id": job_id or record.get("job_id"),
                "model_id": model_id or record.get("model_id"),
                "request_id": request_id or record.get("request_id"),
                "chat_id": chat_id or record.get("chat_id") or user_id,
                "message_id": message_id or record.get("message_id"),
                "sku_id": sku_id or record.get("sku_id"),
                "price": record.get("price") if price is None else price,
                "is_free": bool(record.get("is_free")) if is_free is None else bool(is_free),
                "is_admin_user": bool(record.get("is_admin_user"))
                if is_admin_user is None
                else bool(is_admin_user),
                "status": "delivering",
                "attempts": attempts,
                "created_at": record.get("created_at", now_iso),
                "updated_at": now_iso,
            }
        )
        next_data[key] = record
        return next_data

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


async def _get_delivery_record(storage: Any, *, user_id: int, task_id: str) -> Dict[str, Any]:
    if not hasattr(storage, "read_json_file"):
        return {}
    try:
        data = await storage.read_json_file("delivery_records.json", default={})
    except Exception:
        return {}
    record = data.get(_delivery_key(user_id, task_id), {})
    return dict(record) if isinstance(record, dict) else {}


async def _update_delivery_charge_state(
    storage: Any,
    *,
    user_id: int,
    task_id: str,
    charge_status: str,
    charged: bool = False,
    free_consumed: bool = False,
    charge_error: Optional[str] = None,
) -> None:
    if not hasattr(storage, "update_json_file"):
        return
    now_iso = datetime.now().isoformat()
    key = _delivery_key(user_id, task_id)

    def updater(data: Dict[str, Any]) -> Dict[str, Any]:
        next_data = dict(data or {})
        record = dict(next_data.get(key) or {})
        record.update(
            {
                "charge_status": charge_status,
                "charge_error": charge_error,
                "charged_at": record.get("charged_at") or (now_iso if charged else None),
                "free_consumed_at": record.get("free_consumed_at") or (now_iso if free_consumed else None),
                "updated_at": now_iso,
            }
        )
        next_data[key] = record
        return next_data

    await storage.update_json_file("delivery_records.json", updater)


async def _update_job_charge_state(
    storage: Any,
    *,
    job_id: Optional[str],
    charge_status: str,
    charged: bool = False,
    free_consumed: bool = False,
    charge_error: Optional[str] = None,
) -> None:
    if not job_id or not hasattr(storage, "update_json_file"):
        return
    jobs_filename = _jobs_filename(storage)
    now_iso = datetime.now().isoformat()

    def updater(data: Dict[str, Any]) -> Dict[str, Any]:
        next_data = dict(data or {})
        record = dict(next_data.get(job_id) or {})
        if not record:
            return next_data
        record.update(
            {
                "charge_status": charge_status,
                "charge_error": charge_error,
                "charged_at": record.get("charged_at") or (now_iso if charged else None),
                "free_consumed_at": record.get("free_consumed_at") or (now_iso if free_consumed else None),
                "updated_at": now_iso,
            }
        )
        next_data[job_id] = record
        return next_data

    await storage.update_json_file(jobs_filename, updater)


async def _commit_delivery_charge(
    storage: Any,
    *,
    job: Dict[str, Any],
    user_id: int,
    task_id: str,
    chat_id: int,
    request_id: Optional[str],
    model_id: Optional[str],
) -> None:
    record = await _get_delivery_record(storage, user_id=user_id, task_id=task_id)
    if record.get("charged_at") or record.get("free_consumed_at"):
        return

    sku_id = job.get("sku_id") or record.get("sku_id")
    price_raw = job.get("price") if job.get("price") is not None else record.get("price")
    try:
        price = float(price_raw or 0.0)
    except (TypeError, ValueError):
        price = 0.0

    import bot_kie  # Imported lazily to avoid heavy module load at startup.

    is_admin_user = bool(job.get("is_admin_user") or record.get("is_admin_user") or bot_kie.get_is_admin(user_id))
    is_free = bool(job.get("is_free") or record.get("is_free"))

    if is_admin_user:
        await _update_delivery_charge_state(
            storage,
            user_id=user_id,
            task_id=task_id,
            charge_status="admin_free",
            charged=True,
        )
        await _update_job_charge_state(
            storage,
            job_id=job.get("job_id"),
            charge_status="admin_free",
            charged=True,
        )
        return

    if is_free:
        if not sku_id:
            log_structured_event(
                correlation_id=request_id,
                user_id=user_id,
                chat_id=chat_id,
                action="CHARGE_COMMIT",
                action_path="delivery_reconciler",
                model_id=model_id,
                stage="CHARGE_COMMIT",
                outcome="missing_sku",
                error_code="MISSING_SKU_ID",
                fix_hint="Передавайте sku_id в storage job metadata.",
                param={"task_id": task_id},
            )
            await _update_delivery_charge_state(
                storage,
                user_id=user_id,
                task_id=task_id,
                charge_status="missing_sku",
                charge_error="missing_sku_id",
            )
            await _update_job_charge_state(
                storage,
                job_id=job.get("job_id"),
                charge_status="missing_sku",
                charge_error="missing_sku_id",
            )
            return
        consume_result = await bot_kie.consume_free_generation(
            user_id,
            sku_id,
            correlation_id=request_id,
            task_id=task_id,
            source="delivery_reconciler",
        )
        consume_status = str(consume_result.get("status") or "unknown")
        free_ok = consume_status in {"ok", "duplicate", "admin"}
        await _update_delivery_charge_state(
            storage,
            user_id=user_id,
            task_id=task_id,
            charge_status=f"free_{consume_status}",
            free_consumed=free_ok,
            charge_error=None if free_ok else consume_status,
        )
        await _update_job_charge_state(
            storage,
            job_id=job.get("job_id"),
            charge_status=f"free_{consume_status}",
            free_consumed=free_ok,
            charge_error=None if free_ok else consume_status,
        )
        return

    if price <= 0:
        await _update_delivery_charge_state(
            storage,
            user_id=user_id,
            task_id=task_id,
            charge_status="no_charge_required",
        )
        await _update_job_charge_state(
            storage,
            job_id=job.get("job_id"),
            charge_status="no_charge_required",
        )
        return

    if not sku_id:
        log_structured_event(
            correlation_id=request_id,
            user_id=user_id,
            chat_id=chat_id,
            action="CHARGE_COMMIT",
            action_path="delivery_reconciler",
            model_id=model_id,
            stage="CHARGE_COMMIT",
            outcome="missing_sku",
            error_code="MISSING_SKU_ID",
            fix_hint="Передавайте sku_id в storage job metadata.",
            param={"task_id": task_id, "price": price},
        )
        await _update_delivery_charge_state(
            storage,
            user_id=user_id,
            task_id=task_id,
            charge_status="missing_sku",
            charge_error="missing_sku_id",
        )
        await _update_job_charge_state(
            storage,
            job_id=job.get("job_id"),
            charge_status="missing_sku",
            charge_error="missing_sku_id",
        )
        return

    charge_result = await bot_kie._charge_balance_once(
        user_id=user_id,
        task_id=task_id,
        sku_id=sku_id,
        model_id=model_id,
        price=price,
        correlation_id=request_id,
        chat_id=chat_id,
    )
    charge_status = str(charge_result.get("status") or "unknown")
    charged_ok = charge_status in {"charged", "duplicate"}
    await _update_delivery_charge_state(
        storage,
        user_id=user_id,
        task_id=task_id,
        charge_status=charge_status,
        charged=charged_ok,
        charge_error=None if charged_ok else charge_status,
    )
    await _update_job_charge_state(
        storage,
        job_id=job.get("job_id"),
        charge_status=charge_status,
        charged=charged_ok,
        charge_error=None if charged_ok else charge_status,
    )


def _parse_iso_ts(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def _job_age_seconds(job: Dict[str, Any], *, now_ts: float) -> Optional[float]:
    created_ts = _parse_iso_ts(job.get("created_at"))
    if created_ts is None:
        return None
    return max(0.0, now_ts - created_ts)


def _jobs_filename(storage: Any) -> str:
    jobs_file = getattr(storage, "jobs_file", "generation_jobs.json")
    return os.path.basename(str(jobs_file))


async def _mark_timeout_notified(storage: Any, job: Dict[str, Any], *, timeout_seconds: int) -> None:
    if not hasattr(storage, "update_json_file"):
        return
    job_id = job.get("job_id") or job.get("task_id")
    if not job_id:
        return
    now_iso = datetime.now().isoformat()
    jobs_filename = _jobs_filename(storage)

    def updater(data: Dict[str, Any]) -> Dict[str, Any]:
        next_data = dict(data or {})
        record = dict(next_data.get(job_id) or {})
        record.update(
            {
                "status": "timeout",
                "timeout_seconds": timeout_seconds,
                "timeout_notified_at": record.get("timeout_notified_at") or now_iso,
                "updated_at": now_iso,
            }
        )
        next_data[job_id] = record
        return next_data

    await storage.update_json_file(jobs_filename, updater)


async def _maybe_notify_timeout(
    bot,
    storage: Any,
    job: Dict[str, Any],
    *,
    age_s: Optional[float],
    timeout_seconds: int,
    get_user_language: Optional[Callable[[int], str]],
) -> None:
    if age_s is None or age_s < timeout_seconds:
        return
    if job.get("timeout_notified_at"):
        return
    user_id = job.get("user_id")
    if user_id is None:
        return
    chat_id = job.get("chat_id") or user_id
    lang = get_user_language(user_id) if get_user_language else "ru"
    is_ru = lang == "ru"
    text = (
        "⏳ <b>Генерация занимает больше обычного</b>\n\n"
        "Я продолжу следить за задачей и пришлю результат сюда, как только он будет готов."
        if is_ru
        else (
            "⏳ <b>This generation is taking longer than usual</b>\n\n"
            "I'll keep monitoring it and send the result here as soon as it's ready."
        )
    )
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
    except Exception as exc:
        logger.warning("delivery_timeout_notify_failed job_id=%s error=%s", job.get("job_id"), exc)
    await _mark_timeout_notified(storage, job, timeout_seconds=timeout_seconds)
    log_structured_event(
        user_id=user_id,
        chat_id=chat_id,
        action="DELIVERY_TIMEOUT",
        action_path="delivery_reconciler",
        model_id=job.get("model_id"),
        job_id=job.get("job_id"),
        task_id=job.get("task_id"),
        stage="DELIVERY_POLL",
        outcome="timeout_notified",
        param={"age_s": int(age_s), "timeout_s": timeout_seconds},
    )


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
    chat_id = job.get("chat_id") or user_id
    message_id = job.get("message_id")

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

    if prompt_hash and model_id:
        try:
            from app.generations.request_dedupe_store import update_dedupe_entry

            await update_dedupe_entry(
                user_id,
                model_id,
                prompt_hash,
                job_id=job_id,
                task_id=task_id,
                status="completed",
                media_type=job_result.media_type,
                result_urls=job_result.urls,
                result_text=job_result.text,
            )
        except Exception as dedupe_exc:
            logger.warning("delivery_dedupe_update_failed task_id=%s error=%s", task_id, dedupe_exc)

    try:
        await storage.update_job_status(
            job_id,
            "delivery_pending",
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
        chat_id=chat_id,
        message_id=message_id,
        sku_id=job.get("sku_id"),
        price=job.get("price"),
        is_free=job.get("is_free"),
        is_admin_user=job.get("is_admin_user"),
    )
    if already_delivered:
        try:
            await storage.update_job_status(job_id, "delivered", result_urls=job_result.urls)
        except Exception as storage_exc:
            logger.warning("Failed to mark delivered job: %s", storage_exc)
        try:
            await _commit_delivery_charge(
                storage,
                job=job,
                user_id=user_id,
                task_id=task_id,
                chat_id=chat_id,
                request_id=request_id,
                model_id=model_id,
            )
        except Exception as charge_exc:
            logger.warning("delivery_charge_commit_failed task_id=%s error=%s", task_id, charge_exc)
        log_task_lifecycle(
            state="delivered",
            user_id=user_id,
            task_id=task_id,
            job_id=job_id,
            model_id=model_id,
            source=source,
            detail={"reason": "already_delivered"},
        )
        return True

    if notify_user:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text="✅ Результат готов, отправляю повторно.",
            )
        except Exception:
            pass

    delivered = False
    delivery_error_code: Optional[str] = None
    delivery_error_hint: Optional[str] = None
    try:
        delivered = bool(
            await send_result_file(
                bot,
                chat_id,
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
        delivery_error_code = "TG_DELIVER_EXCEPTION"
        delivery_error_hint = str(exc)

    log_structured_event(
        correlation_id=job.get("request_id"),
        user_id=user_id,
        chat_id=chat_id,
        action="DELIVERY_SEND_OK" if delivered else "DELIVERY_SEND_FAIL",
        action_path=source,
        model_id=model_id,
        task_id=task_id,
        job_id=job_id,
        stage="TG_DELIVER",
        outcome="success" if delivered else "failed",
        error_code=None if delivered else (delivery_error_code or "TG_DELIVER_FALSE"),
        fix_hint=delivery_error_hint,
        param={"message_id": message_id},
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
        try:
            await storage.update_job_status(job_id, "delivered", result_urls=job_result.urls)
        except Exception as storage_exc:
            logger.warning("Failed to update delivered status: %s", storage_exc)
        try:
            await _commit_delivery_charge(
                storage,
                job=job,
                user_id=user_id,
                task_id=task_id,
                chat_id=chat_id,
                request_id=request_id,
                model_id=model_id,
            )
        except Exception as charge_exc:
            logger.warning("delivery_charge_commit_failed task_id=%s error=%s", task_id, charge_exc)
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
    get_user_language: Optional[Callable[[int], str]] = None,
) -> None:
    jobs = await storage.list_jobs_by_status(list(PENDING_STATES), limit=batch_limit)
    if not jobs:
        return

    now_ts = time.time()
    pending_ages = []
    for job in jobs:
        age = _job_age_seconds(job, now_ts=now_ts)
        if age is None:
            continue
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
        age_s = _job_age_seconds(job, now_ts=now_ts)
        await _maybe_notify_timeout(
            bot,
            storage,
            job,
            age_s=age_s,
            timeout_seconds=DELIVERY_POLL_TIMEOUT_SECONDS,
            get_user_language=get_user_language,
        )
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
            prompt_hash = job.get("prompt_hash")
            model_id = job.get("model_id")
            user_id = job.get("user_id")
            if prompt_hash and model_id and user_id is not None:
                try:
                    from app.generations.request_dedupe_store import update_dedupe_entry

                    await update_dedupe_entry(
                        int(user_id),
                        str(model_id),
                        str(prompt_hash),
                        job_id=job.get("job_id"),
                        task_id=task_id,
                        status="failed",
                        result_text=status.get("failMsg"),
                    )
                except Exception as dedupe_exc:
                    logger.warning("delivery_dedupe_fail_update_failed task_id=%s error=%s", task_id, dedupe_exc)
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
    get_user_language: Optional[Callable[[int], str]] = None,
) -> None:
    backoff_seconds = interval_seconds
    max_backoff = max(interval_seconds, DELIVERY_RECONCILER_MAX_BACKOFF_SECONDS)
    while True:
        try:
            await reconcile_pending_results(
                bot,
                storage,
                kie_client,
                batch_limit=batch_limit,
                pending_age_alert_seconds=pending_age_alert_seconds,
                queue_tail_alert_threshold=queue_tail_alert_threshold,
                get_user_language=get_user_language,
            )
            backoff_seconds = interval_seconds
        except Exception as exc:
            logger.error("delivery_reconciler_failed: %s", exc, exc_info=True)
            backoff_seconds = min(max_backoff, max(interval_seconds, backoff_seconds * 2))
        await asyncio.sleep(backoff_seconds)
