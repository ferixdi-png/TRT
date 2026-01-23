import json
from pathlib import Path

from app.kie_contract.schema_loader import list_model_ids
from app.pricing.price_resolver import resolve_price_quote
from app.pricing.price_ssot import list_all_models, list_model_skus


COVERAGE_PATH = Path(__file__).resolve().parents[1] / "PRICING_COVERAGE.json"


def test_registry_models_have_coverage_entry():
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8")).get("models", {})
    missing = [model_id for model_id in list_model_ids() if model_id not in coverage]
    assert not missing, f"Missing coverage entries: {missing}"


def test_price_resolver_matches_all_skus():
    for model_id in list_all_models():
        skus = list_model_skus(model_id)
        for sku in skus:
            quote = resolve_price_quote(
                model_id=model_id,
                mode_index=0,
                gen_type=None,
                selected_params=sku.params,
            )
            assert quote is not None, f"No quote for {model_id} params {sku.params}"
            assert quote.sku_id == sku.sku_key, f"SKU mismatch for {model_id}: {quote.sku_id} != {sku.sku_key}"


def test_sora_2_text_to_video_default_sku_resolves():
    quote = resolve_price_quote(
        model_id="sora-2-text-to-video",
        mode_index=0,
        gen_type="text-to-video",
        selected_params={},
    )
    assert quote is not None
    assert quote.sku_id == "sora-2-text-to-video::n_frames=10"


def test_pricing_coverage_sora_2_text_to_video_ready():
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8")).get("models", {})
    entry = coverage.get("sora-2-text-to-video")
    assert entry is not None
    assert entry.get("status") == "READY"
    assert entry.get("missing_skus", []) == []
