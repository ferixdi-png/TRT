"""Chat Z-Image handler — isolated module for public chat auto-generation.

GATE architecture:
  A single TypeHandler (group=-50) intercepts ALL updates from the target
  chat BEFORE any main-bot handler runs.  For every update from that chat
  it raises ApplicationHandlerStop, so the main bot never sees anything
  from the chat — no menus, no buttons, no fallback text.

  Only valid text messages (non-empty, non-command) trigger a Z-Image
  generation which runs as a background task (no webhook stall).
  On success the bot silently replies with the photo.
  On any failure — cooldown, queue full, generation error — the bot
  stays completely silent (details only in logs).

Config via env vars:
  CHAT_ZIMAGE_CHAT            — @username of the target chat (required)
  CHAT_ZIMAGE_COOLDOWN        — per-user cooldown seconds (default 300)
  CHAT_ZIMAGE_MAX_CONCURRENCY — max parallel generations (default 1)
  CHAT_ZIMAGE_MAX_QUEUE       — max queued requests (default 20)
  CHAT_ZIMAGE_ASPECT_RATIO    — default aspect ratio (default 1:1)
  CHAT_ZIMAGE_TIMEOUT         — generation timeout seconds (default 120)
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
from typing import Any, Dict, List, Optional, Set

import aiohttp
from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes, TypeHandler

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════

CHAT_ZIMAGE_CHAT: str = os.getenv("CHAT_ZIMAGE_CHAT", "").strip()


def _parse_chat_username(raw: str) -> str:
    """Extract bare lowercase username from any format:
    - https://t.me/FERIXDI_FREE  → ferixdi_free
    - @FERIXDI_FREE              → ferixdi_free
    - FERIXDI_FREE               → ferixdi_free
    """
    if not raw:
        return ""
    val = raw.strip()
    # Strip t.me URL prefix (http/https, with or without trailing slash)
    for prefix in ("https://t.me/", "http://t.me/", "t.me/"):
        if val.lower().startswith(prefix):
            val = val[len(prefix):]
            break
    val = val.strip("/").lstrip("@")
    return val.lower()


_TARGET_USERNAME: str = _parse_chat_username(CHAT_ZIMAGE_CHAT)
CHAT_ZIMAGE_MODEL: str = "z-image"
CHAT_ZIMAGE_MAX_CONCURRENCY: int = int(os.getenv("CHAT_ZIMAGE_MAX_CONCURRENCY", "1"))
CHAT_ZIMAGE_MAX_QUEUE: int = int(os.getenv("CHAT_ZIMAGE_MAX_QUEUE", "20"))
CHAT_ZIMAGE_ASPECT_RATIO: str = os.getenv("CHAT_ZIMAGE_ASPECT_RATIO", "1:1")
CHAT_ZIMAGE_TIMEOUT: int = int(os.getenv("CHAT_ZIMAGE_TIMEOUT", "120"))
CHAT_ZIMAGE_ADMIN_IDS: Set[int] = {
    int(x.strip()) for x in os.getenv("CHAT_ZIMAGE_ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

# ═══════════════════════════════════════════════════════════════════════
# PHRASES (only used on successful generation)
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

# ═══════════════════════════════════════════════════════════════════════
# PLACEHOLDER (kept for tests, not sent to users)
# ═══════════════════════════════════════════════════════════════════════

PLACEHOLDER_PATH: Path = Path(__file__).parent / "placeholder.png"
_placeholder_cache: Optional[bytes] = None


def _load_placeholder() -> bytes:
    global _placeholder_cache
    if _placeholder_cache is None:
        _placeholder_cache = PLACEHOLDER_PATH.read_bytes()
    return _placeholder_cache


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
# BACKGROUND TASK REGISTRY (prevent GC)
# ═══════════════════════════════════════════════════════════════════════

_background_tasks: Set[asyncio.Task] = set()


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
# HELPER: run Z-Image generation via storage and KIE
# ═══════════════════════════════════════════════════════════════════════

async def _run_zimage(user_id: int, prompt: str) -> Optional[GenerationResult]:
    """Run Z-Image generation via storage and KIE."""
    logger.info("[CHAT_ZIMAGE] RUN_ZIMAGE_START user_id=%s prompt=%s", user_id, prompt[:50])
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
        correlation_id=correlation_id,
        prompt=prompt,
    )
    logger.info("[CHAT_ZIMAGE] RUN_ZIMAGE_DONE user_id=%s job_id=%s result=OK", user_id, job_id)
    
    # Wait for result using reconciler polling
    from app.delivery.reconciler import wait_for_job_result
    result = await wait_for_job_result(job_id, timeout=CHAT_ZIMAGE_TIMEOUT)
    return result, job_id


# ═══════════════════════════════════════════════════════════════════════
# BACKGROUND GENERATION TASK
# ═══════════════════════════════════════════════════════════════════════

async def _background_generate(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str, limiter: _ChatLimiter) -> None:
    """Background task: wait for slot, run generation, download, reply."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message_id = update.effective_message.message_id
    corr_id = f"corr-{update.update_id}-{user_id}"
    logger.info("[CHAT_ZIMAGE] BACKGROUND_START corr_id=%s user_id=%s chat_id=%s prompt=%s", corr_id, user_id, chat_id, prompt[:50])

    try:
        logger.info("[CHAT_ZIMAGE] BEFORE_SLOT_WAIT corr_id=%s", corr_id)
        async with limiter._sem:
            logger.info("[CHAT_ZIMAGE] SLOT_ACQUIRED corr_id=%s", corr_id)
            result, job_id = await _run_zimage(user_id, prompt)

        if result and result.urls:
            image_data = await _download_image(result.urls[0])
            if image_data:
                phrase = random.choice(PHRASES_OK)
                photo = io.BytesIO(image_data)
                photo.name = "zimage.png"
                await update.effective_message.reply_photo(photo=photo, caption=phrase)
                logger.info(
                    "CHAT_ZIMAGE_OK user_id=%s task_id=%s prompt_len=%d",
                    user_id, job_id, len(prompt),
                )
            else:
                await update.effective_message.reply_text("Не скачалось :(")
                logger.warning("CHAT_ZIMAGE_DOWNLOAD_FAIL user_id=%s job_id=%s", user_id, job_id)
        else:
            await update.effective_message.reply_text("Не сгенерировалось :(")
            logger.warning("CHAT_ZIMAGE_GENERATION_FAIL user_id=%s job_id=%s", user_id, job_id)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("CHAT_ZIMAGE_BACKGROUND_ERROR user_id=%s error=%s", user_id, exc)
        try:
            await update.effective_message.reply_text("Упс, ошибка :(")
        except Exception:
            pass  # Best effort
    finally:
        limiter._in_flight -= 1


