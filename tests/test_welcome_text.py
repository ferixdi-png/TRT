from translations import t


def test_welcome_text_contains_free_models_cta_and_many_networks_phrase():
    welcome_new = t("welcome_new", lang="ru", name="Тест")
    welcome_returning = t("welcome_returning", lang="ru", name="Тест")

    for message in (welcome_new, welcome_returning):
        assert "FERIXDI AI" in message
        assert "Фото / видео / аудио / текст" in message
        assert "параметр" in message.lower()
        assert "бесплат" in message.lower()
        assert "расширенные модели" in message.lower()
        assert "Как пользоваться" in message
