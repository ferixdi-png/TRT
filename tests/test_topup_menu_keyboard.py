from bot_kie import _build_topup_menu_keyboard


def _labels(markup):
    keyboard = getattr(markup, "inline_keyboard", [])
    return [button.text for row in keyboard for button in row]


def test_topup_menu_keyboard_includes_main_menu_ru():
    markup = _build_topup_menu_keyboard("ru")
    labels = _labels(markup)
    assert any("Главное меню" in label for label in labels)


def test_topup_menu_keyboard_includes_main_menu_en():
    markup = _build_topup_menu_keyboard("en")
    labels = _labels(markup)
    assert any("Main Menu" in label for label in labels)
