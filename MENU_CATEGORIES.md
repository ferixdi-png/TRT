# FERIXDI AI — Категории меню

> **Строгая спецификация категорий главного меню бота**

---

## Структура главного меню

| Кнопка | gen_type фильтр | Описание |
|--------|-----------------|----------|
| ⚡ **Fast Tools** | `text-to-image` (топ-5 дешёвых) | Быстрые бесплатные генерации |
| 🎨 **Генерация визуала** | `text-to-image` | Все модели текст → изображение |
| 🖼 **Ремикс изображения** | `image-to-image` | Все модели изображение → изображение |
| 🎬 **Видео по сценарию** | `text-to-video` | Все модели текст → видео |
| 🎞 **Анимировать изображение** | `image-to-video` | Все модели изображение → видео |
| 🧰 **Спец-инструменты** | *см. ниже* | Все остальные режимы |

---

## Fast Tools — Топ-5 самых дешёвых text-to-image

**Критерий отбора:** 5 моделей с `model_type: text-to-image` и минимальной ценой SKU.

| Модель | Цена SKU | free_sku |
|--------|----------|----------|
| `bytedance/seedream` | 2.75 ₽ | ✅ |
| `ideogram/v3-text-to-image` | 2.75 ₽ | ✅ |
| `google/imagen4-fast` | 3.14 ₽ | ✅ |
| `google/nano-banana` | 3.14 ₽ | ✅ |
| `qwen/text-to-image` | 3.14 ₽ | ❌ |

> **Логика:** Сортировка по `sku_price_rub ASC`, взять первые 5 с `model_type=text-to-image`

---

## Генерация визуала (text-to-image)

**gen_type:** `text-to-image`  
**model_type в YAML:** `text_to_image`

| model_id | Цена | Примечание |
|----------|------|------------|
| `z-image` | free | Базовая бесплатная |
| `bytedance/seedream` | 2.75 ₽ | free_sku |
| `ideogram/v3-text-to-image` | 2.75 ₽ | free_sku |
| `google/imagen4-fast` | 3.14 ₽ | free_sku |
| `google/nano-banana` | 3.14 ₽ | free_sku |
| `qwen/text-to-image` | 3.14 ₽ | |
| `flux-2/pro-text-to-image` | - | |
| `flux-2/flex-text-to-image` | - | |
| `seedream/4.5-text-to-image` | - | |
| `bytedance/seedream-v4-text-to-image` | - | |
| `openai/4o-image` | 4.71 ₽ | |
| `grok-imagine/text-to-image` | 6.00 ₽ | |
| `google/imagen4` | 6.29 ₽ | |
| `midjourney/api` | 6.29 ₽ | |
| `google/imagen4-ultra` | 9.43 ₽ | |
| `grok/imagine` | 15.71 ₽ | |

---

## Ремикс изображения (image-to-image)

**gen_type:** `image-to-image`  
**model_type в YAML:** `image_to_image`

| model_id | Цена | Примечание |
|----------|------|------------|
| `ideogram/v3-remix` | 2.75 ₽ | |
| `qwen/image-to-image` | 3.14 ₽ | |
| `flux/kontext` | 3.93 ₽ | |
| `nano-banana-pro` | - | |
| `flux-2/pro-image-to-image` | - | |
| `flux-2/flex-image-to-image` | - | |
| `ideogram/character` | 9.43 ₽ | Консистентные персонажи |

---

## Видео по сценарию (text-to-video)

**gen_type:** `text-to-video`  
**model_type в YAML:** `text_to_video`

| model_id | Цена (мин) | Примечание |
|----------|------------|------------|
| `grok-imagine/text-to-video` | 15.71 ₽ | |
| `kling/v2-1-standard` | 19.64 ₽ | 5 сек |
| `kling/v2-5-turbo` | 33.00 ₽ | |
| `kling/v2-1-pro` | 39.29 ₽ | 5 сек |
| `google/veo-3` | 47.14 ₽ | |
| `google/veo-3.1` | 47.14 ₽ | |
| `kling/v2-1-master-text-to-video` | 125.71 ₽ | 5 сек |
| `sora-2-text-to-video` | - | |
| `sora-2-pro-text-to-video` | - | |
| `kling-2.6/text-to-video` | - | |
| `wan/2-5-text-to-video` | - | |
| `hailuo/02-text-to-video-pro` | - | |
| `hailuo/02-text-to-video-standard` | - | |
| `hailuo/2.3` | 23.57 ₽ | 6 сек/768p |

