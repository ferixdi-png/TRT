"""
Global Telegram error handler registration.
Ensures a consistent error handler is always attached to Application instances.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Awaitable, Optional

from telegram import Update
from telegram.error import Conflict as TelegramConflict
from telegram.ext import Application, ContextTypes

from app.bot_mode import handle_conflict_gracefully
from app.observability.error_guard import ErrorGuard
from app.observability.no_silence_guard import get_no_silence_guard, track_outgoing_action
from app.state.user_state import get_user_language
from app.utils.singleton_lock import release_singleton_lock

logger = logging.getLogger(__name__)


def build_error_handler() -> Callable[[object, ContextTypes.DEFAULT_TYPE], Awaitable[None]]:
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Global error handler for all exceptions in the bot.
        Logs short info (no secrets) and provides a safe user response.
        """
        try:
            error = context.error
            error_type = type(error).__name__
            error_msg = str(error)

            logger.error("[ERROR_HANDLER] Called with error: %s: %s", error_type, error_msg[:200])

            if isinstance(error, TelegramConflict) or "Conflict" in error_msg or "409" in error_msg:
                logger.error("❌❌❌ 409 CONFLICT DETECTED: %s", error_msg)
                logger.error("   Another bot instance is running or webhook is active")
                logger.error("   This process will exit gracefully to prevent conflicts")

                try:
                    if hasattr(context, "application") and context.application:
                        app = context.application
                        if hasattr(app, "updater") and app.updater:
                            try:
                                if app.updater.running:
                                    logger.info("   Stopping updater polling immediately...")
                                    await app.updater.stop()
                                    logger.info("   Updater stopped")
                            except Exception as updater_error:
                                logger.warning("   Could not stop updater: %s", updater_error)

                        try:
                            if app.running:
                                logger.info("   Stopping application...")
                                await app.stop()
                                await app.shutdown()
                                logger.info("   Application stopped")
                        except Exception as stop_error:
                            logger.warning("   Could not stop application: %s", stop_error)
                except Exception as stop_exc:
                    logger.warning("   Error stopping updater/application: %s", stop_exc)

                try:
                    handle_conflict_gracefully(error, "polling")
                except Exception as conflict_exc:
                    logger.error("   Error in handle_conflict_gracefully: %s", conflict_exc)

                logger.error("   Exiting gracefully to prevent repeated conflicts...")
                try:
                    await release_singleton_lock()
                except Exception:
                    pass

                import os

                logger.info("   Exiting with code 0 (immediate termination, no restart needed)")
                os._exit(0)

            logger.exception("❌❌❌ GLOBAL ERROR HANDLER: %s: %s", error_type, error_msg)

            try:
                project_root = Path(__file__).resolve().parents[1]
                error_guard = ErrorGuard(project_root)

                user_id = None
                callback_data = None
                if isinstance(update, Update):
                    if update.effective_user:
                        user_id = update.effective_user.id
                    if update.callback_query:
                        callback_data = update.callback_query.data

                fixed = await error_guard.handle_error(
                    error, update, context, user_id, callback_data
                )
                if fixed:
                    logger.info("✅ Ошибка автоматически исправлена (self-heal)")
            except Exception as heal_error:
                logger.warning("⚠️ Ошибка в self-heal: %s", heal_error)

            user_id = None
            user_lang = "ru"
            chat_id: Optional[int] = None

            if isinstance(update, Update):
                if update.effective_user:
                    user_id = update.effective_user.id
                    user_lang = get_user_language(user_id) if user_id else "ru"
                if update.effective_chat:
                    chat_id = update.effective_chat.id

            logger.error(
                "Error details: %s",
                {
                    "error_type": error_type,
                    "error_message": error_msg,
                    "user_id": user_id,
                    "chat_id": chat_id,
                },
            )

            guard = get_no_silence_guard()
            update_id = update.update_id if isinstance(update, Update) else None

            if isinstance(update, Update) and update.callback_query:
                try:
                    error_text = "⚠️ Ошибка. Откройте /start" if user_lang == "ru" else "⚠️ Error. Open /start"
                    await update.callback_query.answer(error_text, show_alert=True)
                    if update_id:
                        track_outgoing_action(update_id)
                except Exception as answer_exc:
                    logger.warning("Could not answer callback in error handler: %s", answer_exc)

            if isinstance(update, Update) and update.message and chat_id:
                try:
                    error_text = (
                        "❌ <b>Произошла ошибка</b>\n\n"
                        "Ошибка сервера, попробуйте позже.\n\n"
                        "Если проблема повторяется, обратитесь в поддержку."
                    ) if user_lang == "ru" else (
                        "❌ <b>An error occurred</b>\n\n"
                        "Server error, please try later.\n\n"
                        "If the problem persists, please contact support."
                    )
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=error_text,
                        parse_mode="HTML",
                    )
                    if update_id:
                        track_outgoing_action(update_id)
                except Exception as send_exc:
                    logger.warning("Could not send error message: %s", send_exc)

            if update_id:
                await guard.check_and_ensure_response(update, context)
        except Exception as handler_exc:
            logger.critical(
                "❌❌❌ CRITICAL: Error handler itself failed: %s",
                handler_exc,
                exc_info=True,
            )

    return error_handler


def ensure_error_handler_registered(application: Application) -> None:
    if application.error_handlers:
        return
    application.add_error_handler(build_error_handler())
