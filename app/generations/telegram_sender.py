"""Universal Telegram sender for generation results."""
from __future__ import annotations

import logging
import os
import re
import time
from typing import List, Optional, Tuple

import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.error import BadRequest

from app.kie_catalog import ModelSpec
from app.generations.universal_engine import JobResult
from app.generations.media_pipeline import resolve_and_prepare_telegram_payload
from app.services.free_tools_service import get_free_counter_snapshot
from app.observability.trace import trace_event, url_summary
from app.observability.structured_logs import log_structured_event

logger = logging.getLogger(__name__)

TELEGRAM_MAX_BYTES = int(os.getenv("TELEGRAM_MAX_FILE_BYTES", str(50 * 1024 * 1024)))
DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=float(os.getenv("KIE_MEDIA_DOWNLOAD_TIMEOUT", "30")))


def _payload_contains_url(text: Optional[str]) -> bool:
    if not text:
        return False
    return bool(re.search(r"https?://", text))


def _input_file_size(value: object) -> Optional[int]:
    if isinstance(value, InputFile):
        fp = getattr(value, "input_file", None) or getattr(value, "fp", None) or getattr(value, "file", None)
        if hasattr(fp, "getbuffer"):
            return fp.getbuffer().nbytes
        if hasattr(fp, "getvalue"):
            return len(fp.getvalue())
    return None


def _payload_metadata(tg_method: Optional[str], payload: dict) -> Tuple[str, Optional[int]]:
    if tg_method == "send_message":
        return "text", None
    if tg_method == "send_media_group":
        total = 0
        for item in payload.get("media", []):
            media = getattr(item, "media", None)
            size = _input_file_size(media)
            if size is not None:
                total += size
        return "media_group", total or None
    for key in ("photo", "video", "audio", "voice", "animation", "document"):
        if key in payload:
            value = payload.get(key)
            size = _input_file_size(value)
            if isinstance(value, InputFile):
                return "input_file", size
            if isinstance(value, str):
                return "url", size
            return "file", size
    return "unknown", None


