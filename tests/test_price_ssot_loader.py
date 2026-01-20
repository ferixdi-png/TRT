from decimal import Decimal
from types import SimpleNamespace

import pytest
import yaml

import bot_kie
from app.helpers.models_menu import build_model_card_text
from app.pricing import price_ssot
from app.pricing.price_ssot import get_price_for_params, list_free_sku_keys, reset_price_ssot_cache
from app.ux.model_visibility import evaluate_model_visibility, STATUS_HIDDEN_NO_INSTRUCTIONS
from tests.ptb_harness import PTBHarness


def test_price_ssot_loader_parses_fixed_price_file():
    price = get_price_for_params("seedream/4.5-text-to-image", {"quality": "basic"})
    assert price == Decimal("5.11")


def test_model_card_shows_min_price_from_ssot():
    from app.kie_catalog import get_model
    model_obj = get_model("seedream/4.5-text-to-image")
    assert model_obj is not None
    card_text, _ = build_model_card_text(model_obj, mode_index=0, user_lang="ru")
    assert "от 5.11 ₽" in card_text


@pytest.mark.asyncio
async def test_param_buttons_include_price_labels():
    harness = PTBHarness()
    await harness.setup()
    user_id = 3101
    update = harness.create_mock_update_command("/start", user_id=user_id)
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    bot_kie.user_sessions[user_id] = {
        "model_id": "seedream/4.5-text-to-image",
        "model_info": {"name": "Seedream 4.5", "model_type": "text_to_image"},
        "properties": {
            "quality": {
                "type": "enum",
                "required": True,
                "enum": ["basic", "high"],
            }
        },
        "required": ["quality"],
        "skipped_params": set(),
        "params": {},
    }

    try:
        await bot_kie.prompt_for_specific_param(update, context, user_id, "quality", source="test")
        message = harness.outbox.get_last_message()
        buttons = [button.text for row in message["reply_markup"].inline_keyboard for button in row]
        assert any("— 5.11₽" in text for text in buttons)
    finally:
        bot_kie.user_sessions.pop(user_id, None)
        await harness.teardown()


def test_free_is_sku_only(monkeypatch, tmp_path):
    mock_data = {
        "models": [
            {
                "id": "test-model",
                "skus": [
                    {"params": {"mode": "free"}, "price_rub": 0, "unit": "image", "free": True},
                    {"params": {"mode": "paid"}, "price_rub": 10, "unit": "image"},
                ],
            }
        ]
    }
    mock_path = tmp_path / "pricing.yaml"
    mock_path.write_text(yaml.safe_dump(mock_data, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(price_ssot, "PRICING_SSOT_PATH", mock_path)
    reset_price_ssot_cache()
    free_skus = list_free_sku_keys()
    reset_price_ssot_cache()
    assert free_skus == ["test-model::mode=free"]


def test_hide_model_if_not_in_model_ssot(monkeypatch, tmp_path):
    mock_data = {"models": [{"id": "ghost-model", "skus": [{"params": {}, "price_rub": 1.0, "unit": "request"}]}]}
    mock_path = tmp_path / "pricing.yaml"
    mock_path.write_text(yaml.safe_dump(mock_data, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(price_ssot, "PRICING_SSOT_PATH", mock_path)
    reset_price_ssot_cache()

    result = evaluate_model_visibility("ghost-model")
    reset_price_ssot_cache()
    assert result.status == STATUS_HIDDEN_NO_INSTRUCTIONS
