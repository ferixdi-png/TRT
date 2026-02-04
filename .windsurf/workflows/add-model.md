---
description: Добавление новой нейросети в бота
---

# Добавление новой модели KIE AI

## Требуемые данные от пользователя:

1. **model_id** — идентификатор модели (например: `wan/2-6-text-to-video`)
2. **Тип генерации** — text-to-video, image-to-video, text-to-image и т.д.
3. **Параметры API** — список input параметров с типами и значениями
4. **Цены** — credits и official_usd для каждой комбинации параметров

## Шаги добавления (ВСЕ ОБЯЗАТЕЛЬНЫ!):

### 1. ⭐⭐⭐ ГЛАВНОЕ: `app/kie_catalog/models_pricing.yaml`

**БЕЗ ЭТОГО модель НЕ появится в меню!** Это pricing каталог.

```yaml
- id: model-id
  title_ru: Название модели
  type: t2v  # t2i, i2i, t2v, i2v, v2v, tts, stt
  modes:
  - unit: video
    credits: 68.6
    official_usd: 0.343
    notes: default-5.0s-720p
  - unit: video
    credits: 137.2
    official_usd: 0.686
    notes: default-10.0s-720p
  description_ru: Описание модели на русском.
```

### 2. ⭐⭐ `models/kie_models.yaml` — registry моделей

```yaml
  model-id:
    model_type: text_to_video
    input:
      prompt:
        type: string
        required: true
        max: 5000
      duration:
        type: enum
        required: false
        values:
        - '5'
        - '10'
    model_mode: text_to_video
```

### 3. `kie_models.py` → `KIE_MODELS` (обогащение)

```python
{
    "id": "model-id",
    "name": "Название модели",
    "description": "Описание",
    "category": "Видео",
    "emoji": "🎥",
    "pricing": "Краткое описание цен",
    "input_params": { ... }
}
```

### 4. `kie_models.py` → `GENERATION_TYPES`

```python
"text-to-video": {
    "models": [..., "model-id"]
}
```

### 5. `data/kie_pricing_rub.yaml` — цены в рублях

```yaml
- id: model-id
  skus:
    - unit: video
      price_rub: 53.9
      params:
        duration: "5"
        resolution: 720p
      notes: 5s 720p
```

### 6. Для видео-моделей: `bot_kie.py` → `is_video` списки

Найти строки с `is_video = gen.get('model_id', '') in [...]` и добавить model_id.

### 7. Проверка

```bash
python -c "import yaml; yaml.safe_load(open('app/kie_catalog/models_pricing.yaml', encoding='utf-8'))"
python -c "import yaml; yaml.safe_load(open('models/kie_models.yaml', encoding='utf-8'))"
python -m py_compile kie_models.py
python -m pytest tests/test_critical_flows.py -q
```

## Типы моделей:

| type (pricing) | model_type (registry) | Категория меню |
|----------------|----------------------|----------------|
| t2v | text_to_video | 🎬 Видео по сценарию |
| i2v | image_to_video | 🎞 Фото → Видео |
| t2i | text_to_image | 🎨 Текст → Фото |
| i2i | image_to_image | 🖼 Ремикс изображения |

## Чеклист файлов:

- [ ] `app/kie_catalog/models_pricing.yaml` ← КРИТИЧНО!
- [ ] `models/kie_models.yaml`
- [ ] `kie_models.py` → KIE_MODELS
- [ ] `kie_models.py` → GENERATION_TYPES
- [ ] `data/kie_pricing_rub.yaml`
- [ ] `bot_kie.py` → is_video (для видео)
