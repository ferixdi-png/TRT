"""Copy helpers for model and SKU short descriptions."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml

from app.kie_contract.schema_loader import get_model_meta
from app.observability.structured_logs import log_structured_event
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

_COPY_PATH = Path(__file__).resolve().parents[1] / "models" / "model_copy.yaml"


@lru_cache(maxsize=1)
def _load_model_copy() -> Dict[str, Any]:
    if not _COPY_PATH.exists():
        logger.warning("model_copy.yaml missing at %s", _COPY_PATH)
        return {}
    with _COPY_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def _model_type_description(model_type: str) -> str:
    mapping = {
        "text_to_image": "Генерация изображений по тексту",
        "image_to_image": "Преобразование изображений по описанию",
        "image_edit": "Редактирование изображений по запросу",
        "outpaint": "Расширение изображений по описанию",
        "upscale": "Увеличение разрешения изображения",
        "text_to_video": "Генерация видео по тексту",
        "image_to_video": "Анимация изображения в видео",
        "video_upscale": "Улучшение качества видео",
        "video_editing": "Редактирование видео",
        "speech_to_video": "Видео по голосу",
        "lip_sync": "Синхронизация губ с аудио",
        "text_to_speech": "Озвучка текста",
        "text_to_audio": "Генерация аудио по тексту",
        "audio_to_audio": "Обработка аудио",
        "speech_to_text": "Распознавание речи в текст",
        "text": "Генерация текста",
    }
    return mapping.get(model_type, "Генерация результата по запросу")


def _extract_brand(model_id: str) -> str:
    if "/" in model_id:
        return model_id.split("/", 1)[0]
    if "-" in model_id:
        return model_id.split("-", 1)[0]
    return model_id


def _resolve_model_short(model_id: str, correlation_id: str | None) -> Tuple[str, bool, str | None]:
    copy = _load_model_copy()
    entry = copy.get(model_id)
    if isinstance(entry, dict) and entry.get("model_short"):
        return str(entry["model_short"]), False, None

    meta = get_model_meta(model_id) or {}
    model_type = str(meta.get("model_type") or "").lower()
    description = _model_type_description(model_type)
    brand = _extract_brand(model_id).replace("_", " ").title()
    fallback_text = f"{brand}: {description}. Подходит, чтобы быстро попробовать результат."
    reason = "missing_model_short"
    log_structured_event(
        correlation_id=correlation_id,
        action="MODEL_COPY_FALLBACK",
        model_id=model_id,
        outcome="used",
        param={"fallback_used": True, "reason": reason},
    )
    logger.info(
        "MODEL_COPY_FALLBACK fallback_used=true model_id=%s reason=%s correlation_id=%s",
        model_id,
        reason,
        correlation_id,
    )
    return fallback_text, True, reason


def get_model_short(model_id: str) -> str:
    text, _, _ = _resolve_model_short(model_id, None)
    return text


def _normalize_sku_params(sku: Any) -> Dict[str, Any]:
    if sku is None:
        return {}
    if isinstance(sku, dict):
        return dict(sku.get("params") or sku)
    params = getattr(sku, "params", None)
    if isinstance(params, dict):
        return dict(params)
    return {}


def _resolve_sku_key(sku: Any) -> str | None:
    if sku is None:
        return None
    if isinstance(sku, dict):
        return sku.get("sku_id") or sku.get("sku_key")
    return getattr(sku, "sku_id", None) or getattr(sku, "sku_key", None)


def _build_sku_placeholders(params: Dict[str, Any]) -> Dict[str, str | None]:
    duration = params.get("duration")
    n_frames = params.get("n_frames")
    resolution = params.get("resolution") or params.get("size")
    sound = params.get("sound")
    rendering_speed = params.get("rendering_speed")
    quality = params.get("quality")
    upscale = params.get("upscale_factor")

    if n_frames is not None and duration is None:
        duration_value = f"{n_frames} кадров"
    elif duration is not None:
        duration_value = f"{duration} сек"
    else:
        duration_value = None

    audio_value = None
    if sound is not None:
        audio_value = "с аудио" if str(sound).lower() in {"true", "1", "yes"} else "без аудио"

    mode_value = rendering_speed or quality

    scale_value = f"x{upscale}" if upscale is not None else None

    return {
        "duration": duration_value,
        "resolution": str(resolution) if resolution is not None else None,
        "audio": audio_value,
        "mode": str(mode_value) if mode_value is not None else None,
        "scale": scale_value,
        "format": None,
        "limit": None,
    }


def _render_template(template: str, placeholders: Dict[str, str | None]) -> str:
    if "{" not in template:
        return template.strip()
    segments = [segment.strip() for segment in template.split("•")]
    rendered = []
    placeholder_pattern = re.compile(r"\{(\w+)\}")
    for segment in segments:
        keys = placeholder_pattern.findall(segment)
        if not keys:
            rendered.append(segment)
            continue
        if any(not placeholders.get(key) for key in keys):
            continue
        rendered.append(segment.format(**placeholders))
    return " • ".join([seg for seg in rendered if seg])


def _resolve_sku_short(
    model_id: str,
    sku: Any,
    correlation_id: str | None,
) -> Tuple[str, bool, str | None]:
    copy = _load_model_copy()
    entry = copy.get(model_id) or {}
    templates = entry.get("sku_templates") if isinstance(entry, dict) else {}
    sku_key = _resolve_sku_key(sku)
    template = None
    if isinstance(templates, dict):
        by_key = templates.get("by_sku_key") or {}
        if sku_key and isinstance(by_key, dict):
            template = by_key.get(sku_key)
        if not template:
            template = templates.get("default")

    if not template:
        template = "Длительность: {duration} • Разрешение: {resolution} • Аудио: {audio} • Режим: {mode} • Масштаб: {scale} • Формат: {format} • Лимит: {limit}"

    placeholders = _build_sku_placeholders(_normalize_sku_params(sku))
    rendered = _render_template(str(template), placeholders)
    if rendered:
        return rendered, False, None

    reason = "missing_sku_params"
    fallback_text = "SKU: параметры не заданы"
    log_structured_event(
        correlation_id=correlation_id,
        action="MODEL_COPY_FALLBACK",
        model_id=model_id,
        sku_id=sku_key,
        outcome="used",
        param={"fallback_used": True, "reason": reason},
    )
    logger.info(
        "MODEL_COPY_FALLBACK fallback_used=true model_id=%s reason=%s correlation_id=%s",
        model_id,
        reason,
        correlation_id,
    )
    return fallback_text, True, reason


def get_sku_short(model_id: str, sku: Any) -> str:
    text, _, _ = _resolve_sku_short(model_id, sku, None)
    return text


def build_step1_prompt_text(
    model_id: str,
    sku: Any,
    billing_ctx: Dict[str, Any],
    admin_flag: bool,
    *,
    correlation_id: str | None = None,
) -> str:
    model_short, model_fallback, _ = _resolve_model_short(model_id, correlation_id)
    sku_short, sku_fallback, _ = _resolve_sku_short(model_id, sku, correlation_id)

    price_text = billing_ctx.get("price_text") if isinstance(billing_ctx, dict) else None
    price_rub = billing_ctx.get("price_rub") if isinstance(billing_ctx, dict) else None
    is_free = bool(billing_ctx.get("is_free")) if isinstance(billing_ctx, dict) else False

    fallback_used = model_fallback or sku_fallback

    if admin_flag:
        price_lines = [
            "🎁 Бесплатно",
            "🎁 Админ: безлимитные генерации (квота не расходуется).",
        ]
        price_rub = 0
    else:
        if is_free:
            price_lines = ["🎁 Бесплатно"]
        elif price_text:
            price_lines = [str(price_text)]
        else:
            price_lines = ["Цена: уточняется"]

    log_structured_event(
        correlation_id=correlation_id,
        action="STEP1_PROMPT_BUILT",
        model_id=model_id,
        sku_id=_resolve_sku_key(sku),
        price_rub=price_rub,
        outcome="built",
        param={
            "admin": admin_flag,
            "fallback_used": fallback_used,
        },
    )
    logger.info(
        "STEP1_PROMPT_BUILT model_id=%s sku_id=%s admin=%s price_rub=%s fallback_used=%s correlation_id=%s",
        model_id,
        _resolve_sku_key(sku),
        admin_flag,
        price_rub,
        fallback_used,
        correlation_id,
    )

    lines = [
        "📝 Шаг 1/3: Введите prompt:",
        model_short,
        sku_short,
        "Макс. длина: 5000 символов",
        "💡 Формат: текст",
        "💡 Что делать:",
        "• Введите значение в текстовом сообщении",
        "• Отправьте значение текстом",
    ]
    lines.extend(price_lines)

    text = "\n".join(line for line in lines if line)
    return text
