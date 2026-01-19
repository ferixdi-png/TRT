"""Universal media pipeline for Telegram delivery."""
from __future__ import annotations

import io
import logging
import mimetypes
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import aiohttp
from telegram import InputFile, InputMediaPhoto, InputMediaVideo

from app.observability.structured_logs import log_structured_event

logger = logging.getLogger(__name__)

TELEGRAM_MAX_BYTES = int(os.getenv("TELEGRAM_MAX_FILE_BYTES", str(50 * 1024 * 1024)))


@dataclass(frozen=True)
class ResolvedMedia:
    url: str
    payload: str | InputFile
    content_type: str
    content_length: Optional[int]
    method: str
    used_download: bool
    too_large: bool


def _strip_url_query(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    return urlunparse(parsed._replace(query="", fragment=""))


def _safe_domain(raw_url: str) -> str:
    try:
        return urlparse(raw_url).netloc or "unknown"
    except Exception:
        return "unknown"


def _is_textual(content_type: str) -> bool:
    if not content_type:
        return True
    if content_type.startswith("text/"):
        return True
    if content_type in {"application/json", "application/javascript", "application/xml"}:
        return True
    return False


def _media_method_from_type(media_kind: str, content_type: str) -> str:
    normalized = (content_type or "").lower()
    if media_kind in {"document", "file"}:
        return "send_document"
    if normalized in {"application/octet-stream", ""}:
        return "send_document"
    if normalized.startswith("image/"):
        return "send_photo"
    if normalized.startswith("video/"):
        return "send_video"
    if normalized.startswith("audio/"):
        return "send_audio" if media_kind != "voice" else "send_voice"
    if media_kind in {"image", "video", "audio", "voice"}:
        return {
            "image": "send_photo",
            "video": "send_video",
            "audio": "send_audio",
            "voice": "send_voice",
        }.get(media_kind, "send_document")
    return "send_document"


def _infer_filename(url: str, content_type: str, media_kind: str) -> str:
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
        }
        extension = fallback.get(media_kind, ".bin")
    return f"result{extension}"


async def _head_or_range_probe(session: aiohttp.ClientSession, url: str) -> Tuple[str, Optional[int]]:
    try:
        async with session.head(url, allow_redirects=True) as response:
            content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
            content_length = response.content_length
            if content_type:
                return content_type, content_length
    except Exception:
        pass
    try:
        async with session.get(url, allow_redirects=True, headers={"Range": "bytes=0-1023"}) as response:
            content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
            content_length = response.content_length
            return content_type, content_length
    except Exception:
        return "", None


async def _download_with_retries(session: aiohttp.ClientSession, url: str, retries: int = 2) -> Tuple[bytes, str, Optional[int]]:
    last_error: Optional[Exception] = None
    for _ in range(retries + 1):
        try:
            async with session.get(url, allow_redirects=True) as response:
                data = await response.read()
                content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
                content_length = response.content_length or len(data)
                return data, content_type, content_length
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Download failed: {last_error}")


def _is_kie_url(url: str, kie_client: Any) -> bool:
    parsed = urlparse(url)
    base_url = getattr(kie_client, "base_url", "") if kie_client else ""
    base_host = urlparse(base_url).netloc if base_url else ""
    return bool(parsed.netloc and base_host and base_host == parsed.netloc)


async def _resolve_kie_download_url(url: str, kie_client: Any, correlation_id: Optional[str]) -> str:
    if not kie_client:
        return url
    resolver = getattr(kie_client, "get_download_url", None)
    if not callable(resolver):
        return url
    result = await resolver(url, correlation_id=correlation_id)
    if result and result.get("ok") and result.get("url"):
        return result["url"]
    return url


def _build_caption(correlation_id: Optional[str], media_kind: str) -> str:
    short_kind = media_kind or "result"
    corr = correlation_id or "corr-na-na"
    return f"✅ Готово ({short_kind}). ID: {corr}"


