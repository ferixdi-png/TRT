"""Wizard flow for guided model input."""
import logging
import hmac
import hashlib
import os
import time
from typing import Dict, List, Optional, Any
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.ui.input_spec import get_input_spec, InputType
from bot.flows.wizard_presets import (
    get_presets_for_format,
    get_preset_by_id,
    detect_model_format,
)

logger = logging.getLogger(__name__)
router = Router(name="wizard")


async def _wizard_fail_and_return_to_menu(message: Message, state: FSMContext, reason: str) -> None:
    """Log wizard failure and safely return user to the main menu."""
    logger.error("Wizard fallback to menu: %s", reason)
    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="🏠 В меню", callback_data="menu:main"
    )]])

    try:
        await message.answer(
            "❌ Произошла ошибка в мастере. Возвращаю в меню.",
            reply_markup=kb,
            parse_mode="HTML",
        )
    except Exception:
        # If editing fails (deleted message), ignore.
        logger.exception("Failed to send wizard fallback message")


class WizardState(StatesGroup):
    """Wizard FSM states."""
    collecting_input = State()
    settings_input = State()
    confirming = State()


def _is_text2image_model_cfg(model_cfg: dict) -> bool:
    """Best-effort check for text-to-image family (wizard-side)."""
    try:
        ui = model_cfg.get("ui") if isinstance(model_cfg.get("ui"), dict) else {}
        fmt = (ui.get("format_group") or "").lower()
        if fmt in {"text2image", "text-to-image", "t2i"}:
            return True
        cat = (model_cfg.get("category") or "").lower()
        return cat in {"text-to-image", "t2i"}
    except Exception:
        return False


def _parse_t2i_settings(text: str) -> dict:
    """Parse lines like `aspect_ratio=16:9` into a dict.

    Allowed keys: aspect_ratio, num_images, seed
    """
    out = {}
    if not text:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k not in {"aspect_ratio", "num_images", "seed"}:
            continue
        if k == "aspect_ratio":
            # basic validation: 1:1, 16:9, 9:16, etc.
            if ":" not in v:
                continue
            a, b = v.split(":", 1)
            if not (a.isdigit() and b.isdigit()):
                continue
            out[k] = f"{int(a)}:{int(b)}"
        elif k == "num_images":
            if not v.isdigit():
                continue
            n = int(v)
            if not (1 <= n <= 4):
                continue
            out[k] = n
        elif k == "seed":
            try:
                out[k] = int(v)
            except Exception:
                continue
    return out


def _sign_file_id(file_id: str, exp: int) -> str:
    """Sign (file_id, exp) for secure media proxy.

    IMPORTANT: Must match app.webhook_server.media_proxy signature logic.
    """
    secret = os.getenv("MEDIA_PROXY_SECRET", "default_proxy_secret_change_me")
    payload = f"{file_id}:{exp}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return signature


def _get_public_base_url() -> str:
    """Get PUBLIC_BASE_URL for media proxy."""
    return os.getenv("PUBLIC_BASE_URL", os.getenv("WEBHOOK_BASE_URL", "https://unknown.render.com")).rstrip("/")


def _build_signed_media_url(file_id: str) -> str:
    """Create a signed media proxy URL with expiration."""
    base_url = _get_public_base_url()
    # Default TTL: 30 minutes (enough for Kie to fetch once, short enough for safety)
    exp = int(time.time()) + int(os.getenv("MEDIA_PROXY_TTL_SEC", "1800"))
    sig = _sign_file_id(file_id, exp)
    return f"{base_url}/media/telegram/{file_id}?sig={sig}&exp={exp}"


# Wizard start handler (callback: wizard:start:<model_id>)
@router.callback_query(F.data.startswith("wizard:start:"))
async def wizard_start_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Start wizard from callback."""
    model_id = callback.data.split(":", 2)[2]
    
    from app.ui.catalog import get_model
    model = get_model(model_id)
    
    if not model:
        await callback.answer("❌ Модель не найдена", show_alert=True)
        return
    
    await start_wizard(callback, state, model)


# Try example handler (callback: wizard:example:<model_id>)
@router.callback_query(F.data.startswith("wizard:example:"))
async def wizard_example_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Start wizard with example prompt filled in."""
    model_id = callback.data.split(":", 2)[2]
    
    from app.ui.catalog import get_model
    from app.ui.model_profile import build_profile
    
    model = get_model(model_id)
    if not model:
        await callback.answer("❌ Модель не найдена", show_alert=True)
        return
    
    profile = build_profile(model)
    example_prompt = None
    
    if profile.get('examples'):
        example_prompt = profile['examples'][0]  # Use first example
    
    # Start wizard with pre-filled example
    await start_wizard(callback, state, model, prefill_prompt=example_prompt)


