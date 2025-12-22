# Интеграция seedream/4.5-text-to-image

## 📋 Обзор

Документация по интеграции модели `seedream/4.5-text-to-image` согласно официальной документации KIE AI API.

## 🔗 API Документация

- **URL создания задачи**: `POST https://api.kie.ai/api/v1/jobs/createTask`
- **URL статуса задачи**: `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId={taskId}`
- **Модель**: `seedream/4.5-text-to-image`

## 📝 Параметры запроса

### Обязательные параметры

| Параметр | Тип | Описание | Ограничения |
|----------|-----|----------|-------------|
| `model` | string | ID модели | `"seedream/4.5-text-to-image"` |
| `input.prompt` | string | Текстовое описание изображения | Обязательный, максимум 3000 символов |
| `input.aspect_ratio` | string | Соотношение сторон изображения | Обязательный, один из допустимых значений |
| `input.quality` | string | Качество изображения | Обязательный, "basic" или "high" |

### Опциональные параметры

| Параметр | Тип | Описание | Значения по умолчанию |
|----------|-----|----------|----------------------|
| `callBackUrl` | string | URL для уведомлений о завершении | Не указан (нет callback) |

### Допустимые значения

#### `prompt`
- Тип: string
- Обязательный: да
- Максимум: 3000 символов
- **Важно**: Не может быть пустым!

#### `aspect_ratio`
- Тип: string
- Обязательный: да
- Значения:
  - `"1:1"` - Квадрат (default)
  - `"4:3"` - Горизонтальный 4:3
  - `"3:4"` - Вертикальный 3:4
  - `"16:9"` - Горизонтальный 16:9
  - `"9:16"` - Вертикальный 9:16
  - `"2:3"` - Вертикальный 2:3
  - `"3:2"` - Горизонтальный 3:2
  - `"21:9"` - Широкий 21:9
- **Важно**: Обязательный параметр, не опциональный!

#### `quality`
- Тип: string
- Обязательный: да
- Значения:
  - `"basic"` - Basic (2K изображения, default)
  - `"high"` - High (4K изображения)
- **Важно**: Обязательный параметр, не опциональный! Принимается в нижнем регистре.

## 🔧 Реализация в коде

### Валидация параметров

Валидация реализована в `app/services/kie_input_builder.py`:

```python
def _validate_seedream_4_5_text_to_image(
    model_id: str,
    normalized_input: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Специфичная валидация для seedream/4.5-text-to-image согласно документации API.
    """
    if model_id != "seedream/4.5-text-to-image":
        return True, None
    
    # Валидация prompt: обязательный, максимум 3000 символов
    prompt = normalized_input.get('prompt')
    if not prompt:
        return False, "Поле 'prompt' обязательно для генерации изображения"
    
    prompt_len = len(prompt.strip())
    if prompt_len == 0:
        return False, "Поле 'prompt' не может быть пустым"
    if prompt_len > 3000:
        return False, f"Поле 'prompt' слишком длинное: {prompt_len} символов (максимум 3000)"
    
    # Валидация aspect_ratio: обязательный, enum
    aspect_ratio = normalized_input.get('aspect_ratio')
    if not aspect_ratio:
        return False, "Поле 'aspect_ratio' обязательно для генерации изображения"
    
    normalized_aspect_ratio = _normalize_aspect_ratio_for_seedream_4_5(aspect_ratio)
    if normalized_aspect_ratio is None:
        valid_values = ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9"]
        return False, f"Поле 'aspect_ratio' должно быть одним из: {', '.join(valid_values)}"
    normalized_input['aspect_ratio'] = normalized_aspect_ratio
    
    # Валидация quality: обязательный, enum
    quality = normalized_input.get('quality')
    if not quality:
        return False, "Поле 'quality' обязательно для генерации изображения"
    
    normalized_quality = _normalize_quality_for_seedream_4_5(quality)
    if normalized_quality is None:
        return False, f"Поле 'quality' должно быть 'basic' или 'high'"
    normalized_input['quality'] = normalized_quality
    
    return True, None
```

### Нормализация aspect_ratio

Функция нормализации проверяет валидность значения:

