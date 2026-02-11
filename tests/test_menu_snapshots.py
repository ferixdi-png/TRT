import pytest

from bot_kie import _build_free_tools_keyboard
from helpers import build_main_menu_keyboard
from app.kie_catalog.catalog import get_free_tools_model_ids
from app.models.registry import get_models_sync
from app.pricing.ssot_catalog import get_sku_by_id


def _serialize_rows(rows):
    return [
        [(button.text, button.callback_data) for button in row]
        for row in rows
    ]


@pytest.mark.asyncio
async def test_main_menu_keyboard_snapshot():
    keyboard_rows = await build_main_menu_keyboard(user_id=123, user_lang="ru", is_new=False)
    snapshot = _serialize_rows(keyboard_rows)
    assert snapshot == [
        [("🔥 Топ модели", "top_models")],
        [("⚡ Бесплатные генерации", "fast_tools")],
        [("🖼️ Текст → Фото", "gen_type:text-to-image")],
        [("🧩 Редактор фото", "gen_type:image-to-image")],
        [("🎬 Видео по сценарию", "gen_type:text-to-video")],
        [("🎬 Фото → Видео", "gen_type:image-to-video")],
        [("🧰 Другие модели", "special_tools")],
        [("💳 Баланс / Доступ", "check_balance")],
        [("🤝 Партнёрка", "referral_info")],
        [("🌐 Язык / Language", "change_language")],
    ]


def test_free_tools_menu_keyboard_snapshot():
    free_ids = get_free_tools_model_ids(log_selection=False)
    models_map = {model["id"]: model for model in get_models_sync()}
    free_skus = [get_sku_by_id(sku_id) for sku_id in free_ids]
    free_skus = [sku for sku in free_skus if sku and sku.model_id in models_map]
    markup, _count = _build_free_tools_keyboard(
        free_skus=free_skus,
        models_map=models_map,
        user_lang="ru",
    )
    snapshot = _serialize_rows(markup.inline_keyboard)
    # At least one SKU row + back button row
    assert len(snapshot) >= 2, f"Expected at least 2 rows, got {len(snapshot)}"
    # Last row is back-to-menu
    assert snapshot[-1] == [("◀️ Главное меню", "back_to_menu")]
    # All non-back buttons have sku: prefix
    for row in snapshot[:-1]:
        for text, cb in row:
            assert cb.startswith("sku:"), f"Expected sku: callback, got {cb}"
            assert text, "Button text must not be empty"
