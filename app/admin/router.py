from __future__ import annotations
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .ui import render_root, render_users, render_payments, render_stats, render_broadcast_intro
from .diagnostics import build_admin_diagnostics_report
from .repo import users_summary, payments_summary, stats_summary, export_csv
from .auth import is_admin


async def show_admin_root(update_or_query: Any, context: ContextTypes.DEFAULT_TYPE, is_callback: bool = False):
    if is_callback:
        query = update_or_query
        user_id = query.from_user.id
        if not is_admin(user_id):
            await query.answer("❌ Эта функция доступна только администратору.", show_alert=True)
            return
        diagnostics = await build_admin_diagnostics_report()
        text, kb = render_root(diagnostics)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        await query.answer()
    else:
        update: Update = update_or_query
        user_id = update.effective_user.id
        if not is_admin(user_id):
            await update.message.reply_text("❌ Эта команда доступна только администратору.")
            return
        diagnostics = await build_admin_diagnostics_report()
        text, kb = render_root(diagnostics)
        await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("❌ Эта функция доступна только администратору.", show_alert=True)
        return

    data = query.data or ""
    if data == "adm:root":
        diagnostics = await build_admin_diagnostics_report()
        text, kb = render_root(diagnostics)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        await query.answer()
        return

    if data == "adm:users":
        summary = users_summary()
        text, kb = render_users(summary)
        await query.edit_message_text(text, reply_markup=kb)
        await query.answer()
        return

    if data == "adm:payments":
        summary = payments_summary()
        text, kb = render_payments(summary)
        await query.edit_message_text(text, reply_markup=kb)
        await query.answer()
        return

    if data == "adm:stats":
        summary = stats_summary()
        text, kb = render_stats(summary)
        await query.edit_message_text(text, reply_markup=kb)
        await query.answer()
        return

    if data == "adm:export":
        users_buf, payments_buf = export_csv()
        chat_id = query.message.chat_id if query.message else None
        if chat_id:
            await context.bot.send_document(chat_id=chat_id, document=users_buf, filename="users.csv")
            await context.bot.send_document(chat_id=chat_id, document=payments_buf, filename="payments.csv")
        await query.answer("Экспорт отправлен")
        diagnostics = await build_admin_diagnostics_report()
        text, kb = render_root(diagnostics)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        return

    if data == "adm:broadcast":
        text, kb = render_broadcast_intro()
        await query.edit_message_text(text, reply_markup=kb)
        await query.answer()
        return

    if data == "adm:close":
        try:
            await query.delete_message()
        except Exception:
            # Fallback to replace with root panel
            diagnostics = await build_admin_diagnostics_report()
            text, kb = render_root(diagnostics)
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        await query.answer()
        return

    await query.answer("Неизвестная команда")
