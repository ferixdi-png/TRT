"""Unified user-facing status messages for generation pipeline."""
from __future__ import annotations

from typing import Optional


def _corr_suffix(correlation_id: Optional[str]) -> str:
    value = (correlation_id or "corr-na-na").strip()
    if not value:
        return "corr-na-na"
    return value


def build_start_message(model_name: str, correlation_id: Optional[str], *, lang: str) -> str:
    corr = _corr_suffix(correlation_id)
    if lang == "ru":
        return (
            "🚀 <b>Старт генерации</b>\n\n"
            f"🤖 <b>Модель:</b> {model_name}\n"
            f"🧾 <b>ID:</b> <code>{corr}</code>\n\n"
            "Создаю задачу и ставлю её в очередь…"
        )
    return (
        "🚀 <b>Generation started</b>\n\n"
        f"🤖 <b>Model:</b> {model_name}\n"
        f"🧾 <b>ID:</b> <code>{corr}</code>\n\n"
        "Creating the task and placing it in the queue…"
    )


def build_queued_message(model_name: str, correlation_id: Optional[str], *, lang: str) -> str:
    corr = _corr_suffix(correlation_id)
    if lang == "ru":
        return (
            "📥 <b>Задача в очереди</b>\n\n"
            f"🤖 <b>Модель:</b> {model_name}\n"
            f"🧾 <b>ID:</b> <code>{corr}</code>\n\n"
            "Как только очередь подойдёт — начну обработку."
        )
    return (
        "📥 <b>Task queued</b>\n\n"
        f"🤖 <b>Model:</b> {model_name}\n"
        f"🧾 <b>ID:</b> <code>{corr}</code>\n\n"
        "I'll start processing as soon as the queue advances."
    )


def build_waiting_message(model_name: str, correlation_id: Optional[str], *, lang: str, state_hint: Optional[str] = None) -> str:
    corr = _corr_suffix(correlation_id)
    state_line = ""
    if state_hint:
        state_line = (
            f"\n📊 <b>Статус:</b> {state_hint}" if lang == "ru" else f"\n📊 <b>Status:</b> {state_hint}"
        )
    if lang == "ru":
        return (
            "⏳ <b>Обрабатываю запрос</b>\n\n"
            f"🤖 <b>Модель:</b> {model_name}{state_line}\n"
            f"🧾 <b>ID:</b> <code>{corr}</code>\n\n"
            "Я слежу за задачей и пришлю результат сюда."
        )
    return (
        "⏳ <b>Processing your request</b>\n\n"
        f"🤖 <b>Model:</b> {model_name}{state_line}\n"
        f"🧾 <b>ID:</b> <code>{corr}</code>\n\n"
        "I'm monitoring the task and will deliver the result here."
    )


def build_delivery_message(model_name: str, correlation_id: Optional[str], *, lang: str) -> str:
    corr = _corr_suffix(correlation_id)
    if lang == "ru":
        return (
            "📤 <b>Доставляю результат</b>\n\n"
            f"🤖 <b>Модель:</b> {model_name}\n"
            f"🧾 <b>ID:</b> <code>{corr}</code>\n\n"
            "Загружаю файл в Telegram…"
        )
    return (
        "📤 <b>Delivering the result</b>\n\n"
        f"🤖 <b>Model:</b> {model_name}\n"
        f"🧾 <b>ID:</b> <code>{corr}</code>\n\n"
        "Uploading the file to Telegram…"
    )


def build_error_message(correlation_id: Optional[str], *, lang: str, hint: Optional[str] = None) -> str:
    corr = _corr_suffix(correlation_id)
    hint_line = f"\n\n💡 {hint}" if hint else ""
    if lang == "ru":
        return (
            "⚠️ <b>Не удалось завершить генерацию</b>\n\n"
            f"🧾 <b>ID:</b> <code>{corr}</code>{hint_line}\n\n"
            "Попробуйте ещё раз или выберите другую модель."
        )
    return (
        "⚠️ <b>Generation failed</b>\n\n"
        f"🧾 <b>ID:</b> <code>{corr}</code>{hint_line}\n\n"
        "Please try again or choose another model."
    )
