"""
Пример обёрток для callback-обработчиков
Демонстрирует, как извлекать код из _button_callback_impl в отдельные функции
"""

import logging
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)


# =============================================================================
# БАЗОВЫЕ ОБРАБОТЧИКИ (примеры того, как должны выглядеть обработчики)
# =============================================================================

async def handle_back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик кнопки "🏠 Главное меню"
    Возвращает пользователя в главное меню
    """
    from bot_kie import ensure_main_menu
    
    query = update.callback_query
    
    # Подтвердить нажатие кнопки
    try:
        await query.answer()
    except Exception:
        pass
    
    # Показать главное меню
    await ensure_main_menu(update, context, source="back", prefer_edit=True)
    return ConversationHandler.END


async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик кнопки "❌ Отмена"
    Отменяет текущее действие и возвращает в главное меню
    """
    from bot_kie import (
        ensure_main_menu,
        get_session_store,
        get_user_language,
    )
    from app.observability.no_silence_guard import track_outgoing_action
    
    query = update.callback_query
    user_id = query.from_user.id if query and query.from_user else None
    user_lang = get_user_language(user_id) if user_id else "ru"
    update_id = update.update_id
    
    # Подтвердить отмену
    await query.answer("Отменено" if user_lang == "ru" else "Cancelled")
    if update_id:
        track_outgoing_action(update_id, action_type="answerCallbackQuery")
    
    # Очистить сессию
    session_store = get_session_store(context)
    if user_id is not None and user_id in session_store:
        session_store[user_id] = {}
    
    # Вернуться в главное меню
    await ensure_main_menu(update, context, source="cancel", prefer_edit=True)
    return ConversationHandler.END


async def handle_show_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик кнопок "show_models" и "all_models"
    Показывает каталог моделей по категориям
    """
    # Этот код будет извлечен из существующего обработчика
    # Это просто заглушка для демонстрации структуры
    query = update.callback_query
    await query.answer()
    
    # Реальная логика будет здесь
    # (можно импортировать из bot_kie или оставить прямо здесь)
    pass


async def handle_show_all_models_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик кнопки "Все модели"
    Показывает полный список всех доступных моделей
    """
    query = update.callback_query
    await query.answer()
    
    # Реальная логика будет здесь
    pass


# =============================================================================
# ФУНКЦИЯ ДЛЯ СОЗДАНИЯ СЛОВАРЯ ОБРАБОТЧИКОВ
# =============================================================================

def get_handlers_map():
    """
    Возвращает словарь всех обработчиков для dispatcher
    
    Returns:
        Dict[str, Callable]: Маппинг имя_обработчика -> функция
    """
    return {
        # Базовая навигация
        "handle_back_to_menu": handle_back_to_menu,
        "handle_cancel": handle_cancel,
        "handle_show_models": handle_show_models,
        "handle_show_all_models_list": handle_show_all_models_list,
        
        # TODO: Добавить остальные обработчики по мере миграции
    }


# =============================================================================
# ПРИМЕР ИСПОЛЬЗОВАНИЯ
# =============================================================================

"""
В bot_kie.py при инициализации:

from app.buttons.dispatcher import initialize_router
from app.buttons.handlers_example import get_handlers_map

# В main() или где-то при старте:
handlers = get_handlers_map()
initialize_router(handlers)

# В button_callback заменить весь if/elif блок на:
from app.buttons.dispatcher import route_callback

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    user_lang = get_user_language(user_id)
    
    await route_callback(data, update, context, user_id, user_lang)
"""
