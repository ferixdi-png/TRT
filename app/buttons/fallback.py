"""
Fallback Handler для неизвестных callback'ов
Восстанавливает меню и логирует проблему
"""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.observability.exception_boundary import handle_unknown_callback

logger = logging.getLogger(__name__)


async def fallback_callback_handler(
    callback_data: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int = None,
    user_lang: str = 'ru',
    error: str = None
):
    """
    Fallback обработчик для неизвестных или битых callback'ов
    
    Args:
        callback_data: Неизвестный callback_data
        update: Telegram update
        context: Telegram context
        user_id: ID пользователя
        user_lang: Язык пользователя
        error: Ошибка, если была (опционально)
    """
    query = update.callback_query
    fallback_chat_id = update.effective_chat.id if update.effective_chat else None
    
    if error:
        logger.debug("Fallback callback error detail: %s", error, exc_info=True)

    correlation_id = None
    try:
        if query:
            correlation_id = await handle_unknown_callback(update, context, callback_data)
    except Exception:
        logger.debug("Fallback unknown callback logging failed", exc_info=True)
    
    # Отвечаем пользователю
    try:
        if query:
            # Пробуем получить язык из перевода
            try:
                from translations import t

                message = t("button_outdated", lang=user_lang) or "Кнопка устарела, обновил меню"
            except Exception:
                message = "Кнопка устарела, обновил меню" if user_lang == "ru" else "Button outdated, menu updated"

            await query.answer(message, show_alert=False)

            # Восстанавливаем главное меню через единый маршрут
            try:
                from bot_kie import ensure_main_menu

                await ensure_main_menu(
                    update,
                    context,
                    source="unknown_callback_fallback",
                    prefer_edit=True,
                )
                logger.info("✅ Меню восстановлено через ensure_main_menu")
            except Exception as restore_error:
                logger.debug("❌ Не удалось восстановить меню: %s", restore_error, exc_info=True)
            # Пробуем отправить короткое сообщение с кнопкой меню
            try:
                menu_label = "Главное меню" if user_lang == "ru" else "Main menu"
                keyboard = InlineKeyboardMarkup(
                    [[InlineKeyboardButton(menu_label, callback_data="back_to_menu")]]
                )
                message_text = (
                    "Кнопка устарела, открой меню."
                    f" Лог: {correlation_id or 'corr-na'}"
                )
                if query.message:
                    await query.message.reply_text(
                        message_text,
                        reply_markup=keyboard,
                    )
                elif fallback_chat_id:
                    await context.bot.send_message(
                        chat_id=fallback_chat_id,
                        text=message_text,
                        reply_markup=keyboard,
                    )
            except Exception:
                pass
        elif fallback_chat_id:
            menu_label = "Главное меню" if user_lang == "ru" else "Main menu"
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton(menu_label, callback_data="back_to_menu")]]
            )
            await context.bot.send_message(
                chat_id=fallback_chat_id,
                text="Кнопка устарела, открой меню." if user_lang == "ru" else "Button outdated, open the menu.",
                reply_markup=keyboard,
            )

    except Exception as e:
        logger.debug("❌ Ошибка в fallback handler: %s", e, exc_info=True)

