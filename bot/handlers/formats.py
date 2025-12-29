"""Format-based navigation handlers."""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from app.ui.formats import FORMATS, get_model_format, group_models_by_format, get_popular_models, get_recommended_models
from app.ui.render import render_format_page, render_model_card
from app.kie.builder import load_source_of_truth
from app.payments.pricing import calculate_user_price, format_price_rub

logger = logging.getLogger(__name__)
router = Router(name="formats")


class TemplateFlow(StatesGroup):
    answering = State()


@router.callback_query(F.data == "menu:formats")
async def show_formats_menu(callback: CallbackQuery, state: FSMContext) -> None:
    """Show formats menu."""
    await callback.answer()
    
    # Load models
    sot_data = load_source_of_truth()
    models = sot_data.get("models", {})
    
    # Group by format
    grouped = group_models_by_format(models)
    
    text = (
        "🧩 <b>Форматы</b>\n\n"
        "Выберите, что хотите создать:\n\n"
        "👇 Нажмите на формат, чтобы увидеть доступные модели"
    )
    
    buttons = []

    def _ui_price_suffix(model_cfg: dict) -> str:
        """Menu price must reflect what user pays (MARKUP applied)."""
        base = (model_cfg or {}).get("pricing", {}).get("rub_per_use")
        if base is None:
            return ""
        try:
            user_price = calculate_user_price(float(base))
            return f" • {format_price_rub(user_price)}"
        except Exception:
            return ""
    
    def _fmt_label(fmt) -> str:
        parts = [p.strip() for p in (fmt.name or "").split("→")]
        if len(parts) == 2 and parts[0] and parts[1]:
            return f"{fmt.emoji} {parts[0]} → {parts[1]}"
        return f"{fmt.emoji} {fmt.name}"

    # Add format buttons (2 per row)
    row = []
    for format_key, format_obj in FORMATS.items():
        if format_key not in grouped or len(grouped[format_key]) == 0:
            continue  # Skip empty formats
        
        count = len(grouped[format_key])
        button = InlineKeyboardButton(
            text=f"{_fmt_label(format_obj)} ({count})",
            callback_data=f"format:{format_key}"
        )
        row.append(button)
        
        if len(row) == 2:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    # Navigation
    buttons.append([
        InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")
    ])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("format:"))
async def show_format_page(callback: CallbackQuery, state: FSMContext) -> None:
    """Show format page with models."""
    await callback.answer()
    
    # Supports `format:<key>` and `format:<key>:all`
    parts = callback.data.split(":")
    format_key = parts[1] if len(parts) > 1 else ""
    show_all = len(parts) > 2 and parts[2] == "all"
    
    if format_key not in FORMATS:
        await callback.answer("❌ Формат не найден", show_alert=True)
        return
    
    format_obj = FORMATS[format_key]
    
    # Load models
    sot_data = load_source_of_truth()
    models = sot_data.get("models", {})
    
    # Filter models by format
    format_models = []
    for model_id, model_config in models.items():
        if not model_config.get("enabled", True):
            continue
        
        model_format = get_model_format(model_config)
        if model_format and model_format.key == format_key:
            # Keep model_id for UI actions
            format_models.append((model_id, model_config))
    
    if not format_models:
        await callback.answer("❌ Нет доступных моделей", show_alert=True)
        return
    
    # Get recommended and popular
    recommended = get_recommended_models(models, format_key, limit=3)
    popular = get_popular_models(models, limit=8, format_key=format_key)
    
    # Render text
    text = render_format_page(
        format_name=format_obj.name,
        description=format_obj.description,
        input_desc=format_obj.input_desc,
        output_desc=format_obj.output_desc,
        model_count=len(format_models),
    )
    
    buttons = []

    def _ui_price_suffix(pricing: dict) -> str:
        """Price shown in menus should reflect what the user pays (MARKUP applied)."""
        if not pricing:
            return ""
        # Explicit FREE marker (used by free tier)
        if pricing.get("is_free"):
            return " • 🆓"
        base = pricing.get("rub_per_use")
        if base is None:
            return ""
        try:
            user_price = calculate_user_price(float(base))
            return f" • {format_price_rub(user_price)}"
        except Exception:
            # If something is weird in the pricing blob, don't crash UI
            return ""

    # If user asked for the full list in this format
    if show_all:
        # Header line (non-clickable)
        buttons.append([InlineKeyboardButton(text=f"📚 Все модели ({len(format_models)})", callback_data="noop")])

        # Sort for stable UX
        sorted_models = sorted(
            format_models,
            key=lambda x: (x[1].get("short_name") or x[1].get("display_name") or x[1].get("name") or x[0]).lower(),
        )

        for model_id, cfg in sorted_models:
            display_name = cfg.get("short_name", cfg.get("display_name", cfg.get("name", model_id)))
            pricing = cfg.get("pricing", {})
            buttons.append([
                InlineKeyboardButton(
                    text=f"{display_name}{_ui_price_suffix(pricing)}",
                    callback_data=f"model:{model_id}",
                )
            ])

        buttons.append([
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"format:{format_key}"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")
        ])

        await callback.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
        await callback.answer()
        return

    # Recommended section
    if recommended:
        buttons.append([InlineKeyboardButton(text="⭐ РЕКОМЕНДУЕМ", callback_data="noop")])
        for model in recommended[:3]:
            model_id = model.get("model_id", "")
            display_name = model.get("display_name", model_id)
            pricing = model.get("pricing", {})
            is_free = pricing.get("is_free", False)
            
            emoji = "🆓" if is_free else "💎"
            buttons.append([InlineKeyboardButton(
                text=f"{emoji} {display_name}{_ui_price_suffix(pricing)}",
                callback_data=f"model:{model_id}"
            )])
    
    # Popular section
    if popular:
        buttons.append([InlineKeyboardButton(text="🔥 ПОПУЛЯРНЫЕ", callback_data="noop")])
        for model in popular[:5]:
            model_id = model.get("model_id", "")
            display_name = model.get("display_name", model_id)
            pricing = model.get("pricing", {})
            # show end-user price (MARKUP applied)
            price_str = _ui_price_suffix(pricing)
            buttons.append([InlineKeyboardButton(
                text=f"{display_name}{price_str}",
                callback_data=f"model:{model_id}"
            )])
    
    # All models button
    buttons.append([InlineKeyboardButton(
        text=f"📚 Все модели ({len(format_models)})",
        callback_data=f"format:{format_key}:all"
    )])
    
    # Navigation
    buttons.append([
        InlineKeyboardButton(text="◀️ Форматы", callback_data="menu:formats"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main"),
    ])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("model:"))
