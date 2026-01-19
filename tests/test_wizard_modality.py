from bot_kie import _determine_primary_input


def test_text_to_image_does_not_require_image_input():
    model_info = {"model_mode": "text_to_image"}
    input_params = {
        "image_input": {"required": True},
        "prompt": {"required": True},
    }
    primary = _determine_primary_input(model_info, input_params)
    assert primary == {"type": "prompt", "param": "prompt"}


def test_image_edit_requires_image_input():
    model_info = {"model_mode": "image_edit"}
    input_params = {
        "image_urls": {"required": True},
        "prompt": {"required": True},
    }
    primary = _determine_primary_input(model_info, input_params)
    assert primary == {"type": "image", "param": "image_urls"}
