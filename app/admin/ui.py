from __future__ import annotations
from typing import Any, Dict, List, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def admin_root_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("👥 Пользователи", callback_data="adm:users")],
        [InlineKeyboardButton("💳 Платежи", callback_data="adm:payments")],
        [InlineKeyboardButton("📊 Статистика", callback_data="adm:stats")],
        [InlineKeyboardButton("📦 Экспорт CSV", callback_data="adm:export")],
        [InlineKeyboardButton("📣 Рассылка", callback_data="adm:broadcast")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="adm:close")],
    ]
    return InlineKeyboardMarkup(rows)


def render_root() -> Tuple[str, InlineKeyboardMarkup]:
    text = (
        "Админ-панель\n\n"
        "Выберите раздел:"
    )
    return text, admin_root_kb()


def render_users(summary: Dict[str, Any]) -> Tuple[str, InlineKeyboardMarkup]:
    lines: List[str] = [
        "👥 Пользователи",
        f"Всего: {summary['total']}",
        f"Новых за 24ч: {summary['new_24h']}",
        f"Новых за 7д: {summary['new_7d']}",
        "",
    ]
    for u in summary.get("users", []):
        uname = u.get("username") or "—"
        lines.append(f"• {u['user_id']} (@{uname})")
    text = "\n".join(lines)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="adm:root")]])
    return text, kb


def render_payments(summary: Dict[str, Any]) -> Tuple[str, InlineKeyboardMarkup]:
    lines: List[str] = [
        "💳 Платежи",
        f"Сумма всего: {summary['total_sum']}",
        f"За 24ч: {summary['sum_24h']}",
        f"За 7д: {summary['sum_7d']}",
        f"За 30д: {summary['sum_30d']}",
        "",
        "Последние транзакции:",
    ]
    for p in summary.get("latest", [])[:10]:
        lines.append(f"• {p.get('user_id')} +{p.get('amount')} ({p.get('status','')})")
    text = "\n".join(lines)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="adm:root")]])
    return text, kb


def render_stats(summary: Dict[str, Any]) -> Tuple[str, InlineKeyboardMarkup]:
    lines: List[str] = [
        "📊 Статистика (24ч)",
        f"Успешных: {summary['success_24h']}",
        f"Ошибок: {summary['error_24h']}",
        "Топ-модели:",
    ]
    for mid, cnt in summary.get("top_models", []):
        lines.append(f"• {mid}: {cnt}")
    text = "\n".join(lines)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="adm:root")]])
    return text, kb


def render_broadcast_intro() -> Tuple[str, InlineKeyboardMarkup]:
    text = (
        "📣 Рассылка\n\n"
        "Отправьте текст сообщения для рассылки всем пользователям.\n"
        "Для отмены вернитесь назад."
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="adm:root")]])
    return text, kb
