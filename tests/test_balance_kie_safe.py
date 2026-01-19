import helpers


async def test_balance_info_no_kie_credits(monkeypatch, test_env):
    helpers.set_constants(3, 3, 12345)
    helpers._init_imports()
    monkeypatch.setattr(helpers, "_get_client", lambda: object())

    balance_info = await helpers.get_balance_info(12345, "ru")
    message = await helpers.format_balance_message(balance_info, "ru")

    assert "внутренний баланс доступен" in message.lower()
    assert "ошибка" not in message.lower()
