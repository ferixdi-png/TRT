"""Image input adapter for KIE payloads."""
from __future__ import annotations

from typing import Any, Dict, Optional

IMAGE_INPUT_MAPPINGS = {
    "recraft/remove-background": "image",
    "recraft/crisp-upscale": "image",
    "ideogram/v3-reframe": "image_url",
    "topaz/image-upscale": "image_url",
}


def _normalize_image_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, list):
        for item in value:
            if item:
                return str(item)
        return None
    if value == "":
        return None
    return str(value)


def adapt_image_input(model_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Adapt image_input arrays into model-specific KIE fields."""
    if "image_input" not in params:
        return dict(params)

    target_field = IMAGE_INPUT_MAPPINGS.get(model_id)
    if not target_field:
        return dict(params)

    adapted = dict(params)
    raw_value = adapted.pop("image_input", None)
    normalized = _normalize_image_value(raw_value)
    if normalized:
        adapted[target_field] = normalized
    return adapted
