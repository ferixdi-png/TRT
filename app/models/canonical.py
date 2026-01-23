"""Canonicalization helpers for model and KIE identifiers."""
from __future__ import annotations

from typing import Dict, List


MODEL_ID_ALIASES: Dict[str, str] = {
    "sora-2/t2v": "sora-2-text-to-video",
    "openai/sora-2-text-to-video": "sora-2-text-to-video",
    "sora-2/i2v": "sora-2-image-to-video",
    "openai/sora-2-image-to-video": "sora-2-image-to-video",
    "sora-2-pro/t2v": "sora-2-pro-text-to-video",
    "openai/sora-2-pro-text-to-video": "sora-2-pro-text-to-video",
    "sora-2-pro/i2v": "sora-2-pro-image-to-video",
    "openai/sora-2-pro-image-to-video": "sora-2-pro-image-to-video",
    "sora-2-watermark-remover": "sora-watermark-remover",
    "openai/sora-2-watermark-remover": "sora-watermark-remover",
    "openai/sora-watermark-remover": "sora-watermark-remover",
}


def canonicalize_model_id(model_id: str) -> str:
    if not model_id:
        return ""
    return MODEL_ID_ALIASES.get(model_id, model_id)


def canonicalize_kie_model(kie_model: str) -> str:
    if not kie_model:
        return ""
    return MODEL_ID_ALIASES.get(kie_model, kie_model)


def validate_alias_registry() -> List[str]:
    errors: List[str] = []
    reverse: Dict[str, str] = {}
    for alias, canonical in MODEL_ID_ALIASES.items():
        if alias == canonical:
            errors.append(f"alias '{alias}' points to itself")
        existing = reverse.get(alias)
        if existing and existing != canonical:
            errors.append(f"alias '{alias}' maps to both '{existing}' and '{canonical}'")
        reverse[alias] = canonical
    return errors
