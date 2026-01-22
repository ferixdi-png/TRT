"""
Модуль для пошагового подтверждения стоимости перед генерацией.
"""

import logging
from typing import Dict, Any, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def show_price_confirmation(
    bot,
    chat_id: int,
    model_id: str,
    model_name: str,
    params: Dict[str, Any],
    price: float,
    user_id: int,
    lang: str = 'ru',
    is_free: bool = False,
    bonus_available: float = 0.0,
    discount: Optional[float] = None
) -> Optional[Any]:
    """
    Показывает финальное подтверждение с детализацией цены.
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        model_id: ID модели
        model_name: Название модели
        params: Параметры генерации
        price: Итоговая цена
        user_id: ID пользователя
        lang: Язык
        is_free: Бесплатная ли генерация
        bonus_available: Доступные бонусы
        discount: Размер скидки (0.0-1.0)
    
    Returns:
        Сообщение бота или None
    """
    try:
        from bonus_system import get_user_bonuses
        
        price_info = {
            "total_price": price,
            "currency": "RUB",
        }
        
        # Применяем скидку, если есть
        final_price = price
        if discount:
            final_price = price * (1 - discount)
            price_info['discount'] = discount
            price_info['discount_amount'] = price * discount
            price_info['total_price'] = final_price
        
        # Применяем бонусы, если доступны
        if bonus_available > 0 and not is_free:
            if bonus_available >= final_price:
                final_price = 0.0
                price_info['bonus_used'] = final_price
                price_info['bonus_remaining'] = bonus_available - final_price
            else:
                final_price = final_price - bonus_available
                price_info['bonus_used'] = bonus_available
                price_info['bonus_remaining'] = 0.0
            price_info['total_price'] = final_price
        
        if is_free:
            final_price = 0.0
            price_info['total_price'] = 0.0
        
        # Форматируем параметры для отображения
        params_text = ""
        for param_name, param_value in params.items():
            if param_name != 'prompt':  # Промпт показываем отдельно
                params_text += f"  • <b>{param_name}:</b> {param_value}\n"
        
        prompt = params.get('prompt', '')
        
        if lang == 'ru':
            # Получаем тип результата
            result_type_emoji = "📄"  # по умолчанию текст
            result_type_name = "текст"
            if 'image' in model_id.lower() or 'foto' in model_id.lower():
                result_type_emoji = "📷"
                result_type_name = "фото/изображение"
            elif 'video' in model_id.lower():
                result_type_emoji = "🎥"
                result_type_name = "видео"
            elif 'audio' in model_id.lower() or 'voice' in model_id.lower():
                result_type_emoji = "🎧"
                result_type_name = "аудио"
            elif 'music' in model_id.lower():
                result_type_emoji = "🎵"
                result_type_name = "музыка"
            
            # Оцениваем время обработки
            time_estimate = "30 сек"
            if 'video' in model_id.lower():
                time_estimate = "1-3 мин"
            elif 'music' in model_id.lower() or 'audio' in model_id.lower():
                time_estimate = "10-30 сек"
            
            # Получаем баланс пользователя
            user_balance = 0.0
            try:
                from app.state.user_state import get_user_balance
                user_balance = get_user_balance(user_id)
            except:
                pass
            
            balance_after = max(0, user_balance - final_price) if not is_free else user_balance
            
            message_text = (
                f"✨ <b>ПОДТВЕРЖДЕНИЕ ГЕНЕРАЦИИ</b> ✨\n\n"
                f"{'═' * 40}\n\n"
                f"🤖 <b>МОДЕЛЬ:</b>\n"
                f"<code>{model_name}</code>\n\n"
            )
            
            if prompt:
                prompt_preview = prompt[:80] + "..." if len(prompt) > 80 else prompt
                message_text += (
                    f"📝 <b>ЗАПРОС:</b>\n"
                    f"<i>{prompt_preview}</i>\n\n"
                )
            
            if params_text:
                message_text += f"⚙️ <b>ПАРАМЕТРЫ:</b>\n{params_text}\n"
            
            # === СЕКЦИЯ "ЧТО БУДЕТ ПОЛУЧЕНО" ===
            message_text += (
                f"{'═' * 40}\n\n"
                f"📦 <b>ЧТО БУДЕТ ПОЛУЧЕНО:</b>\n"
                f"{result_type_emoji} <b>{result_type_name.upper()}</b>\n\n"
                f"⏱️ <b>ВРЕМЯ ОБРАБОТКИ:</b>\n"
                f"примерно <b>{time_estimate}</b>\n\n"
            )
            
            # === СЕКЦИЯ "ЧТО БУДЕТ СПИСАНО" ===
            message_text += (
                f"{'═' * 40}\n\n"
                f"💳 <b>ЧТО БУДЕТ СПИСАНО:</b>\n"
            )
            
            if is_free:
                message_text += f"🎁 <b>БЕСПЛАТНО</b> (используется бесплатный лимит)\n"
            else:
                message_text += (
                    f"💰 Стоимость: <b>{price:.2f} ₽</b>\n"
                )
                
                if discount:
                    discount_amount = price * discount
                    discount_percent = int(discount * 100)
                    message_text += (
                        f"🎫 Скидка -{discount_percent}%: <b>−{discount_amount:.2f} ₽</b>\n"
                    )
                
                if bonus_available > 0 and price_info.get('bonus_used', 0) > 0:
                    message_text += (
                        f"🎁 Бонусы: <b>−{price_info.get('bonus_used', 0):.2f} ₽</b>\n"
                    )
            
            # Показываем баланс
            message_text += (
                f"\n👤 <b>ВАШ БАЛАНС:</b>\n"
                f"Текущий: <b>{user_balance:.2f}</b> ₽\n"
            )
            
            if not is_free:
                message_text += f"После: <b>{balance_after:.2f}</b> ₽\n"
                message_text += f"Списание: <b>−{final_price:.2f}</b> ₽\n"
                
                if user_balance < final_price:
                    message_text += (
                        f"\n⚠️ <b>НЕДОСТАТОЧНО СРЕДСТВ!</b>\n"
                        f"Не хватает: {final_price - user_balance:.2f} ₽\n"
                        f"Пополните баланс в разделе 💳 <b>Платежи</b>\n"
                    )
            
            message_text += (
                f"\n{'═' * 40}\n\n"
                f"💵 <b>К ОПЛАТЕ:</b> <b>{final_price:.2f} ₽</b>\n\n"
                f"{'═' * 40}\n\n"
                f"🚀 <b>Готовы начать?</b>"
            )
            
            buttons = [
                [InlineKeyboardButton("✅ Подтвердить и начать", callback_data="confirm_generate")],
                [InlineKeyboardButton("✏️ Изменить параметры", callback_data="back_to_previous_step")],
                [InlineKeyboardButton("🏠 В главное меню", callback_data="back_to_menu")],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
            ]
        else:
            # Determine result type
            result_type_emoji = "📄"  # default text
            result_type_name = "text"
            if 'image' in model_id.lower() or 'foto' in model_id.lower():
                result_type_emoji = "📷"
                result_type_name = "photo/image"
            elif 'video' in model_id.lower():
                result_type_emoji = "🎥"
                result_type_name = "video"
            elif 'audio' in model_id.lower() or 'voice' in model_id.lower():
                result_type_emoji = "🎧"
                result_type_name = "audio"
            elif 'music' in model_id.lower():
                result_type_emoji = "🎵"
                result_type_name = "music"
            
            # Estimate processing time
            time_estimate = "30 sec"
            if 'video' in model_id.lower():
                time_estimate = "1-3 min"
            elif 'music' in model_id.lower() or 'audio' in model_id.lower():
                time_estimate = "10-30 sec"
            
            # Get user balance
            user_balance = 0.0
            try:
                from app.state.user_state import get_user_balance
                user_balance = get_user_balance(user_id)
            except:
                pass
            
            balance_after = max(0, user_balance - final_price) if not is_free else user_balance
            
            message_text = (
                f"✨ <b>GENERATION CONFIRMATION</b> ✨\n\n"
                f"{'═' * 40}\n\n"
                f"🤖 <b>MODEL:</b>\n"
                f"<code>{model_name}</code>\n\n"
            )
            
            if prompt:
                prompt_preview = prompt[:80] + "..." if len(prompt) > 80 else prompt
                message_text += (
                    f"📝 <b>QUERY:</b>\n"
                    f"<i>{prompt_preview}</i>\n\n"
                )
            
            if params_text:
                message_text += f"⚙️ <b>PARAMETERS:</b>\n{params_text}\n"
            
            # === SECTION "WHAT YOU'LL GET" ===
            message_text += (
                f"{'═' * 40}\n\n"
                f"📦 <b>WHAT YOU'LL GET:</b>\n"
                f"{result_type_emoji} <b>{result_type_name.upper()}</b>\n\n"
                f"⏱️ <b>PROCESSING TIME:</b>\n"
                f"approx <b>{time_estimate}</b>\n\n"
            )
            
            # === SECTION "WHAT WILL BE DEDUCTED" ===
            message_text += (
                f"{'═' * 40}\n\n"
                f"💳 <b>WHAT WILL BE DEDUCTED:</b>\n"
            )
            
            if is_free:
                message_text += f"🎁 <b>FREE</b> (using free limit)\n"
            else:
                message_text += (
                    f"💰 Cost: <b>{price:.2f}</b> ₽\n"
                )
                
                if discount:
                    discount_amount = price * discount
                    discount_percent = int(discount * 100)
                    message_text += (
                        f"🎫 Discount -{discount_percent}%: <b>−{discount_amount:.2f}</b> ₽\n"
                    )
                
                if bonus_available > 0 and price_info.get('bonus_used', 0) > 0:
                    message_text += (
                        f"🎁 Bonuses: <b>−{price_info.get('bonus_used', 0):.2f}</b> ₽\n"
                    )
            
            # Show balance
            message_text += (
                f"\n👤 <b>YOUR BALANCE:</b>\n"
                f"Current: <b>{user_balance:.2f}</b> ₽\n"
            )
            
            if not is_free:
                message_text += f"After: <b>{balance_after:.2f}</b> ₽\n"
                message_text += f"Deduction: <b>−{final_price:.2f}</b> ₽\n"
                
                if user_balance < final_price:
                    message_text += (
                        f"\n⚠️ <b>INSUFFICIENT FUNDS!</b>\n"
                        f"Missing: {final_price - user_balance:.2f} ₽\n"
                        f"Top up your balance in 💳 <b>Payments</b> section\n"
                    )
            
            message_text += (
                f"\n{'═' * 40}\n\n"
                f"💵 <b>TO PAY:</b> <b>{final_price:.2f}</b> ₽\n\n"
                f"{'═' * 40}\n\n"
                f"🚀 <b>Ready to start?</b>"
            )
            
            buttons = [
                [InlineKeyboardButton("✅ Confirm and Start", callback_data="confirm_generate")],
                [InlineKeyboardButton("✏️ Change Parameters", callback_data="back_to_previous_step")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_menu")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
            ]
        
        return await bot.send_message(
            chat_id=chat_id,
            text=message_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка при показе подтверждения цены: {e}", exc_info=True)
        return None


def update_price_on_parameter_change(
    model_id: str,
    current_params: Dict[str, Any],
    changed_param: str,
    new_value: Any
) -> Dict[str, Any]:
    """
    Обновляет цену при изменении параметра.
    
    Args:
        model_id: ID модели
        current_params: Текущие параметры
        changed_param: Измененный параметр
        new_value: Новое значение
    
    Returns:
        Обновленная информация о цене
    """
    # Обновляем параметры
    updated_params = current_params.copy()
    updated_params[changed_param] = new_value
    
    # Пересчитываем цену
    return {
        "total_price": None,
        "currency": "RUB",
        "params": updated_params,
    }


def build_confirmation_text(
    model_id: str,
    model_name: str,
    params: Dict[str, Any],
    price: float,
    user_id: int,
    lang: str = 'ru',
    is_free: bool = False,
    bonus_available: float = 0.0,
    discount: Optional[float] = None
) -> str:
    """
    Строит текст подтверждения генерации с детализацией цены.
    
    Returns:
        Форматированный текст подтверждения
    """
    try:
        from bonus_system import get_user_bonuses
        
        price_info = {
            "total_price": price,
            "currency": "RUB",
        }
        
        # Применяем скидку, если есть
        final_price = price
        if discount:
            final_price = price * (1 - discount)
            price_info['discount'] = discount
            price_info['discount_amount'] = price * discount
            price_info['total_price'] = final_price
        
        # Применяем бонусы, если доступны
        if bonus_available > 0 and not is_free:
            if bonus_available >= final_price:
                final_price = 0.0
                price_info['bonus_used'] = final_price
                price_info['bonus_remaining'] = bonus_available - final_price
            else:
                final_price = final_price - bonus_available
                price_info['bonus_used'] = bonus_available
                price_info['bonus_remaining'] = 0.0
            price_info['total_price'] = final_price
        
        if is_free:
            final_price = 0.0
            price_info['total_price'] = 0.0
        
        # Форматируем параметры для отображения
        params_text = ""
        for param_name, param_value in params.items():
            if param_name != 'prompt':
                params_text += f"  • <b>{param_name}:</b> {param_value}\n"
        
        prompt = params.get('prompt', '')
        
        # Определяем тип результата
        result_type_emoji = "📄"
        result_type_name = "текст"
        if 'image' in model_id.lower() or 'foto' in model_id.lower():
            result_type_emoji = "📷"
            result_type_name = "фото/изображение"
        elif 'video' in model_id.lower():
            result_type_emoji = "🎥"
            result_type_name = "видео"
        elif 'audio' in model_id.lower() or 'voice' in model_id.lower():
            result_type_emoji = "🎧"
            result_type_name = "аудио"
        elif 'music' in model_id.lower():
            result_type_emoji = "🎵"
            result_type_name = "музыка"
        
        # Оцениваем время обработки
        time_estimate = "30 сек"
        if 'video' in model_id.lower():
            time_estimate = "1-3 мин"
        elif 'music' in model_id.lower() or 'audio' in model_id.lower():
            time_estimate = "10-30 сек"
        
        # Получаем баланс пользователя
        user_balance = 0.0
        try:
            from app.state.user_state import get_user_balance
            user_balance = get_user_balance(user_id)
        except:
            pass
        
        balance_after = max(0, user_balance - final_price) if not is_free else user_balance
        
        if lang == 'ru':
            message_text = (
                f"✨ <b>ПОДТВЕРЖДЕНИЕ ГЕНЕРАЦИИ</b> ✨\n\n"
                f"{'═' * 40}\n\n"
                f"🤖 <b>МОДЕЛЬ:</b>\n"
                f"<code>{model_name}</code>\n\n"
            )
            
            if prompt:
                prompt_preview = prompt[:80] + "..." if len(prompt) > 80 else prompt
                message_text += (
                    f"📝 <b>ЗАПРОС:</b>\n"
                    f"<i>{prompt_preview}</i>\n\n"
                )
            
            if params_text:
                message_text += f"⚙️ <b>ПАРАМЕТРЫ:</b>\n{params_text}\n"
            
            # === СЕКЦИЯ "ЧТО БУДЕТ ПОЛУЧЕНО" ===
            message_text += (
                f"{'═' * 40}\n\n"
                f"📦 <b>ЧТО БУДЕТ ПОЛУЧЕНО:</b>\n"
                f"{result_type_emoji} <b>{result_type_name.upper()}</b>\n\n"
                f"⏱️ <b>ВРЕМЯ ОБРАБОТКИ:</b>\n"
                f"примерно <b>{time_estimate}</b>\n\n"
            )
            
            # === СЕКЦИЯ "ЧТО БУДЕТ СПИСАНО" ===
            message_text += (
                f"{'═' * 40}\n\n"
                f"💳 <b>ЧТО БУДЕТ СПИСАНО:</b>\n"
            )
            
            if is_free:
                message_text += f"🎁 <b>БЕСПЛАТНО</b> (используется бесплатный лимит)\n"
            else:
                message_text += (
                    f"💰 Стоимость: <b>{price:.2f} ₽</b>\n"
                )
                
                if discount:
                    discount_amount = price * discount
                    discount_percent = int(discount * 100)
                    message_text += (
                        f"🎫 Скидка -{discount_percent}%: <b>−{discount_amount:.2f} ₽</b>\n"
                    )
                
                if bonus_available > 0 and price_info.get('bonus_used', 0) > 0:
                    message_text += (
                        f"🎁 Бонусы: <b>−{price_info.get('bonus_used', 0):.2f} ₽</b>\n"
                    )
            
            # Показываем баланс
            message_text += (
                f"\n👤 <b>ВАШ БАЛАНС:</b>\n"
                f"Текущий: <b>{user_balance:.2f}</b> ₽\n"
            )
            
            if not is_free:
                message_text += f"После: <b>{balance_after:.2f}</b> ₽\n"
                message_text += f"Списание: <b>−{final_price:.2f}</b> ₽\n"
                
                if user_balance < final_price:
                    message_text += (
                        f"\n⚠️ <b>НЕДОСТАТОЧНО СРЕДСТВ!</b>\n"
                        f"Не хватает: {final_price - user_balance:.2f} ₽\n"
                        f"Пополните баланс в разделе 💳 <b>Платежи</b>\n"
                    )
            
            message_text += (
                f"\n{'═' * 40}\n\n"
                f"💵 <b>К ОПЛАТЕ:</b> <b>{final_price:.2f}</b> ₽\n\n"
                f"{'═' * 40}\n\n"
                f"🚀 <b>Готовы начать?</b>"
            )
        else:
            # English version
            message_text = (
                f"✨ <b>GENERATION CONFIRMATION</b> ✨\n\n"
                f"{'═' * 40}\n\n"
                f"🤖 <b>MODEL:</b>\n"
                f"<code>{model_name}</code>\n\n"
            )
            
            if prompt:
                prompt_preview = prompt[:80] + "..." if len(prompt) > 80 else prompt
                message_text += (
                    f"📝 <b>QUERY:</b>\n"
                    f"<i>{prompt_preview}</i>\n\n"
                )
            
            if params_text:
                message_text += f"⚙️ <b>PARAMETERS:</b>\n{params_text}\n"
            
            # === SECTION "WHAT YOU'LL GET" ===
            message_text += (
                f"{'═' * 40}\n\n"
                f"📦 <b>WHAT YOU'LL GET:</b>\n"
                f"{result_type_emoji} <b>{result_type_name.upper()}</b>\n\n"
                f"⏱️ <b>PROCESSING TIME:</b>\n"
                f"approx <b>{time_estimate}</b>\n\n"
            )
            
            # === SECTION "WHAT WILL BE DEDUCTED" ===
            message_text += (
                f"{'═' * 40}\n\n"
                f"💳 <b>WHAT WILL BE DEDUCTED:</b>\n"
            )
            
            if is_free:
                message_text += f"🎁 <b>FREE</b> (using free limit)\n"
            else:
                message_text += (
                    f"💰 Cost: <b>{price:.2f}</b> ₽\n"
                )
                
                if discount:
                    discount_amount = price * discount
                    discount_percent = int(discount * 100)
                    message_text += (
                        f"🎫 Discount -{discount_percent}%: <b>−{discount_amount:.2f}</b> ₽\n"
                    )
                
                if bonus_available > 0 and price_info.get('bonus_used', 0) > 0:
                    message_text += (
                        f"🎁 Bonuses: <b>−{price_info.get('bonus_used', 0):.2f}</b> ₽\n"
                    )
            
            # Show balance
            message_text += (
                f"\n👤 <b>YOUR BALANCE:</b>\n"
                f"Current: <b>{user_balance:.2f}</b> ₽\n"
            )
            
            if not is_free:
                message_text += f"After: <b>{balance_after:.2f}</b> ₽\n"
                message_text += f"Deduction: <b>−{final_price:.2f}</b> ₽\n"
                
                if user_balance < final_price:
                    message_text += (
                        f"\n⚠️ <b>INSUFFICIENT FUNDS!</b>\n"
                        f"Missing: {final_price - user_balance:.2f} ₽\n"
                        f"Top up your balance in 💳 <b>Payments</b> section\n"
                    )
            
            message_text += (
                f"\n{'═' * 40}\n\n"
                f"💵 <b>TO PAY:</b> <b>{final_price:.2f}</b> ₽\n\n"
                f"{'═' * 40}\n\n"
                f"🚀 <b>Ready to start?</b>"
            )
        
        return message_text
    except Exception as e:
        logger.error(f"❌ Ошибка при построении текста подтверждения: {e}", exc_info=True)
        return "❌ Ошибка при подготовке подтверждения."

