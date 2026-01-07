import pytest

from app.ui.input_spec import build_input_spec_from_schema


def test_z_image_spec_injects_aspect_ratio_when_missing():
    schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {"prompt": {"type": "string"}},
    }

    spec = build_input_spec_from_schema("z-image", schema)

    names = [f.name for f in spec.fields]
    assert "aspect_ratio" in names

    aspect_field = next(f for f in spec.fields if f.name == "aspect_ratio")
    assert aspect_field.required is True
    assert aspect_field.enum_values == ["1:1", "4:3", "3:4", "16:9", "9:16"]
    assert aspect_field.default == "1:1"