async def start_wizard(
    callback: CallbackQuery,
    state: FSMContext,
    model_config: Dict[str, Any],
    prefill_prompt: Optional[str] = None,
) -> None:
    """
    Start wizard flow for model input.
    
    Args:
        callback: Callback query that triggered wizard
        model_config: Model configuration from KIE_SOURCE_OF_TRUTH
        prefill_prompt: Optional pre-filled prompt (for examples)
    """
    await callback.answer()
    
    model_id = model_config.get("model_id", "unknown")
    display_name = model_config.get("display_name", model_id)
    
    # Get input spec
    spec = get_input_spec(model_config)

    if not spec.fields:
        # No inputs needed, go straight to generation
        logger.info("Wizard checklist: no fields for model %s, auto-starting generation", model_id)
        await callback.message.edit_text(
            f"🚀 <b>{display_name}</b>\n\n"
            "Запускаю генерацию...",
            parse_mode="HTML"
        )
        
        # Save state and trigger generation
        await state.update_data(
            model_id=model_id,
            model_config=model_config,
            wizard_inputs={}
        )
        
        # Import and call generator
        from bot.handlers.flow import trigger_generation
        await trigger_generation(callback.message, state)
        return

    logger.info(
        "Wizard checklist: start for model %s with %d fields",
        model_id,
        len(spec.fields),
    )
    
    # Prefill if provided
    initial_inputs = {}
    if prefill_prompt and spec.fields:
        # Try to fill first text field with example
        for field in spec.fields:
            if field.type == InputType.TEXT and field.name in ["prompt", "text", "description"]:
                initial_inputs[field.name] = prefill_prompt
                break
    
    # Save wizard state
    await state.update_data(
        model_id=model_id,
        model_config=model_config,
        wizard_spec=spec,
        wizard_inputs=initial_inputs,
        wizard_current_field_index=0,
    )
    
    # UX: сразу запускаем сбор полей, чтобы пользователю не приходилось искать,
    # где вводить инпуты (он просто отвечает сообщениями/прикрепляет файлы).
    # При этом обзор остаётся доступен отдельной кнопкой "Подробнее" в карточке модели.
    await start_collecting_inputs(callback, state)


async def start_collecting_inputs(callback: CallbackQuery, state: FSMContext) -> None:
    """Переводит FSM в режим пошагового сбора параметров и показывает 1-е поле."""
    data = await state.get_data()
    spec = data.get("wizard_spec")

    # На всякий: если по какой-то причине спека нет — пробуем достроить по model_config.
    if spec is None:
        model_config = data.get("model_config")
        if model_config:
            try:
                spec = get_input_spec(model_config)
                await state.update_data(wizard_spec=spec)
            except Exception:
                spec = None

    if spec is None:
        await _wizard_fail_and_return_to_menu(callback.message, state, "wizard_spec missing in state")
        return

    # Если вообще нет полей — сразу в генерацию.
    if not spec or not getattr(spec, "fields", None):
        from bot.handlers.flow import trigger_generation
        await trigger_generation(callback.message, state)
        return

    # Инициализируем прогресс визарда.
    await state.set_state(WizardState.collecting_input)
    await state.update_data(wizard_current_field_index=0)

    # Если в state не было контейнера для значений — создаём.
    if not data.get("wizard_inputs"):
        await state.update_data(wizard_inputs={})

    # Показываем первое поле.
    if not spec.fields:
        await _wizard_fail_and_return_to_menu(callback.message, state, "wizard_spec has no fields after validation")
        return

    await show_field_input(callback.message, state, spec.fields[0])


