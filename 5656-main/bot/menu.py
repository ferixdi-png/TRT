"""Menu builders decoupled from aiogram for smoke tests."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_models_catalog() -> list[dict]:
    yaml_path = Path(__file__).resolve().parents[1] / "models" / "kie_models.yaml"
    if not yaml_path.exists():
        logger.warning("[CATALOG] YAML file not found: %s", yaml_path)
        return []
    text = yaml_path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        payload = yaml.safe_load(text) or {}
        return payload.get("models", []) or []
    except Exception as exc:
        logger.warning("[CATALOG] YAML parse failed (%s), using fallback parser", exc)
        models = []
        current = {}
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("- model_id:"):
                if current:
                    models.append(current)
                current = {"model_id": line.split(":", 1)[1].strip()}
            elif line.startswith("name:") and current:
                current["name"] = line.split(":", 1)[1].strip()
        if current:
            models.append(current)
        return models


def build_main_menu_data() -> tuple[str, list[tuple[str, str]]]:
    text = (
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Выберите раздел из главного меню ниже."
    )
    buttons = [
        ("📦 Каталог моделей", "catalog"),
        ("⚡ Быстрые действия", "quick:menu"),
        ("💰 Баланс", "balance"),
        ("🧾 История", "history"),
        ("🆘 Поддержка", "support"),
    ]
    return text, buttons


def build_catalog_text(limit: int = 20) -> str:
    models = load_models_catalog()
    if not models:
        return "Каталог пока недоступен."
    lines = ["📦 <b>Каталог моделей</b>", ""]
    for model in models[:limit]:
        name = model.get("name") or model.get("model_id")
        model_id = model.get("model_id", "")
        lines.append(f"• {name} ({model_id})")
    lines.append("")
    lines.append(f"Показаны первые {min(limit, len(models))} моделей из YAML.")
    return "\n".join(lines)
