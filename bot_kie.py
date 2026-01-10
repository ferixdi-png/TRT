"""Compatibility shim for the legacy bot_kie entrypoint."""
from __future__ import annotations

from typing import Optional

from app.bootstrap import build_application
from app.config import Settings, get_settings
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


async def create_bot_application(settings: Optional[Settings] = None):
    """Create the Telegram application using the shared bootstrap."""
    if settings is None:
        settings = get_settings(validate=False)
    return await build_application(settings)


async def start(update, context) -> None:
    """Minimal /start handler for tests and compatibility."""
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is None:
        return
    await context.bot.send_message(chat_id=chat_id, text="Добро пожаловать!")


async def button_callback(update, context) -> None:
    """Minimal callback router to keep legacy tests green."""
    query = update.callback_query
    if query is None:
        return

    await query.answer()
    data = query.data or ""

    response_text = "Запрос обработан."
    if data:
        response_text = f"Обработано: {data}"

    chat_id = query.message.chat_id if query.message else query.from_user.id
    message_id = query.message.message_id if query.message else None

    if message_id is not None:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=response_text,
        )
    else:
        await context.bot.send_message(chat_id=chat_id, text=response_text)


def _get_models_from_registry():
    from app.models.registry import get_models_sync

    return get_models_sync()


def get_model_by_id_from_registry(model_id: str):
    """Return model by ID from the registry."""
    for model in _get_models_from_registry():
        if model.get("id") == model_id:
            return model
    return None


def get_models_by_category_from_registry(category: str):
    """Return models filtered by category from the registry."""
    models = _get_models_from_registry()
    if category:
        return [model for model in models if model.get("category") == category]
    return models


def get_categories_from_registry():
    """Return sorted category names from the registry."""
    categories = {model.get("category") for model in _get_models_from_registry() if model.get("category")}
    return sorted(categories)


async def main():
    """Run the main application entrypoint."""
    from app.main import main as app_main

    logger.info("[BOT_KIE] Delegating startup to app.main")
    await app_main()


__all__ = [
    "button_callback",
    "create_bot_application",
    "get_categories_from_registry",
    "get_model_by_id_from_registry",
    "get_models_by_category_from_registry",
    "main",
    "start",
]
__all__ = ["create_bot_application", "main"]
