<<<<<<< HEAD
# KIE (Knowledge Is Everything) Telegram Bot

Production-grade Telegram bot for AI model generation via Kie.ai API.

## 🚀 БЫСТРЫЙ СТАРТ

### Локальная разработка:

```bash
# 1. Установи зависимости
pip install -r requirements.txt

# 2. Установи переменные окружения (см. ниже)

# 3. Запусти бота
BOT_MODE=polling python bot_kie.py
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

**Все секреты ТОЛЬКО через ENV, никаких .env файлов в репо!**

---

## 🧪 ТЕСТИРОВАНИЕ

```bash
# Установи тестовое окружение
export APP_ENV=test
export FAKE_KIE_MODE=1

# Запусти проверки
python scripts/verify_project.py
python scripts/behavioral_e2e.py
=======
﻿# Kie.ai Telegram Bot - Production Ready

AI генератор для изображений, видео и аудио через Telegram с монетизацией.

**📚 Документация:**
- [🚀 Quick Start для разработчиков](./QUICK_START_DEV.md)
- [🤝 Contributing Guidelines](./CONTRIBUTING.md)
- [🌐 Deployment на Render](./DEPLOYMENT.md)

**📊 Статус:** Production Ready | 72 модели | PostgreSQL + SQLite

---

## 🚀 Quick Start: Deploy to Render

**[📖 Полная инструкция по деплою →](./DEPLOYMENT.md)**

### За 3 минуты:

1. **PostgreSQL база:** New → PostgreSQL → Free tier
2. **Web Service:** New → Web Service → Python 3
3. **ENV переменные:**
   ```bash
   TELEGRAM_BOT_TOKEN=7...     # от @BotFather
   KIE_API_KEY=kie_...         # от Kie.ai
   DATABASE_URL=postgresql://  # Internal URL
   ADMIN_ID=123456789          # ваш Telegram ID
   BOT_MODE=webhook            # ОБЯЗАТЕЛЬНО для Render
   ```
4. **Deploy!** → Бот работает

**Build Command:**
```bash
pip install -r requirements.txt
```

**Start Command:**
```bash
python main_render.py
>>>>>>> cbb364c8c317bf2ab285b1261d4d267c35b303d6
```

---

<<<<<<< HEAD
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
   python run_bot.py
   ```

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
=======
## ✅ Production Safety

### 🔐 Pricing Protection (P0)

- ✅ **72 модели** в SOURCE_OF_TRUTH
- ✅ **Pricing:** точные цены из Kie.ai
- ✅ **Формула:** `USER_PRICE_RUB = KIE_PRICE_USD × FX_RATE × 2.0`
- ✅ **FX auto-update** из ЦБР (78.43 RUB/USD актуальный)
- ⚠️ **Input schemas:** требуют обновления (см. QUICK_START_DEV.md)

### 🔒 Singleton Lock

- ✅ PostgreSQL advisory lock
- ✅ TTL = 60 секунд
- ✅ Heartbeat каждые 20 секунд
- ✅ Автоочистка stale locks
- ✅ Graceful shutdown (SIGTERM/SIGINT)

### 🌐 Multi-Tenant

- ✅ Один репозиторий → много Render services
- ✅ ENV-based конфигурация
- ✅ `ADMIN_ID` CSV поддержка: `111,222,333`
- ✅ `INSTANCE_NAME` для мониторинга

---

## 📋 Environment Variables Reference

| Переменная | Обязательно | Описание | Пример |
|------------|-------------|----------|--------|
| `TELEGRAM_BOT_TOKEN` | ✅ | Токен от @BotFather | `7123456789:AAHd...` |
| `KIE_API_KEY` | ✅ | API ключ Kie.ai | `kie_...` |
| `DATABASE_URL` | ✅ | PostgreSQL URL | `postgresql://user:pass@host/db` |
| `ADMIN_ID` | ✅ | Telegram ID админов (CSV) | `123456789` или `111,222,333` |
| `BOT_MODE` | ✅ | `webhook` или `polling` | `webhook` (для Render) |
| `INSTANCE_NAME` | ❌ | Имя инстанса | `prod-bot-1` |
| `LOG_LEVEL` | ❌ | `DEBUG`/`INFO`/`WARNING` | `INFO` |
| `RENDER_EXTERNAL_URL` | ❌ | Автоматически (Render) | - |
| **`ADMIN_IDS`** | ❌ | **Альтернатива ADMIN_ID (CSV)** | `111,222,333` |
| **`CURRENCY`** | ❌ | **Валюта отображения** | `RUB` (default) |
| **`KIE_STUB`** | ❌ | **Stub режим для тестов** | `true` или `false` |
| **`PAYMENT_BANK`** | ❌ | **Банк для оплаты** | `Тинькофф` |
| **`PAYMENT_CARD`** | ❌ | **Номер карты** | `5536 9137 XXXX YYYY` |
| **`PAYMENT_CARD_HOLDER`** | ❌ | **Владелец карты** | `IVAN IVANOV` |
| **`PAYMENT_PHONE`** | ❌ | **Телефон для оплаты** | `+7 900 123-45-67` |
| **`PRICING_MARKUP`** | ❌ | **Множитель цены (default: 2.0)** | `2.0` |
| **`STORAGE_MODE`** | ❌ | **Режим хранения** | `local` или `s3` |
| **`SUPPORT_TELEGRAM`** | ❌ | **Telegram поддержки** | `@support_bot` |
| **`SUPPORT_TEXT`** | ❌ | **Текст поддержки** | `Напишите нам` |
| **`TEST_DATABASE_URL`** | ❌ | **БД для тестов** | `postgresql://...` |
| **`TEST_MODE`** | ❌ | **Тестовый режим** | `true` или `false` |
| **`WELCOME_BALANCE_RUB`** | ❌ | **Стартовый баланс новых пользователей** | `100` (₽) |

