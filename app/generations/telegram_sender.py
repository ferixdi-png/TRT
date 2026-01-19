"""Universal Telegram sender for generation results."""
from __future__ import annotations

import io
import logging
import mimetypes
import os
import time
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

import aiohttp
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    InputMediaPhoto,
    InputMediaVideo,
)
from telegram.error import BadRequest

from app.kie_catalog import ModelSpec
from app.generations.universal_engine import JobResult
from app.observability.trace import trace_event, url_summary
from app.observability.structured_logs import log_structured_event

logger = logging.getLogger(__name__)

TELEGRAM_MAX_BYTES = int(os.getenv("TELEGRAM_MAX_FILE_BYTES", str(50 * 1024 * 1024)))
DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=float(os.getenv("KIE_MEDIA_DOWNLOAD_TIMEOUT", "30")))


@dataclass(frozen=True)
class UrlProbe:
    should_download: bool
    content_type: str
    content_length: Optional[int]
    redirected_to_html: bool


@dataclass(frozen=True)
class DownloadedMedia:
    data: bytes
    filename: str
    content_type: str
    size: int
    redirected_to_html: bool
    media_match: bool


def _normalize_media_type(media_type: Optional[str]) -> str:
    return (media_type or "").lower()


def _content_type_matches(media_type: str, content_type: str) -> bool:
    if not content_type:
        return False
    media_type = _normalize_media_type(media_type)
    if media_type in {"image", "video", "audio", "voice"}:
        prefix = "audio/" if media_type in {"audio", "voice"} else f"{media_type}/"
        return content_type.startswith(prefix)
    return True


def _infer_filename(url: str, content_type: str, media_type: str) -> str:
    parsed = urlparse(url)
    name = os.path.basename(parsed.path)
    if name:
        return name
    extension = mimetypes.guess_extension(content_type or "")
    if not extension:
        fallback = {
            "image": ".png",
            "video": ".mp4",
            "audio": ".mp3",
            "voice": ".ogg",
            "json": ".json",
        }
        extension = fallback.get(media_type, ".bin")
    return f"result{extension}"


def _is_bad_webpage_error(exc: BaseException) -> bool:
    if not isinstance(exc, BadRequest):
        return False
    return "wrong type of the web page content" in str(exc).lower()


def _fallback_caption(media_type: str) -> str:
    return f"Result type: {media_type or 'unknown'} (sent as document)"


async def _probe_url(session: aiohttp.ClientSession, url: str, media_type: str) -> UrlProbe:
    try:
        async with session.head(url, allow_redirects=True) as response:
            content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
            content_length = response.content_length
            redirected_to_html = bool(response.history) and content_type.startswith("text/html")
            should_download = False
            if redirected_to_html:
                should_download = True
            if media_type in {"image", "video", "audio", "voice"} and content_type:
                if not _content_type_matches(media_type, content_type):
                    should_download = True
            if content_length and content_length > TELEGRAM_MAX_BYTES:
                should_download = True
            return UrlProbe(
                should_download=should_download,
                content_type=content_type,
                content_length=content_length,
                redirected_to_html=redirected_to_html,
            )
    except Exception:
        return UrlProbe(False, "", None, False)


async def _download_media(session: aiohttp.ClientSession, url: str, media_type: str) -> DownloadedMedia:
    async with session.get(url, allow_redirects=True) as response:
        data = await response.read()
        content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
        size = response.content_length or len(data)
        redirected_to_html = bool(response.history) and content_type.startswith("text/html")
        filename = _infer_filename(url, content_type, media_type)
        media_match = _content_type_matches(media_type, content_type)
        return DownloadedMedia(
            data=data,
            filename=filename,
            content_type=content_type,
            size=size,
            redirected_to_html=redirected_to_html,
            media_match=media_match,
        )


async def _send_by_url(bot, chat_id: int, media_type: str, url: str, caption: Optional[str] = None) -> str:
    if media_type == "image":
        await bot.send_photo(chat_id=chat_id, photo=url, caption=caption)
        return "send_photo"
    if media_type == "video":
        await bot.send_video(chat_id=chat_id, video=url, caption=caption)
        return "send_video"
    if media_type == "voice":
        await bot.send_voice(chat_id=chat_id, voice=url, caption=caption)
        return "send_voice"
    if media_type == "audio":
        await bot.send_audio(chat_id=chat_id, audio=url, caption=caption)
        return "send_audio"
    await bot.send_document(chat_id=chat_id, document=url, caption=caption)
    return "send_document"


async def _send_by_file(bot, chat_id: int, media_type: str, media: DownloadedMedia) -> str:
    payload = InputFile(io.BytesIO(media.data), filename=media.filename)
    if media_type == "image":
        await bot.send_photo(chat_id=chat_id, photo=payload)
        return "send_photo"
    if media_type == "video":
        await bot.send_video(chat_id=chat_id, video=payload)
        return "send_video"
    if media_type == "voice":
        await bot.send_voice(chat_id=chat_id, voice=payload)
        return "send_voice"
    if media_type == "audio":
        await bot.send_audio(chat_id=chat_id, audio=payload)
        return "send_audio"
    await bot.send_document(chat_id=chat_id, document=payload, caption=_fallback_caption(media_type))
    return "send_document"


