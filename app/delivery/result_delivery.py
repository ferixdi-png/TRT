"""Unified delivery pipeline for generation results."""
from __future__ import annotations

import asyncio
import io
import logging
import mimetypes
import os
import time
import uuid
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple
from urllib.parse import urlparse

import aiohttp
from telegram import InputFile

from app.observability.structured_logs import log_structured_event
from app.observability.trace import trace_event, url_summary
from app.utils.url_normalizer import is_valid_result_url

logger = logging.getLogger(__name__)

SAFE_UPLOAD_BYTES = int(os.getenv("TELEGRAM_SAFE_UPLOAD_BYTES", str(45 * 1024 * 1024)))
DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=float(os.getenv("KIE_MEDIA_DOWNLOAD_TIMEOUT", "30")))

HTML_SNIPPET_LIMIT = 1024

@dataclass(frozen=True)
class DeliveryTarget:
    url: str
    data: bytes
    content_type: str
    size_bytes: int


def _short_error_id() -> str:
    return uuid.uuid4().hex[:8]


def _normalize_content_type(content_type: str) -> str:
    return (content_type or "").split(";")[0].strip().lower()


def _looks_like_html(data: bytes, content_type: str) -> bool:
    if _normalize_content_type(content_type) == "text/html":
        return True
    snippet = data[:HTML_SNIPPET_LIMIT].lstrip().lower()
    return snippet.startswith(b"<!doctype html") or snippet.startswith(b"<html") or b"<html" in snippet


def _looks_like_json(data: bytes) -> bool:
    snippet = data[:HTML_SNIPPET_LIMIT].lstrip()
    return snippet.startswith(b"{") or snippet.startswith(b"[")


def _looks_like_text(data: bytes) -> bool:
    if not data:
        return False
    try:
        decoded = data[:HTML_SNIPPET_LIMIT].decode("utf-8", errors="ignore")
    except Exception:
        return False
    printable = sum(1 for ch in decoded if ch.isprintable() or ch in "\r\n\t")
    return printable >= max(1, int(len(decoded) * 0.9))


def _detect_magic_type(data: bytes) -> Optional[str]:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if data.startswith(b"OggS"):
        return "audio/ogg"
    if data.startswith(b"ID3") or data.startswith(b"\xff\xfb"):
        return "audio/mpeg"
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"PK\x03\x04"):
        return "application/zip"
    if b"ftypqt" in data[:16]:
        return "video/quicktime"
    if b"ftyp" in data[:16]:
        return "video/mp4"
    return None


def _resolve_real_mime(content_type: str, data: bytes, url: str) -> str:
    normalized = _normalize_content_type(content_type)
    if normalized in {"text/html", "text/plain", "application/json"}:
        return normalized
    magic_type = _detect_magic_type(data)
    if magic_type:
        return magic_type
    if _looks_like_html(data, normalized):
        return "text/html"
    if _looks_like_json(data):
        return "application/json"
    if _looks_like_text(data):
        return "text/plain"
    if normalized.startswith(("image/", "video/", "audio/")):
        return "application/octet-stream"
    if normalized:
        return normalized
    guessed = mimetypes.guess_type(url)[0]
    return (guessed or "application/octet-stream").lower()


def _is_textual_type(content_type: str) -> bool:
    normalized = _normalize_content_type(content_type)
    return normalized.startswith("text/") or normalized in {"application/json", "application/xml"}


def _method_for_type(content_type: str) -> str:
    normalized = _normalize_content_type(content_type)
    if normalized.startswith("image/"):
        return "send_photo"
    if normalized.startswith("video/"):
        return "send_video"
    if normalized.startswith("audio/"):
        return "send_audio"
    return "send_document"


def _extension_for_type(content_type: str) -> str:
    normalized = _normalize_content_type(content_type)
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/ogg": ".ogg",
        "application/pdf": ".pdf",
        "application/zip": ".zip",
        "text/plain": ".txt",
        "application/json": ".json",
    }
    if normalized in mapping:
        return mapping[normalized]
    guessed = mimetypes.guess_extension(normalized)
    return guessed or ".bin"


def _derive_filename(url: str, content_type: str, index: int, filename_prefix: Optional[str] = None) -> str:
    parsed = urlparse(url)
    name = os.path.basename(parsed.path or "")
    extension = _extension_for_type(content_type)
    if filename_prefix:
        return f"{filename_prefix}_{index}{extension}"
    if name:
        base, ext = os.path.splitext(name)
        return f"{base or f'result_{index}'}{ext or extension}"
    return f"result_{index}{extension}"


async def _download_with_retries(
    session: aiohttp.ClientSession,
    url: str,
    *,
    attempts: int = 4,
    backoff: Tuple[float, ...] = (0.5, 1.0, 2.0),
) -> DeliveryTarget:
    last_error: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            async with session.get(url, allow_redirects=True) as response:
                if response.status >= 400:
                    raise RuntimeError(f"HTTP {response.status}")
                data = await response.read()
                content_type = response.headers.get("Content-Type", "")
                size_bytes = response.content_length or len(data)
                return DeliveryTarget(
                    url=url,
                    data=data,
                    content_type=_normalize_content_type(content_type),
                    size_bytes=size_bytes,
                )
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1:
                delay = backoff[min(attempt, len(backoff) - 1)]
                await asyncio.sleep(delay)
    raise RuntimeError(f"Download failed: {last_error}")


