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
        [("🆓 FAST TOOLS", "free_tools")],
        [("🎨 Генерация визуала", "gen_type:text-to-image")],
        [("🧩 Ремикс изображения", "gen_type:image-to-image")],
        [("🎬 Видео по сценарию", "gen_type:text-to-video")],
        [("🎞️ Анимировать изображение", "gen_type:image-to-video")],
        [("🧰 Спец-инструменты", "other_models")],
        [("💳 Баланс / Доступ", "check_balance")],
        [("🤝 Партнёрка", "referral_info")],
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
    assert snapshot == [
        [
            ("⚡ Google Imagen 4 Fast (default)", "sku:google/imagen4-fast::default"),
            ("🍌 Google Nano Banana (default)", "sku:google/nano-banana::default"),
        ],
        [
            ("✨ Ideogram V3 Text-to-Image (speed=TURBO)", "sku:ideogram/v3-text-to-image::rendering_speed=TURBO"),
            ("🎨 Seedream 3.0 (default)", "sku:bytedance/seedream::default"),
        ],
        [
            ("🖼️ Z-Image (AR 16:9)", "sku:z-image::aspect_ratio=16:9"),
            ("🖼️ Z-Image (AR 1:1)", "sku:z-image::aspect_ratio=1:1"),
        ],
        [
            ("🖼️ Z-Image (AR 3:4)", "sku:z-image::aspect_ratio=3:4"),
            ("🖼️ Z-Image (AR 4:3)", "sku:z-image::aspect_ratio=4:3"),
        ],
        [("🖼️ Z-Image (AR 9:16)", "sku:z-image::aspect_ratio=9:16")],
        [("◀️ Главное меню", "back_to_menu")],
    ]
