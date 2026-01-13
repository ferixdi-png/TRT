"""
Unified Delivery Coordinator
Platform-wide atomic delivery lock for ALL Kie.ai generation types.

Responsibilities:
1. Acquire atomic lock (try_acquire_delivery_lock)
2. Deliver media based on category (image/video/audio/upscale)
3. Mark delivered after successful send
4. Release lock on failure (allow retry)
5. Ensure exactly-once delivery under all race conditions:
   - callback + polling
   - Kie retry callbacks
   - deploy overlap (ACTIVE/PASSIVE)
   - transient Telegram failures
"""

import logging
from typing import Optional, Dict, Any, List
from aiogram import Bot
from aiogram.types import BufferedInputFile, FSInputFile
import aiohttp

logger = logging.getLogger(__name__)

# State normalization: treat these as SUCCESS
SUCCESS_STATES = {"success", "done", "completed"}
FAILURE_STATES = {"failed", "error", "fail", "canceled"}


def normalize_state(raw_state: str) -> str:
    """
    Normalize Kie.ai state variations to canonical form.
    
    Args:
        raw_state: Raw state from Kie API (success/done/completed/failed/etc.)
        
    Returns:
        'success', 'failed', 'running', or raw_state if unknown
    """
    lower = raw_state.lower()
    
    if lower in SUCCESS_STATES:
        return "success"
    elif lower in FAILURE_STATES:
        return "failed"
    elif lower in {"running", "pending", "waiting", "queued"}:
        return "running"
    else:
        return raw_state  # Unknown state, preserve original


async def deliver_result_atomic(
    storage,
    bot: Bot,
    task_id: str,
    chat_id: int,
    result_urls: List[str],
    category: str,
    corr_id: str = "",
    timeout_minutes: int = 5
) -> Dict[str, Any]:
    """
    Atomic delivery coordinator with exactly-once guarantee.
    
    This is the SINGLE delivery pipeline for ALL Kie.ai generation types.
    
    Args:
        storage: Storage instance with try_acquire_delivery_lock/mark_delivered
        bot: Aiogram Bot instance
        task_id: Kie.ai external_task_id
        chat_id: Telegram chat_id to send result to
        result_urls: List of result URLs from Kie.ai
        category: 'image', 'video', 'audio', 'upscale', etc.
        corr_id: Correlation ID for logging
        timeout_minutes: Stale lock timeout
        
    Returns:
        {
            'delivered': bool,          # True if this call delivered
            'already_delivered': bool,  # True if someone else already delivered
            'lock_acquired': bool,      # True if lock was won
            'error': Optional[str]      # Error message if delivery failed
        }
    """
    tag = f"[{corr_id}]" if corr_id else ""
    
    # STEP 1: Try to acquire atomic lock
    logger.info(f"{tag} [DELIVER_COORDINATOR] Attempting lock for task_id={task_id}")
    lock_job = await storage.try_acquire_delivery_lock(task_id, timeout_minutes=timeout_minutes)
    
    if not lock_job:
        # Someone else already delivered or is delivering
        logger.info(f"{tag} [DELIVER_LOCK_SKIP] Already delivered or delivering task_id={task_id}")
        return {
            'delivered': False,
            'already_delivered': True,
            'lock_acquired': False,
            'error': None
        }
    
    # STEP 2: Lock acquired - we are responsible for delivery
    logger.info(f"{tag} [DELIVER_LOCK_WIN] Won delivery race task_id={task_id} category={category}")
    
    if not result_urls:
        error_msg = "No result URLs to deliver"
        logger.error(f"{tag} [DELIVER_ERROR] {error_msg} task_id={task_id}")
        await storage.mark_delivered(task_id, success=False, error=error_msg)
        return {
            'delivered': False,
            'already_delivered': False,
            'lock_acquired': True,
            'error': error_msg
        }
    
    # STEP 3: Deliver media based on category
    try:
        url = result_urls[0]  # Primary result
        logger.info(f"{tag} [DELIVER_START] task_id={task_id} category={category} url={url[:80]}")
        
        if category in {"image", "text2image", "image2image", "upscale", "enhance"}:
            await _deliver_image(bot, chat_id, url, category, tag)
        elif category in {"video", "text2video", "image2video"}:
            await _deliver_video(bot, chat_id, url, tag)
        elif category in {"audio", "music", "text2audio", "text2music"}:
            await _deliver_audio(bot, chat_id, url, tag)
        else:
            # Unknown category - fallback to document
            logger.warning(f"{tag} [DELIVER_UNKNOWN_CATEGORY] category={category}, using document fallback")
            await _deliver_document(bot, chat_id, url, tag)
        
        # STEP 4: Mark delivered AFTER successful send
        logger.info(f"{tag} [DELIVER_OK] task_id={task_id} category={category}")
        await storage.mark_delivered(task_id, success=True)
        logger.info(f"{tag} [MARK_DELIVERED] task_id={task_id}")
        
        return {
            'delivered': True,
            'already_delivered': False,
            'lock_acquired': True,
            'error': None
        }
        
    except Exception as e:
        # STEP 5: On failure - release lock to allow retry
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.exception(f"{tag} [DELIVER_FAIL] task_id={task_id} {error_msg}")
        
        await storage.mark_delivered(task_id, success=False, error=error_msg)
        logger.info(f"{tag} [DELIVER_FAIL_RELEASED] Lock released for retry task_id={task_id}")
        
        return {
            'delivered': False,
            'already_delivered': False,
            'lock_acquired': True,
            'error': error_msg
        }