### Pricing Formula (MASTER PROMPT compliance):
```python
price_rub = price_usd * 78.0 * PRICING_MARKUP
```
- **USD_TO_RUB rate:** 78.0 ₽/USD (фиксированный)
- **MARKUP:** 2.0 (можно переопределить через `PRICING_MARKUP`)
- **Формула:** строго соблюдается во всех модулях

---

## 🧪 Testing

```bash
# Все тесты
python -m pytest tests/ -v

# Pricing safety
python scripts/kie_truth_audit.py

# Registry enrichment
python scripts/enrich_registry.py
```

**59 тестов проходят** ✅

---

## 📦 Возможности

- ✅ **AI генерация:** изображения (Flux, DALL-E), видео (Kling, Luma), аудио
- ✅ **Платежи:** предоплата через Telegram Stars, автоматические возвраты
- ✅ **Pricing safety:** NO fallback prices, только проверенные цены
- ✅ **Singleton lock:** предотвращение дубликатов при blue-green deployment
- ✅ **Graceful shutdown:** корректная остановка при deployment
- ✅ **Multi-tenant:** несколько ботов из одного кода
- `PORT=10000` (healthcheck listener)
- `DRY_RUN=0`

### Конфигурация (опционально)

Создайте `config.json` на основе `config.json.example`:

```json
{
  "base_url": "https://api.kie.ai/api/v1",
  "market_url": "https://kie.ai/ru/market",
  "max_models": 50,
  "request_delay": 0.3,
  "timeout": 15
}
```

Или используйте переменные окружения:
- `KIE_BASE_URL` - базовый URL API
- `KIE_MARKET_URL` - URL маркета
- `MAX_MODELS` - максимальное количество моделей
- `REQUEST_DELAY` - задержка между запросами
- `REQUEST_TIMEOUT` - таймаут запросов

## 🎯 Использование

### ⚠️ Важно: Одноразовый парсинг

Парсинг выполняется **один раз локально**. Результаты сохраняются в `kie_full_api.json` и используются на Render без повторного парсинга.

```bash
# Запуск парсинга (один раз)
python kie_api_scraper.py

# Принудительный перезапуск (если данные уже есть)
python kie_api_scraper.py --force
```

Скрипт автоматически:
1. Сканирует страницу маркета
2. Парсит документацию каждой модели (параллельно)
3. Валидирует структуру всех моделей
4. Сохраняет результаты в `kie_full_api.json`
5. Сохраняет статистику в `kie_scraper_stats.json`

**После парсинга:**
- Закоммитьте `kie_full_api.json` в Git
- На Render парсинг **НЕ запускается** автоматически
- Используются уже спарсенные данные

### Дополнительные опции (как библиотека):

```python
from kie_api_scraper import KieApiScraper

# Настройка количества потоков и кэширования
scraper = KieApiScraper(max_workers=10, enable_cache=True)

# Запуск парсинга
models = scraper.run_full_scrape()

# Фильтрация моделей
video_models = scraper.filter_models(category='video', has_endpoint=True)

# Экспорт по категориям
scraper.export_models_by_category('exports')
```

### Переменные окружения:

- `EXPORT_BY_CATEGORY=true` - включить экспорт по категориям

## 📋 Структура данных

Каждая модель содержит:
- `name` - название модели
- `endpoint` - API endpoint (проверен и валидирован)
- `method` - HTTP метод (обычно POST)
- `base_url` - базовый URL API
- `params` - параметры модели (duration, width, height, steps, temperature, max_length)
- `input_schema` - схема входных данных с обязательными полями
- `example` - пример использования (JSON строка)
- `example_request` - структурированный пример запроса (объект)
- `price` - цена (если доступна)
- `category` - категория модели (video, image, text, audio, other)

## ✅ Валидация

Скрипт автоматически проверяет:
- Наличие всех обязательных полей
- Правильность типов данных
- Соответствие base_url
- Структуру параметров

## 📁 Файлы

- `kie_api_scraper.py` - основной скрипт
- `requirements.txt` - зависимости Python
- `runtime.txt` - версия Python для Render
- `render.yaml` - конфигурация для деплоя на Render
- `.renderignore` - игнорируемые файлы
- `kie_full_api.json` - ⭐ **ГЛАВНЫЙ ФАЙЛ** - результат парсинга (создается после локального запуска)
- `kie_scraper_stats.json` - статистика и метрики (создается после запуска)
- `kie_scraper.log` - лог файл с детальной информацией
- `config.json` - конфигурация (опционально, см. config.json.example)
- `exports/` - экспорт по категориям (если включен)

**Важно:** Файл `kie_full_api.json` должен быть закоммичен в Git и использоваться на Render без повторного парсинга.

## 🔧 Требования

- Python 3.7+
- requests>=2.31.0
- beautifulsoup4>=4.12.0
- lxml>=4.9.0
- urllib3>=2.0.0

## ⚡ Производительность

- **Параллельная обработка**: до 5-10 потоков (настраивается)
- **Кэширование**: избежание повторных запросов
- **Retry механизм**: автоматические повторы при ошибках
- **Оптимизированный парсинг**: множественные стратегии поиска

## 📊 Метрики

После выполнения создается файл `kie_scraper_stats.json` с:
- Временем выполнения
- Количеством запросов (всего, кэшированных, ошибок)
- Статистикой по категориям
- Результатами валидации

## 📝 Лицензия

MIT
>>>>>>> cbb364c8c317bf2ab285b1261d4d267c35b303d6