async def deliver_result(
    bot,
    chat_id: int,
    media_type: str,
    urls: List[str],
    text: Optional[str],
    *,
    model_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    kie_client: Optional[object] = None,
) -> None:
    """Deliver generation result to Telegram with trace logging and fallback."""
    media_type = (media_type or "").lower()
    tg_method = None
    payload_type = "unknown"
    bytes_size = None
    start_ts = time.monotonic()
    async def _send_failure_message(error_code: str, fix_hint: str) -> None:
        message = (
            "⚠️ Не удалось доставить результат.\n\n"
            f"Код: {error_code}\n"
            f"Совет: {fix_hint}\n"
            f"ID: {correlation_id or 'corr-na-na'}"
        )
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as send_exc:
            logger.warning("Telegram failure notification failed: %s", send_exc)

    try:
        async with aiohttp.ClientSession(timeout=DOWNLOAD_TIMEOUT) as session:
            tg_method, payload = await resolve_and_prepare_telegram_payload(
                {"urls": urls, "text": text},
                correlation_id,
                media_type,
                kie_client=kie_client,
                http_client=session,
            )
            if tg_method == "send_message" and _payload_contains_url(payload.get("text")):
                payload.setdefault("disable_web_page_preview", True)
            payload_type, bytes_size = _payload_metadata(tg_method, payload)
            trace_event(
                "info",
                correlation_id or "corr-na-na",
                event="TRACE_IN",
                stage="TG_DELIVER",
                action="TG_SEND",
                tg_method=tg_method,
                media_type=media_type,
            )
            log_structured_event(
                correlation_id=correlation_id,
                action="TG_SEND_ATTEMPT",
                action_path="telegram_sender.deliver_result",
                model_id=model_id,
                stage="TG_SEND",
                outcome="attempt",
                error_code="TG_SEND_ATTEMPT",
                fix_hint="Следим за корректной доставкой медиа в Telegram.",
                param={
                    "tg_method": tg_method,
                    "media_type": media_type,
                    "payload_type": payload_type,
                    "bytes_size": bytes_size,
                },
            )
            send_fn = getattr(bot, tg_method)
            await send_fn(chat_id=chat_id, **payload)

        trace_event(
            "info",
            correlation_id or "corr-na-na",
            event="TRACE_OUT",
            stage="TG_DELIVER",
            action="TG_SEND",
            tg_method=tg_method,
            media_type=media_type,
            url_summary=url_summary(urls[0]) if urls else None,
            outcome="success",
        )
        log_structured_event(
            correlation_id=correlation_id,
            action="TG_SEND_OK",
            action_path="telegram_sender.deliver_result",
            model_id=model_id,
            stage="TG_SEND",
            outcome="success",
            duration_ms=int((time.monotonic() - start_ts) * 1000),
            error_code="TG_SEND_OK",
            fix_hint="Доставка Telegram завершена успешно.",
            param={
                "tg_method": tg_method,
                "media_type": media_type,
                "payload_type": payload_type,
                "bytes_size": bytes_size,
            },
        )
    except BadRequest as exc:
        logger.warning("Telegram media send failed, falling back to document: %s", exc)
        log_structured_event(
            correlation_id=correlation_id,
            action="TG_SEND_FAIL",
            action_path="telegram_sender.deliver_result",
            model_id=model_id,
            stage="TG_SEND",
            outcome="failed",
            duration_ms=int((time.monotonic() - start_ts) * 1000),
            error_code="TG_BAD_REQUEST",
            fix_hint="Fallback to send_document for Telegram.",
            param={
                "tg_method": tg_method,
                "media_type": media_type,
                "payload_type": payload_type,
                "bytes_size": bytes_size,
            },
        )
        try:
            async with aiohttp.ClientSession(timeout=DOWNLOAD_TIMEOUT) as session:
                tg_method, payload = await resolve_and_prepare_telegram_payload(
                    {"urls": urls, "text": text},
                    correlation_id,
                    "document",
                    kie_client=kie_client,
                    http_client=session,
                )
                if tg_method == "send_message" and _payload_contains_url(payload.get("text")):
                    payload.setdefault("disable_web_page_preview", True)
                send_fn = getattr(bot, tg_method)
                await send_fn(chat_id=chat_id, **payload)
        except Exception as send_exc:  # pragma: no cover - best effort
            logger.warning("Telegram fallback send failed: %s", send_exc)
            await _send_failure_message("TG_FALLBACK_FAILED", "Попробуйте повторить запрос позже.")
        return
    except Exception as exc:
        logger.warning("Telegram media send failed, falling back to document: %s", exc)
        trace_event(
            "info",
            correlation_id or "corr-na-na",
            event="TRACE_OUT",
            stage="TG_DELIVER",
            action="TG_SEND",
            tg_method=tg_method,
            media_type=media_type,
            url_summary=url_summary(urls[0]) if urls else None,
            outcome="failed",
            tg_error=str(exc),
        )
        log_structured_event(
            correlation_id=correlation_id,
            action="TG_SEND_FAIL",
            action_path="telegram_sender.deliver_result",
            model_id=model_id,
            stage="TG_SEND",
            outcome="failed",
            duration_ms=int((time.monotonic() - start_ts) * 1000),
            error_code="TG_SEND_FAIL",
            fix_hint="Проверьте параметры отправки в Telegram.",
            param={
                "tg_method": tg_method,
                "media_type": media_type,
                "payload_type": payload_type,
                "bytes_size": bytes_size,
            },
        )
        try:
            async with aiohttp.ClientSession(timeout=DOWNLOAD_TIMEOUT) as session:
                tg_method, payload = await resolve_and_prepare_telegram_payload(
                    {"urls": urls, "text": text},
                    correlation_id,
                    "document",
                    kie_client=kie_client,
                    http_client=session,
                )
                if tg_method == "send_message" and _payload_contains_url(payload.get("text")):
                    payload.setdefault("disable_web_page_preview", True)
                send_fn = getattr(bot, tg_method)
                await send_fn(chat_id=chat_id, **payload)
        except Exception as send_exc:  # pragma: no cover - best effort
            logger.warning("Telegram fallback send failed: %s", send_exc)
            await _send_failure_message("TG_FALLBACK_FAILED", "Попробуйте повторить запрос позже.")


