"""
Построение меню моделей из каталога KIE AI.
Группировка по типам и брендам, отображение цен в рублях.
"""

import hashlib
import logging
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.kie_catalog import load_catalog, get_model, ModelSpec
from app.pricing.price_resolver import format_price_rub
from app.pricing.price_ssot import get_min_price, model_has_free_sku
from app.ux.model_visibility import is_model_visible

logger = logging.getLogger(__name__)

# Кеш маппинга коротких callback_data
_callback_mapping: Dict[str, str] = {}
_reverse_mapping: Dict[str, str] = {}

OTHER_MODELS_TYPE = "other"
OTHER_MODELS_FORCE = {
    "sora-watermark-remover",
    "sora-2-watermark-remover",
}


def _get_model_brand(model_id: str, title: str) -> str:
    """Определяет бренд модели по ID или названию."""
    model_lower = model_id.lower()
    title_lower = title.lower()
    
    # Проверяем по префиксам ID
    if model_id.startswith("flux"):
        return "Flux"
    elif model_id.startswith("kling"):
        return "Kling"
    elif model_id.startswith("wan"):
        return "Wan"
    elif model_id.startswith("google"):
        return "Google"
    elif model_id.startswith("ideogram"):
        return "Ideogram"
    elif model_id.startswith("bytedance") or "seedance" in model_lower or "seedream" in model_lower:
        return "ByteDance"
    elif model_id.startswith("sora") or "openai" in model_lower:
        return "OpenAI"
    elif model_id.startswith("qwen") or model_id.startswith("z-image"):
        return "Qwen"
    elif model_id.startswith("elevenlabs"):
        return "ElevenLabs"
    elif model_id.startswith("hailuo"):
        return "Hailuo"
    elif model_id.startswith("topaz"):
        return "Topaz"
    elif model_id.startswith("recraft"):
        return "Recraft"
    elif model_id.startswith("suno"):
        return "Suno"
    elif model_id.startswith("midjourney"):
        return "Midjourney"
    elif model_id.startswith("runway"):
        return "Runway"
    elif model_id.startswith("grok"):
        return "Grok"
    elif "infinitalk" in model_lower or "meigen" in model_lower:
        return "MeiGen-AI"
    
    # Проверяем по названию
    if "flux" in title_lower:
        return "Flux"
    elif "kling" in title_lower:
        return "Kling"
    elif "google" in title_lower:
        return "Google"
    elif "openai" in title_lower or "sora" in title_lower:
        return "OpenAI"
    
    return "Other"


def _get_type_emoji(model_type: str) -> str:
    """Возвращает эмодзи для типа модели."""
    emoji_map = {
        't2i': '🖼️',
        'i2i': '🎨',
        't2v': '🎬',
        'i2v': '📹',
        'v2v': '🎞️',
        'tts': '🔊',
        'stt': '🎤',
        'sfx': '🎵',
        'audio_isolation': '🎧',
        'upscale': '⬆️',
        'bg_remove': '✂️',
        'watermark_remove': '💧',
        'music': '🎼',
        'lip_sync': '👄',
        'other': '🧩'
    }
    return emoji_map.get(model_type, '🤖')


def _get_type_name_ru(model_type: str) -> str:
    """Возвращает название типа на русском."""
    name_map = {
        't2i': 'Текст → Изображение',
        'i2i': 'Изображение → Изображение',
        't2v': 'Текст → Видео',
        'i2v': 'Изображение → Видео',
        'v2v': 'Видео → Видео',
        'tts': 'Текст → Речь',
        'stt': 'Речь → Текст',
        'sfx': 'Звуковые эффекты',
        'audio_isolation': 'Изоляция аудио',
        'upscale': 'Увеличение качества',
        'bg_remove': 'Удаление фона',
        'watermark_remove': 'Удаление водяного знака',
        'music': 'Музыка',
        'lip_sync': 'Синхронизация губ',
        'other': 'Другие модели'
    }
    return name_map.get(model_type, model_type)


def get_type_label(model_type: str, user_lang: str) -> str:
    """Возвращает подпись типа модели для UI."""
    emoji = _get_type_emoji(model_type)
    type_name = _get_type_name_ru(model_type) if user_lang == "ru" else model_type
    return f"{emoji} {type_name}"


def _create_callback_data(model_id: str) -> str:
    """
    Создаёт callback_data для модели.
    Если model_id слишком длинный, использует короткий формат с маппингом.
    """
    callback_data = f"model:{model_id}"
    callback_bytes = callback_data.encode('utf-8')
    
    # Telegram ограничение: 64 байта
    if len(callback_bytes) <= 64:
        return callback_data
    
    # Используем короткий формат с хешем
    model_hash = hashlib.md5(model_id.encode()).hexdigest()[:12]
    short_callback = f"modelk:{model_hash}"
    
    # Сохраняем маппинг
    _callback_mapping[short_callback] = model_id
    _reverse_mapping[model_id] = short_callback
    
    return short_callback