async def deliver_generation_result(
    context,
    chat_id: int,
    correlation_id: Optional[str],
    model_id: Optional[str],
    gen_type: Optional[str],
    result_urls: Iterable[str],
    caption_text: Optional[str],
    *,
    prefer_upload: bool = True,
    filename_prefix: Optional[str] = None,
) -> None:
    """Deliver generation results through a unified delivery layer."""
    urls = [url for url in result_urls if url]
    start_ts = time.monotonic()
    trace_event(
        "info",
        correlation_id or "corr-na-na",
        event="TRACE_IN",
        stage="TG_DELIVER",
        action="DELIVERY_START",
        model_id=model_id,
        gen_type=gen_type,
    )
    log_structured_event(
        correlation_id=correlation_id,
        user_id=chat_id,
        chat_id=chat_id,
        model_id=model_id,
        gen_type=gen_type,
        action="DELIVERY_START",
        action_path="result_delivery.deliver_generation_result",
        stage="DELIVERY",
        waiting_for="DOWNLOAD",
        outcome="start",
    )

    if not urls:
        if caption_text:
            await context.bot.send_message(chat_id=chat_id, text=caption_text, parse_mode="HTML")
        return

    async with aiohttp.ClientSession(timeout=DOWNLOAD_TIMEOUT) as session:
        for index, url in enumerate(urls, start=1):
            if not is_valid_result_url(url):
                log_structured_event(
                    correlation_id=correlation_id,
                    user_id=chat_id,
                    chat_id=chat_id,
                    model_id=model_id,
                    gen_type=gen_type,
                    action="DELIVERY_VALIDATE",
                    action_path="result_delivery.deliver_generation_result",
                    stage="DELIVERY",
                    waiting_for="URL_VALIDATE",
                    outcome="failed",
                    error_code="INVALID_RESULT_URL",
                    fix_hint="check_kie_response_url_fields",
                    param={"url": url_summary(url)},
                )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "⚠️ Результат получен, но ссылка битая. Попробуйте ещё раз или выберите другую модель.\n"
                        f"ID: {correlation_id or 'corr-na-na'}"
                    ),
                )
                continue
            try:
                target = await _download_with_retries(session, url)
                real_type = _resolve_real_mime(target.content_type, target.data, target.url)
                if _looks_like_html(target.data, real_type):
                    message = (
                        "⚠️ KIE вернул html/preview, нужен другой url.\n"
                        f"{target.url}"
                    )
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        disable_web_page_preview=True,
                    )
                    continue

                if _is_textual_type(real_type):
                    filename = _derive_filename(target.url, real_type, index, filename_prefix)
                    payload = InputFile(io.BytesIO(target.data), filename=filename)
                    await context.bot.send_document(chat_id=chat_id, document=payload)
                    continue

                if target.size_bytes > SAFE_UPLOAD_BYTES or not prefer_upload:
                    message = (
                        "⚠️ Файл слишком большой для Telegram.\n"
                        f"{target.url}"
                    )
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        disable_web_page_preview=True,
                    )
                    continue

                filename = _derive_filename(target.url, real_type, index, filename_prefix)
                payload = InputFile(io.BytesIO(target.data), filename=filename)
                method = _method_for_type(real_type)
                payload_key = {
                    "send_photo": "photo",
                    "send_video": "video",
                    "send_audio": "audio",
                }.get(method, "document")
                kwargs = {payload_key: payload}
                if caption_text and index == 1:
                    kwargs["caption"] = caption_text
                    kwargs["parse_mode"] = "HTML"
                await getattr(context.bot, method)(chat_id=chat_id, **kwargs)
                log_structured_event(
                    correlation_id=correlation_id,
                    user_id=chat_id,
                    chat_id=chat_id,
                    model_id=model_id,
                    gen_type=gen_type,
                    action="DELIVERY_ITEM",
                    action_path="result_delivery.deliver_generation_result",
                    stage="DELIVERY",
                    outcome="sent",
                    duration_ms=int((time.monotonic() - start_ts) * 1000),
                    param={"url": url_summary(target.url), "method": method},
                )
            except Exception as exc:
                error_id = _short_error_id()
                logger.error("Delivery failure for %s: %s", url, exc, exc_info=True)
                log_structured_event(
                    correlation_id=correlation_id,
                    user_id=chat_id,
                    chat_id=chat_id,
                    model_id=model_id,
                    gen_type=gen_type,
                    action="DELIVERY_FAIL",
                    action_path="result_delivery.deliver_generation_result",
                    stage="DELIVERY",
                    outcome="failed",
                    duration_ms=int((time.monotonic() - start_ts) * 1000),
                    error_id=error_id,
                    error_code="TG_DELIVERY_FAILED",
                    fix_hint="send_url_fallback",
                    param={"url": url_summary(url), "error": str(exc)},
                )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "⚠️ Не удалось отправить файл через Telegram.\n"
                        f"Ссылка: {url}\n"
                        f"ID: {error_id}"
                    ),
                    disable_web_page_preview=True,
                )
