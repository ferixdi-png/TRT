from translations import t


def test_welcome_text_contains_free_models_cta_and_many_networks_phrase():
    welcome_new = t("welcome_new", lang="ru", name="Тест")
    welcome_returning = t("welcome_returning", lang="ru", name="Тест")

    for message in (welcome_new, welcome_returning):
        assert "Бесплатные модели" in message
        assert "много нейросетей" in message.lower()
