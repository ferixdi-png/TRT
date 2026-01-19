from app.kie_catalog import catalog


def test_catalog_cache_hits_when_key_unchanged(monkeypatch):
    catalog.reset_catalog_cache()
    calls = {"yaml": 0, "registry": 0}

    def fake_yaml():
        calls["yaml"] += 1
        return [
            {
                "id": "test-model",
                "title_ru": "Test",
                "type": "t2i",
                "modes": [{"unit": "image", "credits": 1, "official_usd": 0.1}],
            }
        ]

    def fake_registry():
        calls["registry"] += 1
        return {
            "test-model": {
                "model_type": "text_to_image",
                "input": {"prompt": {"required": True, "type": "string"}},
            }
        }

    monkeypatch.setattr(catalog, "_compute_catalog_cache_key", lambda: "cache-key")
    monkeypatch.setattr(catalog, "_load_yaml_catalog", fake_yaml)
    monkeypatch.setattr(catalog, "_load_registry_models", fake_registry)

    first = catalog.load_catalog()
    second = catalog.load_catalog()

    assert first and second
    assert calls["yaml"] == 1
    assert calls["registry"] == 1
