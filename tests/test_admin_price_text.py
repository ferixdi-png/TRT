from bot_kie import format_price_rub


def test_admin_price_text_includes_unlimited_message():
    text = format_price_rub(10.0, is_admin=True)

    assert "🎁 Админ: безлимитные генерации (квота не расходуется)." in text
