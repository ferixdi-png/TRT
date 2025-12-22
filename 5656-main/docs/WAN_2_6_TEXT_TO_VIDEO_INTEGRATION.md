# Интеграция wan/2-6-text-to-video

## 📋 Обзор

Документация по интеграции модели `wan/2-6-text-to-video` согласно официальной документации KIE AI API.

## 🔗 API Документация

- **URL создания задачи**: `POST https://api.kie.ai/api/v1/jobs/createTask`
- **URL статуса задачи**: `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId={taskId}`
- **Модель**: `wan/2-6-text-to-video`

## 📝 Параметры запроса

### Обязательные параметры

| Параметр | Тип | Описание | Ограничения |
|----------|-----|----------|-------------|
| `model` | string | ID модели | `"wan/2-6-text-to-video"` |
| `input.prompt` | string | Текстовое описание видео | 1-5000 символов, обязательный |

### Опциональные параметры

| Параметр | Тип | Описание | Значения по умолчанию |
|----------|-----|----------|----------------------|
| `input.duration` | string | Длительность видео в секундах | `"5"` |
| `input.resolution` | string | Разрешение видео | `"1080p"` |
| `callBackUrl` | string | URL для уведомлений о завершении | Не указан (нет callback) |

### Допустимые значения

#### `duration`
- `"5"` - 5 секунд
- `"10"` - 10 секунд
- `"15"` - 15 секунд
- **Важно**: Должно быть строкой, не числом!

#### `resolution`
- `"720p"` - 720p разрешение
- `"1080p"` - 1080p разрешение
- **Важно**: Должно быть строкой с суффиксом "p"!

#### `prompt`
- Минимум: 1 символ
- Максимум: 5000 символов
- Поддерживает китайский и английский языки

## 🔧 Реализация в коде

### Валидация параметров

Валидация реализована в `app/services/kie_input_builder.py`:

```python
def _validate_wan_2_6_text_to_video(
    model_id: str,
    normalized_input: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Специфичная валидация для wan/2-6-text-to-video согласно документации API.
    """
    if model_id != "wan/2-6-text-to-video":
        return True, None
    
    # Валидация prompt: обязательный, 1-5000 символов
    prompt = normalized_input.get('prompt')
    if not prompt:
        return False, "Поле 'prompt' обязательно для генерации видео"
    
    prompt_len = len(prompt.strip())
    if prompt_len < 1:
        return False, "Поле 'prompt' не может быть пустым"
    if prompt_len > 5000:
        return False, f"Поле 'prompt' слишком длинное: {prompt_len} символов (максимум 5000)"
    
    # Валидация duration: опциональный, "5" | "10" | "15", default "5"
    duration = normalized_input.get('duration')
    if duration is not None:
        normalized_duration = _normalize_duration_for_wan_2_6(duration)
        if normalized_duration is None:
            return False, f"Поле 'duration' должно быть '5', '10' или '15' (получено: {duration})"
        normalized_input['duration'] = normalized_duration
    
    # Валидация resolution: опциональный, "720p" | "1080p", default "1080p"
    resolution = normalized_input.get('resolution')
    if resolution is not None:
        normalized_resolution = _normalize_resolution_for_wan_2_6(resolution)
        if normalized_resolution is None:
            return False, f"Поле 'resolution' должно быть '720p' или '1080p' (получено: {resolution})"
        normalized_input['resolution'] = normalized_resolution
    
    return True, None
```

### Нормализация параметров

Функции нормализации автоматически конвертируют числа в строки:

```python
def _normalize_duration_for_wan_2_6(value: Any) -> Optional[str]:
    """
    Нормализует duration для wan/2-6-text-to-video.
    Принимает числа (5, 10, 15) или строки ("5", "10", "15") и возвращает строку.
    """
    # Конвертирует 5 -> "5", 10 -> "10", 15 -> "15"
    # Убирает "s" или "seconds" в конце
    # Возвращает None если значение невалидно
```

### Дефолтные значения

Если параметры не указаны, применяются дефолты:

```python
if model_id == "wan/2-6-text-to-video":
    if 'duration' not in normalized_input:
        normalized_input['duration'] = "5"  # Default согласно документации
    if 'resolution' not in normalized_input:
        normalized_input['resolution'] = "1080p"  # Default согласно документации
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
  "model": "wan/2-6-text-to-video",
  "input": {
    "prompt": "In a hyperrealistic ASMR video, a hand uses a knitted knife to slowly slice a burger made entirely of knitted wool.",
    "duration": "5",
    "resolution": "1080p"
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

1. **Валидация prompt**: Проверяется длина (1-5000 символов)
2. **Нормализация duration**: Автоматически конвертируется в строку ("5", "10", "15")
3. **Нормализация resolution**: Автоматически добавляется суффикс "p" если отсутствует
4. **Дефолтные значения**: Применяются если параметры не указаны
5. **Callback URL**: Передаётся в API если настроен

## 🔍 Логирование

Все параметры логируются (без секретов):

```
MODEL=wan/2-6-text-to-video TYPE=t2v INPUT_KEYS=['prompt', 'duration', 'resolution'] 
INPUT_PREVIEW={'prompt': 'In a hyperrealistic...', 'duration': '5', 'resolution': '1080p'}
```

## 📚 Связанные файлы

- `app/services/kie_input_builder.py` - Валидация и нормализация параметров
- `app/kie_catalog/input_schemas.py` - Схемы входных параметров
- `app/integrations/kie_client.py` - KIE API клиент
- `app/kie_catalog/models_pricing.yaml` - Каталог моделей и цен

## ⚠️ Важные замечания

1. **duration и resolution должны быть строками**, не числами
2. **prompt ограничен 5000 символами** - проверяется при валидации
3. **Дефолтные значения**: duration="5", resolution="1080p"
4. **Callback URL опционален** - если не указан, уведомления не отправляются

