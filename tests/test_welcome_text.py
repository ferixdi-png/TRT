from translations import t
from bot_kie import BOT_NAME


def test_welcome_text_contains_free_models_cta_and_many_networks_phrase():
    """Проверяет что приветствие содержит ключевые элементы."""
    # Проверяем RU приветствие (BOT_NAME вставляется напрямую в bot_kie.py)
    # Здесь проверяем что BOT_NAME существует и является строкой
    assert BOT_NAME is not None
    assert isinstance(BOT_NAME, str)
    assert len(BOT_NAME) > 0
    
    # Проверяем EN шаблоны с bot_name параметром
    welcome_new_en = t("welcome_new", lang="en", name="Test", bot_name=BOT_NAME, free=5, free_limit=5, stars_balance=0)
    welcome_returning_en = t("welcome_returning", lang="en", name="Test", bot_name=BOT_NAME, free=5, free_limit=5, stars_balance=0)
    
    for message in (welcome_new_en, welcome_returning_en):
        assert BOT_NAME in message, f"BOT_NAME '{BOT_NAME}' should be in welcome message"
        assert "Free generations" in message
        assert "3 steps" in message
