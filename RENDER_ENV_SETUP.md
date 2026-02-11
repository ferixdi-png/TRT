# 🔐 НАСТРОЙКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ДЛЯ RENDER

## Дата: 2025-12-18

---

## ✅ ИСПОЛЬЗОВАНИЕ СУЩЕСТВУЮЩИХ ПЕРЕМЕННЫХ

Проект использует **только те переменные окружения**, которые уже настроены в Render для вашего проекта.

**НЕ создавайте дополнительные переменные** - используйте текущие настройки.

---

## 📋 ОБЯЗАТЕЛЬНЫЕ ПЕРЕМЕННЫЕ

Эти переменные **обязательны** для работы бота:

### 1. `TELEGRAM_BOT_TOKEN`
- **Описание:** Токен Telegram бота
- **Где получить:** [@BotFather](https://t.me/BotFather)
- **Использование в коде:** `os.getenv('TELEGRAM_BOT_TOKEN')`

### 2. `KIE_API_KEY`
- **Описание:** Ключ API KIE.ai
- **Где получить:** [kie.ai](https://kie.ai)
- **Использование в коде:** `os.getenv('KIE_API_KEY')`

### 3. `DATABASE_URL`
- **Описание:** URL базы данных PostgreSQL
- **Автоматически:** Устанавливается при создании PostgreSQL Database в Render
- **Использование в коде:** `os.getenv('DATABASE_URL')`

### 4. `ADMIN_ID`
- **Описание:** ID администратора Telegram
- **Как получить:** Отправьте `/start` боту [@userinfobot](https://t.me/userinfobot)
- **Использование в коде:** `int(os.getenv('ADMIN_ID', '0'))`

---

## 📋 ОПЦИОНАЛЬНЫЕ ПЕРЕМЕННЫЕ

Эти переменные **опциональны** - проект будет работать с значениями по умолчанию:

### Платежи (если нужны):
- `PAYMENT_BANK` - Детали банка
- `PAYMENT_CARD_HOLDER` - Имя держателя карты
- `PAYMENT_PHONE` - Номер телефона

### Поддержка (если нужна):
- `SUPPORT_TELEGRAM` - Telegram контакт поддержки
- `SUPPORT_TEXT` - Текст поддержки

### Runtime Configuration:
- `ALLOW_REAL_GENERATION` - Разрешить реальные генерации (по умолчанию: `0`)
- `TEST_MODE` - Тестовый режим (по умолчанию: `0`)
- `DRY_RUN` - Режим симуляции (по умолчанию: `0`)

### Дополнительные настройки:
- `KIE_API_URL` - URL API KIE.ai (по умолчанию: `https://api.kie.ai`)
- `CREDIT_TO_RUB_RATE` - Курс кредита к рублю (по умолчанию: `0.1`)
- `KIE_TIMEOUT_SECONDS` - Таймаут запросов (по умолчанию: `30`)
- `MAX_CONCURRENT_GENERATIONS_PER_USER` - Максимум генераций (по умолчанию: `3`)
- `DB_MAXCONN` - Максимум соединений с БД (по умолчанию: `3`)
- `STORAGE_MODE` - `auto` (по умолчанию). `auto` использует PostgreSQL при наличии `DATABASE_URL`, иначе GitHub storage
- `PARTNER_ID`/`BOT_INSTANCE_ID` - идентификатор партнера/инстанса, используется как ключ изоляции данных в PostgreSQL

---

## 🔧 КАК НАСТРОИТЬ В RENDER

1. Откройте ваш **Web Service** в Render Dashboard
2. Перейдите в раздел **"Environment"**
3. Проверьте наличие всех обязательных переменных:
   - `TELEGRAM_BOT_TOKEN`
   - `KIE_API_KEY`
   - `DATABASE_URL` (автоматически при создании БД)
   - `ADMIN_ID`
4. При необходимости добавьте опциональные переменные
5. Сохраните изменения
6. Перезапустите сервис

### Примечания по хранению и блокировкам
- `STORAGE_MODE=auto` использует PostgreSQL, если задан `DATABASE_URL`; при первом старте пустой БД данные мигрируются из GitHub storage автоматически
- Redis настраивается автором автоматически, партнёрам не нужно указывать `REDIS_URL`

---

## ✅ ПРОВЕРКА ПЕРЕМЕННЫХ

Запустите скрипт проверки:

```bash
python scripts/check_env_variables.py
```

Или:

```bash
python scripts/verify_render_env.py
```

Скрипт покажет:
- ✅ Какие переменные настроены
- ❌ Какие переменные отсутствуют
- ⚠️ Проблемы с форматом значений

---

## 📝 ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ В КОДЕ

Проект использует стандартный подход для работы с переменными окружения:

```python
import os
from dotenv import load_dotenv

load_dotenv()

# Обязательные переменные
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
KIE_API_KEY = os.getenv('KIE_API_KEY')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

# Опциональные переменные с значениями по умолчанию
KIE_API_URL = os.getenv('KIE_API_URL', 'https://api.kie.ai')
PAYMENT_BANK = os.getenv('PAYMENT_BANK', '')
PAYMENT_CARD_HOLDER = os.getenv('PAYMENT_CARD_HOLDER', '')
PAYMENT_PHONE = os.getenv('PAYMENT_PHONE', '')
SUPPORT_TELEGRAM = os.getenv('SUPPORT_TELEGRAM', '')
SUPPORT_TEXT = os.getenv('SUPPORT_TEXT', '')
```

---

## ⚠️ ВАЖНО

1. **НЕ коммитьте** `.env` файл с реальными ключами в Git
2. Используйте **только переменные окружения** в Render Dashboard
3. Все секретные данные должны быть в переменных окружения, **не в коде**
4. Используйте **существующие переменные** из Render, не создавайте новые

---

## ✅ ГОТОВО

После настройки всех переменных окружения в Render, проект готов к деплою!

Для проверки запустите:
```bash
python scripts/verify_render_env.py
```

