"""
Primary UX flow: categories -> models -> inputs -> confirmation -> generation.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.kie.builder import load_source_of_truth
from app.kie.validator import validate_input_type, ModelContractError
from app.payments.charges import get_charge_manager
from app.payments.integration import generate_with_payment

router = Router(name="flow")


CATEGORY_LABELS = {
    "t2i": "🎨 Images",
    "i2i": "✏️ Edit",
    "t2v": "🎬 Video",
    "i2v": "🎬 Video",
    "v2v": "🎬 Video",
    "lip_sync": "🎬 Video",
    "music": "🎵 Audio",
    "sfx": "🎵 Audio",
    "tts": "🎵 Audio",
    "stt": "🎵 Audio",
    "audio_isolation": "🎵 Audio",
    "upscale": "✏️ Edit",
    "bg_remove": "✏️ Edit",
    "watermark_remove": "✏️ Edit",
    "general": "⭐ Top",
    "other": "⭐ Top",
}


def _source_of_truth() -> Dict[str, Any]:
    return load_source_of_truth()


def _models_by_category() -> Dict[str, List[Dict[str, Any]]]:
    models = _source_of_truth().get("models", [])
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for model in models:
        category = model.get("category", "other")
        grouped.setdefault(category, []).append(model)
    return grouped


def _category_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text="🎨 Images", callback_data="cat:t2i"),
        InlineKeyboardButton(text="🎬 Video", callback_data="cat:video"),
        InlineKeyboardButton(text="🎵 Audio", callback_data="cat:audio"),
        InlineKeyboardButton(text="✏️ Edit", callback_data="cat:edit"),
        InlineKeyboardButton(text="⭐ Top", callback_data="cat:top"),
        InlineKeyboardButton(text="💰 Balance", callback_data="balance"),
        InlineKeyboardButton(text="ℹ️ Support", callback_data="support"),
    ]
    rows = [[buttons[i]] for i in range(len(buttons))]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _model_keyboard(models: List[Dict[str, Any]], back_cb: str) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for model in models:
        model_id = model.get("model_id", "unknown")
        title = model.get("name") or model_id
        rows.append([InlineKeyboardButton(text=title, callback_data=f"model:{model_id}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _model_detail_text(model: Dict[str, Any]) -> str:
    name = model.get("name") or model.get("model_id")
    best_for = model.get("best_for") or model.get("description") or "Описание отсутствует"
    price = model.get("price") or "N/A"
    eta = model.get("eta") or "N/A"
    return (
        f"<b>{name}</b>\n\n"
        f"Best for: {best_for}\n"
        f"Цена: {price}\n"
        f"ETA: {eta}\n"
    )


def _model_detail_keyboard(model_id: str, back_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Сгенерировать", callback_data=f"gen:{model_id}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data=back_cb)],
        ]
    )


class InputFlow(StatesGroup):
    waiting_input = State()
    confirm = State()


@dataclass
class InputContext:
    model_id: str
    required_fields: List[str]
    properties: Dict[str, Any]
    collected: Dict[str, Any]
    index: int = 0


def _field_prompt(field_name: str, field_spec: Dict[str, Any]) -> str:
    field_type = field_spec.get("type", "string")
    enum = field_spec.get("enum")
    if enum:
        return f"Выберите значение для <b>{field_name}</b>:"
    if field_type in {"file", "file_id", "file_url"}:
        return f"Отправьте файл для <b>{field_name}</b>:"
    if field_type in {"url", "link", "source_url"}:
        return f"Отправьте ссылку для <b>{field_name}</b> (http/https):"
    return f"Введите значение для <b>{field_name}</b>:"


def _enum_keyboard(field_spec: Dict[str, Any]) -> Optional[InlineKeyboardMarkup]:
    enum = field_spec.get("enum")
    if not enum:
        return None
    rows = [[InlineKeyboardButton(text=str(val), callback_data=f"enum:{val}")] for val in enum]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "Выберите категорию:",
        reply_markup=_category_keyboard(),
    )


@router.callback_query(F.data == "main_menu")
async def main_menu_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        "📋 Главное меню\n\nВыберите категорию:",
        reply_markup=_category_keyboard(),
    )


@router.callback_query(F.data == "support")
async def support_cb(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text("ℹ️ Поддержка\n\nНапишите в поддержку, если нужна помощь.")


@router.callback_query(F.data == "balance")
async def balance_cb(callback: CallbackQuery) -> None:
    await callback.answer()
    balance = get_charge_manager().get_user_balance(callback.from_user.id)
    await callback.message.edit_text(f"💰 Баланс: {balance} кредитов")


@router.callback_query(F.data.startswith("cat:"))
async def category_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    category = callback.data.split(":", 1)[1]
    grouped = _models_by_category()

    if category == "video":
        models = grouped.get("t2v", []) + grouped.get("i2v", []) + grouped.get("v2v", []) + grouped.get("lip_sync", [])
    elif category == "audio":
        models = grouped.get("music", []) + grouped.get("sfx", []) + grouped.get("tts", []) + grouped.get("stt", []) + grouped.get("audio_isolation", [])
    elif category == "edit":
        models = grouped.get("i2i", []) + grouped.get("upscale", []) + grouped.get("bg_remove", []) + grouped.get("watermark_remove", [])
    elif category == "top":
        models = grouped.get("general", []) + grouped.get("other", [])
    else:
        models = grouped.get(category, [])

    if not models:
        await callback.message.edit_text("⚠️ В этой категории пока нет моделей.", reply_markup=_category_keyboard())
        return

    await state.update_data(category=category)
    await callback.message.edit_text(
        "Выберите модель:",
        reply_markup=_model_keyboard(models, "main_menu"),
    )


@router.callback_query(F.data.startswith("model:"))
async def model_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    model_id = callback.data.split(":", 1)[1]
    model = next((m for m in _source_of_truth().get("models", []) if m.get("model_id") == model_id), None)
    if not model:
        await callback.message.edit_text("⚠️ Модель не найдена.", reply_markup=_category_keyboard())
        return

    await state.update_data(model_id=model_id)
    await callback.message.edit_text(
        _model_detail_text(model),
        reply_markup=_model_detail_keyboard(model_id, "main_menu"),
    )


@router.callback_query(F.data.startswith("gen:"))
async def generate_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    model_id = callback.data.split(":", 1)[1]
    model = next((m for m in _source_of_truth().get("models", []) if m.get("model_id") == model_id), None)
    if not model:
        await callback.message.edit_text("⚠️ Модель не найдена.", reply_markup=_category_keyboard())
        return

    input_schema = model.get("input_schema", {})
    required_fields = input_schema.get("required", [])
    properties = input_schema.get("properties", {})
    ctx = InputContext(model_id=model_id, required_fields=required_fields, properties=properties, collected={})
    await state.update_data(flow_ctx=ctx.__dict__)

    if not required_fields:
        await _show_confirmation(callback.message, state, model)
        return

    field_name = required_fields[0]
    field_spec = properties.get(field_name, {})
    await state.set_state(InputFlow.waiting_input)
    await callback.message.answer(
        _field_prompt(field_name, field_spec),
        reply_markup=_enum_keyboard(field_spec),
    )


@router.callback_query(F.data.startswith("enum:"), InputFlow.waiting_input)
async def enum_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    value = callback.data.split(":", 1)[1]
    await _save_input_and_continue(callback.message, state, value)


@router.message(InputFlow.waiting_input)
async def input_message(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    flow_ctx = InputContext(**data.get("flow_ctx"))
    field_name = flow_ctx.required_fields[flow_ctx.index]
    field_spec = flow_ctx.properties.get(field_name, {})
    field_type = field_spec.get("type", "string")

    if field_type in {"file", "file_id", "file_url"}:
        file_id = None
        if message.photo:
            file_id = message.photo[-1].file_id
        elif message.document:
            file_id = message.document.file_id
        elif message.video:
            file_id = message.video.file_id
        elif message.audio:
            file_id = message.audio.file_id
        if not file_id:
            await message.answer("⚠️ Нужен файл. Отправьте фото/документ/видео/аудио.")
            return
        await _save_input_and_continue(message, state, file_id)
        return

    value = message.text
    if value is None:
        await message.answer("⚠️ Ожидается текстовое значение.")
        return
    await _save_input_and_continue(message, state, value)


async def _save_input_and_continue(message: Message, state: FSMContext, value: Any) -> None:
    data = await state.get_data()
    flow_ctx = InputContext(**data.get("flow_ctx"))
    field_name = flow_ctx.required_fields[flow_ctx.index]
    field_spec = flow_ctx.properties.get(field_name, {})
    field_type = field_spec.get("type", "string")

    try:
        validate_input_type(value, field_type, field_name)
    except ModelContractError as e:
        await message.answer(f"⚠️ {e}")
        return

    flow_ctx.collected[field_name] = value
    flow_ctx.index += 1
    await state.update_data(flow_ctx=flow_ctx.__dict__)

    if flow_ctx.index >= len(flow_ctx.required_fields):
        model = next((m for m in _source_of_truth().get("models", []) if m.get("model_id") == flow_ctx.model_id), None)
        await _show_confirmation(message, state, model)
        return

    next_field = flow_ctx.required_fields[flow_ctx.index]
    next_spec = flow_ctx.properties.get(next_field, {})
    await message.answer(
        _field_prompt(next_field, next_spec),
        reply_markup=_enum_keyboard(next_spec),
    )


async def _show_confirmation(message: Message, state: FSMContext, model: Optional[Dict[str, Any]]) -> None:
    if not model:
        await message.answer("⚠️ Модель не найдена.")
        return
    data = await state.get_data()
    flow_ctx = InputContext(**data.get("flow_ctx"))
    price = model.get("price") or "N/A"
    await state.set_state(InputFlow.confirm)
    await message.answer(
        f"{_model_detail_text(model)}\n"
        f"Параметры: {flow_ctx.collected}\n\n"
        f"Цена: {price}\n"
        "Подтвердить генерацию?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🚀 Подтвердить", callback_data="confirm")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
            ]
        ),
    )


@router.callback_query(F.data == "cancel", InputFlow.confirm)
async def cancel_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.edit_text("❌ Отменено. Возврат в меню.", reply_markup=_category_keyboard())


@router.callback_query(F.data == "confirm", InputFlow.confirm)
async def confirm_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    flow_ctx = InputContext(**data.get("flow_ctx"))
    model = next((m for m in _source_of_truth().get("models", []) if m.get("model_id") == flow_ctx.model_id), None)
    if not model:
        await callback.message.edit_text("⚠️ Модель не найдена.")
        await state.clear()
        return

    price_raw = model.get("price") or 0
    try:
        amount = float(price_raw)
    except (TypeError, ValueError):
        amount = 0.0

    await callback.message.edit_text("⏳ Генерация запущена. Пожалуйста, подождите...")

    def heartbeat(text: str) -> None:
        asyncio.create_task(callback.message.answer(text))

    result = await generate_with_payment(
        model_id=flow_ctx.model_id,
        user_inputs=flow_ctx.collected,
        user_id=callback.from_user.id,
        amount=amount,
        progress_callback=heartbeat,
    )

    await state.clear()

    if result.get("success"):
        urls = result.get("result_urls") or []
        if urls:
            await callback.message.answer("\n".join(urls))
        else:
            await callback.message.answer("✅ Готово!")
        await callback.message.answer(
            "Что дальше?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔁 Повторить", callback_data=f"gen:{flow_ctx.model_id}")],
                    [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")],
                ]
            ),
        )
    else:
        await callback.message.answer(result.get("message", "❌ Ошибка"))
        await callback.message.answer(
            "Попробовать ещё раз?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔁 Повторить", callback_data=f"gen:{flow_ctx.model_id}")],
                    [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")],
                ]
            ),
        )


@router.callback_query()
async def fallback_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer("⚠️ Кнопка устарела. Нажмите /start.")
