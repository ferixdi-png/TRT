from __future__ import annotations

from app.ux import model_visibility as mv


def test_default_unsupported_model_is_blocked() -> None:
    mv._unsupported_models.cache_clear()
    result = mv.evaluate_model_visibility("openai/4o-image")
    assert result.status == mv.STATUS_BLOCKED_UNSUPPORTED
    assert result.issues


def test_env_unsupported_models_extend_blocklist(monkeypatch) -> None:
    monkeypatch.setenv("KIE_UNSUPPORTED_MODELS", "custom/model, another/model ")
    mv._unsupported_models.cache_clear()
    result = mv.evaluate_model_visibility("custom/model")
    assert result.status == mv.STATUS_BLOCKED_UNSUPPORTED

    # Cleanup cache for other tests that may rely on default state.
    mv._unsupported_models.cache_clear()
