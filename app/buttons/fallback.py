"""
Fallback Handler для неизвестных callback'ов
Восстанавливает меню и логирует проблему
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

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
    
    # Логируем проблему
    logger.error("=" * 80)
    logger.error("❌❌❌ UNHANDLED CALLBACK DATA")
    logger.error("=" * 80)
    logger.error(f"   Callback data: '{callback_data}'")
    logger.error(f"   User ID: {user_id}")
    logger.error(f"   Message ID: {query.message.message_id if query and query.message else 'N/A'}")
    logger.error(f"   Query ID: {query.id if query else 'N/A'}")
    if error:
        logger.error(f"   Error: {error}")
    logger.error("=" * 80)
    
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
                logger.info("✅ Меню восстановлено через ensure_main_menu для user_id=%s", user_id)
            except Exception as restore_error:
                logger.error("❌ Не удалось восстановить меню: %s", restore_error, exc_info=True)
                # Пробуем просто отправить /start
                try:
                    await query.message.reply_text(
                        "Обновите меню командой /start" if user_lang == "ru" else "Update menu with /start"
                    )
                except Exception:
                    pass

    except Exception as e:
        logger.error("❌ Ошибка в fallback handler: %s", e, exc_info=True)





