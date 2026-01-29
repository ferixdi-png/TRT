"""
Menu Categories Configuration - FERIXDI AI

Строгая спецификация категорий главного меню бота.
Документация: MENU_CATEGORIES.md
"""

from typing import Dict, List, Set

# ============================================================================
# КАТЕГОРИИ ГЛАВНОГО МЕНЮ
# ============================================================================

# Основные категории с отдельными кнопками в меню
MAIN_MENU_CATEGORIES = {
    "fast_tools": {
        "emoji": "⚡",
        "name_ru": "Fast Tools",
        "name_en": "Fast Tools",
        "description_ru": "Топ-5 дешёвых text-to-image",
        "description_en": "Top-5 cheapest text-to-image",
        "gen_types": ["text-to-image"],
        "filter": "top_5_cheapest",  # Специальный фильтр
    },
    "visual_generation": {
        "emoji": "🎨",
        "name_ru": "Генерация визуала",
        "name_en": "Visual Generation",
        "description_ru": "Текст → Изображение",
        "description_en": "Text → Image",
        "gen_types": ["text-to-image"],
    },
    "image_remix": {
        "emoji": "🖼",
        "name_ru": "Ремикс изображения",
        "name_en": "Image Remix",
        "description_ru": "Изображение → Изображение",
        "description_en": "Image → Image",
        "gen_types": ["image-to-image"],
    },
    "video_script": {
        "emoji": "🎬",
        "name_ru": "Видео по сценарию",
        "name_en": "Video from Script",
        "description_ru": "Текст → Видео",
        "description_en": "Text → Video",
        "gen_types": ["text-to-video"],
    },
    "animate_image": {
        "emoji": "🎞",
        "name_ru": "Анимировать изображение",
        "name_en": "Animate Image",
        "description_ru": "Изображение → Видео",
        "description_en": "Image → Video",
        "gen_types": ["image-to-video"],
    },
    "special_tools": {
        "emoji": "🧰",
        "name_ru": "Спец-инструменты",
        "name_en": "Special Tools",
        "description_ru": "Редактирование, аудио, апскейл и др.",
        "description_en": "Editing, audio, upscale, etc.",
        "gen_types": [
            "image-edit",
            "image-editing",
            "video-editing",
            "video-to-video",
            "upscale",
            "video-upscale",
            "outpaint",
            "lip-sync",
            "speech-to-video",
            "text-to-music",
            "text-to-speech",
            "speech-to-text",
            "text-to-audio",
            "audio-to-audio",
            "chat",
        ],
    },
}

# ============================================================================
# МАППИНГ gen_type → Категория
# ============================================================================

GEN_TYPE_TO_CATEGORY: Dict[str, str] = {
    # Основные категории (отдельные кнопки в меню)
    "text-to-image": "visual_generation",
    "image-to-image": "image_remix",
    "text-to-video": "video_script",
    "image-to-video": "animate_image",
    
    # Спец-инструменты (все попадают в 🧰)
    "image-edit": "special_tools",
    "image-editing": "special_tools",
    "video-editing": "special_tools",
    "video-to-video": "special_tools",
    "upscale": "special_tools",
    "video-upscale": "special_tools",
    "outpaint": "special_tools",
    "lip-sync": "special_tools",
    "speech-to-video": "special_tools",
    "text-to-music": "special_tools",
    "text-to-speech": "special_tools",
    "speech-to-text": "special_tools",
    "text-to-audio": "special_tools",
    "audio-to-audio": "special_tools",
    "chat": "special_tools",
}

# ============================================================================
# МАППИНГ model_type (YAML) → gen_type (UI)
# ============================================================================

MODEL_TYPE_TO_GEN_TYPE: Dict[str, str] = {
    # Основные типы
    "text_to_image": "text-to-image",
    "image_to_image": "image-to-image",
    "text_to_video": "text-to-video",
    "image_to_video": "image-to-video",
    
    # Спец-инструменты
    "image_edit": "image-edit",
    "video_editing": "video-editing",
    "upscale": "upscale",
    "video_upscale": "video-upscale",
    "outpaint": "outpaint",
    "lip_sync": "lip-sync",
    "speech_to_video": "speech-to-video",
    "text_to_music": "text-to-music",
    "text_to_speech": "text-to-speech",
    "speech_to_text": "speech-to-text",
    "audio_to_audio": "audio-to-audio",
    "chat": "chat",
}

# ============================================================================
# СПЕЦ-ИНСТРУМЕНТЫ — подкатегории
# ============================================================================

SPECIAL_TOOLS_SUBCATEGORIES = {
    "image_editing": {
        "emoji": "✏️",
        "name_ru": "Редактирование изображений",
        "name_en": "Image Editing",
        "gen_types": ["image-edit", "image-editing", "outpaint"],
    },
    "upscale": {
        "emoji": "🔍",
        "name_ru": "Апскейл / Улучшение",
        "name_en": "Upscale / Enhance",
        "gen_types": ["upscale", "video-upscale"],
    },
    "video_editing": {
        "emoji": "🎥",
        "name_ru": "Редактирование видео",
        "name_en": "Video Editing",
        "gen_types": ["video-editing", "video-to-video"],
    },
    "audio": {
        "emoji": "🎵",
        "name_ru": "Аудио / Музыка",
        "name_en": "Audio / Music",
        "gen_types": ["text-to-music", "text-to-speech", "speech-to-text", "text-to-audio", "audio-to-audio"],
    },
    "lip_sync": {
        "emoji": "👄",
        "name_ru": "Lip Sync / Озвучка",
        "name_en": "Lip Sync",
        "gen_types": ["lip-sync", "speech-to-video"],
    },
    "chat": {
        "emoji": "💬",
        "name_ru": "AI-чат",
        "name_en": "AI Chat",
        "gen_types": ["chat"],
    },
}

# ============================================================================
# FAST TOOLS — правила
# ============================================================================

FAST_TOOLS_CONFIG = {
    "count": 5,  # Топ-5 моделей
    "allowed_gen_types": ["text-to-image"],  # СТРОГО только text-to-image
    "sort_by": "price_rub",  # Сортировка по цене
    "sort_order": "asc",  # По возрастанию (дешёвые первые)
    "prefer_free_sku": True,  # Приоритет моделям с free_sku
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_category_for_gen_type(gen_type: str) -> str:
    """Возвращает категорию меню для gen_type."""
    return GEN_TYPE_TO_CATEGORY.get(gen_type, "special_tools")


def get_gen_type_for_model_type(model_type: str) -> str:
    """Преобразует model_type из YAML в gen_type для UI."""
    return MODEL_TYPE_TO_GEN_TYPE.get(model_type, model_type.replace("_", "-"))


def get_category_info(category_id: str, lang: str = "ru") -> Dict:
    """Возвращает информацию о категории."""
    category = MAIN_MENU_CATEGORIES.get(category_id, {})
    name_key = f"name_{lang}"
    desc_key = f"description_{lang}"
    return {
        "id": category_id,
        "emoji": category.get("emoji", "🔧"),
        "name": category.get(name_key, category.get("name_ru", category_id)),
        "description": category.get(desc_key, category.get("description_ru", "")),
        "gen_types": category.get("gen_types", []),
    }


def is_gen_type_in_special_tools(gen_type: str) -> bool:
    """Проверяет, относится ли gen_type к спец-инструментам."""
    return get_category_for_gen_type(gen_type) == "special_tools"


def get_all_special_tools_gen_types() -> Set[str]:
    """Возвращает все gen_types для спец-инструментов."""
    return set(MAIN_MENU_CATEGORIES["special_tools"]["gen_types"])