async def send_job_result(
    bot,
    chat_id: int,
    spec: ModelSpec,
    job_result: JobResult,
    *,
    price_rub: Optional[float] = None,
    elapsed: Optional[float] = None,
    user_lang: str = "ru",
    correlation_id: Optional[str] = None,
    kie_client: Optional[object] = None,
) -> None:
    """Send generation output to Telegram based on media_type."""
    media_type = spec.output_media_type or job_result.media_type
    urls = job_result.urls

    await deliver_result(
        bot,
        chat_id,
        media_type,
        urls,
        job_result.text,
        model_id=spec.id,
        correlation_id=correlation_id,
        kie_client=kie_client,
    )

    price_text = ""
    if price_rub is not None:
        price_display = f"{int(price_rub)}"
        price_text = f"\n💰 <b>Цена:</b> {price_display} ₽"

    elapsed_text = ""
    if elapsed is not None:
        elapsed_text = f"\n⏱️ <b>Время:</b> {elapsed:.1f}s"

    free_counter_line = ""
    try:
        snapshot = await get_free_counter_snapshot(chat_id)
        remaining = snapshot.get("remaining", 0)
        limit = snapshot.get("limit_per_hour", 0)
        minutes = max(0, int(snapshot.get("next_refill_in", 0) / 60))
        if user_lang == "en":
            free_counter_line = (
                f"Free: {remaining}/{limit} • refresh in {minutes} min"
                if remaining > 0
                else f"Next free in {minutes} min"
            )
        else:
            free_counter_line = (
                f"Бесплатные: {remaining}/{limit} • обновится через {minutes} мин"
                if remaining > 0
                else f"Следующая бесплатная через {minutes} мин"
            )
    except Exception:
        free_counter_line = ""

    if user_lang == "en":
        summary = (
            f"✅ <b>Generation complete</b>\n\n"
            f"🤖 <b>Model:</b> {spec.name}"
            f"{price_text}"
            f"{elapsed_text}"
        )
        buttons = [
            [InlineKeyboardButton("🔁 Generate again", callback_data="generate_again")],
            [InlineKeyboardButton("🏠 Main menu", callback_data="back_to_menu")],
        ]
    else:
        summary = (
            f"✅ <b>Генерация завершена</b>\n\n"
            f"🤖 <b>Модель:</b> {spec.name}"
            f"{price_text}"
            f"{elapsed_text}"
        )
        buttons = [
            [InlineKeyboardButton("🔁 Ещё раз", callback_data="generate_again")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")],
        ]

    if free_counter_line:
        summary = f"{summary}\n\n🆓 {free_counter_line}"
        log_structured_event(
            correlation_id=correlation_id,
            user_id=chat_id,
            chat_id=chat_id,
            action="FREE_COUNTER_VIEW",
            action_path="telegram_sender.send_job_result",
            outcome="shown",
            error_code="FREE_COUNTER_VIEW_OK",
            fix_hint="Показан счетчик бесплатных генераций после результата.",
            param={"free_counter_line": free_counter_line},
        )

    buttons.append([InlineKeyboardButton("🕒 Проверить статус", callback_data="check_status")])
    log_structured_event(
        correlation_id=correlation_id,
        action="TG_SEND_ATTEMPT",
        action_path="telegram_sender.send_job_result",
        model_id=spec.id,
        stage="TG_SEND",
        outcome="attempt",
        error_code="TG_SEND_SUMMARY_ATTEMPT",
        fix_hint="Отправляем итоговую карточку в Telegram.",
        param={"tg_method": "send_message", "media_type": "summary"},
    )
    await bot.send_message(
        chat_id=chat_id,
        text=summary,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )
    trace_event(
        "info",
        correlation_id or "corr-na-na",
        event="TRACE_OUT",
        stage="TG_DELIVER",
        action="TG_SEND",
        tg_method="send_message",
        media_type="summary",
        outcome="success",
    )
    log_structured_event(
        correlation_id=correlation_id,
        action="GEN_COMPLETE",
        action_path="telegram_sender.send_job_result",
        model_id=spec.id,
        stage="GEN_COMPLETE",
        outcome="sent",
        error_code="TG_SUMMARY_SENT",
        fix_hint="Отправка итогового сообщения завершена.",
        param={"summary_sent": True},
    )
