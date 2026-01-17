"""Router registry."""
from __future__ import annotations

from bot.handlers.admin import router as admin_router
from bot.handlers.balance import router as balance_router
from bot.handlers.diag import router as diag_router
from bot.handlers.error_handler import router as error_handler_router
from bot.handlers.flow import router as flow_router
from bot.handlers.gallery import router as gallery_router
from bot.handlers.history import router as history_router
from bot.handlers.marketing import router as marketing_router
from bot.handlers.quick_actions import router as quick_actions_router
from bot.handlers.zero_silence import router as zero_silence_router
from bot.handlers.z_image import router as z_image_router

__all__ = [
    "admin_router",
    "balance_router",
    "diag_router",
    "error_handler_router",
    "flow_router",
    "gallery_router",
    "history_router",
    "marketing_router",
    "quick_actions_router",
    "zero_silence_router",
    "z_image_router",
]