async def _send_downloaded_media(
    bot,
    chat_id: int,
    media_type: str,
    download: DownloadedMedia,
    *,
    correlation_id: Optional[str],
) -> str:
    if download.size > TELEGRAM_MAX_BYTES:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ Файл слишком большой для отправки в Telegram.\n"
                f"ID: {correlation_id or 'corr-na-na'}"
            ),
        )
        return "send_message"
    target_type = media_type if download.media_match else "document"
    return await _send_by_file(bot, chat_id, target_type, download)


async def _send_single_with_fallback(
    bot,
    chat_id: int,
    media_type: str,
    url: str,
    *,
    correlation_id: Optional[str],
    session: aiohttp.ClientSession,
) -> str:
    probe = await _probe_url(session, url, media_type)
    if probe.content_length and probe.content_length > TELEGRAM_MAX_BYTES:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ Файл слишком большой для отправки в Telegram.\n"
                f"ID: {correlation_id or 'corr-na-na'}"
            ),
        )
        return "send_message"
    if probe.should_download:
        download = await _download_media(session, url, media_type)
        return await _send_downloaded_media(bot, chat_id, media_type, download, correlation_id=correlation_id)
    try:
        return await _send_by_url(bot, chat_id, media_type, url)
    except BadRequest as exc:
        if not _is_bad_webpage_error(exc):
            raise
        download = await _download_media(session, url, media_type)
        return await _send_downloaded_media(bot, chat_id, media_type, download, correlation_id=correlation_id)


async def _send_media_group(
    bot,
    chat_id: int,
    media_type: str,
    urls: List[str],
) -> str:
    if media_type == "image":
        media = [InputMediaPhoto(media=url) for url in urls]
        await bot.send_media_group(chat_id=chat_id, media=media)
        return "send_media_group"
    if media_type == "video":
        media = [InputMediaVideo(media=url) for url in urls]
        await bot.send_media_group(chat_id=chat_id, media=media)
        return "send_media_group"
    for url in urls:
        await bot.send_document(chat_id=chat_id, document=url)
    return "send_document"


async def deliver_result(
    bot,
    chat_id: int,
    media_type: str,
    urls: List[str],
    text: Optional[str],
    *,
    model_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> None:
    """Deliver generation result to Telegram with trace logging and fallback."""
    media_type = _normalize_media_type(media_type)
    tg_method = None
    start_ts = time.monotonic()
    try:
        if media_type in {"text", "json"}:
            if text:
                tg_method = "send_message"
                send_fn = lambda: bot.send_message(chat_id=chat_id, text=text)
            elif urls:
                tg_method = "send_document"
                send_fn = lambda: bot.send_document(chat_id=chat_id, document=urls[0])
            else:
                tg_method = "send_message"
                send_fn = lambda: bot.send_message(chat_id=chat_id, text="")
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
            await send_fn()
        elif media_type in {"image", "video"}:
            async with aiohttp.ClientSession(timeout=DOWNLOAD_TIMEOUT) as session:
                if len(urls) > 1:
                    tg_method = "send_media_group"
                    download_required = False
                    for url in urls:
                        probe = await _probe_url(session, url, media_type)
                        if probe.should_download:
                            download_required = True
                            break
                    if download_required:
                        for url in urls:
                            await _send_single_with_fallback(
                                bot,
                                chat_id,
                                media_type,
                                url,
                                correlation_id=correlation_id,
                                session=session,
                            )
                        tg_method = "send_photo" if media_type == "image" else "send_video"
                    else:
                        try:
                            await _send_media_group(bot, chat_id, media_type, urls)
                        except BadRequest as exc:
                            if _is_bad_webpage_error(exc):
                                for url in urls:
                                    await _send_single_with_fallback(
                                        bot,
                                        chat_id,
                                        media_type,
                                        url,
                                        correlation_id=correlation_id,
                                        session=session,
                                    )
                                tg_method = "send_photo" if media_type == "image" else "send_video"
                            else:
                                raise
                elif urls:
                    tg_method = await _send_single_with_fallback(
                        bot,
                        chat_id,
                        media_type,
                        urls[0],
                        correlation_id=correlation_id,
                        session=session,
                    )
        elif media_type in {"audio", "voice"}:
            async with aiohttp.ClientSession(timeout=DOWNLOAD_TIMEOUT) as session:
                for url in urls:
                    tg_method = await _send_single_with_fallback(
                        bot,
                        chat_id,
                        media_type,
                        url,
                        correlation_id=correlation_id,
                        session=session,
                    )
        else:
            if urls:
                tg_method = "send_document"
                await bot.send_document(chat_id=chat_id, document=urls[0], caption=_fallback_caption(media_type))

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
            if urls:
                await bot.send_document(chat_id=chat_id, document=urls[0], caption=_fallback_caption(media_type))
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "⚠️ Не удалось отправить результат.\n"
                        f"ID: {correlation_id or 'corr-na-na'}"
                    ),
                )
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
