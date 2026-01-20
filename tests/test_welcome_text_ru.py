from app.ux.texts_ru import build_welcome_text_ru


def test_build_welcome_text_ru_contains_required_phrases():
    text = build_welcome_text_ru(
        name="Илья",
        is_new=True,
        remaining=2,
        limit_per_hour=5,
        next_refill_in=3600,
        next_refill_at_local="13:37",
        balance="120 ₽",
        compact_free_counter_hint=False,
    )
    lower_text = text.lower()

    assert "ferixdi ai" in lower_text
    assert "бесплатные модели" in lower_text
    assert "много нейронок" in lower_text
    assert "фото" in lower_text
    assert "видео" in lower_text
    assert "апскейл" in lower_text
    assert "удаление фона" in lower_text
    assert "оплата в рублях" in lower_text
    assert "выберите раздел → модель → введите параметры → подтвердите → получите файл" in lower_text
    assert "2/5" in text
    assert "3600" in text
    assert "13:37" in text


def test_build_welcome_text_ru_compact_free_counter_hint():
    text = build_welcome_text_ru(
        name="Илья",
        is_new=False,
        remaining=2,
        limit_per_hour=5,
        next_refill_in=3600,
        next_refill_at_local="13:37",
        balance=None,
        compact_free_counter_hint=True,
    )
    lower_text = text.lower()

    assert "счетчике ниже" in lower_text
    assert "2/5" not in text
    assert "3600" not in text
