# 🔐 ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ДЛЯ RENDER

## Дата: 2025-12-18

---

## 📋 ОБЯЗАТЕЛЬНЫЕ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ

### Основные переменные:

```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_here

# KIE AI API
KIE_API_KEY=your_kie_api_key_here
KIE_API_URL=https://api.kie.ai

# Database
DATABASE_URL=postgresql://user:***REDACTED***@host:port/database

# Admin
ADMIN_ID=your_telegram_user_id
```

---

## 📋 ОПЦИОНАЛЬНЫЕ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ

### Платежи:

```bash
PAYMENT_BANK=your_bank_details
PAYMENT_CARD_HOLDER=card_holder_name
PAYMENT_PHONE=payment_phone_number
```

### Поддержка:

```bash
SUPPORT_TELEGRAM=@support_username
SUPPORT_TEXT=Support contact information
```

### Runtime Configuration:

```bash
# Для продакшн используйте:
ALLOW_REAL_GENERATION=1
TEST_MODE=0
DRY_RUN=0

# Для тестирования используйте:
ALLOW_REAL_GENERATION=0
TEST_MODE=1
DRY_RUN=1
```

### Pricing:

```bash
CREDIT_TO_RUB_RATE=0.1
```

### Timeouts и Limits:

```bash
KIE_TIMEOUT_SECONDS=30
MAX_CONCURRENT_GENERATIONS_PER_USER=3
DB_MAXCONN=3
```

---

## 🔧 КАК НАСТРОИТЬ В RENDER

1. Откройте ваш Web Service в Render Dashboard
2. Перейдите в раздел **"Environment"**
3. Добавьте все необходимые переменные окружения
4. Сохраните изменения
5. Перезапустите сервис

---

## ✅ ПРОВЕРКА ПЕРЕМЕННЫХ

Проект автоматически проверяет наличие обязательных переменных при запуске:

- `TELEGRAM_BOT_TOKEN` - обязательна
- `KIE_API_KEY` - обязательна для реальных генераций
- `DATABASE_URL` - обязательна для работы с БД
- `ADMIN_ID` - обязательна для админ-функций

Если переменная отсутствует, бот будет использовать значения по умолчанию или JSON fallback.

---

## 🚀 КАКИЕ ФАЙЛЫ ЗАПУСКАТЬ

| Режим | Что запускать | Команда |
| --- | --- | --- |
| polling | `entrypoints/run_bot.py` (канон) | `python entrypoints/run_bot.py` |
| webhook | `entrypoints/run_bot.py` или `main_render.py` | `python entrypoints/run_bot.py` |
| web (healthcheck) | `entrypoints/run_bot.py` | `BOT_MODE=web python entrypoints/run_bot.py` |

**Важно:** `app/main.py` предназначен только для локального polling/web и завершится с ошибкой при `BOT_MODE=webhook`.

---

## 📝 ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ В КОДЕ

```python
import os
from dotenv import load_dotenv

load_dotenv()

# Основные переменные
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
KIE_API_KEY = os.getenv('KIE_API_KEY')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

# Опциональные переменные
PAYMENT_BANK = os.getenv('PAYMENT_BANK', '')
PAYMENT_CARD_HOLDER = os.getenv('PAYMENT_CARD_HOLDER', '')
PAYMENT_PHONE = os.getenv('PAYMENT_PHONE', '')
SUPPORT_TELEGRAM = os.getenv('SUPPORT_TELEGRAM', '')
SUPPORT_TEXT = os.getenv('SUPPORT_TEXT', '')

# Runtime configuration
ALLOW_REAL_GENERATION = os.getenv('ALLOW_REAL_GENERATION', '0') == '1'
TEST_MODE = os.getenv('TEST_MODE', '0') == '1'
DRY_RUN = os.getenv('DRY_RUN', '0') == '1'
```

---

## ⚠️ ВАЖНО

- **НЕ коммитьте** `.env` файл с реальными ключами в Git
- Используйте переменные окружения в Render Dashboard
- Все секретные данные должны быть в переменных окружения, а не в коде

---

## ✅ ГОТОВО

После настройки всех переменных окружения в Render, проект готов к деплою!
