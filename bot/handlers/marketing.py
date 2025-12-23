"""
Marketing-focused handlers - полный UX flow для маркетологов.

Интеграция с DatabaseService для баланса и истории.
НЕ заменяет существующие handlers - работает параллельно.
"""
import logging
from decimal import Decimal
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.ui.marketing_menu import (
    MARKETING_CATEGORIES,
    build_ui_tree,
    get_category_info,
    get_model_by_id
)
from app.payments.pricing import calculate_user_price, format_price_rub

logger = logging.getLogger(__name__)

router = Router(name="marketing")


class MarketingStates(StatesGroup):
    """FSM states for marketing flow."""
    select_category = State()
    select_model = State()
    enter_prompt = State()
    confirm_price = State()


# Global database service (будет установлен в main_render.py)
_db_service = None


def set_database_service(db_service):
    """Set database service for handlers."""
    global _db_service
    _db_service = db_service


def _get_db_service():
    """Get database service or None if not available."""
    return _db_service


@router.message(Command("marketing"))
async def cmd_marketing(message: Message, state: FSMContext):
    """Marketing main menu."""
    await state.clear()
    
    text = (
        "🚀 <b>Маркетинговые инструменты</b>\n\n"
        "Выберите категорию креативов:"
    )
    
    keyboard = _build_marketing_menu()
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "marketing:main")
async def cb_marketing_main(callback: CallbackQuery, state: FSMContext):
    """Marketing main menu callback."""
    await state.clear()
    
    text = (
        "🚀 <b>Маркетинговые инструменты</b>\n\n"
        "Выберите категорию креативов:"
    )
    
    keyboard = _build_marketing_menu()
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


def _build_marketing_menu() -> InlineKeyboardMarkup:
    """Build marketing categories menu."""
    tree = build_ui_tree()
    rows = []
    
    for cat_key, cat_data in MARKETING_CATEGORIES.items():
        count = len(tree.get(cat_key, []))
        if count == 0:
            continue  # Skip empty categories
        
        emoji = cat_data.get("emoji", "")
        title = cat_data.get("title", "")
        button_text = f"{emoji} {title} ({count})"
        
        rows.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"mcat:{cat_key}"
            )
        ])
    
    # Additional buttons
    rows.append([
        InlineKeyboardButton(text="💳 Баланс", callback_data="balance:main"),
        InlineKeyboardButton(text="📜 История", callback_data="history:main")
    ])
    rows.append([
        InlineKeyboardButton(text="◀️ Главное меню", callback_data="main_menu")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("mcat:"))
async def cb_marketing_category(callback: CallbackQuery, state: FSMContext):
    """Show models in marketing category."""
    cat_key = callback.data.split(":", 1)[1]
    cat_info = get_category_info(cat_key)
    
    if not cat_info:
        await callback.answer("Категория не найдена", show_alert=True)
        return
    
    tree = build_ui_tree()
    models = tree.get(cat_key, [])
    
    if not models:
        await callback.answer("В этой категории пока нет доступных моделей", show_alert=True)
        return
    
    emoji = cat_info.get("emoji", "")
    title = cat_info.get("title", "")
    desc = cat_info.get("desc", "")
    
    text = (
        f"{emoji} <b>{title}</b>\n\n"
        f"{desc}\n\n"
        f"Доступно моделей: {len(models)}"
    )
    
    keyboard = _build_models_keyboard(cat_key, models)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


def _build_models_keyboard(cat_key: str, models: list) -> InlineKeyboardMarkup:
    """Build models selection keyboard."""
    rows = []
    
    for model in models[:10]:  # Limit to 10 for now
        model_id = model.get("model_id", "")
        name = model.get("name") or model_id
        
        # Get price
        price = model.get("price")
        if price:
            user_price = calculate_user_price(Decimal(str(price)))
            price_text = f" • {format_price_rub(user_price)}"
        else:
            price_text = ""
        
        button_text = f"{name}{price_text}"
        rows.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"mmodel:{model_id}"
            )
        ])
    
    if len(models) > 10:
        rows.append([
            InlineKeyboardButton(
                text=f"... ещё {len(models) - 10} моделей",
                callback_data=f"mcat_page:{cat_key}:1"
            )
        ])
    
    rows.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="marketing:main")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("mmodel:"))
