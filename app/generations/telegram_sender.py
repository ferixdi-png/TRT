"""Universal Telegram sender for generation results."""
from __future__ import annotations

import logging
import os
import time
from typing import List, Optional

import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

from app.kie_catalog import ModelSpec
from app.generations.universal_engine import JobResult
from app.generations.media_pipeline import resolve_and_prepare_telegram_payload
from app.observability.trace import trace_event, url_summary
from app.observability.structured_logs import log_structured_event

logger = logging.getLogger(__name__)

TELEGRAM_MAX_BYTES = int(os.getenv("TELEGRAM_MAX_FILE_BYTES", str(50 * 1024 * 1024)))
DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=float(os.getenv("KIE_MEDIA_DOWNLOAD_TIMEOUT", "30")))


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
    start_ts = time.monotonic()
    try:
        async with aiohttp.ClientSession(timeout=DOWNLOAD_TIMEOUT) as session:
            tg_method, payload = await resolve_and_prepare_telegram_payload(
                {"urls": urls, "text": text},
                correlation_id,
                media_type,
                kie_client=kie_client,
                http_client=session,
            )
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
                action="TG_SEND",
                action_path="telegram_sender.deliver_result",
                model_id=model_id,
                stage="TG_SEND",
                outcome="attempt",
                param={"tg_method": tg_method, "media_type": media_type},
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
            action="TG_SEND",
            action_path="telegram_sender.deliver_result",
            model_id=model_id,
            stage="TG_SEND",
            outcome="success",
            duration_ms=int((time.monotonic() - start_ts) * 1000),
            param={"tg_method": tg_method, "media_type": media_type},
        )
    except BadRequest as exc:
        logger.warning("Telegram media send failed, falling back to document: %s", exc)
        log_structured_event(
            correlation_id=correlation_id,
            action="TG_SEND",
            action_path="telegram_sender.deliver_result",
            model_id=model_id,
            stage="TG_SEND",
            outcome="failed",
            duration_ms=int((time.monotonic() - start_ts) * 1000),
            error_code="TG_BAD_REQUEST",
            fix_hint="Fallback to send_document for Telegram.",
            param={"tg_method": tg_method, "media_type": media_type},
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
                send_fn = getattr(bot, tg_method)
                await send_fn(chat_id=chat_id, **payload)
        except Exception as send_exc:  # pragma: no cover - best effort
            logger.warning("Telegram fallback send failed: %s", send_exc)
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
            action="TG_SEND",
            action_path="telegram_sender.deliver_result",
            model_id=model_id,
            stage="TG_SEND",
            outcome="failed",
            duration_ms=int((time.monotonic() - start_ts) * 1000),
            error_code="TG_SEND_FAIL",
            fix_hint="Проверьте параметры отправки в Telegram.",
            param={"tg_method": tg_method, "media_type": media_type},
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
                send_fn = getattr(bot, tg_method)
                await send_fn(chat_id=chat_id, **payload)
        except Exception as send_exc:  # pragma: no cover - best effort
            logger.warning("Telegram fallback send failed: %s", send_exc)


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
        price_display = f"{price_rub:.2f}".rstrip("0").rstrip(".")
        price_text = f"\n💰 <b>Цена:</b> {price_display} ₽"

    elapsed_text = ""
    if elapsed is not None:
        elapsed_text = f"\n⏱️ <b>Время:</b> {elapsed:.1f}s"

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

    buttons.append([InlineKeyboardButton("🕒 Проверить статус", callback_data="check_status")])
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
        stage="TG_SEND",
        outcome="sent",
        param={"summary_sent": True},
    )
