"""
Quick actions for common use cases - Instagram, TikTok, YouTube, etc.
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
import json
from pathlib import Path

router = Router(name="quick_actions")

# Quick action workflows
QUICK_ACTIONS = {
    "instagram_post": {
        "name": "📸 Instagram пост",
        "description": "Создайте крутой пост для Instagram",
        "recommended_models": [
            {"id": "flux-2/flex-text-to-image", "price": 0.99, "reason": "Идеально для соцсетей"},
            {"id": "z-image", "price": 0.0, "reason": "Бесплатная альтернатива"},
        ],
        "prompt_examples": [
            "Неоновый постер в стиле киберпанк с надписью 'Future is Now'",
            "Минималистичный дизайн для Instagram, пастельные тона",
            "Яркий баннер для Instagram Stories, градиент от розового к фиолетовому"
        ]
    },
    "tiktok_video": {
        "name": "🎬 TikTok видео",
        "description": "Создайте вирусное видео для TikTok",
        "recommended_models": [
            {"id": "grok-imagine/text-to-video", "price": 7.90, "reason": "Лучшее качество"},
            {"id": "sora-2-text-to-video", "price": 9.88, "reason": "Премиум вариант"},
        ],
        "prompt_examples": [
            "Таймлапс восхода солнца над океаном, 5 секунд",
            "Динамичная анимация логотипа с эффектами, 3 секунды",
            "Трансформация дня в ночь над городом, 7 секунд"
        ]
    },
    "youtube_thumbnail": {
        "name": "🖼️ Превью для YouTube",
        "description": "Привлекающая внимание обложка",
        "recommended_models": [
            {"id": "flux-2/pro-text-to-image", "price": 1.98, "reason": "Высокое качество"},
            {"id": "flux-2/flex-text-to-image", "price": 0.99, "reason": "Баланс цены и качества"},
        ],
        "prompt_examples": [
            "Яркая обложка для YouTube про путешествия, вау-эффект",
            "Драматичный кадр для игрового видео на YouTube",
            "Превью для обучающего видео, профессиональный стиль"
        ]
    },
    "logo_design": {
        "name": "🎨 Логотип",
        "description": "Создайте логотип для бренда",
        "recommended_models": [
            {"id": "flux-2/flex-text-to-image", "price": 0.99, "reason": "Отлично для логотипов"},
            {"id": "z-image", "price": 0.0, "reason": "Бесплатная версия"},
        ],
        "prompt_examples": [
            "Минималистичный логотип для AI стартапа, векторный стиль",
            "Современный логотип для кофейни, теплые тона",
            "Технологичный логотип для IT компании, геометрия"
        ]
    },
    "reels_instagram": {
        "name": "📹 Instagram Reels",
        "description": "Короткое видео для Reels",
        "recommended_models": [
            {"id": "grok-imagine/text-to-video", "price": 7.90, "reason": "Идеально для Reels"},
            {"id": "hailuo/text-to-video", "price": 19.75, "reason": "Максимальное качество"},
        ],
        "prompt_examples": [
            "Плавная анимация продукта с вращением, 5 секунд",
            "Динамичный переход между сценами, music video стиль",
            "Таймлапс создания арт-работы, 7 секунд"
        ]
    }
}


@router.callback_query(F.data == "quick:menu")
async def show_quick_actions(callback: CallbackQuery, state: FSMContext):
    """Show quick actions menu"""
    await callback.answer()
    
    buttons = []
    for action_id, action in QUICK_ACTIONS.items():
        buttons.append([
            InlineKeyboardButton(
                text=action['name'],
                callback_data=f"quick:action:{action_id}"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text="◀️ В меню", callback_data="menu:main")])
    
    await callback.message.edit_text(
        "⚡ <b>Быстрые действия</b>\n\n"
        "Готовые сценарии для популярных задач:\n\n"
        "🎯 Выберите что хотите создать:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("quick:action:"))
async def show_action_details(callback: CallbackQuery, state: FSMContext):
    """Show quick action details with model recommendations"""
    await callback.answer()
    
    action_id = callback.data.split(":", 2)[2]
    action = QUICK_ACTIONS.get(action_id)
    
    if not action:
        await callback.message.answer("⚠️ Действие не найдено")
        return
    
    # Build recommendations text
    text = f"{action['name']}\n\n"
    text += f"<b>{action['description']}</b>\n\n"
    text += "<b>Рекомендуемые модели:</b>\n"
    
    for idx, model in enumerate(action['recommended_models'], 1):
        price_str = "FREE" if model['price'] == 0 else f"{model['price']:.2f}₽"
        text += f"{idx}. {model['id'].split('/')[-1]} ({price_str})\n"
        text += f"   <i>{model['reason']}</i>\n\n"
    
    text += "💡 Выберите модель или посмотрите примеры промптов"
    
    # Build buttons
    buttons = []
    for model in action['recommended_models']:
        model_name = model['id'].split('/')[-1].replace('-', ' ').title()
        price_str = "🆓" if model['price'] == 0 else f"{model['price']:.2f}₽"
        buttons.append([
            InlineKeyboardButton(
                text=f"{model_name} ({price_str})",
                callback_data=f"model:{model['id']}"
            )
        ])
    
    # Add examples button
    buttons.append([
        InlineKeyboardButton(
            text="💡 Примеры промптов",
            callback_data=f"quick:examples:{action_id}"
        )
    ])
    
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="quick:menu")
    ])
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("quick:examples:"))
async def show_action_examples(callback: CallbackQuery, state: FSMContext):
    """Show example prompts for quick action"""
    await callback.answer()
    
    action_id = callback.data.split(":", 2)[2]
    action = QUICK_ACTIONS.get(action_id)
    
    if not action:
        await callback.message.answer("⚠️ Действие не найдено")
        return
    
    # Build examples text
    text = f"💡 <b>Примеры промптов - {action['name']}</b>\n\n"
    
    for idx, example in enumerate(action['prompt_examples'], 1):
        text += f"{idx}. \"{example}\"\n\n"
    
    text += "Выберите пример чтобы использовать его!"
    
    # Build buttons - each example is clickable
    buttons = []
    for idx, example in enumerate(action['prompt_examples']):
        # Use first few words as button label
        label = ' '.join(example.split()[:4]) + "..."
        buttons.append([
            InlineKeyboardButton(
                text=f"✨ {label}",
                callback_data=f"quick:use:{action_id}:{idx}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data=f"quick:action:{action_id}")
    ])
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("quick:use:"))
async def use_quick_example(callback: CallbackQuery, state: FSMContext):
    """Use example prompt and pre-select model"""
    await callback.answer("Готовим генерацию!")
    
    parts = callback.data.split(":")
    action_id = parts[2]
    example_idx = int(parts[3])
    
    action = QUICK_ACTIONS.get(action_id)
    if not action or example_idx >= len(action['prompt_examples']):
        await callback.message.answer("⚠️ Пример не найден")
        return
    
    prompt = action['prompt_examples'][example_idx]
    recommended_model = action['recommended_models'][0]['id']  # Use best model
    
    # We keep only lightweight prefill data in state.
    await state.update_data(
        wizard_prefill={"prompt": prompt},
        wizard_prefill_force_prompt_edit=False,
    )
    
    # Show confirmation
    model_name = recommended_model.split('/')[-1].replace('-', ' ').title()
    price = action['recommended_models'][0]['price']
    price_str = "FREE" if price == 0 else f"{price:.2f}₽"
    
    await callback.message.edit_text(
        f"✨ <b>Готово к генерации!</b>\n\n"
        f"<b>Задача:</b> {action['name']}\n"
        f"<b>Модель:</b> {model_name}\n"
        f"<b>Цена:</b> {price_str}\n\n"
        f"<b>Промпт:</b>\n{prompt}\n\n"
        f"Начинаем?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, создать!", callback_data=f"quick:run:{action_id}:{example_idx}")],
            [InlineKeyboardButton(text="✏️ Изменить промпт", callback_data=f"quick:edit:{action_id}:{example_idx}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"quick:examples:{action_id}")]
        ])
    )


@router.callback_query(F.data.startswith("quick:run:"))
async def quick_run(callback: CallbackQuery, state: FSMContext):
    """Start wizard immediately with prefilled prompt."""
    await callback.answer()

    parts = callback.data.split(":")
    action_id = parts[2]
    example_idx = int(parts[3])

    action = QUICK_ACTIONS.get(action_id)
    if not action or example_idx >= len(action['prompt_examples']):
        await callback.message.answer("⚠️ Пример не найден")
        return

    prompt = action['prompt_examples'][example_idx]
    model_id = action['recommended_models'][0]['id']

    from app.ui.catalog import get_model
    from bot.flows.wizard import start_wizard

    model_config = get_model(model_id)
    if not model_config:
        await callback.message.answer("❌ Модель не найдена")
        return

    await state.update_data(
        wizard_prefill={"prompt": prompt},
        wizard_prefill_force_prompt_edit=False,
    )
    await start_wizard(callback.message, state, model_id, model_config)


@router.callback_query(F.data.startswith("quick:edit:"))
async def quick_edit(callback: CallbackQuery, state: FSMContext):
    """Start wizard with prompt prefilled but force prompt step for editing."""
    await callback.answer()

    parts = callback.data.split(":")
    action_id = parts[2]
    example_idx = int(parts[3])

    action = QUICK_ACTIONS.get(action_id)
    if not action or example_idx >= len(action['prompt_examples']):
        await callback.message.answer("⚠️ Пример не найден")
        return

    prompt = action['prompt_examples'][example_idx]
    model_id = action['recommended_models'][0]['id']

    from app.ui.catalog import get_model
    from bot.flows.wizard import start_wizard

    model_config = get_model(model_id)
    if not model_config:
        await callback.message.answer("❌ Модель не найдена")
        return

    await state.update_data(
        wizard_prefill={"prompt": prompt},
        wizard_prefill_force_prompt_edit=True,
    )
    await start_wizard(callback.message, state, model_id, model_config)


@router.callback_query(F.data == "quick:repeat_last")
async def cb_quick_repeat_last(callback: CallbackQuery, state: FSMContext):
    """Repeat last successful generation (Syntx UX)."""
    await callback.answer()
    try:
        from app.payments.charges import get_charge_manager
        from app.database.services import JobService
        cm = get_charge_manager()
        db = getattr(cm, "db_service", None) if cm else None
        if not db:
            await callback.answer("⚠️ База недоступна", show_alert=True)
            return

        jobs = await JobService(db).list_user_jobs(callback.from_user.id, limit=5)
        if not jobs:
            await callback.answer("История пока пустая 🙂", show_alert=True)
            return

        # Prefer last succeeded job
        job_id = None
        for j in jobs:
            if (j.get("status") or "").lower() == "succeeded":
                job_id = j.get("id")
                break
        if job_id is None:
            job_id = jobs[0].get("id")

        full = await JobService(db).get(int(job_id)) if job_id else None
        if not full:
            await callback.answer("Не нашёл последнюю задачу", show_alert=True)
            return

        model_id = str(full.get("model_id") or "")
        input_json = full.get("input_json") or {}
        if not model_id:
            await callback.answer("В истории нет модели", show_alert=True)
            return

        from app.ui.catalog import get_model
        from bot.flows.wizard import start_wizard

        model = get_model(model_id)
        if not model:
            await callback.answer("Модель больше недоступна", show_alert=True)
            return

        await state.update_data(wizard_prefill=input_json)
        await start_wizard(callback, state, model_config=model)

    except Exception as e:
        logger.error(f"repeat_last failed: {e}", exc_info=True)
        await callback.answer("Не получилось повторить. Попробуйте через историю.", show_alert=True)
