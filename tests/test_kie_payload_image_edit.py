from app.kie_catalog import get_model_map
from app.kie_contract.payload_builder import build_kie_payload


def test_recraft_remove_background_payload_maps_image_input():
    model_spec = get_model_map()["recraft/remove-background"]
    payload = build_kie_payload(
        model_spec,
        {"image_input": ["https://example.com/image.png"]},
    )

    assert payload["model"] == model_spec.kie_model
    assert payload["input"]["image"] == "https://example.com/image.png"
    assert "image_input" not in payload["input"]
