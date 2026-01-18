"""Universal Telegram sender for generation results."""
from __future__ import annotations

import logging
from typing import List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo

from app.kie_catalog import ModelSpec
from app.generations.universal_engine import JobResult

logger = logging.getLogger(__name__)


async def _send_media_group(bot, chat_id: int, media_type: str, urls: List[str]) -> None:
    if media_type == "image":
        media = [InputMediaPhoto(media=url) for url in urls]
        await bot.send_media_group(chat_id=chat_id, media=media)
    elif media_type == "video":
        media = [InputMediaVideo(media=url) for url in urls]
        await bot.send_media_group(chat_id=chat_id, media=media)
    else:
        for url in urls:
            await bot.send_document(chat_id=chat_id, document=url)


async def send_job_result(
    bot,
    chat_id: int,
    spec: ModelSpec,
    job_result: JobResult,
    *,
    price_rub: Optional[float] = None,
    elapsed: Optional[float] = None,
    user_lang: str = "ru",
) -> None:
    """Send generation output to Telegram based on media_type."""
    media_type = job_result.media_type
    urls = job_result.urls

    try:
        if media_type == "text":
            await bot.send_message(chat_id=chat_id, text=job_result.text or "")
        elif media_type == "image":
            if len(urls) > 1:
                await _send_media_group(bot, chat_id, media_type, urls)
            elif urls:
                await bot.send_photo(chat_id=chat_id, photo=urls[0])
        elif media_type == "video":
            if len(urls) > 1:
                await _send_media_group(bot, chat_id, media_type, urls)
            elif urls:
                await bot.send_video(chat_id=chat_id, video=urls[0])
        elif media_type in {"audio", "voice"}:
            if urls:
                if media_type == "voice":
                    await bot.send_voice(chat_id=chat_id, voice=urls[0])
                else:
                    await bot.send_audio(chat_id=chat_id, audio=urls[0])
        else:
            if urls:
                await bot.send_document(chat_id=chat_id, document=urls[0])
    except Exception as exc:
        logger.warning("Telegram media send failed, falling back to document: %s", exc)
        if urls:
            await bot.send_document(chat_id=chat_id, document=urls[0])

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
