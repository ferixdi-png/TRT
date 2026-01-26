"""Recovery loop for orphaned dedupe entries without task IDs."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.generations.request_dedupe_store import (
    DedupeEntry,
    list_dedupe_entries,
    update_dedupe_entry,
)
from app.observability.dedupe_metrics import metrics_snapshot, record_orphan_count
from app.observability.structured_logs import log_structured_event
from app.utils.logging_config import get_logger

logger = get_logger(__name__)
try:  # pragma: no cover - optional dependency
    import asyncpg

    _DB_DEGRADED_EXCEPTIONS = (asyncio.TimeoutError, TimeoutError, asyncpg.PostgresError)
except Exception:  # pragma: no cover
    _DB_DEGRADED_EXCEPTIONS = (asyncio.TimeoutError, TimeoutError)

ORPHAN_STATES = {
    "create_start",
    "task_created",
    "pending",
    "queued",
    "waiting",
    "success",
    "result_validated",
    "tg_deliver",
    "delivery_pending",
    "deduped",
    "running",
}


def _entry_age_seconds(entry: DedupeEntry, *, now_ts: float) -> float:
    updated_ts = entry.updated_ts or 0.0
    if updated_ts <= 0:
        return float("inf")
    return max(0.0, now_ts - updated_ts)


def _build_orphan_message(lang: str, model_id: str) -> tuple[str, InlineKeyboardMarkup]:
    is_ru = lang == "ru"
    text = (
        "⚠️ <b>Генерация зависла до создания task_id</b>\n\n"
        "Мы не смогли восстановить задачу автоматически. "
        "Нажмите «Повторить», чтобы запустить заново."
        if is_ru
        else (
            "⚠️ <b>Generation stalled before task_id creation</b>\n\n"
            "We could not recover the task automatically. "
            "Tap Retry to start it again."
        )
    )
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔁 Повторить" if is_ru else "🔁 Retry", callback_data=f"retry_generate:{model_id}")],
            [InlineKeyboardButton("🏠 Главное меню" if is_ru else "🏠 Main menu", callback_data="back_to_menu")],
        ]
    )
    return text, keyboard


async def _recover_task_id(
    entry: DedupeEntry,
    *,
    resolve_task_id: Callable[[str], Awaitable[Optional[str]]],
    kie_client: Any,
) -> Optional[str]:
    if entry.task_id:
        return entry.task_id
    recovered: Optional[str] = None
    if entry.job_id:
        try:
            recovered = await resolve_task_id(entry.job_id)
        except Exception as exc:
            logger.warning("dedupe_recover_job_lookup_failed job_id=%s error=%s", entry.job_id, exc)
    if recovered:
        return recovered
    provider_lookup = getattr(kie_client, "resolve_task_id", None)
    if provider_lookup and entry.job_id:
        try:
            recovered = await provider_lookup(entry.job_id)
        except Exception as exc:
            logger.warning("dedupe_recover_provider_lookup_failed job_id=%s error=%s", entry.job_id, exc)
    return recovered


def _should_notify(entry: DedupeEntry, *, now_ts: float, cooldown_seconds: int) -> bool:
    last_notified = entry.orphan_notified_ts or 0.0
    if last_notified <= 0:
        return True
    return now_ts - last_notified >= cooldown_seconds


async def reconcile_dedupe_orphans(
    bot,
    kie_client,
    *,
    resolve_task_id: Callable[[str], Awaitable[Optional[str]]],
    get_user_language: Callable[[int], str],
    batch_limit: int,
    orphan_max_age_seconds: int,
    orphan_alert_threshold: int,
    notify_cooldown_seconds: int = 900,
) -> None:
    entries = await list_dedupe_entries(limit=batch_limit)
    now_ts = time.time()
    orphan_entries = [
        entry
        for entry in entries
        if not entry.task_id and (entry.status or "").lower() in ORPHAN_STATES
    ]
    orphan_count = len(orphan_entries)
    record_orphan_count(orphan_count, alert_threshold=orphan_alert_threshold)
    if orphan_count == 0:
        return

    for entry in orphan_entries:
        age_seconds = _entry_age_seconds(entry, now_ts=now_ts)
        recovered_task_id = await _recover_task_id(entry, resolve_task_id=resolve_task_id, kie_client=kie_client)
        recovery_attempts = int(entry.recovery_attempts or 0) + 1
        if recovered_task_id:
            await update_dedupe_entry(
                entry.user_id,
                entry.model_id,
                entry.prompt_hash,
                task_id=recovered_task_id,
                status="running",
                last_recovery_ts=now_ts,
                recovery_attempts=recovery_attempts,
            )
            log_structured_event(
                user_id=entry.user_id,
                action="DEDUPE_RECONCILE",
                action_path="dedupe_reconciler",
                model_id=entry.model_id,
                job_id=entry.job_id,
                task_id=recovered_task_id,
                stage="DEDUPE_RECOVERY",
                outcome="recovered",
                param={"age_s": int(age_seconds)},
            )
            continue
        if age_seconds < orphan_max_age_seconds:
            continue
        await update_dedupe_entry(
            entry.user_id,
            entry.model_id,
            entry.prompt_hash,
            status="failed",
            last_recovery_ts=now_ts,
            recovery_attempts=recovery_attempts,
            result_text="dedupe_orphan_failed",
        )
        log_structured_event(
            user_id=entry.user_id,
            action="DEDUPE_RECONCILE",
            action_path="dedupe_reconciler",
            model_id=entry.model_id,
            job_id=entry.job_id,
            task_id=None,
            stage="DEDUPE_RECOVERY",
            outcome="failed_orphan",
            param={"age_s": int(age_seconds)},
        )
        if not _should_notify(entry, now_ts=now_ts, cooldown_seconds=notify_cooldown_seconds):
            continue
        lang = get_user_language(entry.user_id)
        text, keyboard = _build_orphan_message(lang, entry.model_id)
        try:
            await bot.send_message(entry.user_id, text, parse_mode="HTML", reply_markup=keyboard)
        except Exception as exc:
            logger.warning(
                "dedupe_reconcile_notify_failed user_id=%s job_id=%s error=%s",
                entry.user_id,
                entry.job_id,
                exc,
            )
            continue
        await update_dedupe_entry(
            entry.user_id,
            entry.model_id,
            entry.prompt_hash,
            orphan_notified_ts=now_ts,
        )

    snapshot = metrics_snapshot()
    log_structured_event(
        action="DEDUPE_METRICS",
        action_path="dedupe_reconciler",
        stage="DEDUPE_MONITOR",
        outcome="observed",
        param=snapshot,
    )


async def run_dedupe_reconciler_loop(
    bot,
    kie_client,
    *,
    resolve_task_id: Callable[[str], Awaitable[Optional[str]]],
    get_user_language: Callable[[int], str],
    interval_seconds: int,
    batch_limit: int,
    orphan_max_age_seconds: int,
    orphan_alert_threshold: int,
) -> None:
    backoff_seconds = interval_seconds
    db_backoff_seconds = 0
    while True:
        try:
            await reconcile_dedupe_orphans(
                bot,
                kie_client,
                resolve_task_id=resolve_task_id,
                get_user_language=get_user_language,
                batch_limit=batch_limit,
                orphan_max_age_seconds=orphan_max_age_seconds,
                orphan_alert_threshold=orphan_alert_threshold,
            )
            backoff_seconds = interval_seconds
            db_backoff_seconds = 0
        except _DB_DEGRADED_EXCEPTIONS as exc:
            db_backoff_seconds = 5 if db_backoff_seconds == 0 else min(60, db_backoff_seconds * 2)
            backoff_seconds = max(interval_seconds, db_backoff_seconds)
            logger.warning(
                "DB_DEGRADED_BACKOFF source=dedupe_reconciler delay_s=%s error=%s",
                backoff_seconds,
                exc,
            )
        except Exception as exc:
            logger.error("dedupe_reconciler_failed: %s", exc, exc_info=True)
            backoff_seconds = max(interval_seconds, min(60, backoff_seconds * 2))
        await asyncio.sleep(backoff_seconds)