---

## Анимировать изображение (image-to-video)

**gen_type:** `image-to-video`  
**model_type в YAML:** `image_to_video`

| model_id | Цена (мин) | Примечание |
|----------|------------|------------|
| `runway/gen-4` | 9.43 ₽ | 5 сек/720p |
| `bytedance/v1-pro-fast-image-to-video` | 12.57 ₽ | 5 сек/720p |
| `kling/v2-1-master-image-to-video` | 125.71 ₽ | 5 сек |
| `sora-2-image-to-video` | - | |
| `sora-2-pro-image-to-video` | - | |
| `kling-2.6/image-to-video` | - | |
| `kling/v2-5-turbo-image-to-video-pro` | - | |
| `wan/2-5-image-to-video` | - | |
| `wan/2-2-animate-move` | - | |
| `wan/2-2-animate-replace` | - | |
| `hailuo/02-image-to-video-pro` | - | |
| `hailuo/02-image-to-video-standard` | - | |

---

## Спец-инструменты

**gen_type:** Все остальные режимы, не входящие в основные категории.

### Редактирование изображений (image-edit)

| model_id | Цена | Примечание |
|----------|------|------------|
| `ideogram/v3-edit` | 2.75 ₽ | |
| `google/nano-banana-edit` | 3.14 ₽ | |
| `qwen/image-edit` | 4.71 ₽ | |
| `seedream/4.5-edit` | - | |
| `bytedance/seedream-v4-edit` | - | |
| `ideogram/character-edit` | 9.43 ₽ | |
| `ideogram/character-remix` | 9.43 ₽ | |
| `recraft/remove-background` | - | Удаление фона |

### Апскейл (upscale)

| model_id | Примечание |
|----------|------------|
| `topaz/image-upscale` | Улучшение изображений |
| `recraft/crisp-upscale` | Чёткий апскейл |
| `topaz/video-upscale` | Улучшение видео |

### Расширение кадра (outpaint)

| model_id | Примечание |
|----------|------------|
| `ideogram/v3-reframe` | Расширение границ изображения |

### Видео-редактирование (video-editing)

| model_id | Примечание |
|----------|------------|
| `sora-watermark-remover` | Удаление водяных знаков |

### Lip Sync (lip-sync)

| model_id | Цена | Примечание |
|----------|------|------------|
| `infinitalk/from-audio` | 2.36 ₽ | 480p |
| `kling/v1-avatar-standard` | - | |
| `kling/ai-avatar-v1-pro` | - | |

### Speech to Video (speech-to-video)

| model_id | Примечание |
|----------|------------|
| `wan/2-2-a14b-speech-to-video-turbo` | Озвученное видео |

### Аудио/Музыка

| model_id | Цена | Тип |
|----------|------|-----|
| `elevenlabs/audio-isolation` | 0.16 ₽ | audio-to-audio |
| `elevenlabs/sound-effect` | 0.19 ₽ | text-to-audio |
| `elevenlabs/text-to-speech` | 4.71 ₽ | text-to-speech |
| `elevenlabs/speech-to-text` | 2.75 ₽ | speech-to-text |
| `suno/v5` | 9.43 ₽ | text-to-music |

### Чат / AI-ассистент

| model_id | Цена | Примечание |
|----------|------|------------|
| `google/nanobanana-gemini-2.5-flash` | 14.14 ₽ | Чат с ИИ |

---

## Маппинг gen_type → Категория

```python
MENU_CATEGORY_MAP = {
    # Основные категории (отдельные кнопки в меню)
    "text-to-image": "visual_generation",      # 🎨 Генерация визуала
    "image-to-image": "image_remix",           # 🖼 Ремикс изображения
    "text-to-video": "video_script",           # 🎬 Видео по сценарию
    "image-to-video": "animate_image",         # 🎞 Анимировать изображение
    
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
    "audio-to-audio": "special_tools",
    "chat": "special_tools",
}
```

---

## Правила Fast Tools

