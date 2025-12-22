# АРХИТЕКТУРА СИСТЕМЫ

**Дата создания:** 2025-12-21  
**Версия:** 1.0

---

## ТОЧКИ ВХОДА (ENTRYPOINTS)

### Render (Production)
- **Файл:** `app/main.py`
- **Команда:** `python -m app.main`
- **Функции:**
  - `load_settings()` - загрузка и валидация настроек из ENV
  - `build_application(settings)` - создание Telegram Application
  - `run(settings, application)` - запуск бота (polling/webhook)

### Legacy Entrypoint
- **Файл:** `run_bot.py` (deprecated)
- **Файл:** `bot_kie.py` (функция `main()`)
- **Использование:** Fallback если `create_bot_application` не найден

---

## СЛОИ АРХИТЕКТУРЫ

### 1. HANDLERS LAYER (Telegram Bot API)

**Файл:** `bot_kie.py` (основной, ~26,000 строк)

**Компоненты:**
- **Command Handlers:**
  - `/start` - приветствие и главное меню
  - `/help` - справка
  - `/balance` - проверка баланса
  - `/cancel` - отмена операции
  - `/models` - список моделей
  - `/generate` - начало генерации

- **Callback Handlers:**
  - `button_callback()` - универсальный роутер для всех кнопок
  - Обрабатывает: `gen_type:`, `category:`, `select_model:`, `set_param:`, `confirm_generate`, и т.д.

- **Message Handlers:**
  - `input_parameters()` - сбор параметров генерации (текст, фото, видео)
  - `handle_payment_screenshot()` - обработка скриншотов оплаты
  - `handle_text_message()` - обработка текстовых сообщений

- **Conversation Handlers:**
  - Генерация: `SELECTING_MODEL` → `INPUTTING_PARAMS` → `CONFIRMING_GENERATION`
  - Оплата: `SELECTING_AMOUNT` → `WAITING_PAYMENT_SCREENSHOT`
  - Админ: `WAITING_BROADCAST_MESSAGE`, `WAITING_CURRENCY_RATE`

**Состояние пользователя:**
- `user_sessions[user_id]` - сессии для сбора параметров
- `active_generations[(user_id, task_id)]` - активные генерации
- `active_generations_lock` - asyncio.Lock для защиты

---

### 2. SERVICES LAYER

**Директория:** `app/services/`

**Модули:**
- **`user_service.py`** - операции с пользователями
- **`payments_service.py`** - операции с платежами
- **`generation_service.py`** - управление генерациями
  - `create_generation()` - создание задачи генерации
  - `poll_generation_status()` - опрос статуса
  - `cancel_generation_job()` - отмена генерации

---

### 3. INTEGRATIONS LAYER

**Директория:** `app/integrations/`

**Модули:**
- **`kie_client.py`** - клиент для KIE AI API
  - `create_task()` - создание задачи
  - `get_task_status()` - получение статуса
  - `get_credits()` - проверка баланса API
  - Retry/backoff логика

- **`kie_stub.py`** - симулятор KIE API для тестов
  - Активируется через `KIE_STUB=1`

---

### 4. STORAGE LAYER

**Директория:** `app/storage/`

**Интерфейс:** `app/storage/base.py` - `BaseStorage`

**Реализации:**
- **`json_storage.py`** - JSON файлы в `DATA_DIR`
  - Атомарные записи (temp + rename)
  - Filelock для безопасности
  - Файлы: `user_balances.json`, `payments.json`, `generations_history.json`, и т.д.

- **`pg_storage.py`** - PostgreSQL через `asyncpg`
  - Connection pooling
  - Транзакции для атомарности

**Factory:** `app/storage/factory.py`
- Автоматический выбор: PostgreSQL (если `DATABASE_URL`) или JSON

---

### 5. DOMAIN LAYER

**Директория:** `app/domain/`

**Модули:**
- **`models_registry.py`** - реестр всех 47 моделей KIE AI
  - `get_model_by_id()` - получение модели по ID
  - `get_models_by_category()` - фильтрация по категории
  - `get_generation_types()` - типы генераций
  - `normalize_model_for_api()` - нормализация для API

---

## ГДЕ ЖИВЁТ СОСТОЯНИЕ ПОЛЬЗОВАТЕЛЯ

### 1. Runtime State (в памяти)
- **`user_sessions[user_id]`** - сессии для сбора параметров
  - Структура: `{'model_id': str, 'params': dict, 'waiting_for': str, ...}`
  - Очищается после завершения операции или таймаута

- **`active_generations[(user_id, task_id)]`** - активные генерации
  - Структура: `{'session_data': dict, 'task_id': str, 'status': str, ...}`
  - Очищается после завершения/отмены генерации

### 2. Persistent State (storage)
- **Баланс:** `storage.get_user_balance(user_id)`
- **Язык:** `storage.get_user_language(user_id)`
- **История генераций:** `storage.get_user_generations_history(user_id)`
- **Платежи:** `storage.list_payments(user_id)`
- **Рефералы:** `storage.get_referrals_for_user(user_id)`

### 3. Кеши
- **Кеш файлов:** `_data_cache` (в `bot_kie.py`)
- **Кеш HTTP клиента:** `_http_client` (aiohttp.ClientSession)
- **TTL:** `CACHE_TTL = 300` секунд

---

## ЗАВИСИМОСТИ МЕЖДУ СЛОЯМИ

```
bot_kie.py (handlers)
    ↓
app/services/* (business logic)
    ↓
app/integrations/* (external APIs)
    ↓
app/storage/* (data persistence)
    ↓
app/domain/* (domain models)
```

**Важно:** Handlers не должны напрямую обращаться к storage/integrations, только через services.

---

## КОНФИГУРАЦИЯ

**Файл:** `app/config.py`

**Settings:**
- Загружается из ENV переменных
- Fail-fast валидация обязательных полей
- Graceful degradation для опциональных

**Глобальный экземпляр:** `get_settings()` - singleton

---

## ЛОГИРОВАНИЕ

**Файл:** `app/utils/logging_config.py`

**Особенности:**
- Структурированное логирование
- `log_error_with_stacktrace()` - детальные ошибки
- Настройка через `setup_logging()`

---

## SINGLETON LOCK

**Файл:** `app/utils/singleton_lock.py`

**Механизм:**
1. PostgreSQL advisory lock (если `DATABASE_URL`)
2. Filelock `/app/data/bot.lock` (fallback)

**Цель:** Предотвратить двойной запуск на Render

---

## HEALTHCHECK

**Файл:** `app/utils/healthcheck.py`

**Endpoint:** `/health`

**Ответ:** JSON с `uptime`, `storage`, `kie_mode`

**Особенности:**
- Запускается в том же event loop
- Не блокирует polling

---

## ИЗВЕСТНЫЕ ПРОБЛЕМЫ АРХИТЕКТУРЫ

1. **Монолитный `bot_kie.py`** (~26,000 строк)
   - Сложно поддерживать
   - Высокий риск регрессий

2. **Глобальные переменные:**
   - `user_sessions`, `active_generations`
   - Нет централизованного управления состоянием

3. **Дублирование кода:**
   - Множественные проверки баланса
   - Повторяющаяся логика валидации

4. **Смешение слоёв:**
   - Handlers напрямую обращаются к storage
   - Нет четкого разделения ответственности

---

## ПЛАН УЛУЧШЕНИЙ

См. `docs/PLAN.md` для детального плана идеализации.
