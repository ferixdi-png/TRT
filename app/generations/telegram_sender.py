"""Universal Telegram sender for generation results."""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from types import SimpleNamespace
from typing import List, Optional, Dict, Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.kie_catalog import ModelSpec
from app.generations.universal_engine import JobResult
from app.delivery.result_delivery import deliver_generation_result
from app.generations.media_pipeline import resolve_and_prepare_telegram_payload
from app.utils.url_normalizer import (
    is_valid_result_url,
    normalize_result_urls,
    ResultUrlNormalizationError,
)
import aiohttp
from app.services.free_tools_service import format_free_counter_block, get_free_counter_snapshot
from app.pricing.price_resolver import format_price_rub
from app.observability.trace import trace_event, url_summary
from app.observability.structured_logs import log_structured_event

logger = logging.getLogger(__name__)

CAPTION_PARAM_LIMIT = 3
CAPTION_VALUE_LIMIT = 40


def _sanitize_caption_value(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    if len(cleaned) <= CAPTION_VALUE_LIMIT:
        return cleaned
    return f"{cleaned[:CAPTION_VALUE_LIMIT]}…"


def _summarize_params(params: Optional[Dict[str, Any]]) -> str:
    if not params:
        return "params: n/a"
    parts: List[str] = []
    for key, value in params.items():
        if len(parts) >= CAPTION_PARAM_LIMIT:
            break
        if value is None:
            continue
        if isinstance(value, str):
            if key in {"prompt", "text"}:
                display = _sanitize_caption_value(value)
            elif value.startswith("http"):
                display = url_summary(value) or _sanitize_caption_value(value)
            else:
                display = _sanitize_caption_value(value)
        elif isinstance(value, list):
            if value and isinstance(value[0], str) and value[0].startswith("http"):
                display = url_summary(value[0]) or f"list({len(value)})"
            else:
                display = f"list({len(value)})"
        else:
            display = str(value)
        parts.append(f"{key}={display}")
    return ", ".join(parts) if parts else "params: n/a"


def _sanitize_filename_component(value: str) -> str:
    safe = re.sub(r"[^\w\-\.]+", "_", value.strip())
    safe = re.sub(r"_+", "_", safe)
    return safe[:80] if safe else "result"


def build_result_caption(
    model_label: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    timestamp: Optional[str] = None,
    extra_text: Optional[str] = None,
) -> str:
    ts = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M")
    params_text = _summarize_params(params)
    base = f"{model_label} • {params_text} • {ts}"
    if extra_text:
        return f"{base}\n{extra_text}"
    return base


def build_result_filename_prefix(
    model_label: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    timestamp: Optional[str] = None,
) -> str:
    ts = timestamp or datetime.now().strftime("%Y-%m-%d_%H-%M")
    params_text = _summarize_params(params)
    base = f"{model_label}_{params_text}_{ts}"
    return _sanitize_filename_component(base)


async def deliver_result(
    bot,
    chat_id: int,
    media_type: str,
    urls: List[str],
    text: Optional[str],
    *,
    model_id: Optional[str] = None,
    gen_type: Optional[str] = None,
    correlation_id: Optional[str] = None,
    kie_client: Optional[object] = None,
    params: Optional[Dict[str, Any]] = None,
    model_label: Optional[str] = None,
) -> bool:
    """Deliver generation result to Telegram with unified delivery."""
    media_type = (media_type or "").lower()
    label = model_label or model_id or "model"
    caption_text = text
    if media_type != "text":
        caption_text = build_result_caption(
            label,
            params,
            extra_text=text,
        )
    if not caption_text:
        caption_text = f"✅ Готово. ID: {correlation_id or 'corr-na-na'}"
    filename_prefix = build_result_filename_prefix(label, params)
    start_ts = time.monotonic()
    normalized_urls: List[str] = []
    try:
        normalized_urls = normalize_result_urls(
            urls,
            correlation_id=correlation_id,
            model_id=model_id,
            stage="TG_DELIVER",
        )
    except ResultUrlNormalizationError as exc:
        logger.error("URL normalization failed: %s", exc)
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ Результат получен, но ссылка битая. Попробуйте ещё раз или выберите другую модель.\n"
                f"ID: {correlation_id or 'corr-na-na'}"
            ),
        )
        return False

    log_structured_event(
        correlation_id=correlation_id,
        user_id=chat_id,
        chat_id=chat_id,
        model_id=model_id,
        gen_type=gen_type or media_type,
        action="TG_DELIVER",
        action_path="telegram_sender.deliver_result",
        stage="TG_DELIVER",
        outcome="start",
        param={"media_type": media_type, "urls_count": len(normalized_urls)},
    )

    invalid_urls = [url for url in normalized_urls if not is_valid_result_url(url)]
    if invalid_urls:
        log_structured_event(
            correlation_id=correlation_id,
            user_id=chat_id,
            chat_id=chat_id,
            model_id=model_id,
            gen_type=gen_type or media_type,
            action="TG_DELIVER",
            action_path="telegram_sender.deliver_result",
            stage="TG_DELIVER",
            waiting_for="URL_VALIDATE",
            outcome="failed",
            error_code="INVALID_RESULT_URL",
            fix_hint="check_kie_response_url_fields",
            param={"invalid_urls": [url_summary(url) for url in invalid_urls]},
        )
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ Результат получен, но ссылка битая. Попробуйте ещё раз или выберите другую модель.\n"
                f"ID: {correlation_id or 'corr-na-na'}"
            ),
        )
        return False

    if media_type == "text":
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=caption_text,
                parse_mode="HTML",
            )
            log_structured_event(
                correlation_id=correlation_id,
                user_id=chat_id,
                chat_id=chat_id,
                model_id=model_id,
                gen_type=gen_type or media_type,
                action="TG_DELIVER",
                action_path="telegram_sender.deliver_result",
                stage="TG_DELIVER",
                outcome="success",
                duration_ms=int((time.monotonic() - start_ts) * 1000),
                param={"tg_method": "send_message", "media_type": "text"},
            )
            log_structured_event(
                correlation_id=correlation_id,
                user_id=chat_id,
                chat_id=chat_id,
                model_id=model_id,
                gen_type=gen_type or media_type,
                action="RESULT_DELIVERED",
                action_path="telegram_sender.deliver_result",
                stage="TG_DELIVER",
                outcome="success",
                param={"media_type": media_type, "tg_method": "send_message"},
            )
        except Exception as exc:
            log_structured_event(
                correlation_id=correlation_id,
                user_id=chat_id,
                chat_id=chat_id,
                model_id=model_id,
                gen_type=gen_type or media_type,
                action="TG_DELIVER",
                action_path="telegram_sender.deliver_result",
                stage="TG_DELIVER",
                outcome="failed",
                duration_ms=int((time.monotonic() - start_ts) * 1000),
                error_code="TG_DELIVER_FAILED",
                fix_hint=str(exc),
            )
            raise
        return True

    async with aiohttp.ClientSession() as session:
        tg_method, payload = await resolve_and_prepare_telegram_payload(
            {"urls": normalized_urls, "text": text},
            correlation_id,
            media_type or "document",
            kie_client,
            session,
            filename_prefix=filename_prefix,
        )
        try:
            await getattr(bot, tg_method)(chat_id=chat_id, **payload)
            log_structured_event(
                correlation_id=correlation_id,
                user_id=chat_id,
                chat_id=chat_id,
                model_id=model_id,
                gen_type=gen_type or media_type,
                action="TG_DELIVER",
                action_path="telegram_sender.deliver_result",
                stage="TG_DELIVER",
                outcome="success",
                duration_ms=int((time.monotonic() - start_ts) * 1000),
                param={"tg_method": tg_method, "media_type": media_type},
            )
            log_structured_event(
                correlation_id=correlation_id,
                user_id=chat_id,
                chat_id=chat_id,
                model_id=model_id,
                gen_type=gen_type or media_type,
                action="RESULT_DELIVERED",
                action_path="telegram_sender.deliver_result",
                stage="TG_DELIVER",
                outcome="success",
                param={"media_type": media_type, "tg_method": tg_method},
            )
        except Exception as exc:
            fallback_urls = ", ".join(normalized_urls[:3]) if normalized_urls else "URL missing"
            log_structured_event(
                correlation_id=correlation_id,
                user_id=chat_id,
                chat_id=chat_id,
                model_id=model_id,
                gen_type=gen_type or media_type,
                action="TG_DELIVER",
                action_path="telegram_sender.deliver_result",
                stage="TG_DELIVER",
                outcome="failed",
                duration_ms=int((time.monotonic() - start_ts) * 1000),
                error_code="TG_DELIVER_FAILED",
                fix_hint="send_url_fallback",
                param={"error": str(exc), "urls": [url_summary(url) for url in normalized_urls[:3]]},
            )
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "⚠️ Не удалось отправить файл через Telegram. Вот ссылка:\n"
                    f"{fallback_urls}"
                ),
                disable_web_page_preview=True,
            )
            log_structured_event(
                correlation_id=correlation_id,
                user_id=chat_id,
                chat_id=chat_id,
                model_id=model_id,
                gen_type=gen_type or media_type,
                action="TG_DELIVER_FALLBACK",
                action_path="telegram_sender.deliver_result",
                stage="TG_DELIVER",
                outcome="sent",
                error_code="TG_DELIVER_FALLBACK_URL",
                fix_hint="Sent URL fallback after upload failure.",
            )
            return True
    return True


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

    caption_text = job_result.text
    filename_prefix = None
    if urls:
        caption_text = build_result_caption(spec.name or spec.id, extra_text=job_result.text)
        filename_prefix = build_result_filename_prefix(spec.name or spec.id)
    await deliver_generation_result(
        SimpleNamespace(bot=bot),
        chat_id,
        correlation_id,
        spec.id,
        spec.model_mode,
        urls,
        caption_text or f"✅ Готово. ID: {correlation_id or 'corr-na-na'}",
        prefer_upload=True,
        filename_prefix=filename_prefix,
    )

    price_text = ""
    if price_rub is not None:
        price_display = format_price_rub(price_rub)
        price_text = f"\n💰 <b>Цена:</b> {price_display} ₽"

    elapsed_text = ""
    if elapsed is not None:
        elapsed_text = f"\n⏱️ <b>Время:</b> {elapsed:.1f}s"

    free_counter_line = ""
    try:
        snapshot = await get_free_counter_snapshot(chat_id)
        free_counter_line = format_free_counter_block(
            snapshot.get("remaining", 0),
            snapshot.get("limit_per_day", 0),
            snapshot.get("next_refill_in", 0),
            user_lang=user_lang,
            is_admin=bool(snapshot.get("is_admin")),
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
        summary = f"{summary}\n\n{free_counter_line}"
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
