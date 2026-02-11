import yaml
from pathlib import Path

from app.helpers.copy import build_step1_prompt_text, get_model_short, get_sku_short
from app.model_descriptions import format_intro_card
from app.kie_contract.schema_loader import list_model_ids
from app.pricing.ssot_catalog import list_model_skus


MODEL_COPY_PATH = Path(__file__).resolve().parents[1] / "app" / "models" / "model_copy.yaml"


def _load_model_copy():
    return yaml.safe_load(MODEL_COPY_PATH.read_text(encoding="utf-8"))


def test_build_step1_prompt_includes_model_and_sku():
    model_id = "z-image"
    sku = list_model_skus(model_id)[0]
    billing_ctx = {
        "price_text": "Цена по прайсу: 1.00 ₽",
        "price_rub": "1.00",
        "is_free": False,
    }

    text = build_step1_prompt_text(model_id, sku, billing_ctx, admin_flag=False)

    # Intro card title from model_descriptions.yaml is embedded
    from app.model_descriptions import get_model_description
    desc = get_model_description(model_id)
    title = desc.get("title") or model_id
    assert title in text
    # Prompt instruction present
    assert "Опиши что хочешь получить" in text
    # Price present
    assert "1.00" in text


def test_build_step1_prompt_has_example():
    model_id = "z-image"
    sku = list_model_skus(model_id)[0]
    billing_ctx = {
        "price_text": "Цена по прайсу: 1.00 ₽",
        "price_rub": "1.00",
        "is_free": False,
    }

    text = build_step1_prompt_text(model_id, sku, billing_ctx, admin_flag=False)

    assert "Пример:" in text


def test_build_step1_prompt_admin_free_sets_price_zero(caplog):
    model_id = "z-image"
    sku = list_model_skus(model_id)[0]
    billing_ctx = {
        "price_text": "Цена по прайсу: 10.00 ₽",
        "price_rub": "10.00",
        "is_free": False,
    }

    with caplog.at_level("INFO"):
        text = build_step1_prompt_text(
            model_id,
            sku,
            billing_ctx,
            admin_flag=True,
            correlation_id="corr-test",
        )

    assert "👑 Админ: безлимитные генерации (квота не расходуется)." in text
    assert any("price_rub=0" in record.message for record in caplog.records)


def test_model_copy_covers_registry_ids():
    model_copy = _load_model_copy()
    missing = [model_id for model_id in list_model_ids() if model_id not in model_copy]
    assert not missing


def test_model_short_fallback_logs(caplog):
    with caplog.at_level("INFO"):
        text = get_model_short("unknown/test-model")

    assert text
    assert any("fallback_used=true" in record.message for record in caplog.records)
