"""Generation routing helpers."""
from __future__ import annotations

from typing import Any, Dict

from app.services.generation_service import GenerationService


async def submit_generation(
    user_id: int,
    model_id: str,
    model_name: str,
    params: Dict[str, Any],
    price: float,
) -> str:
    service = GenerationService()
    return await service.create_generation(
        user_id=user_id,
        model_id=model_id,
        model_name=model_name,
        params=params,
        price=price,
    )