async def show_model_card(callback: CallbackQuery, state: FSMContext, model_id: str = None) -> None:
    """Show model card."""
    await callback.answer()
    
    if model_id is None:
        model_id = callback.data.split(":", 1)[1]
    
    # Load models
    sot_data = load_source_of_truth()
    models = sot_data.get("models", {})
    
    if model_id not in models:
        await callback.answer("❌ Модель не найдена", show_alert=True)
        return
    
    model_config = models[model_id]
    
    # Render card
    text = render_model_card(model_config, show_advanced=False)
    
    # Buttons
    buttons = []
    
    # Main actions
    buttons.append([InlineKeyboardButton(
        text="🚀 Запустить",
        callback_data=f"launch:{model_id}"
    )])
    
    # Templates (if available for this format)
    from app.ui.templates import get_templates_for_format
    model_format = get_model_format(model_config)
    if model_format:
        templates = get_templates_for_format(model_format.key)
        if templates:
            buttons.append([InlineKeyboardButton(
                text=f"🧪 Шаблоны ({len(templates)})",
                callback_data=f"templates:{model_id}"
            )])
    
    # Info & Navigation
    buttons.append([
        InlineKeyboardButton(text="📖 Подробнее", callback_data=f"model:{model_id}:info"),
        InlineKeyboardButton(text="⭐ В избранное", callback_data=f"fav:add:{model_id}"),
    ])
    
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data=f"format:{model_format.key}" if model_format else "menu:formats"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main"),
    ])
    
    # Balance/Support row
    buttons.append([
        InlineKeyboardButton(text="💳 Баланс", callback_data="menu:balance"),
        InlineKeyboardButton(text="🆘 Поддержка", callback_data="menu:help"),
    ])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("launch:"))
async def launch_model(callback: CallbackQuery, state: FSMContext) -> None:
    """Launch model with wizard."""
    await callback.answer()
    
    model_id = callback.data.split(":", 1)[1]
    
    # Load model
    sot_data = load_source_of_truth()
    models = sot_data.get("models", {})
    
    if model_id not in models:
        await callback.answer("❌ Модель не найдена", show_alert=True)
        return
    
    model_config = models[model_id]
    
    # Start wizard
    from bot.flows.wizard import start_wizard
    await start_wizard(callback, state, model_config)


@router.callback_query(F.data.startswith("templates:"))
async def show_templates(callback: CallbackQuery, state: FSMContext) -> None:
    """Show templates for model."""
    await callback.answer()
    
    model_id = callback.data.split(":", 1)[1]
    
    # Load model
    sot_data = load_source_of_truth()
    models = sot_data.get("models", {})
    
    if model_id not in models:
        await callback.answer("❌ Модель не найдена", show_alert=True)
        return
    
    model_config = models[model_id]
    model_format = get_model_format(model_config)
    
    if not model_format:
        await callback.answer("❌ Нет шаблонов", show_alert=True)
        return
    
    from app.ui.templates import get_templates_for_format
    templates = get_templates_for_format(model_format.key)
    
    if not templates:
        await callback.answer("❌ Нет шаблонов для этого формата", show_alert=True)
        return
    
    display_name = model_config.get("display_name", model_id)
    
    text = (
        f"🧪 <b>Шаблоны для {display_name}</b>\n\n"
        "Готовые сценарии для маркетологов:\n\n"
        "👇 Выберите шаблон:"
    )
    
    buttons = []
    
    for template in templates:
        buttons.append([InlineKeyboardButton(
            text=template.name,
            callback_data=f"use_template:{model_id}:{template.id}"
        )])
    
    buttons.append([
        InlineKeyboardButton(text="◀️ К модели", callback_data=f"model:{model_id}"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main"),
    ])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("use_template:"))
