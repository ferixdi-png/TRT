"""Chat Z-Image handler — isolated module for public chat auto-generation.

Every text message in the target chat triggers a Z-Image generation.
Response is always: image + short charismatic phrase (or placeholder on error).

Config via env vars:
  CHAT_ZIMAGE_CHAT          — @username of the target chat (required to enable)
  CHAT_ZIMAGE_COOLDOWN      — per-user cooldown in seconds (default 300)
  CHAT_ZIMAGE_MAX_CONCURRENCY — max parallel generations (default 1)
  CHAT_ZIMAGE_MAX_QUEUE     — max queued requests (default 20)
  CHAT_ZIMAGE_ASPECT_RATIO  — default aspect ratio (default 1:1)
  CHAT_ZIMAGE_TIMEOUT       — generation timeout in seconds (default 120)
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import random
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes, MessageHandler, filters

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════

CHAT_ZIMAGE_CHAT: str = os.getenv("CHAT_ZIMAGE_CHAT", "").strip()
CHAT_ZIMAGE_MODEL: str = "z-image"
CHAT_ZIMAGE_COOLDOWN: int = int(os.getenv("CHAT_ZIMAGE_COOLDOWN", "300"))
CHAT_ZIMAGE_MAX_CONCURRENCY: int = int(os.getenv("CHAT_ZIMAGE_MAX_CONCURRENCY", "1"))
CHAT_ZIMAGE_MAX_QUEUE: int = int(os.getenv("CHAT_ZIMAGE_MAX_QUEUE", "20"))
CHAT_ZIMAGE_ASPECT_RATIO: str = os.getenv("CHAT_ZIMAGE_ASPECT_RATIO", "1:1")
CHAT_ZIMAGE_TIMEOUT: int = int(os.getenv("CHAT_ZIMAGE_TIMEOUT", "120"))

# ═══════════════════════════════════════════════════════════════════════
# PHRASES
# ═══════════════════════════════════════════════════════════════════════

PHRASES_OK: List[str] = [
    "Держи, как просил",
    "Лови, свежак",
    "Готово, забирай",
    "Залетаем, держи",
    "Вот твой результат",
    "Сделал, смотри",
    "Поймал идею, держи",
    "Красиво вышло, держи",
]

PHRASE_COOLDOWN: str = "Кулдаун, вернусь позже"
PHRASE_QUEUE_FULL: str = "Очередь занята, повтори позже"
PHRASE_ERROR: str = "Глюкнуло, повтори"

# ═══════════════════════════════════════════════════════════════════════
# PLACEHOLDER IMAGE
# ═══════════════════════════════════════════════════════════════════════

PLACEHOLDER_PATH: Path = Path(__file__).parent / "placeholder.png"
_placeholder_cache: Optional[bytes] = None


def _load_placeholder() -> bytes:
    global _placeholder_cache
    if _placeholder_cache is None:
        _placeholder_cache = PLACEHOLDER_PATH.read_bytes()
    return _placeholder_cache


# ═══════════════════════════════════════════════════════════════════════
# COOLDOWN TRACKER
# ═══════════════════════════════════════════════════════════════════════

_cooldowns: Dict[int, float] = {}


def _check_cooldown(user_id: int) -> Optional[float]:
    """Returns remaining seconds if on cooldown, None if ready."""
    last = _cooldowns.get(user_id)
    if last is None:
        return None
    elapsed = time.monotonic() - last
    if elapsed >= CHAT_ZIMAGE_COOLDOWN:
        return None
    return CHAT_ZIMAGE_COOLDOWN - elapsed


def _set_cooldown(user_id: int) -> None:
    _cooldowns[user_id] = time.monotonic()


# ═══════════════════════════════════════════════════════════════════════
# CONCURRENCY LIMITER (isolated from main bot)
# ═══════════════════════════════════════════════════════════════════════

class _ChatLimiter:
    """Semaphore-based limiter with bounded queue for chat mode."""

    def __init__(self, max_concurrency: int, max_queue: int) -> None:
        self._sem = asyncio.Semaphore(max_concurrency)
        self._in_flight: int = 0
        self._max_in_flight: int = max_concurrency + max_queue

    def try_enter(self) -> bool:
        """Try to enter the queue. Returns False if full."""
        if self._in_flight >= self._max_in_flight:
            return False
        self._in_flight += 1
        return True

    async def wait_for_slot(self) -> None:
        """Wait for a concurrency slot (blocks until available)."""
        await self._sem.acquire()

    def release(self) -> None:
        """Release concurrency slot and leave queue."""
        self._sem.release()
        self._in_flight = max(0, self._in_flight - 1)

    def leave_queue(self) -> None:
        """Leave queue without running (error before slot acquired)."""
        self._in_flight = max(0, self._in_flight - 1)


_limiter: Optional[_ChatLimiter] = None


def _get_limiter() -> _ChatLimiter:
    global _limiter
    if _limiter is None:
        _limiter = _ChatLimiter(CHAT_ZIMAGE_MAX_CONCURRENCY, CHAT_ZIMAGE_MAX_QUEUE)
    return _limiter


# ═══════════════════════════════════════════════════════════════════════
# HELPER: send placeholder reply
# ═══════════════════════════════════════════════════════════════════════

async def _send_placeholder(message: Any, text: str) -> None:
    """Send placeholder image with short text as reply-to-message."""
    try:
        data = _load_placeholder()
        photo = io.BytesIO(data)
        photo.name = "placeholder.png"
        await message.reply_photo(photo=photo, caption=text)
    except Exception as exc:
        logger.error("CHAT_ZIMAGE_PLACEHOLDER_FAIL error=%s", exc)


# ═══════════════════════════════════════════════════════════════════════
# HELPER: download image from URL
# ═══════════════════════════════════════════════════════════════════════

async def _download_image(url: str) -> Optional[bytes]:
    """Download image bytes from a result URL."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    return await resp.read()
                logger.warning(
                    "CHAT_ZIMAGE_DOWNLOAD_FAIL url=%s status=%d",
                    url[:80], resp.status,
                )
    except Exception as exc:
        logger.error("CHAT_ZIMAGE_DOWNLOAD_ERROR url=%s error=%s", url[:80], exc)
    return None


