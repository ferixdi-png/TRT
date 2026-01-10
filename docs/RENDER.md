# RENDER DEPLOYMENT CONFIGURATION

**Дата создания:** 2025-12-21  
**Версия:** 1.0

---

## START COMMAND

**Файл:** `render.yaml`

```yaml
startCommand: python -m app.main
```

**Entrypoint:** `app/main.py`

**Функции:**
- `load_settings()` - загрузка настроек
- `build_application()` - создание Application
- `run()` - запуск бота

---

## ENVIRONMENT VARIABLES

### Обязательные

| Переменная | Описание | При отсутствии |
|-----------|----------|----------------|
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота | exit(1) с логом "MISSING TELEGRAM_BOT_TOKEN" |

### Опциональные (graceful degradation)

| Переменная | Описание | При отсутствии |
|-----------|----------|----------------|
| `ADMIN_ID` | ID администратора | Админ-функции отключены, бот стартует |
| `KIE_API_KEY` | Ключ KIE AI API | Генерации отключены, бот стартует |
| `DATABASE_URL` | URL PostgreSQL | Используется JSON storage |
| `PORT` | Порт для healthcheck | Healthcheck не запускается |
| `DATA_DIR` | Директория для данных | По умолчанию: `/app/data` |
| `RENDER` | Флаг Render окружения | Автоматически устанавливается Render |
| `RENDER_EXTERNAL_URL` | Внешний URL | Опционально (не используется) |
| `WEB_CONCURRENCY` | Количество worker процессов | Опционально (не используется) |

### Дополнительные

| Переменная | Описание | По умолчанию |
|-----------|----------|--------------|
| `STORAGE_MODE` | Режим хранения (auto/postgres/json) | `auto` |
| `BOT_MODE` | Режим работы (polling/webhook) | `polling` |
| `WEBHOOK_BASE_URL` | Базовый URL для webhook | Не задан |
| `WEBHOOK_URL` | Legacy alias для webhook base URL (deprecated) | Не задан |
| `KIE_STUB` | Использовать stub вместо реального API | `0` (реальный API) |
| `PAYMENT_PHONE` | Номер телефона для СБП | Не задан |
| `PAYMENT_BANK` | Банк для СБП | Не задан |
| `PAYMENT_CARD_HOLDER` | Получатель для СБП | Не задан |

---

## HEALTHCHECK

**Файл:** `app/utils/healthcheck.py`

**Endpoint:** `/health`

**Метод:** GET

**Ответ:**
```json
{
  "status": "ok",
  "uptime": 12345,
  "storage": "json",
  "kie_mode": "real"
}
```

**Особенности:**
- Запускается в том же event loop (не блокирует polling)
- Порт берется из `PORT` env (по умолчанию 8000)
- Если `PORT` не задан → healthcheck не запускается

**render.yaml:**
```yaml
healthCheckPath: /health
healthCheckGracePeriod: 60
```

---

## SINGLETON LOCK

**Файл:** `app/utils/singleton_lock.py`

**Механизм:**
1. PostgreSQL advisory lock (если `DATABASE_URL` доступен)
   - Lock key: хеш от `TELEGRAM_BOT_TOKEN`
   - Соединение держится весь runtime
   - Освобождается при shutdown

2. Filelock (fallback)
   - Файл: `/app/data/bot.lock`
   - Non-blocking (timeout 0.1 сек)
   - Освобождается при shutdown

**При невозможности взять lock:**
- Лог: "ANOTHER INSTANCE RUNNING"
- `exit(0)` (не ошибка, чтобы Render не рестартил бесконечно)

**Важно:** Lock получается ДО любых async операций в `app/main.py:run()`

---

## DATA DIRECTORY

**По умолчанию:** `/app/data`

**Проверка при старте:**
- Создание директории (если не существует)
- Проверка прав записи (тест файла `.write_test`)
- Если нельзя писать → `exit(1)`

**Структура:**
```
/app/data/
├── bot.lock                    # Singleton lock
├── user_balances.json          # Балансы пользователей
├── payments.json                # История платежей
├── generations_history.json    # История генераций
├── user_languages.json          # Языковые настройки
├── daily_free_generations.json  # Бесплатные генерации
├── promocodes.json             # Промокоды
├── referrals.json              # Реферальная система
├── broadcasts.json             # Статистика рассылок
├── blocked_users.json          # Заблокированные пользователи
├── admin_limits.json           # Лимиты админов
├── currency_rate.json          # Курс валют
└── gift_claimed.json          # Подарки
```

**Важно:** На Render файловая система ephemeral, данные теряются при перезапуске контейнера. Для персистентности нужен volume или внешнее хранилище.

---

## BUILD CONFIGURATION

**Файл:** `render.yaml`

```yaml
services:
  - type: web
    name: telegram-bot
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python -m app.main
    envVars:
      - key: PYTHONPATH
        value: "."
    healthCheckPath: /health
    healthCheckGracePeriod: 60
```

---

## REQUIREMENTS

**Файл:** `requirements.txt`

**Ключевые зависимости:**
- `python-telegram-bot==20.8` (зафиксирована версия)
- `aiohttp>=3.8.0` (async HTTP)
- `asyncpg>=0.29.0` (PostgreSQL)
- `filelock>=3.13.0` (singleton lock)

**Опциональные (lazy import):**
- `Pillow` - закомментирован (опционально)
- `pytesseract` - закомментирован (опционально)

---

## ЛОГИРОВАНИЕ

**На старте:**
- "BOT STARTING" - начало запуска
- Startup banner с версией, режимом storage, KIE mode, и т.д.
- "BOT READY" - после регистрации handlers

**При ошибках:**
- Stacktrace в лог
- Пользователю: "Ошибка, попробуйте снова"

**Особенности:**
- Структурированное логирование через `app/utils/logging_config.py`
- Unicode поддержка для русских символов

---

## ИЗВЕСТНЫЕ ПРОБЛЕМЫ НА RENDER

1. **Ephemeral filesystem:**
   - Данные теряются при перезапуске
   - Решение: использовать PostgreSQL или внешнее хранилище

2. **409 Conflict:**
   - Двойной запуск polling
   - Решение: singleton lock + `delete_webhook` перед polling

3. **Healthcheck timeout:**
   - Render считает сервис мёртвым
   - Решение: healthcheck endpoint + grace period 60 сек

4. **Тишина в логах:**
   - Нет видимости что происходит
   - Решение: логирование на каждом этапе старта

---

## РЕКОМЕНДАЦИИ

1. **Использовать PostgreSQL:**
   - Персистентное хранилище
   - Advisory lock для singleton
   - Надежнее чем JSON файлы

2. **Мониторинг:**
   - Проверять логи на Render Dashboard
   - Настроить алерты на ошибки

3. **Backup:**
   - Регулярные бэкапы данных
   - Особенно `user_balances.json` и `payments.json`