async def show_wizard_overview(message: Message, state: FSMContext, spec, model_config: Dict) -> None:
    """
    Show wizard overview - what inputs will be collected.
    
    Args:
        message: Message to edit
        state: FSM state
        spec: InputSpec object
        model_config: Model configuration
    """
    from app.ui import tone_ru
    # Import from canonical module (deploys sometimes lacked the thin wrapper).
    from app.ui.model_profile import build_model_profile
    
    model_id = model_config.get("model_id", "unknown")
    display_name = model_config.get("display_name", model_id)
    profile = build_model_profile(model_config)
    
    # Build checklist of required inputs
    input_emojis = {
        InputType.TEXT: "✍️",
        InputType.IMAGE_URL: "🖼",
        InputType.IMAGE_FILE: "🖼",
        InputType.VIDEO_URL: "🎬",
        InputType.VIDEO_FILE: "🎬",
        InputType.AUDIO_URL: "🎙",
        InputType.AUDIO_FILE: "🎙",
        InputType.NUMBER: "🔢",
        InputType.ENUM: "📋",
        InputType.BOOLEAN: "✅",
    }
    
    text = tone_ru.WIZARD_OVERVIEW_TITLE.format(model_name=display_name)
    
    for idx, field in enumerate(spec.fields, 1):
        emoji = input_emojis.get(field.type, "📝")
        required_mark = "" if field.required else " (опционально)"
        text += f"\n{idx}. {emoji} <b>{field.description or field.name}</b>{required_mark}"

    # Absolute newbie-friendly hint: where to enter inputs
    text += (
        "\n\n💡 <b>Куда вводить?</b> Прямо в этот чат.\n"
        "Текст — просто напиши сообщением. Файл — прикрепи (📎).\n"
        "Я проведу по шагам, ничего лишнего."
    )
    
    # Show price info
    price_label = profile.get("price", {}).get("label", "—")
    text += f"\n\n💰 <b>Цена:</b> {price_label}"
    
    # Presets if available
    model_format = detect_model_format(model_config)
    presets = get_presets_for_format(model_format) if model_format else []
    
    text += "\n\n👇 Выберите действие:"
    
    # Build keyboard
    buttons = []
    
    # Presets button if available
    if presets:
        buttons.append([InlineKeyboardButton(
            text=tone_ru.WIZARD_PRESETS_BTN,
            callback_data=f"wizard:presets:{model_id}"
        )])
    
    # Start collecting
    buttons.append([InlineKeyboardButton(
        text=tone_ru.WIZARD_START_BTN,
        callback_data="wizard:start_collecting"
    )])
    
    # Navigation
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data=f"card:{model_id}"),
        InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
    ])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    try:
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "wizard:start_collecting")
async def wizard_start_collecting_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Start collecting inputs after overview."""
    await callback.answer()
    await start_collecting_inputs(callback, state)


@router.callback_query(F.data.startswith("wizard:presets:"))
async def wizard_show_presets(callback: CallbackQuery, state: FSMContext) -> None:
    """Show presets for model."""
    await callback.answer()
    
    model_id = callback.data.split(":", 2)[2]
    
    from app.ui.catalog import get_model
    model = get_model(model_id)
    
    if not model:
        await callback.message.edit_text("❌ Модель не найдена", parse_mode="HTML")
        return
    
    # Detect format
    model_format = detect_model_format(model)
    if not model_format:
        await callback.answer("Пресеты недоступны для этой модели", show_alert=True)
        return
    
    presets = get_presets_for_format(model_format)
    
    if not presets:
        await callback.answer("Пресеты не найдены", show_alert=True)
        return
    
    # Show presets
    text = (
        f"🔥 <b>Готовые пресеты</b>\n\n"
        f"Выберите шаблон для быстрого старта:"
    )
    
    buttons = []
    for preset in presets:
        buttons.append([InlineKeyboardButton(
            text=preset["name"],
            callback_data=f"wizard:use_preset:{preset['id']}"
        )])
    
    # Back
    buttons.append([InlineKeyboardButton(
        text="◀️ Назад",
        callback_data=f"wizard:start:{model_id}"
    )])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("wizard:use_preset:"))
async def wizard_use_preset(callback: CallbackQuery, state: FSMContext) -> None:
    """Use preset prompt."""
    await callback.answer()
    
    preset_id = callback.data.split(":", 2)[2]
    preset = get_preset_by_id(preset_id)
    
    if not preset:
        await callback.answer("❌ Пресет не найден", show_alert=True)
        return
    
    # Get wizard state
    data = await state.get_data()
    spec = data.get("wizard_spec")
    
    if not spec:
        await callback.message.edit_text("❌ Ошибка: спецификация не найдена", parse_mode="HTML")
        return
    
    # Fill first text field with preset prompt
    preset_prompt = preset.get("prompt", "")
    wizard_inputs = data.get("wizard_inputs", {})
    
    for field in spec.fields:
        if field.type == InputType.TEXT and field.name in ["prompt", "text", "description"]:
            wizard_inputs[field.name] = preset_prompt
            break
    
    await state.update_data(wizard_inputs=wizard_inputs)
    
    # Show confirmation
    await callback.message.edit_text(
        f"✅ Применён пресет:\n<b>{preset['name']}</b>\n\n"
        f"<i>{preset_prompt}</i>\n\n"
        f"Продолжаем сбор остальных параметров...",
        parse_mode="HTML"
    )
    
    # Continue with next field or confirmation
    current_idx = 0
    # Find first unfilled required field
    for idx, field in enumerate(spec.fields):
        if field.name not in wizard_inputs and field.required:
            current_idx = idx
            break
    
    if current_idx < len(spec.fields):
        await state.update_data(wizard_current_field_index=current_idx)
        await show_field_input(callback.message, state, spec.fields[current_idx])
    else:
        # All fields filled, show confirmation
        await wizard_show_confirmation(callback, state)


async def show_field_input(message: Message, state: FSMContext, field) -> None:
    """
    Show input prompt for a field.
    
    Args:
        message: Message to edit
        state: FSM state
        field: InputField object
    """
    data = await state.get_data()
    model_config = data.get("model_config", {})
    display_name = model_config.get("display_name", "Модель")
    spec = data.get("wizard_spec")
    current_idx = data.get("wizard_current_field_index", 0)
    
    # Calculate step number
    total_fields = len(spec.fields) if spec else 1
    step_num = current_idx + 1
    
    # Build field description
    if field is None:
        await _wizard_fail_and_return_to_menu(message, state, "field missing in show_field_input")
        return

    field_emoji = {
        InputType.TEXT: "✍️",
        InputType.IMAGE_URL: "🖼",
        InputType.IMAGE_FILE: "🖼",
        InputType.VIDEO_URL: "🎬",
        InputType.VIDEO_FILE: "🎬",
        InputType.AUDIO_URL: "🎙",
        InputType.AUDIO_FILE: "🎙",
        InputType.NUMBER: "🔢",
        InputType.ENUM: "📋",
        InputType.BOOLEAN: "✅",
    }.get(field.type, "📝")
    
    # Educational header
    text = (
        f"🧠 <b>{display_name}</b>  •  Шаг {step_num}/{total_fields}\n\n"
        f"{field_emoji} <b>{field.description or field.name}</b>\n\n"
    )

    # Show current text2image settings (if any)
    try:
        if _is_text2image_model_cfg(model_config):
            overrides = data.get("wizard_overrides", {}) or {}
            if overrides:
                # Keep it minimal
                parts = []
                for k in ("aspect_ratio", "num_images", "seed"):
                    if k in overrides:
                        parts.append(f"{k}={overrides[k]}")
                if parts:
                    text += f"⚙️ <b>Настройки:</b> <code>{' '.join(parts)}</code>\n\n"
    except Exception:
        pass
    
    if field.example:
        text += f"💡 <b>Пример:</b> <i>{field.example}</i>\n\n"
    
    if field.enum_values:
        text += "<b>Варианты:</b>\n"
        for val in field.enum_values:
            text += f"• {val}\n"
        text += "\n"
    
    if field.type == InputType.NUMBER:
        if field.min_value is not None and field.max_value is not None:
            text += f"📊 Диапазон: {field.min_value}–{field.max_value}\n\n"
        if field.default is not None:
            text += f"По умолчанию: {field.default}\n\n"
    
    # Format-specific hints (максимально простыми словами)
    if field.type in [InputType.IMAGE_FILE, InputType.VIDEO_FILE, InputType.AUDIO_FILE]:
        text += "📎 Прикрепи файл (скрепка) следующим сообщением\n\n"
    elif field.type in [InputType.IMAGE_URL, InputType.VIDEO_URL, InputType.AUDIO_URL]:
        text += "📎 Прикрепи файл (скрепка) ИЛИ отправь ссылку следующим сообщением\n\n"
    elif field.type == InputType.TEXT:
        text += "💬 Просто напиши текст следующим сообщением\n\n"
    
    text += "👇 Отправь ответ:"
    
    # Build keyboard
    buttons = []

    # Settings for text2image (no extra steps; just optional overrides)
    if _is_text2image_model_cfg(model_config) and field and getattr(field, "name", "") in {"prompt", "text"}:
        buttons.append([InlineKeyboardButton(text="⚙️ Настройки", callback_data="wizard:settings")])
    
    # Skip button for optional fields
    if not field.required:
        buttons.append([InlineKeyboardButton(text="⏭ Пропустить", callback_data="wizard:skip")])
    
    # Use default button if available
    if field.default is not None:
        buttons.append([InlineKeyboardButton(
            text=f"✨ Использовать по умолчанию ({field.default})",
            callback_data="wizard:use_default"
        )])
    
    # Navigation
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="wizard:back"),
        InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
    ])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    try:
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "wizard:skip", WizardState.collecting_input)
async def wizard_skip_field(callback: CallbackQuery, state: FSMContext) -> None:
    """Skip optional field."""
    await callback.answer()
    
    data = await state.get_data()
    spec = data.get("wizard_spec")
    current_index = data.get("wizard_current_field_index", 0)

    if not spec or not getattr(spec, "fields", None):
        await _wizard_fail_and_return_to_menu(callback.message, state, "wizard_spec missing during skip")
        return

    if current_index >= len(spec.fields):
        await _wizard_fail_and_return_to_menu(callback.message, state, "wizard_current_field_index out of range on skip")
        return
    
    current_field = spec.fields[current_index]
    
    if current_field.required:
        await callback.answer("❌ Это поле обязательно!", show_alert=True)
        return
    
    # Move to next field
    next_index = current_index + 1
    await state.update_data(wizard_current_field_index=next_index)
    
    if next_index >= len(spec.fields):
        await wizard_show_confirmation(callback, state)
    else:
        await show_field_input(callback.message, state, spec.fields[next_index])


@router.callback_query(F.data == "wizard:settings", WizardState.collecting_input)
async def wizard_open_settings(callback: CallbackQuery, state: FSMContext) -> None:
    """Open quick settings for text2image defaults."""
    await callback.answer()
    data = await state.get_data()
    model_config = data.get("model_config", {}) or {}
    if not _is_text2image_model_cfg(model_config):
        await callback.answer("⚙️ Настройки доступны только для text-to-image", show_alert=True)
        return

    overrides = data.get("wizard_overrides", {}) or {}
    current = "\n".join([f"{k}={overrides[k]}" for k in ("aspect_ratio", "num_images", "seed") if k in overrides])
    if not current:
        current = "(пока пусто)"

    text = (
        "⚙️ <b>Настройки генерации</b>\n\n"
        "Отправь одним сообщением строки формата <code>ключ=значение</code>:\n"
        "<code>aspect_ratio=16:9</code>\n"
        "<code>num_images=2</code>\n"
        "<code>seed=123</code>\n\n"
        f"Текущие: \n<code>{current}</code>\n\n"
        "Я применю их к текущей генерации (можно менять каждый раз)."
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="wizard:settings_back")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")],
    ])

    await state.set_state(WizardState.settings_input)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "wizard:settings_back", WizardState.settings_input)
async def wizard_settings_back(callback: CallbackQuery, state: FSMContext) -> None:
    """Return from settings to the current field prompt."""
    await callback.answer()
    data = await state.get_data()
    spec = data.get("wizard_spec")
    idx = data.get("wizard_current_field_index", 0)
    await state.set_state(WizardState.collecting_input)
    if not spec or not getattr(spec, "fields", None) or idx >= len(spec.fields):
        await _wizard_fail_and_return_to_menu(callback.message, state, "wizard_spec missing on settings_back")
        return
    await show_field_input(callback.message, state, spec.fields[idx])


@router.message(WizardState.settings_input)
async def wizard_settings_save(message: Message, state: FSMContext) -> None:
    """Parse and store text2image settings, then return to the current field."""
    data = await state.get_data()
    model_config = data.get("model_config", {}) or {}
    if not _is_text2image_model_cfg(model_config):
        await state.set_state(WizardState.collecting_input)
        await message.answer("⚠️ Настройки недоступны для этой модели")
        return

    parsed = _parse_t2i_settings(message.text or "")
    if not parsed:
        await message.answer(
            "❌ Не понял настройки. Пример:\n<code>aspect_ratio=16:9\nnum_images=2\nseed=123</code>",
            parse_mode="HTML",
        )
        return

    overrides = data.get("wizard_overrides", {}) or {}
    overrides.update(parsed)
    await state.update_data(wizard_overrides=overrides)

    # Return to current field
    spec = data.get("wizard_spec")
    idx = data.get("wizard_current_field_index", 0)
    await state.set_state(WizardState.collecting_input)
    if not spec or not getattr(spec, "fields", None) or idx >= len(spec.fields):
        await message.answer("✅ Настройки сохранены")
        return

    await message.answer("✅ Настройки применены")
    await show_field_input(message, state, spec.fields[idx])


@router.callback_query(F.data == "wizard:use_default", WizardState.collecting_input)
async def wizard_use_default(callback: CallbackQuery, state: FSMContext) -> None:
    """Use default value for field."""
    await callback.answer()
    
    data = await state.get_data()
    spec = data.get("wizard_spec")
    current_index = data.get("wizard_current_field_index", 0)
    inputs = data.get("wizard_inputs", {})

    if not spec or not getattr(spec, "fields", None):
        await _wizard_fail_and_return_to_menu(callback.message, state, "wizard_spec missing during use_default")
        return

    if current_index >= len(spec.fields):
        await _wizard_fail_and_return_to_menu(callback.message, state, "wizard_current_field_index out of range on use_default")
        return
    
    current_field = spec.fields[current_index]
    
    if current_field.default is None:
        await callback.answer("❌ Нет значения по умолчанию", show_alert=True)
        return
    
    # Save default value
    inputs[current_field.name] = current_field.default
    
    # Move to next field
    next_index = current_index + 1
    await state.update_data(
        wizard_inputs=inputs,
        wizard_current_field_index=next_index
    )
    
    if next_index >= len(spec.fields):
        await wizard_show_confirmation(callback, state)
    else:
        await show_field_input(callback.message, state, spec.fields[next_index])


@router.callback_query(F.data == "wizard:back", WizardState.collecting_input)
async def wizard_go_back(callback: CallbackQuery, state: FSMContext) -> None:
    """Go back to previous field."""
    await callback.answer()
    
    data = await state.get_data()
    current_index = data.get("wizard_current_field_index", 0)
    
    if current_index <= 0:
        # Go back to model card
        await state.clear()
        model_id = data.get("model_id")
        
        # Show model card again
        from bot.handlers.formats import show_model_card
        await show_model_card(callback, model_id)
        return

    # Go to previous field
    spec = data.get("wizard_spec")
    if not spec or not getattr(spec, "fields", None):
        await _wizard_fail_and_return_to_menu(callback.message, state, "wizard_spec missing during back navigation")
        return

    prev_index = current_index - 1
    if prev_index >= len(spec.fields):
        await _wizard_fail_and_return_to_menu(callback.message, state, "wizard_current_field_index out of range on back")
        return
    await state.update_data(wizard_current_field_index=prev_index)
    await show_field_input(callback.message, state, spec.fields[prev_index])


@router.message(WizardState.collecting_input)
async def wizard_process_input(message: Message, state: FSMContext) -> None:
    """Process user input for current field (text or file upload)."""
    data = await state.get_data()
    spec = data.get("wizard_spec")
    current_index = data.get("wizard_current_field_index", 0)
    inputs = data.get("wizard_inputs", {})

    if not spec or not getattr(spec, "fields", None):
        await _wizard_fail_and_return_to_menu(message, state, "wizard_spec missing during input")
        return

    if current_index >= len(spec.fields):
        await _wizard_fail_and_return_to_menu(message, state, "wizard_current_field_index out of range on input")
        return
    
    current_field = spec.fields[current_index]
    
    # Handle file uploads (IMAGE_FILE, VIDEO_FILE, AUDIO_FILE, IMAGE_URL, VIDEO_URL, AUDIO_URL)
    if current_field.type in (InputType.IMAGE_FILE, InputType.VIDEO_FILE, InputType.AUDIO_FILE, 
                              InputType.IMAGE_URL, InputType.VIDEO_URL, InputType.AUDIO_URL):
        file_id = None
        
        # Check for IMAGE
        if current_field.type in (InputType.IMAGE_FILE, InputType.IMAGE_URL):
            if message.photo:
                file_id = message.photo[-1].file_id
            elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
                file_id = message.document.file_id
        
        # Check for VIDEO
        elif current_field.type in (InputType.VIDEO_FILE, InputType.VIDEO_URL):
            if message.video:
                file_id = message.video.file_id
            elif message.document and message.document.mime_type and message.document.mime_type.startswith("video/"):
                file_id = message.document.file_id
        
        # Check for AUDIO
        elif current_field.type in (InputType.AUDIO_FILE, InputType.AUDIO_URL):
            if message.audio:
                file_id = message.audio.file_id
            elif message.voice:
                file_id = message.voice.file_id
            elif message.document and message.document.mime_type and message.document.mime_type.startswith("audio/"):
                file_id = message.document.file_id
        
        if file_id:
            # Generate signed URL for media proxy
            base_url = _get_public_base_url()
            if base_url and base_url != "https://unknown.render.com":
                media_url = _build_signed_media_url(file_id)
                
                # Save URL (will be passed to KIE API)
                inputs[current_field.name] = media_url
                
                # Acknowledge upload
                await message.answer(
                    f"✅ <b>Файл принят!</b>\n\n"
                    f"📎 {current_field.description or current_field.name}",
                    parse_mode="HTML"
                )
            else:
                # Fallback: no BASE_URL configured, ask for URL
                await message.answer(
                    f"⚠️ <b>Загрузка файлов недоступна</b>\n\n"
                    f"Пришлите прямую ссылку на {current_field.description or current_field.name}:",
                    parse_mode="HTML"
                )
                return
        elif message.text and message.text.startswith(("http://", "https://")):
            # User sent URL as text - accept it
            inputs[current_field.name] = message.text
            await message.answer(
                f"✅ <b>Ссылка принята!</b>\n\n"
                f"🔗 {current_field.description or current_field.name}",
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"❌ <b>Неверный формат</b>\n\n"
                f"Ожидается: файл ИЛИ ссылка\n\n"
                f"📎 Загрузите файл или отправьте http(s) URL",
                parse_mode="HTML"
            )
            return
    else:
        # Text/boolean/number input
        user_input = message.text

        if not user_input:
            await message.answer("❌ Пустой ввод. Попробуйте снова.", parse_mode="HTML")
            return

        # Validate input
        is_valid, error = current_field.validate(user_input)

        if not is_valid:
            await message.answer(
                f"❌ <b>Ошибка валидации:</b>\n{error}\n\n"
                "Попробуйте снова:",
                parse_mode="HTML"
            )
            return

        # Save normalized input for downstream payload
        inputs[current_field.name] = current_field.coerce(user_input)
    
    # Move to next field
    next_index = current_index + 1
    await state.update_data(
        wizard_inputs=inputs,
        wizard_current_field_index=next_index
    )
    
    if next_index >= len(spec.fields):
        await wizard_show_confirmation(message, state)
    else:
        await show_field_input(message, state, spec.fields[next_index])


async def wizard_show_confirmation(message_or_callback, state: FSMContext) -> None:
    """Show confirmation screen with summary."""
    data = await state.get_data()
    model_config = data.get("model_config", {})
    inputs = data.get("wizard_inputs", {})
    
    model_id = model_config.get("model_id", "unknown")
    display_name = model_config.get("display_name", model_id)
    
    # Get price
    pricing = model_config.get("pricing", {})
    price_rub = pricing.get("rub_per_use", 0)
    is_free = pricing.get("is_free", False)
    
    # Build summary
    text = (
        f"✅ <b>Подтверждение запуска</b>\n\n"
        f"🎯 <b>Модель:</b> {display_name}\n\n"
        f"<b>Параметры:</b>\n"
    )
    
    for field_name, value in inputs.items():
        text += f"• {field_name}: {value}\n"

    overrides = data.get("wizard_overrides", {}) or {}
    if overrides:
        # Keep only known keys for clarity
        parts = []
        for k in ("aspect_ratio", "num_images", "seed"):
            if k in overrides:
                parts.append(f"{k}={overrides[k]}")
        if parts:
            text += f"\n⚙️ Настройки: <code>{' '.join(parts)}</code>\n"
    
    text += "\n"
    
    if is_free:
        text += "🆓 <b>Бесплатно</b>\n\n"
    else:
        text += f"💰 <b>Стоимость:</b> {price_rub:.2f} ₽\n\n"
    
    text += "🚀 Всё готово к запуску!"
    
    buttons = [
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="wizard:confirm")],
        [InlineKeyboardButton(text="✏️ Изменить", callback_data="wizard:edit")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")],
    ]
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await state.set_state(WizardState.confirming)
    
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message_or_callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "wizard:confirm", WizardState.confirming)
async def wizard_confirm_and_generate(callback: CallbackQuery, state: FSMContext) -> None:
    """Confirm and start generation."""
    await callback.answer()
    
    data = await state.get_data()
    model_config = data.get("model_config", {})
    inputs = data.get("wizard_inputs", {})
    
    model_id = model_config.get("model_id", "unknown")
    display_name = model_config.get("display_name", model_id)
    
    # Show "starting..." message
    await callback.message.edit_text(
        f"🚀 <b>{display_name}</b>\n\n"
        "Запускаю генерацию...",
        parse_mode="HTML"
    )
    
    # Build payload from inputs
    payload = dict(inputs)  # Copy wizard inputs

    # Apply quick settings overrides (text-to-image defaults)
    overrides = data.get("wizard_overrides", {}) or {}
    if overrides:
        payload.update(overrides)
    
    # Add defaults from schema if missing
    schema = model_config.get("input_schema", {})
    properties = schema.get("properties", {})
    
    for field_name, field_spec in properties.items():
        if field_name not in payload and "default" in field_spec:
            payload[field_name] = field_spec["default"]
    
    # Save generation context
    await state.update_data(
        model_id=model_id,
        payload=payload,
        is_free_selected=False,  # Will be determined by pricing
    )
    
    # Clear wizard state
    await state.clear()
    
    # Trigger generation via payment integration
    # Note: payload arg kept for backward compat in integration.py
    from app.payments.integration import generate_with_payment
    from app.payments.charges import get_charge_manager
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    try:
        cm = get_charge_manager()
        
        result = await generate_with_payment(
            user_id=user_id,
            model_id=model_id,
            user_inputs=payload,
            amount=0.0,  # Will be calculated inside
            charge_manager=cm,
        )
        
        # Send result
        if result.get("success"):
            output_url = result.get("output_url")
            
            success_text = (
                f"✅ <b>Готово!</b>\n\n"
                f"🎨 Модель: {display_name}\n\n"
            )
            
            # Build result keyboard
            buttons = [
                [InlineKeyboardButton(text="🔁 Повторить", callback_data=f"launch:{model_id}")],
                [
                    InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
                    InlineKeyboardButton(text="💳 Баланс", callback_data="menu:balance"),
                ],
            ]
            kb = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            # Send text message
            await callback.message.answer(success_text, reply_markup=kb, parse_mode="HTML")
            
            # Send media result
            if output_url:
                output_type = model_config.get("output_type", "").lower()
                
                try:
                    if "video" in output_type:
                        await callback.message.answer_video(output_url)
                    elif "image" in output_type:
                        await callback.message.answer_photo(output_url)
                    elif "audio" in output_type:
                        await callback.message.answer_audio(output_url)
                    else:
                        await callback.message.answer(f"📎 Результат: {output_url}")
                except Exception as e:
                    logger.error(f"Failed to send media result: {e}")
                    await callback.message.answer(f"📎 Результат: {output_url}")
        else:
            # Error
            error_msg = result.get("error", "Неизвестная ошибка")
            error_code = result.get("error_code", "unknown")
            
            # Sanitize error message for user
            user_error = _sanitize_error_for_user(error_msg, error_code)
            
            error_text = (
                f"❌ <b>Ошибка генерации</b>\n\n"
                f"🎨 Модель: {display_name}\n\n"
                f"<b>Что произошло:</b>\n{user_error}\n\n"
                f"💡 Попробуйте изменить параметры и запустить снова"
            )
            
            buttons = [
                [InlineKeyboardButton(text="🔁 Повторить", callback_data=f"launch:{model_id}")],
                [
                    InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
                    InlineKeyboardButton(text="🆘 Поддержка", callback_data="menu:help"),
                ],
            ]
            kb = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            await callback.message.answer(error_text, reply_markup=kb, parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Generation failed: {e}", exc_info=True)
        
        error_text = (
            f"❌ <b>Ошибка генерации</b>\n\n"
            f"🎨 Модель: {display_name}\n\n"
            f"Произошла непредвиденная ошибка. Попробуйте ещё раз.\n\n"
            f"Если проблема повторяется, свяжитесь с поддержкой."
        )
        
        buttons = [
            [InlineKeyboardButton(text="🔁 Повторить", callback_data=f"launch:{model_id}")],
            [
                InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
                InlineKeyboardButton(text="🆘 Поддержка", callback_data="menu:help"),
            ],
        ]
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.answer(error_text, reply_markup=kb, parse_mode="HTML")


def _sanitize_error_for_user(error_msg: str, error_code: str) -> str:
    """
    Convert technical error to user-friendly message.
    
    Args:
        error_msg: Raw error message
        error_code: Error code
    
    Returns:
        User-friendly error message
    """
    error_lower = error_msg.lower()
    
    if "required" in error_lower or "field" in error_lower:
        return "Не хватает обязательного поля. Пожалуйста, заполните все данные."
    
    if "invalid" in error_lower or "validation" in error_lower:
        return "Некорректные данные. Проверьте введённые значения."
    
    if "timeout" in error_lower or "timed out" in error_lower:
        return "Превышено время ожидания. Попробуйте ещё раз."
    
    if "rate limit" in error_lower or "too many" in error_lower:
        return "Слишком много запросов. Подождите немного и попробуйте снова."
    
    if "balance" in error_lower or "insufficient" in error_lower:
        return "Недостаточно средств. Пополните баланс."
    
    # Generic fallback
    return "Произошла ошибка. Попробуйте изменить параметры или обратитесь в поддержку."


@router.callback_query(F.data == "wizard:edit", WizardState.confirming)
async def wizard_edit_inputs(callback: CallbackQuery, state: FSMContext) -> None:
    """Go back to edit inputs."""
    await callback.answer()
    
    data = await state.get_data()
    spec = data.get("wizard_spec")
    
    # Go back to first field
    await state.update_data(wizard_current_field_index=0)
    await state.set_state(WizardState.collecting_input)
    await show_field_input(callback.message, state, spec.fields[0])
