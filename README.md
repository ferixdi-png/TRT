# KIE (Knowledge Is Everything) Telegram Bot

Production-grade Telegram bot for AI model generation via Kie.ai API.

**📚 Документация:**
- [🚀 Quick Start для разработчиков](./QUICK_START_DEV.md)
- [🤝 Contributing Guidelines](./CONTRIBUTING.md)
- [🌐 Deployment на Render](./DEPLOYMENT.md)

**📊 Статус:** Production Ready | 72 модели | PostgreSQL + SQLite

---

## 🚀 БЫСТРЫЙ СТАРТ

### Локальная разработка:

```bash
# 1. Установи зависимости
pip install -r requirements.txt

# 2. Установи переменные окружения (см. ниже)

# 3. Запусти бота
BOT_MODE=polling python bot_kie.py
```

### Deploy to Render (за 3 минуты):

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
- `ADMIN_ID` - Telegram ID админов (CSV: `111,222,333`)
- `BOT_MODE` - `webhook` (для Render) или `polling` (для локальной разработки)

### Опциональные:
- `APP_ENV` - `prod` (default), `dev`, или `test`
- `FAKE_KIE_MODE` - `1` для тестов (обязательно в CI)
- `RENDER_API_KEY` - для чтения логов Render
- `RENDER_SERVICE_ID` - для чтения логов Render
- `INSTANCE_NAME` - имя инстанса для мониторинга
- `LOG_LEVEL` - `DEBUG`/`INFO`/`WARNING` (default: `INFO`)
- `PAYMENT_BANK` - банк для оплаты
- `PAYMENT_CARD_HOLDER` - владелец карты
- `PAYMENT_PHONE` - телефон для оплаты
- `SUPPORT_TELEGRAM` - Telegram поддержки
- `SUPPORT_TEXT` - текст поддержки
- `PRICING_MARKUP` - множитель цены (default: 2.0)
- `WELCOME_BALANCE_RUB` - стартовый баланс новых пользователей (default: 0)

**Все секреты ТОЛЬКО через ENV, никаких .env файлов в репо!**

---

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

## 🧪 ТЕСТИРОВАНИЕ

```bash
# Установи тестовое окружение
export APP_ENV=test
export FAKE_KIE_MODE=1

# Запусти проверки
python scripts/verify_project.py
python scripts/behavioral_e2e.py
```

### Все тесты:
```bash
python -m pytest tests/ -v
```

**59 тестов проходят** ✅

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
├── main_render.py          # Точка входа для Render
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
```

---

## 📦 Возможности

- ✅ **AI генерация:** изображения (Flux, DALL-E), видео (Kling, Luma), аудио
- ✅ **Платежи:** предоплата через Telegram Stars, автоматические возвраты
- ✅ **Pricing safety:** NO fallback prices, только проверенные цены
- ✅ **Singleton lock:** предотвращение дубликатов при blue-green deployment
- ✅ **Graceful shutdown:** корректная остановка при deployment
- ✅ **Multi-tenant:** несколько ботов из одного кода
- ✅ **Health check:** `/health` endpoint для мониторинга

---

## 📝 Лицензия

MIT
