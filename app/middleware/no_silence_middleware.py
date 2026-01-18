"""Middleware that guarantees a response for every update."""
from __future__ import annotations

from typing import Awaitable, Callable
from telegram import Update
from telegram.ext import ContextTypes

from app.observability.no_silence_guard import get_no_silence_guard


async def ensure_no_silence(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    handler: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[object]],
) -> object:
    """Run handler and enforce no-silence fallback if needed."""
    guard = get_no_silence_guard()
    result = await handler(update, context)
    await guard.check_and_ensure_response(update, context, result)
    return result