# ═══════════════════════════════════════════════════════════════════════
# GATE HANDLER — intercepts ALL updates from the target chat
# ═══════════════════════════════════════════════════════════════════════

async def _chat_zimage_gate(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Gate for the target chat.

    - Runs in group=-50 (before main bot handlers, after audit/logging).
    - For ANY update from the target chat: raises ApplicationHandlerStop
      so the main bot never sees it (no menus, no buttons, no fallback).
    - For valid text messages: spawns a background generation task.
    - For everything else (callbacks, commands, media): silently drops.
    - Updates from OTHER chats pass through untouched (return normally).
    """
    chat = update.effective_chat
    if not chat:
        return  # not a chat update — pass through to main handlers

    chat_username = (chat.username or "").lower()
    if chat_username != _TARGET_USERNAME:
        return  # not the target chat — pass through

    # ═══ This IS the target chat — block ALL main handlers ═══

    message = update.effective_message
    if message and message.text and not message.text.startswith("/"):
        prompt = message.text.strip()
        user = update.effective_user
        user_id = user.id if user else 0

        if prompt and user_id:
            # Queue — silent skip if full
            limiter = _get_limiter()
            if not limiter.try_enter():
                logger.info(
                    "CHAT_ZIMAGE_QUEUE_FULL user_id=%s in_flight=%d",
                    user_id, limiter._in_flight,
                )
            else:
                # Launch background task (no webhook stall)
                # Rate-limiting is handled by Telegram Slow Mode in chat settings
                task = asyncio.create_task(
                    _background_generate(update, context, prompt, limiter),
                    name=f"chat_zimg_{user_id}_{uuid.uuid4().hex[:6]}",
                )
                _background_tasks.add(task)
                task.add_done_callback(_background_tasks.discard)

                logger.info(
                    "CHAT_ZIMAGE_QUEUED user_id=%s chat_id=%s prompt_len=%d tasks=%d",
                    user_id, chat.id, len(prompt), len(_background_tasks),
                )

    # Block ALL further handler processing for this chat
    raise ApplicationHandlerStop


# ═══════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════

def register_chat_zimage_handler(application: Any) -> bool:
    """Register the chat Z-Image gate handler if CHAT_ZIMAGE_CHAT is set.

    Uses TypeHandler in group=-50 to intercept ALL update types from the
    target chat before any main-bot handler runs.

    Returns True if registered, False if disabled.
    """
    if not CHAT_ZIMAGE_CHAT:
        logger.debug("CHAT_ZIMAGE_DISABLED env CHAT_ZIMAGE_CHAT not set")
        return False

    handler = TypeHandler(Update, _chat_zimage_gate)

    # group=-50: after audit/logging (-100, -99) but before main handlers (0+)
    application.add_handler(handler, group=-50)

    logger.info(
        "CHAT_ZIMAGE_REGISTERED chat=%s resolved_username=%s model=%s "
        "concurrency=%d queue=%d aspect=%s timeout=%ds admin_ids=%s group=-50",
        CHAT_ZIMAGE_CHAT,
        _TARGET_USERNAME,
        CHAT_ZIMAGE_MODEL,
        CHAT_ZIMAGE_MAX_CONCURRENCY,
        CHAT_ZIMAGE_MAX_QUEUE,
        CHAT_ZIMAGE_ASPECT_RATIO,
        CHAT_ZIMAGE_TIMEOUT,
        CHAT_ZIMAGE_ADMIN_IDS or "none",
    )
    return True
