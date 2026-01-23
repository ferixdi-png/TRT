import builtins
import os
from types import SimpleNamespace

import pytest


def test_catalog_consistency():
    from app.kie_catalog import get_model_map
    from app.models.yaml_registry import load_yaml_models
    from app.pricing.price_ssot import list_all_models, list_model_skus
    from app.pricing.ssot_catalog import get_pricing_coverage_entry

    registry_models = load_yaml_models()
    catalog = get_model_map()
    pricing_models = list_all_models()

    assert pricing_models, "pricing SSOT must define at least one model"

    sku_ids = set()
    for model_id in pricing_models:
        assert model_id in registry_models, f"pricing model missing in registry: {model_id}"
        assert model_id in catalog, f"pricing model missing in catalog: {model_id}"
        skus = list_model_skus(model_id)
        if not skus:
            coverage = get_pricing_coverage_entry(model_id) or {}
            assert coverage, f"missing pricing coverage for model without skus: {model_id}"
            status = coverage.get("status", "UNKNOWN")
            assert status != "READY", f"model without skus must be blocked: {model_id}"
            continue
        for sku in skus:
            assert sku.sku_key not in sku_ids, f"duplicate sku_id detected: {sku.sku_key}"
            sku_ids.add(sku.sku_key)
            assert sku.price_rub is not None, f"sku missing price: {sku.sku_key}"
            assert sku.unit, f"sku missing unit: {sku.sku_key}"

    for model_id, spec in catalog.items():
        assert spec.id, "catalog model missing id"
        assert spec.description_ru, f"catalog model missing description: {model_id}"
        assert spec.type, f"catalog model missing category/type: {model_id}"
        assert spec.model_type, f"catalog model missing model_type: {model_id}"
        assert spec.model_mode, f"catalog model missing model_mode: {model_id}"


def test_menu_build_no_io(monkeypatch):
    import bot_kie

    sample_models = [{"id": "demo-model", "model_type": "text_to_image"}]
    monkeypatch.setattr(bot_kie, "_GEN_TYPE_MODELS_CACHE", {})
    monkeypatch.setattr(bot_kie, "_VISIBLE_MODEL_IDS_CACHE", {"demo-model"})
    monkeypatch.setattr(bot_kie, "get_models_cached_only", lambda: sample_models)

    def _no_open(*_args, **_kwargs):
        raise AssertionError("unexpected IO in menu build")

    monkeypatch.setattr(builtins, "open", _no_open)

    models, cache_status = bot_kie.get_visible_models_by_generation_type_cached("text-to-image")
    assert cache_status in {"hit", "miss"}
    assert [model["id"] for model in models] == ["demo-model"]


def test_db_storage_no_file_fallback(monkeypatch):
    import bot_kie

    class FakeStorage:
        def __init__(self):
            self.history = {}
            self.payments = {}

        async def add_generation_to_history(self, user_id, model_id, model_name, params, result_urls, price, operation_id=None):
            entries = self.history.setdefault(str(user_id), [])
            gen_id = f"gen_{len(entries) + 1}"
            entries.append({"id": gen_id, "model_id": model_id})
            return gen_id

        async def get_user_generations_history(self, user_id, limit=10):
            return self.history.get(str(user_id), [])[-limit:]

        async def update_json_file(self, filename, update_fn):
            self.payments = update_fn(self.payments)
            return self.payments

    fake_storage = FakeStorage()
    monkeypatch.setattr("app.storage.factory.get_storage", lambda: fake_storage)
    monkeypatch.setattr("app.config.get_settings", lambda: SimpleNamespace(get_storage_mode=lambda: "db"))
    monkeypatch.setattr(bot_kie, "add_user_balance", lambda *_args, **_kwargs: None)

    monkeypatch.setattr(os.path, "exists", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("file IO")))
    monkeypatch.setattr(builtins, "open", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("file IO")))

    gen_id = bot_kie.save_generation_to_history(
        user_id=1,
        model_id="demo",
        model_name="Demo",
        params={},
        result_urls=[],
        task_id="task-1",
        price=0.0,
    )
    assert gen_id is not None
    history = bot_kie.get_user_generations_history(1, limit=10)
    assert history

    payment = bot_kie.add_payment(1, 10.0, screenshot_file_id="dup-1")
    assert payment.get("id") is not None


def test_idempotent_payments(monkeypatch):
    import bot_kie

    class FakeStorage:
        def __init__(self):
            self.payments = {}

        async def update_json_file(self, filename, update_fn):
            self.payments = update_fn(self.payments)
            return self.payments

    fake_storage = FakeStorage()
    monkeypatch.setattr("app.storage.factory.get_storage", lambda: fake_storage)
    monkeypatch.setattr("app.config.get_settings", lambda: SimpleNamespace(get_storage_mode=lambda: "db"))

    balance_calls = []

    def _track_balance(*_args, **_kwargs):
        balance_calls.append(1)

    monkeypatch.setattr(bot_kie, "add_user_balance", _track_balance)

    first = bot_kie.add_payment(1, 15.0, screenshot_file_id="same-shot")
    second = bot_kie.add_payment(1, 15.0, screenshot_file_id="same-shot")

    assert first.get("id") == second.get("id")
    assert len(balance_calls) == 1


def test_state_machine_paths():
    from app.buttons.router_config import CALLBACK_ROUTES

    routes = {route[0] for route in CALLBACK_ROUTES}
    required = {"back_to_menu", "show_models", "show_all_models_list", "gen_type:", "category:"}
    assert required.issubset(routes)