# ═══════════════════════════════════════════════════════════════════════
# HELPER: run Z-Image generation via universal engine
# ═══════════════════════════════════════════════════════════════════════

async def _run_zimage(user_id: int, prompt: str) -> Any:
    """Run Z-Image generation through the existing KIE adapter.

    Returns a JobResult on success, None on failure.
    """
    from app.generations.universal_engine import run_generation
    from app.storage import get_storage

    job_id = f"chat-zimg-{uuid.uuid4().hex[:12]}"
    correlation_id = f"corr-chat-zimg-{user_id}-{uuid.uuid4().hex[:8]}"

    session_params: Dict[str, Any] = {
        "prompt": prompt,
        "aspect_ratio": CHAT_ZIMAGE_ASPECT_RATIO,
    }

    storage = get_storage()
    await storage.add_generation_job(
        job_id=job_id,
        user_id=user_id,
        model_id=CHAT_ZIMAGE_MODEL,
        model_name="Z-Image",
        params=session_params,
        price=0.0,
        status="pending",
        is_free=True,
        prompt=prompt,
        correlation_id=correlation_id,
    )

    result = await run_generation(
        user_id=user_id,
        model_id=CHAT_ZIMAGE_MODEL,
        session_params=session_params,
        correlation_id=correlation_id,
        job_id=job_id,
        price=0.0,
        is_free=True,
        wait_for_result=True,
        timeout=CHAT_ZIMAGE_TIMEOUT,
    )
    return result


# ═══════════════════════════════════════════════════════════════════════
# MAIN HANDLER
# ═══════════════════════════════════════════════════════════════════════

