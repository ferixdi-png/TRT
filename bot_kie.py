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


async def main():
    """Run the main application entrypoint."""
    from app.main import main as app_main

    logger.info("[BOT_KIE] Delegating startup to app.main")
    await app_main()


__all__ = ["create_bot_application", "main"]
