from app.kie_catalog import get_free_tools_model_ids, get_model_map
from app.models.registry import get_models_sync


def test_free_menu_has_five_non_audio_models():
    model_ids = get_free_tools_model_ids()
    assert len(model_ids) == 5

    registry_ids = {m.get("id") for m in get_models_sync()}
    catalog = get_model_map()
    audio_types = {"tts", "stt", "sfx", "audio_isolation", "music", "lip_sync"}

    for model_id in model_ids:
        assert model_id in registry_ids
        assert model_id in catalog
        spec = catalog[model_id]
        model_mode = (spec.model_mode or spec.model_type or "").lower()
        assert spec.type not in audio_types
        assert "audio" not in model_id.lower()
        assert "audio" not in model_mode
        assert "speech" not in model_mode