async def _handle_chat_zimage(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle a text message in the target public chat."""
    message = update.effective_message
    if not message or not message.text:
        return

    user = update.effective_user
    user_id = user.id if user else 0
    chat = update.effective_chat
    prompt = message.text.strip()

    if not prompt:
        return

    logger.info(
        "CHAT_ZIMAGE_MSG user_id=%s chat_id=%s prompt_len=%d",
        user_id, chat.id if chat else 0, len(prompt),
    )

    # ── Cooldown check ──────────────────────────────────────────────
    remaining = _check_cooldown(user_id)
    if remaining is not None:
        logger.info(
            "CHAT_ZIMAGE_COOLDOWN user_id=%s remaining_s=%.0f", user_id, remaining
        )
        await _send_placeholder(message, PHRASE_COOLDOWN)
        return

    # ── Queue check ─────────────────────────────────────────────────
    limiter = _get_limiter()
    if not limiter.try_enter():
        logger.info("CHAT_ZIMAGE_QUEUE_FULL user_id=%s in_flight=%d", user_id, limiter._in_flight)
        await _send_placeholder(message, PHRASE_QUEUE_FULL)
        return

    try:
        # Set cooldown immediately to prevent spam during generation
        _set_cooldown(user_id)

        # Wait for a concurrency slot
        await limiter.wait_for_slot()
    except Exception:
        limiter.leave_queue()
        await _send_placeholder(message, PHRASE_ERROR)
        return

    try:
        # Show typing indicator
        if chat:
            try:
                await context.bot.send_chat_action(
                    chat_id=chat.id, action=ChatAction.UPLOAD_PHOTO
                )
            except Exception:
                pass

        # Run generation
        result = await _run_zimage(user_id, prompt)

        if result and result.urls:
            image_data = await _download_image(result.urls[0])
            if image_data:
                phrase = random.choice(PHRASES_OK)
                photo = io.BytesIO(image_data)
                photo.name = "zimage.png"
                await message.reply_photo(photo=photo, caption=phrase)
                logger.info(
                    "CHAT_ZIMAGE_OK user_id=%s task_id=%s prompt_len=%d",
                    user_id, result.task_id, len(prompt),
                )
                return

        # No result or download failed
        logger.warning("CHAT_ZIMAGE_NO_RESULT user_id=%s", user_id)
        await _send_placeholder(message, PHRASE_ERROR)

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.error(
            "CHAT_ZIMAGE_ERROR user_id=%s error=%s",
            user_id, str(exc)[:200], exc_info=True,
        )
        await _send_placeholder(message, PHRASE_ERROR)
    finally:
        limiter.release()


# ═══════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════

def register_chat_zimage_handler(application: Any) -> bool:
    """Register the chat Z-Image handler if CHAT_ZIMAGE_CHAT is set.

    Returns True if registered, False if disabled.
    """
    if not CHAT_ZIMAGE_CHAT:
        logger.debug("CHAT_ZIMAGE_DISABLED env CHAT_ZIMAGE_CHAT not set")
        return False

    username = CHAT_ZIMAGE_CHAT.lstrip("@")
    chat_filter = filters.Chat(username=username)
    text_filter = filters.TEXT & ~filters.COMMAND

    handler = MessageHandler(
        chat_filter & text_filter,
        _handle_chat_zimage,
    )

    # Group 100 — isolated from main bot handlers (groups 0-10)
    application.add_handler(handler, group=100)

    logger.info(
        "CHAT_ZIMAGE_REGISTERED chat=%s model=%s cooldown=%ds "
        "concurrency=%d queue=%d aspect=%s timeout=%ds",
        CHAT_ZIMAGE_CHAT,
        CHAT_ZIMAGE_MODEL,
        CHAT_ZIMAGE_COOLDOWN,
        CHAT_ZIMAGE_MAX_CONCURRENCY,
        CHAT_ZIMAGE_MAX_QUEUE,
        CHAT_ZIMAGE_ASPECT_RATIO,
        CHAT_ZIMAGE_TIMEOUT,
    )
    return True
