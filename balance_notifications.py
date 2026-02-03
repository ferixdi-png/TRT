"""
Модуль для уведомлений о списании баланса и обновлениях баланса.
"""

import logging
from typing import Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Курс конвертации RUB -> Stars
RUB_TO_STARS_RATE = 1.3

def _format_price(amount: float, lang: str) -> str:
    """Форматирует цену в зависимости от языка."""
    if lang == 'ru':
        return f"{amount:.2f} ₽"
    else:
        stars = max(1, int(amount / RUB_TO_STARS_RATE))
        return f"{stars} ⭐"


async def send_balance_deduction_notification(
    bot,
    chat_id: int,
    user_id: int,
    amount: float,
    model_name: str,
    remaining_balance: float,
    bonus_used: float = 0.0,
    lang: str = 'ru'
) -> Optional[Any]:
    """
    Отправляет уведомление о списании баланса.
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        user_id: ID пользователя
        amount: Сумма списания
        model_name: Название модели
        remaining_balance: Оставшийся баланс
        bonus_used: Использованные бонусы
        lang: Язык
    """
    try:
        if lang == 'ru':
            message_text = (
                f"💳 <b>Списание средств</b>\n\n"
                f"📊 <b>Модель:</b> {model_name}\n"
                f"💰 <b>Списано:</b> {amount:.2f} ₽\n"
            )
            
            if bonus_used > 0:
                message_text += f"🎁 <b>Использовано бонусов:</b> {bonus_used:.2f} ₽\n"
            
            message_text += (
                f"💵 <b>Остаток баланса:</b> {remaining_balance:.2f} ₽\n\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
        else:
            # EN: показываем в Stars
            message_text = (
                f"💳 <b>Balance Deduction</b>\n\n"
                f"📊 <b>Model:</b> {model_name}\n"
                f"💰 <b>Deducted:</b> {_format_price(amount, 'en')}\n"
            )
            
            if bonus_used > 0:
                message_text += f"🎁 <b>Bonuses used:</b> {_format_price(bonus_used, 'en')}\n"
            
            message_text += (
                f"💵 <b>Remaining balance:</b> {_format_price(remaining_balance, 'en')}\n\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
        
        return await bot.send_message(
            chat_id=chat_id,
            text=message_text,
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке уведомления о списании: {e}", exc_info=True)
        return None


async def send_insufficient_balance_message(
    bot,
    chat_id: int,
    required: float,
    current_balance: float,
    bonus_available: float = 0.0,
    lang: str = 'ru'
) -> Optional[Any]:
    """
    Отправляет сообщение о недостаточном балансе с рекомендациями.
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        required: Требуемая сумма
        current_balance: Текущий баланс
        bonus_available: Доступные бонусы
        lang: Язык
    """
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        needed = required - current_balance - bonus_available
        
        if lang == 'ru':
            message_text = (
                f"⚠️ <b>Недостаточно средств</b>\n\n"
                f"💰 <b>Требуется:</b> {required:.2f} ₽\n"
                f"💳 <b>Ваш баланс:</b> {current_balance:.2f} ₽\n"
            )
            
            if bonus_available > 0:
                message_text += f"🎁 <b>Доступно бонусов:</b> {bonus_available:.2f} ₽\n"
                if bonus_available >= needed:
                    message_text += f"✅ <b>Бонусов достаточно для оплаты!</b>\n"
                else:
                    message_text += f"❌ <b>Не хватает:</b> {needed:.2f} ₽\n"
            else:
                message_text += f"❌ <b>Не хватает:</b> {needed:.2f} ₽\n"
            
            message_text += (
                f"\n💡 <b>Рекомендации:</b>\n"
                f"• Пополните баланс через команду /balance\n"
                f"• Используйте промо-коды для получения бонусов\n"
                f"• Пригласите друга и получите 50 ₽ бонусов\n"
            )
            
            buttons = [
                [InlineKeyboardButton("💳 Пополнить баланс", callback_data="topup_balance")],
                [InlineKeyboardButton("🎁 Мои бонусы", callback_data="my_bonuses")],
                [InlineKeyboardButton("🎫 Промо-коды", callback_data="promo_codes")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
            ]
        else:
            # EN: показываем в Stars
            message_text = (
                f"⚠️ <b>Insufficient Funds</b>\n\n"
                f"💰 <b>Required:</b> {_format_price(required, 'en')}\n"
                f"💳 <b>Your balance:</b> {_format_price(current_balance, 'en')}\n"
            )
            
            if bonus_available > 0:
                message_text += f"🎁 <b>Available bonuses:</b> {_format_price(bonus_available, 'en')}\n"
                if bonus_available >= needed:
                    message_text += f"✅ <b>Bonuses are enough to pay!</b>\n"
                else:
                    message_text += f"❌ <b>Need:</b> {_format_price(needed, 'en')}\n"
            else:
                message_text += f"❌ <b>Need:</b> {_format_price(needed, 'en')}\n"
            
            message_text += (
                f"\n💡 <b>Recommendations:</b>\n"
                f"• Top up balance via /balance command\n"
                f"• Use promo codes to get bonuses\n"
                f"• Invite a friend and get 38 ⭐ bonus\n"
            )
            
            buttons = [
                [InlineKeyboardButton("💳 Top Up Balance", callback_data="topup_balance")],
                [InlineKeyboardButton("🎁 My Bonuses", callback_data="my_bonuses")],
                [InlineKeyboardButton("🎫 Promo Codes", callback_data="promo_codes")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_menu")]
            ]
        
        return await bot.send_message(
            chat_id=chat_id,
            text=message_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке сообщения о недостаточном балансе: {e}", exc_info=True)
        return None


async def send_balance_update(
    bot,
    chat_id: int,
    user_id: int,
    new_balance: float,
    bonus_balance: float = 0.0,
    lang: str = 'ru'
) -> Optional[Any]:
    """
    Отправляет обновление баланса после операции.
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        user_id: ID пользователя
        new_balance: Новый баланс
        bonus_balance: Бонусный баланс
        lang: Язык
    """
    try:
        if lang == 'ru':
            message_text = (
                f"💳 <b>Обновление баланса</b>\n\n"
                f"💰 <b>Ваш баланс:</b> {new_balance:.2f} ₽\n"
            )
            
            if bonus_balance > 0:
                message_text += f"🎁 <b>Бонусный баланс:</b> {bonus_balance:.2f} ₽\n"
            
            message_text += f"\n⏰ {datetime.now().strftime('%H:%M:%S')}"
        else:
            # EN: показываем в Stars
            message_text = (
                f"💳 <b>Balance Update</b>\n\n"
                f"💰 <b>Your balance:</b> {_format_price(new_balance, 'en')}\n"
            )
            
            if bonus_balance > 0:
                message_text += f"🎁 <b>Bonus balance:</b> {_format_price(bonus_balance, 'en')}\n"
            
            message_text += f"\n⏰ {datetime.now().strftime('%H:%M:%S')}"
        
        return await bot.send_message(
            chat_id=chat_id,
            text=message_text,
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке обновления баланса: {e}", exc_info=True)
        return None

