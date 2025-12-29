"""
History handlers - показ истории генераций и транзакций.
"""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.payments.pricing import format_price_rub

logger = logging.getLogger(__name__)

router = Router(name="history")


@router.callback_query(F.data == "menu:history")
async def cb_menu_history(callback: CallbackQuery, state: FSMContext):
    """Alias: menu:history -> history:main (no dead buttons)."""
    return await cb_history_main(callback, state)

# Global database service
_db_service = None


def set_database_service(db_service):
    """Set database service for handlers."""
    global _db_service
    _db_service = db_service


def _get_db_service():
    """Get database service or None."""
    return _db_service


@router.callback_query(F.data == "history:main")
async def cb_history_main(callback: CallbackQuery, state: FSMContext):
    """Show generation history with visual gallery."""
    await state.clear()
    
    db_service = _get_db_service()
    if not db_service:
        await callback.answer("⚠️ База данных недоступна", show_alert=True)
        return
    
    from app.database.services import JobService
    
    job_service = JobService(db_service)
    jobs = await job_service.list_user_jobs(callback.from_user.id, limit=10)
    
    text = "📜 <b>История генераций</b>\n\n"
    
    if not jobs:
        text += "<i>У вас пока нет генераций</i>\n\n"
        text += "💡 Попробуйте создать что-то в разделе ⚡ Быстрые действия!"
    else:
        # Count by status
        succeeded = sum(1 for j in jobs if j.get("status") == "succeeded")
        failed = sum(1 for j in jobs if j.get("status") == "failed")
        running = sum(1 for j in jobs if j.get("status") in ("running", "queued"))
        
        text += f"✅ Успешно: {succeeded} | ❌ Ошибки: {failed} | 🔄 В работе: {running}\n\n"
        
        # Show recent jobs with clickable details
        text += "<b>Последние генерации:</b>\n"
        for idx, job in enumerate(jobs[:5], 1):
            model_id = job.get("model_id", "unknown")
            status = job.get("status", "unknown")
            price = job.get("price_rub", 0)
            created = job.get("created_at")
            
            # Status emoji
            status_emoji = {
                "succeeded": "✅",
                "failed": "❌",
                "running": "🔄",
                "queued": "⏱️",
            }.get(status, "•")
            
            # Format date
            date_str = created.strftime("%d.%m %H:%M") if created else "—"
            
            # Short model name
            model_name = model_id.split('/')[-1] if '/' in model_id else model_id
            
            text += f"\n{idx}. {status_emoji} {model_name} ({format_price_rub(price)}) - {date_str}"
    
    # Build keyboard with quick job access
    keyboard_rows = []

    # Add buttons for the most recent jobs (fast rerun path)
    if jobs:
        for idx, job in enumerate(jobs[:5], 1):
            job_id = job.get("id")
            model_id = job.get("model_id", "unknown")
            status = job.get("status", "unknown")

            status_emoji = {
                "succeeded": "✅",
                "failed": "❌",
                "running": "🔄",
                "queued": "⏱️",
            }.get(status, "•")

            model_name = model_id.split('/')[-1] if '/' in model_id else model_id
            keyboard_rows.append([
                InlineKeyboardButton(
                    text=f"{status_emoji} {idx}. {model_name}",
                    callback_data=f"history:job:{job_id}",
                )
            ])
    
    if jobs and any(j.get("status") == "succeeded" for j in jobs):
        keyboard_rows.append([
            InlineKeyboardButton(text="🖼️ Просмотр галереи", callback_data="history:gallery")
        ])
    
    keyboard_rows.append([
        InlineKeyboardButton(text="📊 История транзакций", callback_data="history:transactions")
    ])
    keyboard_rows.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="balance:main")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("history:job:"))
async def cb_history_job_details(callback: CallbackQuery, state: FSMContext):
    """Show details for a specific job with rerun action."""
    await callback.answer()

    db_service = _get_db_service()
    if not db_service:
        await callback.answer("⚠️ База данных недоступна", show_alert=True)
        return

    from app.database.services import JobService

    try:
        job_id = int(callback.data.split(":", 2)[2])
    except Exception:
        await callback.answer("⚠️ Неверный идентификатор", show_alert=True)
        return

    job_service = JobService(db_service)
    job = await job_service.get(job_id)
    if not job or job.get("user_id") != callback.from_user.id:
        await callback.answer("⚠️ Генерация не найдена", show_alert=True)
        return

    model_id = job.get("model_id", "unknown")
    status = job.get("status", "unknown")
    price = job.get("price_rub", 0)
    created = job.get("created_at")

    status_emoji = {
        "succeeded": "✅",
        "failed": "❌",
        "running": "🔄",
        "queued": "⏱️",
        "draft": "📝",
    }.get(status, "•")

    date_str = created.strftime("%d.%m.%Y %H:%M") if created else "—"
    model_name = model_id.split('/')[-1] if '/' in model_id else model_id

    text = (
        f"🧾 <b>Детали генерации</b>\n\n"
        f"{status_emoji} <b>{model_name}</b>\n"
        f"💰 {format_price_rub(price)}\n"
        f"📅 {date_str}\n\n"
    )

    # Show result urls if any
    result_json = job.get("result_json") or {}
    urls = []
    if isinstance(result_json, dict):
        urls = result_json.get("result_urls") or result_json.get("resultUrls") or []
    if urls:
        text += "<b>Результаты:</b>\n"
        for u in urls[:5]:
            text += f"• {u}\n"
        if len(urls) > 5:
            text += f"… и ещё {len(urls) - 5}\n"
        text += "\n"

    # Error if failed
    if status == "failed":
        err = job.get("error_text")
        if err:
            text += f"<b>Ошибка:</b>\n<i>{err}</i>\n\n"

    # Persist last job id in state for rerun
    await state.update_data(history_last_job_id=job_id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Повторить с теми же параметрами", callback_data="history:rerun")],
        [InlineKeyboardButton(text="⭐ В избранные модели", callback_data=f"fav:add:{model_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="history:main")],
    ])

    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "history:rerun")
