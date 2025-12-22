"""
Bot KIE (Knowledge Information Extraction) handlers.
"""
import logging
from telegram import Update
from telegram.ext import (
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

logger = logging.getLogger(__name__)

# Conversation states
GENERATION_STATE = 1


async def generation_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start generation conversation."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Starting generation...")
    return GENERATION_STATE


async def generation_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process generation request."""
    # Handle generation logic
    if update.message:
        await update.message.reply_text("Processing...")
    return GENERATION_STATE


async def generation_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finish generation conversation."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Generation complete!")
    return ConversationHandler.END


async def generation_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel generation conversation."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Generation cancelled.")
    return ConversationHandler.END


# Fixed ConversationHandler: removed per_message=True to avoid PTB warnings
# Using CallbackQueryHandler for entry_points and state handlers
generation_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(generation_start, pattern="^start_generation$")
    ],
    states={
        GENERATION_STATE: [
            CallbackQueryHandler(generation_process, pattern="^process$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, generation_process),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(generation_cancel, pattern="^cancel$"),
    ],
    # Removed per_message=True to fix PTB warning
    # per_message=True causes issues with message context
)

