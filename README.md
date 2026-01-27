# KIE (Knowledge Is Everything) Telegram Bot

Production-grade Telegram bot for AI model generation via Kie.ai API.

## 🚀 БЫСТРЫЙ СТАРТ

### Локальная разработка:

```bash
# 1. Установи зависимости
pip install -r requirements.txt

# 2. Установи переменные окружения (см. ниже)

# 3. Запусти бота
BOT_MODE=polling python entrypoints/run_bot.py
```

### Автоматический деплой через GitHub Actions:

1. **Добавь GitHub Secrets** (один раз):
   - `RENDER_DEPLOY_HOOK` (предпочтительно) ИЛИ `RENDER_API_KEY` + `RENDER_SERVICE_ID`
   - `RENDER_HEALTH_URL` (опционально, для health check)

2. **Push в main** → CI запускается автоматически
3. **После CI PASS** → Deploy на Render автоматически

**Подробнее:** см. `GITHUB_ACTIONS_SETUP.md`

**GitHub Secrets (один раз):**
- Перейди: Repository → Settings → Secrets and variables → Actions
- Добавь: `RENDER_DEPLOY_HOOK` = `https://api.render.com/deploy/srv-XXXXX?key=XXXXX`
  - Получи из: Render Dashboard → Service → Settings → Deploy Hook

---

## 🔐 ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ

### Обязательные:
- `TELEGRAM_BOT_TOKEN` - токен бота от @BotFather
- `KIE_API_KEY` - API ключ от Kie.ai
- `DATABASE_URL` - PostgreSQL connection string (для production)

### Опциональные:
- `BOT_MODE` - `polling` (default) или `webhook`
- `APP_ENV` - `prod` (default), `dev`, или `test`
- `FAKE_KIE_MODE` - `1` для тестов (обязательно в CI)
- `RENDER_API_KEY` - для чтения логов Render
- `RENDER_SERVICE_ID` - для чтения логов Render
- `AUTO_SET_WEBHOOK` - `1` чтобы принудительно включить авто-установку webhook в webhook-режиме
- `REQUIRE_WEBHOOK_REGISTERED` - `1` чтобы падать при пустом/несовпадающем webhook в Telegram

**Все секреты ТОЛЬКО через ENV, никаких .env файлов в репо!**

---

## 🤝 Partner quickstart (5 минут)

Для партнёров достаточно **4–5 переменных** в Render ENV:

```env
TELEGRAM_BOT_TOKEN=123456:ABCDEF
ADMIN_ID=123456789
BOT_INSTANCE_ID=partner-01
WEBHOOK_BASE_URL=https://your-service.onrender.com
KIE_API_KEY=optional-kie-api-key
```

Проверка после деплоя: откройте `/admin` и убедитесь, что статус DB/Redis **ok**, `BOT_INSTANCE_ID` отображается, а ключевые ENV отмечены как `SET`.  
Подробная инструкция: `docs/PARTNER_QUICKSTART.md`.

---

## 🧪 ТЕСТИРОВАНИЕ

```bash
# Установи тестовое окружение
export APP_ENV=test
export FAKE_KIE_MODE=1

# Запусти проверки
python scripts/verify_project.py
python scripts/behavioral_e2e.py
```

---

## 📊 КОМАНДЫ

### Проверка проекта:
```bash
python scripts/verify_project.py
```

### Поведенческое тестирование:
```bash
python scripts/behavioral_e2e.py
```

### Полный цикл автопилота:
```bash
python scripts/autopilot_one_command.py
```

### Чтение логов Render:
```bash
python scripts/read_logs.py --since 60m --grep "ERROR|Traceback"
```

---

## 📁 СТРУКТУРА ПРОЕКТА

```
├── bot_kie.py              # Главный файл бота
├── kie_models.py           # Список моделей KIE.ai
├── app/                    # Модули приложения
│   ├── config.py          # Конфигурация из ENV
│   ├── singleton_lock.py  # Singleton lock (409 fix)
│   └── bot_mode.py        # Управление режимами
├── scripts/                # Скрипты автопилота
│   ├── verify_project.py  # Единственная команда правды
│   ├── behavioral_e2e.py  # Поведенческое тестирование
│   ├── preflight_checks.py # Критические проверки
│   └── autopilot_one_command.py # Полный цикл
├── tests/                  # Тесты
│   ├── fakes/             # Fake API для тестов
│   └── test_*.py          # Unit/E2E тесты
├── .github/workflows/      # GitHub Actions
│   ├── ci.yml             # CI pipeline
│   └── deploy_render.yml  # Deploy на Render
└── artifacts/              # Артефакты проверок
├── knowledge_store/   # JSON storage directory
│   └── entries.json
└── README.md
```

## Running the Bot Locally

### Prerequisites
- Python 3.8+
- Telegram bot token (get from [@BotFather](https://t.me/BotFather))
- KIE API key (from KIE AI platform)

### Quick Start

1. **Install dependencies:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Create and configure `.env` file:**
   ```bash
   cp .env.example .env
   # Edit .env and fill in your values
   ```
   
   Required variables:
   - `TELEGRAM_BOT_TOKEN` - Your Telegram bot token
   - `KIE_API_KEY` - Your KIE API key
   - `KIE_API_URL` - KIE API endpoint (default: `https://api.kie.ai`)
   - `KIE_DEFAULT_MODEL` - (Optional) Default model ID for /ask command

3. **Run the bot:**
   ```bash
   python entrypoints/run_bot.py
   ```

   (Shortcut wrapper is available as `python run_bot.py`.)

### Important Notes
- **Only one instance** of the bot can use the same token simultaneously
- The bot uses **polling** to check for messages
- User data is stored in `knowledge_store/` directory

## Usage Examples

- `/start` - Initialize bot
- `/search Python` - Find entries containing "Python" in local knowledge base
- `/ask What is photosynthesis?` - Get relevant information
- `/add The sky is blue` - Add new knowledge to the database
- `/help` - Display available commands
- `/models` - List available models from KIE AI

## Development

The project is structured with:
- A modular knowledge storage system
- Asynchronous Telegram bot handlers
- Environment-based configuration
- Proper error handling
- Test scripts for functionality verification