1. **Источник:** Только модели с `model_type: text-to-image`
2. **Сортировка:** По минимальной цене SKU (`sku_price_rub ASC`)
3. **Количество:** Ровно 5 моделей
4. **Приоритет free_sku:** Модели с `free_sku=True` показываются первыми при равной цене
5. **Обновление:** Список обновляется при старте бота из актуальных SKU

---

## Анализ логов PRICING_COVERAGE_OK

### Все модели с ценами (из логов 2026-01-29):

| model_id | sku_id | price_rub | free_sku | Категория |
|----------|--------|-----------|----------|-----------|
| bytedance/seedream | default | 2.75 | ✅ | text-to-image |
| ideogram/v3-text-to-image | TURBO | 2.75 | ✅ | text-to-image |
| google/imagen4-fast | default | 3.14 | ✅ | text-to-image |
| google/nano-banana | default | 3.14 | ✅ | text-to-image |
| qwen/text-to-image | default | 3.14 | ❌ | text-to-image |
| ideogram/v3-remix | TURBO | 2.75 | ❌ | image-to-image |
| qwen/image-to-image | default | 3.14 | ❌ | image-to-image |
| flux/kontext | default | 3.93 | ❌ | image-to-image |
| ideogram/v3-edit | TURBO | 2.75 | ❌ | image-edit |
| google/nano-banana-edit | default | 3.14 | ❌ | image-edit |
| openai/4o-image | default | 4.71 | ❌ | text-to-image |
| qwen/image-edit | default | 4.71 | ❌ | image-edit |
| grok-imagine/text-to-image | default | 6.00 | ❌ | text-to-image |
| google/imagen4 | default | 6.29 | ❌ | text-to-image |
| midjourney/api | default | 6.29 | ❌ | text-to-image |
| runway/gen-4 | 5s/720p | 9.43 | ❌ | image-to-video |
| ideogram/character | TURBO | 9.43 | ❌ | image-to-image |
| ideogram/character-edit | TURBO | 9.43 | ❌ | image-edit |
| ideogram/character-remix | TURBO | 9.43 | ❌ | image-edit |
| google/imagen4-ultra | default | 9.43 | ❌ | text-to-image |
| suno/v5 | default | 9.43 | ❌ | text-to-music |
| bytedance/v1-pro-fast-image-to-video | 5s/720p | 12.57 | ❌ | image-to-video |
| grok/imagine | default | 15.71 | ❌ | text-to-image |
| grok-imagine/text-to-video | default | 15.71 | ❌ | text-to-video |
| kling/v2-1-standard | 5s | 19.64 | ❌ | text-to-video |
| hailuo/2.3 | 6s/768p | 23.57 | ❌ | text-to-video |
| kling/v2-5-turbo | default | 33.00 | ❌ | text-to-video |
| kling/v2-1-pro | 5s | 39.29 | ❌ | text-to-video |
| google/veo-3 | default | 47.14 | ❌ | text-to-video |
| google/veo-3.1 | default | 47.14 | ❌ | text-to-video |
| kling/v2-1-master-text-to-video | 5s | 125.71 | ❌ | text-to-video |
| kling/v2-1-master-image-to-video | 5s | 125.71 | ❌ | image-to-video |
| infinitalk/from-audio | 480p | 2.36 | ❌ | lip-sync |
| elevenlabs/audio-isolation | default | 0.16 | ❌ | audio-to-audio |
| elevenlabs/sound-effect | default | 0.19 | ❌ | text-to-audio |
| elevenlabs/speech-to-text | default | 2.75 | ❌ | speech-to-text |
| elevenlabs/text-to-speech | default | 4.71 | ❌ | text-to-speech |
| google/nanobanana-gemini-2.5-flash | default | 14.14 | ❌ | chat |

---

## Итоговая статистика

| Категория | Кол-во моделей | Мин. цена |
|-----------|----------------|-----------|
| text-to-image | 16+ | 2.75 ₽ |
| image-to-image | 7+ | 2.75 ₽ |
| text-to-video | 13+ | 15.71 ₽ |
| image-to-video | 12+ | 9.43 ₽ |
| Спец-инструменты | 15+ | 0.16 ₽ |

---

*FERIXDI AI Menu Categories v1.0 — 2026-01-29*
