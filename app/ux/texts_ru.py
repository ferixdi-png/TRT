"""RU UX text helpers for model cards and confirmations."""
from __future__ import annotations

from typing import List, Optional


def build_model_card(
    model_name: str,
    model_id: str,
    price_text: str,
    required_fields: List[str],
    examples: List[str],
) -> str:
    required_block = "\n".join(f"• {field}" for field in required_fields) if required_fields else "—"
    examples_block = "\n".join(f"• {example}" for example in examples) if examples else "—"
    return (
        f"<b>{model_name}</b>\n"
        f"<code>{model_id}</code>\n\n"
        f"💳 <b>Цена:</b> {price_text}\n"
        f"🧩 <b>Обязательные поля:</b>\n{required_block}\n\n"
        f"📌 <b>Примеры:</b>\n{examples_block}"
    )


def build_confirm_summary(model_name: str, price_text: str, summary: str) -> str:
    return (
        f"✅ <b>Подтверждение</b>\n\n"
        f"Модель: <b>{model_name}</b>\n"
        f"Цена: <b>{price_text}</b>\n\n"
        f"{summary}"
    )


def build_welcome_text_ru(
    *,
    name: str,
    is_new: bool,
    remaining: int,
    limit_per_hour: int,
    next_refill_in: int,
    next_refill_at_local: str,
    balance: Optional[str] = None,
    compact_free_counter_hint: bool = False,
) -> str:
    greeting = "Привет" if is_new else "С возвращением"
    lines = [
        f"👋 <b>{greeting}, {name}!</b>",
        "FERIXDI AI — уже запущенный и стабильно работающий бот для генерации контента.",
        "Бесплатные модели + очень много нейронок: фото, видео, апскейл, удаление фона и другие задачи.",
        "Бот честно показывает, сколько бесплатных генераций осталось и когда они восстановятся "
        "(через час после использования / таймер).",
        "UX: выберите раздел → модель → введите параметры → подтвердите → получите файл.",
        "Оплата в рублях доступна как опция, но основной фокус — бесплатные модели.",
    ]

    if compact_free_counter_hint:
        lines.append("🆓 Остаток бесплатных и время восстановления — в счетчике ниже.")
    else:
        lines.append(
            "🆓 Бесплатно сейчас: "
            f"{remaining}/{limit_per_hour} · таймер {next_refill_in} сек (в {next_refill_at_local})."
        )

    if balance:
        lines.append(f"💳 Баланс: {balance}")

    return "\n".join(lines)