```python
def _normalize_aspect_ratio_for_seedream_4_5(value: Any) -> Optional[str]:
    """
    Нормализует aspect_ratio для seedream/4.5-text-to-image.
    """
    if value is None:
        return None
    
    str_value = str(value).strip()
    
    # Валидные значения
    valid_values = ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9"]
    if str_value in valid_values:
        return str_value
    
    return None
```

### Нормализация quality

Функция нормализации конвертирует в нижний регистр:

```python
def _normalize_quality_for_seedream_4_5(value: Any) -> Optional[str]:
    """
    Нормализует quality для seedream/4.5-text-to-image.
    Конвертирует в нижний регистр.
    """
    if value is None:
        return None
    
    str_value = str(value).strip().lower()
    
    # Валидные значения
    valid_values = ["basic", "high"]
    if str_value in valid_values:
        return str_value
    
    return None
```

### Дефолтные значения

Если параметры не указаны, применяются дефолты:

```python
if model_id == "seedream/4.5-text-to-image":
    if 'aspect_ratio' not in normalized_input:
        normalized_input['aspect_ratio'] = "1:1"  # Default согласно документации
    if 'quality' not in normalized_input:
        normalized_input['quality'] = "basic"  # Default согласно документации
```

### Callback URL

Callback URL поддерживается через переменную окружения `KIE_CALLBACK_URL`:

```python
def get_callback_url() -> Optional[str]:
    """
    Получает callback URL из настроек.
    """
    settings = get_settings()
    callback_url = getattr(settings, 'kie_callback_url', None)
    if not callback_url:
        import os
        callback_url = os.getenv('KIE_CALLBACK_URL')
    return callback_url
```

## 📊 Пример использования

### Пример запроса

```json
{
  "model": "seedream/4.5-text-to-image",
  "input": {
    "prompt": "A full-process cafe design tool for entrepreneurs and designers. It covers core needs including store layout, functional zoning, decoration style, equipment selection, and customer group adaptation, supporting integrated planning of \"commercial attributes + aesthetic design.\" Suitable as a promotional image for a cafe design SaaS product, with a 16:9 aspect ratio.",
    "aspect_ratio": "1:1",
    "quality": "basic"
  },
  "callBackUrl": "https://your-domain.com/api/callback"
}
```

### Пример ответа

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "taskId": "281e5b0*********************f39b9"
  }
}
```

## ✅ Проверка интеграции

1. **Валидация prompt**: Проверяется длина (максимум 3000 символов)
2. **Валидация aspect_ratio**: Проверяется что значение из допустимого списка
3. **Валидация quality**: Проверяется что значение "basic" или "high" (конвертируется в нижний регистр)
4. **Дефолтные значения**: Применяются если параметры не указаны (aspect_ratio="1:1", quality="basic")
5. **Callback URL**: Передаётся в API если настроен

## 🔍 Логирование

Все параметры логируются (без секретов):

```
MODEL=seedream/4.5-text-to-image TYPE=t2i INPUT_KEYS=['prompt', 'aspect_ratio', 'quality'] 
INPUT_PREVIEW={'prompt': 'A full-process cafe...', 'aspect_ratio': '1:1', 'quality': 'basic'}
```

## 📚 Связанные файлы

- `app/services/kie_input_builder.py` - Валидация и нормализация параметров
- `app/kie_catalog/input_schemas.py` - Схемы входных параметров
- `app/integrations/kie_client.py` - KIE API клиент
- `app/kie_catalog/models_pricing.yaml` - Каталог моделей и цен

## ⚠️ Важные замечания

1. **prompt максимум 3000 символов** - проверяется при валидации
2. **aspect_ratio обязательный** - не опциональный! Должен быть указан явно или будет применён дефолт "1:1"
3. **quality обязательный** - не опциональный! Должен быть указан явно или будет применён дефолт "basic"
4. **quality конвертируется в нижний регистр** - "Basic" → "basic", "High" → "high"
5. **Дефолтные значения**: aspect_ratio="1:1", quality="basic"
6. **Callback URL опционален** - если не указан, уведомления не отправляются

## 🎯 Ключевые отличия от других t2i моделей

1. **Обязательные параметры**: `aspect_ratio` и `quality` обязательны (не опциональны!)
2. **Ограничение prompt**: Максимум 3000 символов (не 5000!)
3. **Специфичные значения**: aspect_ratio имеет 8 вариантов, quality только 2

