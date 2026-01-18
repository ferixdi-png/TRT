"""RU UX text helpers for model cards and confirmations."""
from __future__ import annotations

from typing import List


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
