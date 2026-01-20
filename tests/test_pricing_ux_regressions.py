from app.helpers.models_menu import build_model_card_text
from app.kie_catalog import get_model
from app.pricing.ssot_catalog import format_pricing_blocked_message
from bot_kie import build_option_confirm_text


def test_model_card_shows_from_price():
    model = get_model("z-image")
    assert model is not None
    text, _ = build_model_card_text(model, user_lang="ru")
    assert "от" in text
    assert "₽" in text


def test_option_confirm_text_includes_option_price():
    text = build_option_confirm_text("en", "Duration", "10", 12.34)
    assert "This option:" in text
    assert "12.34 ₽" in text


def test_blocked_message_links_to_coverage_report():
    text = format_pricing_blocked_message("midjourney/api", user_lang="ru")
    assert "PRICING_COVERAGE.md#model-midjourney-api" in text
