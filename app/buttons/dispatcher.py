"""
Центральный диспетчер callback-ов
Связывает callback_data с обработчиками из bot_kie.py
"""

import logging
from typing import Callable, Dict, Optional
from telegram import Update
from telegram.ext import ContextTypes

from app.buttons.registry import ButtonRegistry, CallbackRouter, CallbackType
from app.buttons.router_config import CALLBACK_ROUTES
from app.buttons.fallback import fallback_callback_handler

logger = logging.getLogger(__name__)

# Глобальный экземпляр роутера
_global_router: Optional[CallbackRouter] = None
_handlers_map: Dict[str, Callable] = {}


def initialize_router(handlers: Dict[str, Callable]) -> CallbackRouter:
    """
    Инициализирует глобальный роутер с обработчиками из bot_kie.py
    
    Args:
        handlers: Словарь {handler_name: handler_function}
    
    Returns:
        Настроенный CallbackRouter
    """
    global _global_router, _handlers_map
    
    _handlers_map = handlers
    registry = ButtonRegistry()
    
    # Регистрируем все маршруты из конфигурации
    registered_count = 0
    missing_handlers = []
    
    for callback_data, callback_type, description, handler_name in CALLBACK_ROUTES:
        if handler_name in handlers:
            registry.register(
                callback_data=callback_data,
                handler=handlers[handler_name],
                handler_name=handler_name,
                callback_type=callback_type,
                description=description
            )
            registered_count += 1
        else:
            missing_handlers.append(f"  - {handler_name} (для '{callback_data}')")
    
    if missing_handlers:
        logger.warning(
            f"⚠️ Не найдено {len(missing_handlers)} обработчиков:\n" + 
            "\n".join(missing_handlers)
        )
    
    logger.info(f"✅ Зарегистрировано {registered_count} callback-маршрутов")
    
    # Создаем роутер с fallback
    router = CallbackRouter(registry)
    router.set_fallback_handler(fallback_callback_handler)
    
    _global_router = router
    return router


def get_router() -> Optional[CallbackRouter]:
    """Возвращает глобальный роутер"""
    return _global_router


async def route_callback(
    callback_data: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int = None,
    user_lang: str = 'ru'
) -> bool:
    """
    Маршрутизирует callback к нужному обработчику
    
    Args:
        callback_data: Данные callback
        update: Telegram update
        context: Telegram context
        user_id: ID пользователя
        user_lang: Язык пользователя
    
    Returns:
        bool: True если обработано успешно, False если использован fallback
    """
    if not _global_router:
        logger.error("❌ Роутер не инициализирован! Вызовите initialize_router() сначала.")
        return False
    
    return await _global_router.route(callback_data, update, context, user_id, user_lang)


def get_router_stats() -> Dict[str, int]:
    """Получить статистику работы роутера"""
    if _global_router:
        return _global_router.get_stats()
    return {"error": "Router not initialized"}
