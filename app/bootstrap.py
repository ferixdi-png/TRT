"""
Bootstrap - создание Application с dependency container
Все зависимости хранятся в application.bot_data["deps"]
"""

import logging
import asyncio
from typing import Optional, Dict, Any

from telegram.ext import Application
from telegram import Bot

from app.config import Settings, get_settings
from app.storage import get_storage
from app.telegram_error_handler import ensure_error_handler_registered
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


class DependencyContainer:
    """Контейнер зависимостей для бота"""
    
    def __init__(self):
        self.settings: Optional[Settings] = None
        self.storage = None
        self.kie_client = None
        self.lock_conn = None
        self.lock_key_int: Optional[int] = None
        self.user_sessions: Dict[int, Dict[str, Any]] = {}
        self.active_generations: Dict[int, Dict[str, Any]] = {}
        self.active_generations_lock = asyncio.Lock()
        self.saved_generations: Dict[int, list] = {}

    def _storage_fallback_disabled(self, reason: str) -> None:
        logger.warning(
            "[STORAGE] fallback_disabled=true reason=%s mode=github_only",
            reason,
        )
        
    async def initialize(self, settings: Settings):
        """Инициализирует все зависимости"""
        self.settings = settings
        
        # Инициализация storage
        try:
            self.storage = get_storage()
            storage_ok = True
            if hasattr(self.storage, "initialize") and asyncio.iscoroutinefunction(self.storage.initialize):
                storage_ok = await self.storage.initialize()
            elif hasattr(self.storage, "test_connection"):
                storage_ok = await asyncio.to_thread(self.storage.test_connection)

            if storage_ok:
                logger.info("[OK] Storage initialized")
            else:
                logger.warning("[WARN] Storage connection test failed")
                self._storage_fallback_disabled("connection_test_failed")
        except Exception as e:
            logger.error(f"[ERROR] Failed to initialize storage: {e}")
            # Мягкая деградация - продолжаем без storage
            self._storage_fallback_disabled("storage_init_exception")
        
        # Инициализация KIE client (ленивая, при первом использовании)
        # Не инициализируем здесь, чтобы избежать side effects при импорте
        
        # Инициализация singleton lock (ленивая)
        # Не инициализируем здесь, чтобы избежать side effects при импорте
        
        logger.info("[OK] Dependency container initialized")
    
    def get_storage(self):
        """Получить storage"""
        return self.storage
    
    def get_kie_client(self):
        """Получить KIE client (ленивая инициализация)"""
        if self.kie_client is None:
            # Ленивая инициализация при первом использовании
            try:
                from app.kie.kie_client import get_kie_client
                if self.settings and self.settings.kie_api_key:
                    client = get_kie_client()
                    client.api_key = self.settings.kie_api_key
                    client.base_url = (self.settings.kie_api_url or "https://api.kie.ai").rstrip("/")
                    self.kie_client = client
                    logger.info("[OK] KIE client initialized")
                else:
                    logger.warning("[WARN] KIE_API_KEY not set, KIE client not available")
            except ImportError:
                logger.warning("[WARN] kie_client module not found")
            except Exception as e:
                logger.error(f"[ERROR] Failed to initialize KIE client: {e}")
        
        return self.kie_client


def get_deps(application: Application) -> DependencyContainer:
    """
    Получить dependency container из application
    
    Args:
        application: Telegram Application
        
    Returns:
        DependencyContainer
    """
    if "deps" not in application.bot_data:
        # Создаем если еще нет
        application.bot_data["deps"] = DependencyContainer()
    
    return application.bot_data["deps"]


async def create_application(settings: Optional[Settings] = None) -> Application:
    """
    Создает Telegram Application с dependency container
    
    Args:
        settings: Настройки (если None, загружаются из env)
        
    Returns:
        Application с инициализированными зависимостями
    """
    if settings is None:
        settings = get_settings()
    
    # Создаем Application с post_init для обработки ошибок updater
    async def post_init(app: Application) -> None:
        """Post-init hook для обработки ошибок updater"""
        # Обработчик ошибок уже добавлен в bot_kie.py, но убеждаемся что он есть
        logger.debug("[BOOTSTRAP] Post-init hook called")
    
    # Создаем Application с post_init
    async def post_shutdown(app: Application) -> None:
        deps = get_deps(app)
        kie_client = deps.get_kie_client()
        close_fn = getattr(kie_client, "close", None)
        if kie_client and callable(close_fn):
            await close_fn()
            logger.info("[OK] KIE client session closed")
        storage = deps.get_storage()
        close_storage = getattr(storage, "close", None)
        if storage and callable(close_storage):
            result = close_storage()
            if asyncio.iscoroutine(result):
                await result
            logger.info("[OK] Storage closed")

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    ensure_error_handler_registered(application)
    
    # Инициализируем dependency container
    deps = DependencyContainer()
    await deps.initialize(settings)
    application.bot_data["deps"] = deps
    
    logger.info("[OK] Application created with dependency container")
    
    return application


async def build_application(settings: Optional[Settings] = None) -> Application:
    """
    Создает и настраивает Application (alias для create_application)
    
    Args:
        settings: Настройки (если None, загружаются из env)
        
    Returns:
        Application с инициализированными зависимостями
    """
    return await create_application(settings)
