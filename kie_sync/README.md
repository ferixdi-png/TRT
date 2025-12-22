# KIE Market Synchronizer

Синхронизатор для автоматического сбора данных о моделях с https://kie.ai/market

## Установка

```bash
pip install -r kie_sync/requirements.txt
playwright install chromium
```

## Использование

### 1. Discover режим (поиск JSON endpoints)

Сначала запустите discover для анализа структуры данных:

```bash
python -m kie_sync.cli discover
```

Это найдет все JSON endpoints и структуры данных на странице market.

### 2. Sync режим (синхронизация)

После discover запустите sync для обновления файлов:

```bash
# Dry-run (показать что изменится)
python -m kie_sync.cli sync --dry-run

# Реальная синхронизация
python -m kie_sync.cli sync

# Синхронизация конкретной модели
python -m kie_sync.cli sync --model "wan/2-6-text-to-video"
```

## Структура выходных файлов

### pricing/config.yaml
Матрица цен в USD для каждой модели:
```yaml
models:
  wan/2-6-text-to-video:
    type: matrix
    axes: ["duration", "resolution"]
    table:
      "5":
        "720p": 0.35
        "1080p": 0.53
```

### models/catalog.yaml
Input схемы для каждой модели:
```yaml
models:
  wan/2-6-text-to-video:
    input_schema:
      prompt:
        type: string
        required: true
        max_length: 800
      duration:
        type: enum
        required: false
        enum: ["5", "10", "15"]
```

## Валидация

Автоматическая валидация проверяет:
- YAML валидность
- Required поля не пустые
- Enum значения - строки
- max_len/лимиты - числовые