async def use_template(callback: CallbackQuery, state: FSMContext) -> None:
    """Start template question flow and then launch wizard with a built prompt."""
    await callback.answer()

    # use_template:<model_id>:<template_id>
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("❌ Некорректный шаблон", show_alert=True)
        return
    model_id, template_id = parts[1], parts[2]

    sot_data = load_source_of_truth()
    models = sot_data.get("models", {})
    model_config = models.get(model_id)
    if not model_config:
        await callback.answer("❌ Модель не найдена", show_alert=True)
        return

    model_format = get_model_format(model_config)
    if not model_format:
        await callback.answer("❌ Формат не найден", show_alert=True)
        return

    from app.ui.templates import get_template
    template = get_template(template_id, model_format.key)
    if not template:
        await callback.answer("❌ Шаблон не найден", show_alert=True)
        return

    # Store flow context
    await state.set_state(TemplateFlow.answering)
    await state.update_data(
        tpl={
            "model_id": model_id,
            "format_key": model_format.key,
            "template_id": template_id,
            "q_index": 0,
            "answers": {},
        }
    )

    q = template.questions[0] if template.questions else None
    if not q:
        # No questions: immediately launch wizard with the built prompt
        prompt = template.build_prompt({})
        bot_msg = await callback.message.edit_text(
            "🚀 Запускаю шаблон…", parse_mode="HTML"
        )
        from bot.flows.wizard import start_wizard

        class _Dummy:
            def __init__(self, msg: Message):
                self.message = msg
            async def answer(self, *args, **kwargs):
                return None

        await state.clear()
        await start_wizard(_Dummy(bot_msg), state, model_config, prefill_prompt=prompt)
        return

    example = q.get("example")
    example_line = f"\n\n<i>Пример: {example}</i>" if example else ""
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="tpl:cancel")],
            [InlineKeyboardButton(text="◀️ К списку шаблонов", callback_data=f"templates:{model_id}")],
        ]
    )
    await callback.message.edit_text(
        f"🧪 <b>{template.name}</b>\n\n{q.get('text', 'Введите значение:')}{example_line}",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "tpl:cancel")
async def cancel_template_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    tpl = (data.get("tpl") or {})
    model_id = tpl.get("model_id")
    await state.clear()
    if model_id:
        await callback.message.edit_text(
            "Ок, шаблон отменён.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ К модели", callback_data=f"model:{model_id}")],
                    [InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")],
                ]
            ),
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            "Ок, шаблон отменён.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")]]
            ),
            parse_mode="HTML",
        )


@router.message(TemplateFlow.answering)
async def template_answer_msg(message: Message, state: FSMContext) -> None:
    """Collect template answers sequentially."""
    data = await state.get_data()
    tpl_state = (data.get("tpl") or {})
    model_id = tpl_state.get("model_id")
    format_key = tpl_state.get("format_key")
    template_id = tpl_state.get("template_id")
    q_index = int(tpl_state.get("q_index", 0) or 0)
    answers = dict(tpl_state.get("answers") or {})

    # Load model/template
    sot_data = load_source_of_truth()
    models = sot_data.get("models", {})
    model_config = models.get(model_id)
    if not model_config:
        await state.clear()
        await message.answer("⚠️ Модель не найдена. Нажмите /start")
        return

    from app.ui.templates import get_template
    template = get_template(template_id, format_key)
    if not template:
        await state.clear()
        await message.answer("⚠️ Шаблон не найден. Нажмите /start")
        return

    # Save answer
    text = (message.text or "").strip()
    if not text:
        await message.answer("Напишите ответ текстом 🙂")
        return

    # Current question key
    if template.questions and q_index < len(template.questions):
        key = template.questions[q_index].get("key") or f"q{q_index}"
        answers[key] = text
    q_index += 1

    # Next question
    if template.questions and q_index < len(template.questions):
        await state.update_data(tpl={**tpl_state, "q_index": q_index, "answers": answers})
        q = template.questions[q_index]
        example = q.get("example")
        example_line = f"\n\n<i>Пример: {example}</i>" if example else ""
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="tpl:cancel")],
                [InlineKeyboardButton(text="◀️ К списку шаблонов", callback_data=f"templates:{model_id}")],
            ]
        )
        await message.answer(
            f"🧪 <b>{template.name}</b>\n\n{q.get('text', 'Введите значение:')}{example_line}",
            reply_markup=kb,
            parse_mode="HTML",
        )
        return

    # Done: build prompt and launch wizard
    prompt = template.build_prompt(answers)

    # Create a bot message that wizard can safely edit
    bot_msg = await message.answer("🚀 Запускаю генерацию по шаблону…", parse_mode="HTML")

    from bot.flows.wizard import start_wizard

    class _Dummy:
        def __init__(self, msg: Message):
            self.message = msg
        async def answer(self, *args, **kwargs):
            return None

    await state.clear()
    await start_wizard(_Dummy(bot_msg), state, model_config, prefill_prompt=prompt)


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery) -> None:
    """No-op callback for section headers."""
    await callback.answer()