async def cb_history_rerun(callback: CallbackQuery, state: FSMContext):
    """Start wizard for the last opened job, prefilled, then show confirmation."""
    await callback.answer()

    db_service = _get_db_service()
    if not db_service:
        await callback.answer("⚠️ База данных недоступна", show_alert=True)
        return

    data = await state.get_data()
    job_id = data.get("history_last_job_id")
    if not job_id:
        await callback.answer("⚠️ Сначала откройте генерацию из истории", show_alert=True)
        return

    from app.database.services import JobService
    from app.ui.catalog import get_model
    from app.ui.input_spec import get_input_spec
    from bot.flows.wizard import WizardState, wizard_show_confirmation

    job_service = JobService(db_service)
    job = await job_service.get(int(job_id))
    if not job or job.get("user_id") != callback.from_user.id:
        await callback.answer("⚠️ Генерация не найдена", show_alert=True)
        return

    model_id = job.get("model_id", "unknown")
    model_cfg = get_model(model_id)
    if not model_cfg:
        await callback.answer("⚠️ Модель недоступна", show_alert=True)
        return

    spec = get_input_spec(model_cfg)
    inputs = job.get("input_json") or {}
    if not isinstance(inputs, dict):
        inputs = {}

    # Prepare wizard state (no dead-end: user can confirm or edit)
    await state.clear()
    await state.set_state(WizardState.confirming)
    await state.update_data(
        model_config=model_cfg,
        wizard_spec=spec,
        wizard_inputs=inputs,
        wizard_current_field_index=0,
    )

    await wizard_show_confirmation(callback, state)


@router.callback_query(F.data == "history:gallery")
async def cb_history_gallery(callback: CallbackQuery, state: FSMContext):
    """Show visual gallery of successful generations."""
    await callback.answer()
    
    db_service = _get_db_service()
    if not db_service:
        await callback.answer("⚠️ База данных недоступна", show_alert=True)
        return
    
    from app.database.services import JobService
    
    job_service = JobService(db_service)
    jobs = await job_service.list_user_jobs(callback.from_user.id, limit=20)
    
    # Filter only succeeded jobs
    succeeded_jobs = [j for j in jobs if j.get("status") == "succeeded"]
    
    if not succeeded_jobs:
        await callback.message.edit_text(
            "🖼️ <b>Галерея генераций</b>\n\n"
            "<i>У вас пока нет завершённых генераций</i>\n\n"
            "💡 Создайте что-то крутое через ⚡ Быстрые действия!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="history:main")]
            ])
        )
        return
    
    # Build gallery text
    text = "🖼️ <b>Галерея ваших генераций</b>\n\n"
    text += f"Всего успешных работ: {len(succeeded_jobs)}\n\n"
    
    # Show up to 5 recent succeeded jobs with details
    for idx, job in enumerate(succeeded_jobs[:5], 1):
        job_id = job.get("id")
        model_id = job.get("model_id", "unknown")
        price = job.get("price_rub", 0)
        created = job.get("created_at")
        
        model_name = model_id.split('/')[-1] if '/' in model_id else model_id
        date_str = created.strftime("%d.%m.%Y %H:%M") if created else "—"
        
        text += (
            f"{idx}. <b>{model_name}</b>\n"
            f"   💰 {format_price_rub(price)} | 📅 {date_str}\n\n"
        )
    
    if len(succeeded_jobs) > 5:
        text += f"<i>...и ещё {len(succeeded_jobs) - 5} работ</i>\n"
    
    # Buttons to navigate
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Создать ещё", callback_data="quick:menu")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="history:main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "history:transactions")
async def cb_history_transactions(callback: CallbackQuery, state: FSMContext):
    """Show transaction history."""
    db_service = _get_db_service()
    if not db_service:
        await callback.answer("⚠️ База данных недоступна", show_alert=True)
        return
    
    from app.database.services import WalletService
    from decimal import Decimal
    
    wallet_service = WalletService(db_service)
    history = await wallet_service.get_history(callback.from_user.id, limit=20)
    
    text = "📊 <b>История транзакций</b>\n\n"
    
    if not history:
        text += "<i>У вас пока нет транзакций</i>"
    else:
        for entry in history:
            kind = entry.get("kind", "")
            amount = entry.get("amount_rub", Decimal("0.00"))
            created = entry.get("created_at")
            ref = entry.get("ref", "")
            
            # Format kind
            kind_emoji = {
                "topup": "💵",
                "charge": "💸",
                "refund": "↩️",
                "hold": "🔒",
                "release": "🔓"
            }.get(kind, "•")
            
            kind_text = {
                "topup": "Пополнение",
                "charge": "Списание",
                "refund": "Возврат",
                "hold": "Резерв",
                "release": "Освобождение"
            }.get(kind, kind)
            
            # Format date
            date_str = created.strftime("%d.%m %H:%M") if created else "—"
            
            text += (
                f"\n{kind_emoji} {kind_text}: {format_price_rub(amount)}\n"
                f"  Дата: {date_str}\n"
            )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к генерациям", callback_data="history:main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


# Export router
__all__ = ["router", "set_database_service"]
