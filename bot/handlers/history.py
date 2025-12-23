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
    """Show generation history."""
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
        text += "<i>У вас пока нет генераций</i>"
    else:
        for job in jobs:
            job_id = job.get("id")
            model_id = job.get("model_id", "unknown")
            status = job.get("status", "unknown")
            price = job.get("price_rub", 0)
            created = job.get("created_at")
            
            # Status emoji
            status_emoji = {
                "draft": "📝",
                "await_confirm": "⏳",
                "queued": "⏱️",
                "running": "🔄",
                "succeeded": "✅",
                "failed": "❌",
                "refunded": "↩️",
                "cancelled": "🚫"
            }.get(status, "•")
            
            status_text = {
                "draft": "Черновик",
                "await_confirm": "Ожидает подтверждения",
                "queued": "В очереди",
                "running": "Выполняется",
                "succeeded": "Завершено",
                "failed": "Ошибка",
                "refunded": "Возвращено",
                "cancelled": "Отменено"
            }.get(status, status)
            
            # Format date
            date_str = created.strftime("%d.%m %H:%M") if created else "—"
            
            text += (
                f"\n{status_emoji} <b>{model_id}</b>\n"
                f"  Статус: {status_text}\n"
                f"  Стоимость: {format_price_rub(price)}\n"
                f"  Дата: {date_str}\n"
            )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 История транзакций", callback_data="history:transactions")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="balance:main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


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
