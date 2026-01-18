from bot_kie import is_known_callback_data


def test_callbacks_gen_type_are_routed_not_fallback():
    assert is_known_callback_data("gen_type:text-to-image")
    assert is_known_callback_data("gen_type:image-to-image")
    assert is_known_callback_data("gen_type:text-to-video")
    assert is_known_callback_data("gen_type:image-edit")