async def _resolve_single_media(
    url: str,
    media_kind: str,
    correlation_id: Optional[str],
    kie_client: Any,
    http_client: aiohttp.ClientSession,
) -> ResolvedMedia:
    resolved_url = url
    if _is_kie_url(url, kie_client):
        resolved_url = await _resolve_kie_download_url(url, kie_client, correlation_id)

    content_type, content_length = await _head_or_range_probe(http_client, resolved_url)
    too_large = bool(content_length and content_length > TELEGRAM_MAX_BYTES)
    needs_download = _is_textual(content_type) or too_large

    if needs_download:
        data, dl_type, dl_length = await _download_with_retries(http_client, resolved_url)
        filename = _infer_filename(resolved_url, dl_type, media_kind)
        payload = InputFile(io.BytesIO(data), filename=filename)
        method = _media_method_from_type(media_kind, dl_type)
        return ResolvedMedia(
            url=resolved_url,
            payload=payload,
            content_type=dl_type,
            content_length=dl_length,
            method=method,
            used_download=True,
            too_large=bool(dl_length and dl_length > TELEGRAM_MAX_BYTES),
        )

    method = _media_method_from_type(media_kind, content_type)
    return ResolvedMedia(
        url=resolved_url,
        payload=resolved_url,
        content_type=content_type,
        content_length=content_length,
        method=method,
        used_download=False,
        too_large=False,
    )


async def resolve_and_prepare_telegram_payload(
    result: Any,
    correlation_id: Optional[str],
    media_kind: str,
    kie_client: Any,
    http_client: aiohttp.ClientSession,
) -> Tuple[str, Dict[str, Any]]:
    """
    Resolve generation result into a Telegram method + payload kwargs.

    Returns (tg_method, payload_kwargs).
    """
    urls: List[str] = []
    text = None
    if isinstance(result, dict):
        urls = [url for url in result.get("urls", []) if url]
        text = result.get("text")
    else:
        urls = [url for url in getattr(result, "urls", []) if url]
        text = getattr(result, "text", None)

    media_kind = (media_kind or "").lower()
    if media_kind in {"text", "json"} or (text and not urls):
        return "send_message", {"text": text or "", "parse_mode": "HTML"}

    if not urls:
        return "send_message", {
            "text": f"⚠️ Нет результата для отправки. ID: {correlation_id or 'corr-na-na'}",
        }

    resolved_items = [
        await _resolve_single_media(url, media_kind, correlation_id, kie_client, http_client) for url in urls
    ]
    for item in resolved_items:
        fallback_reason = None
        if item.used_download:
            fallback_reason = "downloaded_for_validation"
        if item.too_large:
            fallback_reason = "telegram_size_limit"
        log_media_resolution(
            correlation_id=correlation_id,
            media_kind=media_kind,
            resolved_url=item.url,
            content_type=item.content_type,
            content_length=item.content_length,
            tg_method=item.method,
            fallback_reason=fallback_reason,
        )

    caption = _build_caption(correlation_id, media_kind)

    if len(resolved_items) > 1 and all(item.method in {"send_photo", "send_video"} for item in resolved_items):
        media_group = []
        for idx, item in enumerate(resolved_items):
            if item.method == "send_photo":
                media_group.append(InputMediaPhoto(media=item.payload, caption=caption if idx == 0 else None))
            else:
                media_group.append(InputMediaVideo(media=item.payload, caption=caption if idx == 0 else None))
        return "send_media_group", {"media": media_group}

    first_item = resolved_items[0]
    if first_item.too_large:
        return "send_message", {
            "text": (
                "⚠️ Файл слишком большой для Telegram. "
                f"ID: {correlation_id or 'corr-na-na'}"
            ),
        }

    payload_key = {
        "send_photo": "photo",
        "send_video": "video",
        "send_audio": "audio",
        "send_voice": "voice",
    }.get(first_item.method, "document")
    return first_item.method, {payload_key: first_item.payload, "caption": caption}


def log_media_resolution(
    *,
    correlation_id: Optional[str],
    media_kind: str,
    resolved_url: str,
    content_type: str,
    content_length: Optional[int],
    tg_method: str,
    fallback_reason: Optional[str],
) -> None:
    log_structured_event(
        correlation_id=correlation_id,
        action="MEDIA_RESOLVE",
        action_path="media_pipeline.resolve_and_prepare_telegram_payload",
        stage="MEDIA_RESOLVE",
        outcome="resolved",
        param={
            "media_kind": media_kind,
            "resolved_domain": _safe_domain(resolved_url),
            "content_type": content_type,
            "content_length": content_length,
            "tg_method": tg_method,
            "fallback_reason": fallback_reason,
            "resolved_url": _strip_url_query(resolved_url),
        },
    )