async def cb_model_details(callback: CallbackQuery, state: FSMContext):
    """Show model details and start generation flow."""
    model_id = callback.data.split(":", 1)[1]
    model = get_model_by_id(model_id)
    
    if not model:
        await callback.answer("Модель не найдена", show_alert=True)
        return
    
    name = model.get("name") or model_id
    description = model.get("description", "Нет описания")
    category = model.get("category", "unknown")
    
    # Get price
    price = model.get("price")
    if price:
        user_price = calculate_user_price(Decimal(str(price)))
        price_text = format_price_rub(user_price)
    else:
        price_text = "Цена не определена"
    
    text = (
        f"<b>{name}</b>\n\n"
        f"{description}\n\n"
        f"💰 Стоимость: {price_text}\n"
        f"📂 Категория: {category}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🚀 Запустить генерацию",
            callback_data=f"mgen:start:{model_id}"
        )],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="marketing:main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("mgen:start:"))
async def cb_start_generation(callback: CallbackQuery, state: FSMContext):
    """Start generation flow - ask for prompt."""
    model_id = callback.data.split(":", 2)[2]
    model = get_model_by_id(model_id)
    
    if not model:
        await callback.answer("Модель не найдена", show_alert=True)
        return
    
    # Save model to state
    await state.update_data(model_id=model_id)
    await state.set_state(MarketingStates.enter_prompt)
    
    text = (
        f"<b>Генерация: {model.get('name', model_id)}</b>\n\n"
        f"Введите текст промпта для генерации:"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="marketing:main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.message(MarketingStates.enter_prompt)
async def process_prompt(message: Message, state: FSMContext):
    """Process user prompt and show price confirmation."""
    prompt = message.text.strip()
    
    if not prompt:
        await message.answer("❌ Промпт не может быть пустым. Попробуйте ещё раз:")
        return
    
    data = await state.get_data()
    model_id = data.get("model_id")
    model = get_model_by_id(model_id)
    
    if not model:
        await message.answer("❌ Ошибка: модель не найдена")
        await state.clear()
        return
    
    # Calculate price
    price = model.get("price")
    if not price:
        await message.answer("❌ Ошибка: цена модели не определена")
        await state.clear()
        return
    
    user_price = calculate_user_price(Decimal(str(price)))
    
    # Check balance
    db_service = _get_db_service()
    if db_service:
        from app.database.services import UserService, WalletService
        
        user_service = UserService(db_service)
        wallet_service = WalletService(db_service)
        
        # Ensure user exists
        await user_service.get_or_create(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name
        )
        
        # Get balance
        balance_data = await wallet_service.get_balance(message.from_user.id)
        balance = balance_data.get("balance_rub", Decimal("0.00"))
        
        balance_text = f"\n💰 Ваш баланс: {format_price_rub(balance)}"
        
        if balance < user_price:
            text = (
                f"❌ <b>Недостаточно средств</b>\n\n"
                f"Стоимость: {format_price_rub(user_price)}\n"
                f"Ваш баланс: {format_price_rub(balance)}\n\n"
                f"Необходимо пополнить баланс на {format_price_rub(user_price - balance)}"
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Пополнить", callback_data="balance:topup")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="marketing:main")]
            ])
            await message.answer(text, reply_markup=keyboard)
            await state.clear()
            return
    else:
        balance_text = ""
    
    # Save prompt and show confirmation
    await state.update_data(prompt=prompt, price=float(user_price))
    await state.set_state(MarketingStates.confirm_price)
    
    text = (
        f"<b>Подтверждение генерации</b>\n\n"
        f"Модель: {model.get('name', model_id)}\n"
        f"Промпт: {prompt}\n"
        f"Стоимость: {format_price_rub(user_price)}"
        f"{balance_text}\n\n"
        f"Подтвердите запуск генерации:"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="mgen:confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="marketing:main")]
    ])
    
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "mgen:confirm")
async def cb_confirm_generation(callback: CallbackQuery, state: FSMContext):
    """Confirm and start actual KIE generation with full database integration."""
    import uuid
    from datetime import datetime, timezone
    
    data = await state.get_data()
    model_id = data.get("model_id")
    prompt = data.get("prompt")
    price_float = data.get("price", 0.0)
    user_price = Decimal(str(price_float))
    
    await state.clear()
    
    db_service = _get_db_service()
    if not db_service:
        await callback.answer("⚠️ База данных недоступна", show_alert=True)
        return
    
    from app.database.services import UserService, WalletService, JobService
    from app.kie.generator import KieGenerator
    
    user_service = UserService(db_service)
    wallet_service = WalletService(db_service)
    job_service = JobService(db_service)
    
    user_id = callback.from_user.id
    job_id = str(uuid.uuid4())
    
    model = get_model_by_id(model_id)
    if not model:
        await callback.answer("❌ Модель не найдена", show_alert=True)
        return
    
    # Ensure user exists
    await user_service.get_or_create(
        user_id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    # Hold balance
    hold_ref = f"hold_{job_id}"
    hold_ok = await wallet_service.hold_balance(user_id, user_price, hold_ref)
    
    if not hold_ok:
        text = (
            f"❌ <b>Недостаточно средств</b>\n\n"
            f"Стоимость: {format_price_rub(user_price)}\n\n"
            f"Пополните баланс и попробуйте снова"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Пополнить", callback_data="balance:topup")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="marketing:main")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
        return
    
    # Create job
    job_params = {
        "prompt": prompt,
        "model_id": model_id
    }
    
    await job_service.create_job(
        job_id=job_id,
        user_id=user_id,
        model_id=model_id,
        params=job_params,
        price_rub=user_price
    )
    
    await job_service.update_status(job_id, "queued")
    
    # Update UI
    await callback.message.edit_text(
        f"🔄 <b>Генерация запущена</b>\n\n"
        f"Модель: {model.get('name', model_id)}\n"
        f"Промпт: {prompt}\n\n"
        f"⏳ Ожидаем результат..."
    )
    await callback.answer("Генерация запущена!")
    
    # Generate in background
    try:
        # Initialize KIE generator
        generator = KieGenerator()
        
        # Update status
        await job_service.update_status(job_id, "running")
        
        # Call KIE API
        result = await generator.generate(model_id, job_params)
        
        # Check result
        if result.get("status") == "succeeded":
            # Extract result URL or data
            output = result.get("output", {})
            file_url = output.get("file_url") or output.get("url")
            text_result = output.get("text")
            
            # Charge balance
            charge_ref = f"charge_{job_id}"
            await wallet_service.charge(user_id, user_price, charge_ref, hold_ref=hold_ref)
            
            # Update job
            await job_service.update_status(job_id, "succeeded")
            await job_service.update_result(job_id, result)
            
            # Send result to user
            result_text = (
                f"✅ <b>Генерация завершена!</b>\n\n"
                f"Модель: {model.get('name', model_id)}\n"
                f"Стоимость: {format_price_rub(user_price)}\n\n"
            )
            
            if text_result:
                result_text += f"<b>Результат:</b>\n{text_result}\n\n"
            
            if file_url:
                result_text += f"<b>Файл:</b> {file_url}\n\n"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎨 Новая генерация", callback_data="marketing:main")],
                [InlineKeyboardButton(text="💳 Баланс", callback_data="balance:main")]
            ])
            
            await callback.message.answer(result_text, reply_markup=keyboard)
        
        else:
            # Generation failed - refund
            error = result.get("error", "Неизвестная ошибка")
            
            refund_ref = f"refund_{job_id}"
            await wallet_service.refund(user_id, user_price, refund_ref, hold_ref=hold_ref)
            
            await job_service.update_status(job_id, "failed")
            await job_service.update_result(job_id, result)
            
            error_text = (
                f"❌ <b>Ошибка генерации</b>\n\n"
                f"Модель: {model.get('name', model_id)}\n"
                f"Ошибка: {error}\n\n"
                f"Средства возвращены на баланс: {format_price_rub(user_price)}"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data=f"mmodel:{model_id}")],
                [InlineKeyboardButton(text="◀️ В меню", callback_data="marketing:main")]
            ])
            
            await callback.message.answer(error_text, reply_markup=keyboard)
    
    except Exception as e:
        logger.exception(f"Generation error for job {job_id}")
        
        # Refund on exception
        refund_ref = f"refund_{job_id}"
        await wallet_service.refund(user_id, user_price, refund_ref, hold_ref=hold_ref)
        
        await job_service.update_status(job_id, "failed")
        
        error_text = (
            f"❌ <b>Произошла ошибка</b>\n\n"
            f"Не удалось выполнить генерацию.\n"
            f"Средства возвращены: {format_price_rub(user_price)}\n\n"
            f"Попробуйте позже или обратитесь в поддержку"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В меню", callback_data="marketing:main")]
        ])
        
        await callback.message.answer(error_text, reply_markup=keyboard)


# Export router
__all__ = ["router", "set_database_service"]