def _resolve_model_id(callback_data: str) -> Optional[str]:
    """Разрешает callback_data в model_id (поддерживает короткий формат)."""
    if callback_data.startswith("model:"):
        return callback_data[6:]  # Убираем "model:"
    elif callback_data.startswith("modelk:"):
        hash_part = callback_data[7:]  # Убираем "modelk:"
        # Ищем в маппинге
        for short, model_id in _callback_mapping.items():
            if short.endswith(hash_part):
                return model_id
        # Если не нашли, пробуем найти по хешу из обратного маппинга
        for model_id in _reverse_mapping.keys():
            model_hash = hashlib.md5(model_id.encode()).hexdigest()[:12]
            if model_hash == hash_part:
                return model_id
        # Fallback: пересчитать хеши по каталогу (на случай разных процессов)
        try:
            for model in load_catalog():
                model_hash = hashlib.md5(model.id.encode()).hexdigest()[:12]
                if model_hash == hash_part:
                    return model.id
        except Exception as exc:
            logger.warning("Failed to resolve modelk callback via catalog: %s", exc)
    return None


def build_models_menu_by_type(
    user_lang: str = 'ru',
    *,
    default_model_id: Optional[str] = None,
) -> InlineKeyboardMarkup:
    """
    Строит меню моделей, сгруппированных по типам.
    
    Returns:
        InlineKeyboardMarkup с кнопками моделей, сгруппированных по типам
    """
    catalog = load_catalog()
    
    type_order = ['t2i', 'i2i', 't2v', 'i2v', 'v2v', 'tts', 'stt', 'sfx', 'audio_isolation', 
                  'upscale', 'bg_remove', 'watermark_remove', 'music', 'lip_sync', OTHER_MODELS_TYPE]
    
    # Группируем по типам
    models_by_type: Dict[str, List[ModelSpec]] = defaultdict(list)
    for model in catalog:
        if not is_model_visible(model.id):
            continue
        model_type = model.type
        if model.id in OTHER_MODELS_FORCE or model_type not in type_order:
            model_type = OTHER_MODELS_TYPE
        models_by_type[model_type].append(model)
    
    keyboard = []

    if default_model_id:
        default_model = get_model(default_model_id)
        if default_model and is_model_visible(default_model.id):
            type_emoji = _get_type_emoji(default_model.type)
            button_text = f"⭐ {type_emoji} {default_model.title_ru}"
            keyboard.append([
                InlineKeyboardButton(
                    button_text,
                    callback_data=_create_callback_data(default_model.id),
                )
            ])
            keyboard.append([])  # Spacer after default shortcut
    
    # Сортируем типы для отображения
    
    for model_type in type_order:
        if model_type not in models_by_type:
            continue
        
        models = models_by_type[model_type]
        if not models:
            continue
        
        # Заголовок типа (кликабельный для фильтрации)
        emoji = _get_type_emoji(model_type)
        type_name = _get_type_name_ru(model_type) if user_lang == 'ru' else model_type
        keyboard.append([
            InlineKeyboardButton(
                f"{emoji} {type_name} ({len(models)})",
                callback_data=f"type_header:{model_type}"
            )
        ])
        
        # Группируем модели по брендам
        models_by_brand: Dict[str, List[ModelSpec]] = defaultdict(list)
        for model in models:
            brand = _get_model_brand(model.id, model.title_ru)
            models_by_brand[brand].append(model)
        
        # Сортируем бренды
        brand_order = ['Flux', 'Kling', 'Wan', 'Google', 'OpenAI', 'Ideogram', 'ByteDance', 
                      'Qwen', 'ElevenLabs', 'Hailuo', 'Topaz', 'Recraft', 'Suno', 
                      'Midjourney', 'Runway', 'Grok', 'MeiGen-AI', 'Other']
        
        for brand in brand_order:
            if brand not in models_by_brand:
                continue
            
            brand_models = models_by_brand[brand]
            if not brand_models:
                continue
            
            # Кнопки моделей (по 1 в ряд, так как могут быть длинными)
            for model in sorted(brand_models, key=lambda m: m.title_ru):
                # Получаем эмодзи для типа модели
                type_emoji = _get_type_emoji(model.type)
                
                # Формируем текст кнопки с эмодзи (без цены)
                button_text = f"{type_emoji} {model.title_ru}"
                
                # Ограничение Telegram: ~64 символа для текста кнопки
                if len(button_text.encode('utf-8')) > 60:
                    max_len = 58  # запас для многобайтовых символов
                    button_text = f"{type_emoji} {model.title_ru[:max_len]}..."
                
                callback_data = _create_callback_data(model.id)
                
                keyboard.append([
                    InlineKeyboardButton(
                        button_text,
                        callback_data=callback_data
                    )
                ])
    
    # Кнопка "Назад"
    keyboard.append([])  # Пустая строка для разделения
    if user_lang == 'ru':
        keyboard.append([InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")])
    else:
        keyboard.append([InlineKeyboardButton("🔙 Back to menu", callback_data="back_to_menu")])
    
    return InlineKeyboardMarkup(keyboard)


def build_models_menu_for_type(
    user_lang: str,
    model_type: str,
) -> Tuple[InlineKeyboardMarkup, int]:
    """Строит меню моделей только для указанного типа."""
    catalog = load_catalog()
    filtered_models: List[ModelSpec] = []
    for model in catalog:
        if not is_model_visible(model.id):
            continue
        effective_type = model.type
        if model.id in OTHER_MODELS_FORCE or effective_type not in {
            "t2i",
            "i2i",
            "t2v",
            "i2v",
            "v2v",
            "tts",
            "stt",
            "sfx",
            "audio_isolation",
            "upscale",
            "bg_remove",
            "watermark_remove",
            "music",
            "lip_sync",
            OTHER_MODELS_TYPE,
        }:
            effective_type = OTHER_MODELS_TYPE
        if effective_type != model_type:
            continue
        filtered_models.append(model)

    keyboard: List[List[InlineKeyboardButton]] = []
    for model in sorted(filtered_models, key=lambda m: m.title_ru):
        type_emoji = _get_type_emoji(model.type)
        button_text = f"{type_emoji} {model.title_ru}"
        if len(button_text.encode("utf-8")) > 60:
            max_len = 58
            button_text = f"{type_emoji} {model.title_ru[:max_len]}..."
        keyboard.append([
            InlineKeyboardButton(
                button_text,
                callback_data=_create_callback_data(model.id),
            )
        ])

    keyboard.append([])
    if user_lang == "ru":
        keyboard.append([InlineKeyboardButton("🔙 Все модели", callback_data="show_all_models_list")])
        keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")])
    else:
        keyboard.append([InlineKeyboardButton("🔙 All models", callback_data="show_all_models_list")])
        keyboard.append([InlineKeyboardButton("🏠 Main menu", callback_data="back_to_menu")])

    return InlineKeyboardMarkup(keyboard), len(filtered_models)


def _default_mode_label(index: int, user_lang: str) -> str:
    if user_lang == "ru":
        fallbacks = ["Стандартный", "Высокое качество", "Быстрый", "Дополнительный"]
    else:
        fallbacks = ["Standard", "High quality", "Fast", "Extra"]
    if index < len(fallbacks):
        return fallbacks[index]
    return fallbacks[-1]


def _resolve_mode_label(mode: ModelSpec, index: int, user_lang: str) -> str:
    mode_item = mode.modes[index] if mode.modes else None
    if not mode_item:
        return _default_mode_label(index, user_lang)
    if user_lang == "ru":
        title = mode_item.title_ru or _default_mode_label(index, user_lang)
        hint = mode_item.short_hint_ru
    else:
        title = mode_item.notes or mode_item.title_ru or _default_mode_label(index, user_lang)
        hint = mode_item.notes
    return f"{title} · {hint}" if hint else title


def build_model_card_text(model: ModelSpec, mode_index: int = 0, user_lang: str = 'ru') -> Tuple[str, InlineKeyboardMarkup]:
    """
    Строит текст карточки модели и клавиатуру.
    
    Args:
        model: ModelSpec модели
        mode_index: Индекс режима (по умолчанию 0)
        user_lang: Язык пользователя
    
    Returns:
        Tuple (текст карточки, клавиатура)
    """
    if mode_index < 0 or mode_index >= len(model.modes):
        mode_index = 0
    
    price_rub = get_min_price(model.id)
    price_display = format_price_rub(price_rub) if price_rub is not None else "—"
    free_option = model_has_free_sku(model.id)
    
    # Формируем текст карточки
    type_emoji = _get_type_emoji(model.type)
    try:
        from app.ux.form_engine import summarize_required_fields
        required_fields = summarize_required_fields(model.id)
    except Exception:
        required_fields = []
    required_text = ", ".join(required_fields) if required_fields else ("—" if user_lang == "ru" else "—")
    examples = []
    if "prompt" in required_fields:
        examples.append("prompt=\"Футуристический город\"" if user_lang == "ru" else "prompt=\"Futuristic city\"")
    if "image_url" in required_fields or "image_urls" in required_fields:
        examples.append("image_url=https://example.com/image.jpg")
    if "audio_url" in required_fields:
        examples.append("audio_url=https://example.com/audio.mp3")
    if "video_url" in required_fields or "video_urls" in required_fields:
        examples.append("video_url=https://example.com/video.mp4")
    example_text = "; ".join(examples) if examples else ("—" if user_lang == "ru" else "—")
    price_label = f"от {price_display} ₽" if price_rub is not None else ("цена уточняется" if user_lang == "ru" else "pricing pending")
    free_option_label = "Free option" if free_option else ""
    if user_lang == 'ru':
        type_name = _get_type_name_ru(model.type)
        
        card_text = (
            f"╔═══════════════════════════════════════════╗\n"
            f"║  {type_emoji} <b>{model.title_ru}</b> {type_emoji}          ║\n"
            f"╚═══════════════════════════════════════════╝\n\n"
            f"╔═══════════════════════════════════════════╗\n"
            f"║  📋 ТИП ГЕНЕРАЦИИ: {type_name} 📋        ║\n"
            f"╚═══════════════════════════════════════════╝\n"
        )
        
        if model.description_ru:
            card_text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n📝 <b>Описание:</b> {model.description_ru}\n"
        
        card_text += (
            f"\n╔═══════════════════════════════════════════╗\n"
            f"║  💰 ЦЕНА: <b>{price_label}</b> 💰              ║\n"
            f"╚═══════════════════════════════════════════╝\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📥 <b>Вход:</b> {', '.join(model.required_inputs_ru) if model.required_inputs_ru else required_text}\n"
            f"📤 <b>Выход:</b> {model.output_type_ru or '—'}\n"
            f"📌 <b>Пример:</b> {example_text}\n"
        )
        if free_option_label:
            card_text += f"🏷️ <b>{free_option_label}</b>\n"
        
        if len(model.modes) > 1:
            card_text += (
                f"\n╔═══════════════════════════════════════════╗\n"
                f"║  📌 ДОСТУПНО РЕЖИМОВ: {len(model.modes)} 📌    ║\n"
                f"╚═══════════════════════════════════════════╝\n"
            )
    else:
        card_text = (
            f"╔═══════════════════════════════════╗\n"
            f"║  {type_emoji} <b>{model.title_ru}</b>  ║\n"
            f"╚═══════════════════════════════════╝\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 <b>Generation Type:</b> {model.type}\n"
        )
        
        if model.description_ru:
            card_text += f"📝 <b>Description:</b> {model.description_ru}\n"
        
        card_text += (
            f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>PRICE:</b> <b>{price_label}</b>\n"
            f"📥 <b>Input:</b> {required_text}\n"
            f"📤 <b>Output:</b> {model.output_type_ru or '—'}\n"
            f"📌 <b>Example:</b> {example_text}\n"
        )
        if free_option_label:
            card_text += f"🏷️ <b>{free_option_label}</b>\n"
        
        if len(model.modes) > 1:
            card_text += f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            card_text += f"📌 <b>Available modes:</b> {len(model.modes)}\n"
    
    # Формируем клавиатуру
    keyboard = []
    
    if user_lang == 'ru':
        keyboard.append([
            InlineKeyboardButton("🚀 Сгенерировать", callback_data=f"select_model:{model.id}")
        ])
        keyboard.append([
            InlineKeyboardButton("📸 Пример", callback_data=f"example:{model.id}"),
            InlineKeyboardButton("ℹ️ Инфо", callback_data=f"info:{model.id}")
        ])
        keyboard.append([
            InlineKeyboardButton("🔙 Назад к моделям", callback_data="show_models")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("🚀 Generate", callback_data=f"select_model:{model.id}")
        ])
        keyboard.append([
            InlineKeyboardButton("📸 Example", callback_data=f"example:{model.id}"),
            InlineKeyboardButton("ℹ️ Info", callback_data=f"info:{model.id}")
        ])
        keyboard.append([
            InlineKeyboardButton("🔙 Back to models", callback_data="show_models")
        ])
    
    return card_text, InlineKeyboardMarkup(keyboard)


def resolve_model_id_from_callback(callback_data: str) -> Optional[str]:
    """
    Разрешает callback_data в model_id.
    Используется в обработчиках для получения model_id из callback.
    """
    return _resolve_model_id(callback_data)
