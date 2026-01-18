from app.config import get_settings


def test_settings_has_storage_mode():
    settings = get_settings()
    assert settings.storage_mode
