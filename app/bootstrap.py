"""
Bootstrap - создание Application с dependency container
Все зависимости хранятся в application.bot_data["deps"]
"""

import asyncio
import inspect
import logging
from typing import Optional, Dict, Any

from telegram.ext import Application
from telegram import Bot
from telegram.request import HTTPXRequest

from app.config import Settings, get_settings
from app.storage import get_storage
from app.telegram_error_handler import ensure_error_handler_registered
from app.observability.safe_handler import install_safe_handler_wrapper
from app.utils.logging_config import get_logger
from app.session_store import get_session_store

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
            "[STORAGE] fallback_disabled=true reason=%s mode=db_only",
            reason,
        )

    async def _log_boot_storage_status(self, storage: Any) -> None:
        if storage is None:
            return

        def _count_records(payload: Any, *, history: bool = False) -> int:
            if isinstance(payload, dict):
                if history:
                    return sum(len(value) for value in payload.values() if isinstance(value, list))
                return len(payload)
            if isinstance(payload, list):
                return len(payload)
            return 0

        counts: Dict[str, Dict[str, Any]] = {}
        items = {
            "balances": "user_balances.json",
            "daily_free": "daily_free_generations.json",
            "payments": "payments.json",
            "history": "generations_history.json",
        }
        for key, filename in items.items():
            try:
                payload = await storage.read_json_file(filename, default={})
                counts[key] = {
                    "loaded": True,
                    "records": _count_records(payload, history=(key == "history")),
                }
            except Exception as exc:
                logger.warning("BOOT_STATUS preload_failed file=%s error=%s", filename, exc)
                counts[key] = {"loaded": False, "records": 0}

        logger.info(
            "BOOT_STATUS STORAGE_BACKEND=postgres partner_id=%s "
            "balances_loaded=%s balances_records_count=%s "
            "daily_free_loaded=%s daily_free_records_count=%s "
            "payments_loaded=%s payments_records_count=%s "
            "history_loaded=%s history_records_count=%s",
            getattr(storage, "partner_id", ""),
            counts["balances"]["loaded"],
            counts["balances"]["records"],
            counts["daily_free"]["loaded"],
            counts["daily_free"]["records"],
            counts["payments"]["loaded"],
            counts["payments"]["records"],
            counts["history"]["loaded"],
            counts["history"]["records"],
        )
        
    async def initialize(self, settings: Settings):
        """Инициализирует все зависимости"""
        self.settings = settings
        
        # Инициализация storage
        try:
            self.storage = get_storage()
            storage_ok = True
            if hasattr(self.storage, "initialize") and inspect.iscoroutinefunction(self.storage.initialize):
                storage_ok = await self.storage.initialize()
            elif hasattr(self.storage, "ping") and inspect.iscoroutinefunction(self.storage.ping):
                storage_ok = await self.storage.ping()
            elif hasattr(self.storage, "test_connection"):
                storage_ok = await asyncio.to_thread(self.storage.test_connection)

            if storage_ok:
                logger.info("[OK] Storage initialized")
                await self._log_boot_storage_status(self.storage)
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


async def create_application(settings: Optional[Settings] = None, *, bot_override: Optional[Bot] = None) -> Application:
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

    request = HTTPXRequest(
        connect_timeout=settings.telegram_http_connect_timeout_seconds,
        read_timeout=settings.telegram_http_read_timeout_seconds,
        write_timeout=settings.telegram_http_write_timeout_seconds,
        pool_timeout=settings.telegram_http_pool_timeout_seconds,
        connection_pool_size=settings.telegram_http_connection_pool_size,
    )
    if bot_override is not None:
        builder = Application.builder().bot(bot_override)
    else:
        builder = Application.builder().token(settings.telegram_bot_token)
    if bot_override is None:
        builder = builder.request(request)
    builder = (
        builder
        .post_init(post_init)
        .post_shutdown(post_shutdown)
    )
    if settings.test_mode and hasattr(builder, "updater"):
        builder = builder.updater(None)
    application = builder.build()
    if settings.test_mode:
        try:
            object.__setattr__(application.bot, "_initialized", True)
        except Exception:
            setattr(application.bot, "_initialized", True)
        setattr(application, "_initialized", True)
    ensure_error_handler_registered(application)
    install_safe_handler_wrapper(application)
    
    # Инициализируем dependency container
    deps = DependencyContainer()
    await deps.initialize(settings)
    deps.user_sessions = get_session_store().data
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
