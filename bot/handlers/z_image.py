"""
Z-Image handler for SINGLE_MODEL mode.

Provides simple flow:
1. User clicks "Создать картинку"
2. Bot asks for prompt
3. User sends prompt
4. Bot generates via Kie.ai z-image
5. Bot sends result
"""

import asyncio
import logging
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.kie.z_image_client import get_z_image_client, TaskStatus

logger = logging.getLogger(__name__)
router = Router(name="z_image")


class ZImageStates(StatesGroup):
    """States for z-image flow."""
    waiting_prompt = State()
    waiting_aspect_ratio = State()


ASPECT_RATIOS = {
    "1:1": "Квадрат 1:1",
    "16:9": "Широкий 16:9",
    "9:16": "Вертикальный 9:16",
    "4:3": "Классический 4:3",
    "3:4": "Портрет 3:4",
}


@router.callback_query(F.data == "zimage:start")
async def zimage_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Start z-image generation flow."""
    await callback.answer()
    await state.set_state(ZImageStates.waiting_prompt)
    
    await callback.message.edit_text(
        "🖼 <b>Z-Image Generator</b>\n\n"
        "📝 Опишите картинку, которую хотите создать:\n\n"
        "<i>Например:</i>\n"
        "• Кот-космонавт на луне\n"
        "• Закат над океаном в стиле импрессионизма\n"
        "• Футуристический город с летающими машинами\n\n"
        "💡 Чем подробнее описание, тем лучше результат!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
        ])
    )


@router.message(ZImageStates.waiting_prompt)
async def zimage_prompt(message: Message, state: FSMContext) -> None:
    """Handle prompt input."""
    prompt = message.text.strip()
    
    if not prompt or len(prompt) < 3:
        await message.answer(
            "❌ Описание слишком короткое. Попробуйте ещё раз:"
        )
        return
    
    # Store prompt
    await state.update_data(prompt=prompt)
    await state.set_state(ZImageStates.waiting_aspect_ratio)
    
    # Ask for aspect ratio
    keyboard = []
    for ratio, label in ASPECT_RATIOS.items():
        keyboard.append([InlineKeyboardButton(
            text=label, 
            callback_data=f"zimage:ratio:{ratio}"
        )])
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="zimage:start")])
    
    await message.answer(
        f"📐 <b>Выберите формат изображения:</b>\n\n"
        f"📝 Ваш запрос:\n<i>{prompt[:100]}</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )


@router.callback_query(F.data.startswith("zimage:ratio:"))
async def zimage_generate(callback: CallbackQuery, state: FSMContext) -> None:
    """Generate image with selected aspect ratio."""
    await callback.answer()
    
    ratio = callback.data.split(":", 2)[2]
    if ratio not in ASPECT_RATIOS:
        ratio = "1:1"
    
    # Get stored data
    data = await state.get_data()
    prompt = data.get("prompt", "")
    
    if not prompt:
        await callback.message.edit_text(
            "❌ Ошибка: промпт не найден. Начните заново:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🖼 Создать картинку", callback_data="zimage:start")]
            ])
        )
        await state.clear()
        return
    
    # Clear state (generation complete)
    await state.clear()
    
    # Show "generating" message
    status_msg = await callback.message.edit_text(
        f"⏳ <b>Генерирую изображение...</b>\n\n"
        f"📝 Запрос: <i>{prompt[:100]}</i>\n"
        f"📐 Формат: {ASPECT_RATIOS[ratio]}\n\n"
        f"⏱ Это займёт 10-30 секунд",
        reply_markup=None
    )
    
    # Get z-image client
    client = get_z_image_client()
    
    try:
        # Create task
        result = await client.create_task(
            prompt=prompt,
            aspect_ratio=ratio,
        )
        
        task_id = result.task_id
        
        # Update status
        await status_msg.edit_text(
            f"⏳ <b>Генерация запущена</b>\n\n"
            f"🆔 ID: <code>{task_id}</code>\n"
            f"📝 Запрос: <i>{prompt[:100]}</i>\n\n"
            f"⏱ Ожидайте результат...",
        )
        
        # Poll for completion (max 5 minutes)
        final_result = await client.poll_until_complete(
            task_id=task_id,
            max_wait=300.0,
            poll_interval=3.0,
        )
        
        # Check result
        if final_result.status == TaskStatus.SUCCESS and final_result.image_url:
            # Send image
            await callback.message.answer_photo(
                photo=final_result.image_url,
                caption=f"✅ <b>Готово!</b>\n\n"
                        f"📝 Запрос: <i>{prompt[:100]}</i>\n"
                        f"🆔 ID: <code>{task_id}</code>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🖼 Создать ещё", callback_data="zimage:start")],
                    [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
                ])
            )
            
            # Delete status message
            try:
                await status_msg.delete()
            except Exception:
                pass
        
        elif final_result.status == TaskStatus.FAILED:
            error_text = final_result.error or "Неизвестная ошибка"
            await status_msg.edit_text(
                f"❌ <b>Ошибка генерации</b>\n\n"
                f"🆔 ID: <code>{task_id}</code>\n"
                f"📝 Запрос: <i>{prompt[:100]}</i>\n\n"
                f"❗️ {error_text}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="zimage:start")],
                    [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
                ])
            )
        
        else:
            # Unknown status
            await status_msg.edit_text(
                f"⚠️ <b>Неожиданный статус</b>\n\n"
                f"🆔 ID: <code>{task_id}</code>\n"
                f"📊 Статус: {final_result.status.value}\n\n"
                f"Попробуйте снова или обратитесь в поддержку.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="zimage:start")],
                    [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
                ])
            )
    
    except asyncio.TimeoutError:
        await status_msg.edit_text(
            f"⏱ <b>Таймаут генерации</b>\n\n"
            f"📝 Запрос: <i>{prompt[:100]}</i>\n\n"
            f"Генерация заняла слишком много времени (>5 минут).\n"
            f"Попробуйте упростить запрос или попробуйте снова позже.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="zimage:start")],
                [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
            ])
        )
    
    except Exception as exc:
        logger.exception(f"[ZIMAGE] Generation failed: {exc}")
        
        await status_msg.edit_text(
            f"❌ <b>Ошибка</b>\n\n"
            f"📝 Запрос: <i>{prompt[:100]}</i>\n\n"
            f"Не удалось создать изображение: {str(exc)[:200]}\n\n"
            f"Попробуйте снова или обратитесь в поддержку.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="zimage:start")],
                [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
            ])
        )