async def _deliver_image(bot: Bot, chat_id: int, url: str, category: str, tag: str):
    """Deliver image with 3-level fallback"""
    caption = "✅ Генерация завершена"
    if category in {"upscale", "enhance"}:
        caption = "✅ Улучшено"
    
    try:
        # Level 1: Direct URL (Telegram fetches)
        await bot.send_photo(chat_id, url, caption=caption)
        logger.info(f"{tag} [DELIVER_IMAGE_OK] method=direct_url")
    except Exception as e1:
        logger.warning(f"{tag} [DELIVER_IMAGE_FALLBACK_BYTES] direct_url failed: {e1}")
        try:
            # Level 2: Download bytes
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    resp.raise_for_status()
                    image_bytes = await resp.read()
            
            input_file = BufferedInputFile(image_bytes, filename="result.jpg")
            await bot.send_photo(chat_id, photo=input_file, caption=caption)
            logger.info(f"{tag} [DELIVER_IMAGE_OK] method=bytes")
        except Exception as e2:
            logger.warning(f"{tag} [DELIVER_IMAGE_FALLBACK_DOCUMENT] bytes failed: {e2}")
            # Level 3: Send as document
            await bot.send_document(chat_id, url, caption=f"{caption}\n\nURL: {url}")
            logger.info(f"{tag} [DELIVER_IMAGE_OK] method=document")


async def _deliver_video(bot: Bot, chat_id: int, url: str, tag: str):
    """Deliver video with fallback"""
    caption = "✅ Видео готово"
    
    try:
        await bot.send_video(chat_id, url, caption=caption)
        logger.info(f"{tag} [DELIVER_VIDEO_OK] method=direct_url")
    except Exception as e:
        logger.warning(f"{tag} [DELIVER_VIDEO_FALLBACK_DOCUMENT] {e}")
        await bot.send_document(chat_id, url, caption=f"{caption}\n\nURL: {url}")
        logger.info(f"{tag} [DELIVER_VIDEO_OK] method=document")


async def _deliver_audio(bot: Bot, chat_id: int, url: str, tag: str):
    """Deliver audio with fallback"""
    caption = "✅ Аудио готово"
    
    try:
        await bot.send_audio(chat_id, url, caption=caption)
        logger.info(f"{tag} [DELIVER_AUDIO_OK] method=direct_url")
    except Exception as e:
        logger.warning(f"{tag} [DELIVER_AUDIO_FALLBACK_DOCUMENT] {e}")
        await bot.send_document(chat_id, url, caption=f"{caption}\n\nURL: {url}")
        logger.info(f"{tag} [DELIVER_AUDIO_OK] method=document")


async def _deliver_document(bot: Bot, chat_id: int, url: str, tag: str):
    """Deliver as document (generic fallback)"""
    await bot.send_document(chat_id, url, caption="✅ Результат готов")
    logger.info(f"{tag} [DELIVER_DOCUMENT_OK]")
