# Render-First Setup - Документация

Проект настроен для стабильного и предсказуемого запуска на Render.com (Web Service/Worker).

## Основные изменения

### 1. Единый модуль конфигурации

**`app/config.py`** - единственный источник истины для конфигурации:
- Читает ТОЛЬКО ENV переменные (никаких `.env` файлов в runtime)
- Валидация вызывается через `validate()` метод (не при импорте)
- Не падает на импорте - валидация только в entrypoint

**Использование:**
```python
from app.config import get_settings

# Без валидации (для импортов)
settings = get_settings()

# С валидацией (в entrypoint)
settings = get_settings(validate=True)
```

### 2. Thin-wrapper для обратной совместимости

**`config.py`** и **`config_runtime.py`** - тонкие обёртки вокруг `app/config`:
- Поддерживают старый API для обратной совместимости
- Делегируют все вызовы в `app.config`
- Отмечены как DEPRECATED

### 3. Единый entrypoint для Render

**`main_render.py`** - главная точка входа для Render:
- Логирует ENV snapshot (без секретов) при старте
- Поднимает health server на PORT (если задан - Web Service режим)
- Запускает Telegram bot (polling/webhook по ENV)
- Валидирует конфигурацию перед запуском
- Ничего не запускается при импорте модулей

**Использование:**
```bash
# На Render (Web Service)
python main_render.py

# Или через Dockerfile
CMD ["python3", "main_render.py"]
```

### 4. Dockerfile обновлён

Dockerfile использует `main_render.py` как entrypoint:
```dockerfile
CMD ["python3", "main_render.py"]
```

### 5. Preflight checks исправлены

**`scripts/preflight_checks.py`** - watchdog теперь умный:
- `PREFLIGHT_WATCHDOG=0` - выключает проверку watchdog
- `PREFLIGHT_WATCHDOG_MAX_HOURS=N` - максимальное количество часов (по умолчанию 24)
- Не падает на чистом окружении или dev окружении
- `artifacts/verify_last_pass.json` добавлен в `.gitignore`

## Критерии готовности

✅ **Старт на Render Web Service:**
- Порт открыт (`/health` => 200)
- Бот стартует
- ENV snapshot логируется

✅ **Старт на Render Worker:**
- Бот стартует без health server (PORT не задан)
- Работает без падений

✅ **Нет падений на импорте:**
- Валидация только в entrypoint
- Понятные ошибки в entrypoint

✅ **Preflight checks проходят:**
- Работают на чистом окружении
- Watchdog настраивается через ENV

## Environment Variables

### Обязательные
- `TELEGRAM_BOT_TOKEN` - токен Telegram бота

### Опциональные (с умолчаниями)
- `ADMIN_ID` - ID администратора (0 = отключено)
- `PORT` - порт для healthcheck (0 = Worker режим, без healthcheck)
- `BOT_MODE` - режим работы: `polling` или `webhook` (по умолчанию `polling`)
- `WEBHOOK_URL` - URL для webhook (обязателен если `BOT_MODE=webhook`)
- `DATABASE_URL` - строка подключения к PostgreSQL
- `STORAGE_MODE` - режим хранения: `postgres`, `json`, `auto` (по умолчанию `auto`)
- `KIE_API_KEY` - ключ API KIE.ai (опционально)
- `KIE_API_URL` - URL API KIE.ai (по умолчанию `https://api.kie.ai`)
- `DATA_DIR` - директория для данных (по умолчанию `/app/data`)

### Preflight checks
- `PREFLIGHT_WATCHDOG` - включить/выключить watchdog (`1` или `0`, по умолчанию `1`)
- `PREFLIGHT_WATCHDOG_MAX_HOURS` - максимальное количество часов для watchdog (по умолчанию `24`)

## Проверки

```bash
# Проверка синтаксиса
python -m compileall . -q

# Preflight checks
python scripts/preflight_checks.py

# (опционально) Verify project
python scripts/verify_project.py
```

## Миграция со старого кода

Если ваш код использует старые модули:
- `from config import settings` → `from app.config import get_settings; settings = get_settings()`
- `from config_runtime import is_test_mode` → `from app.config import get_settings; settings = get_settings(); settings.test_mode`

Старые модули работают через обратную совместимость, но рекомендуется мигрировать на `app.config`.

