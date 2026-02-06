# 🚀 ИНСТРУКЦИЯ ПО ДЕПЛОЮ НА RENDER

## Дата: 2025-12-18

---

## 📋 ПРЕДВАРИТЕЛЬНЫЕ ТРЕБОВАНИЯ

### 1. Аккаунт Render
- Зарегистрируйтесь на [render.com](https://render.com)
- Подтвердите email

### 2. Подготовка репозитория
- Проект должен быть в Git репозитории (GitHub, GitLab, Bitbucket)
- Все файлы должны быть закоммичены

---

## 🔧 ШАГ 1: НАСТРОЙКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ

В Render Dashboard → Environment Variables добавьте:

### Обязательные переменные (установить вручную в Render Dashboard):

```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_here
ADMIN_ID=your_telegram_user_id

# KIE AI API
KIE_API_KEY=your_kie_api_key_here

# Database (PostgreSQL)
DATABASE_URL=postgresql://user:***REDACTED***@host:port/database
```

**Примечание:** `DATABASE_URL` автоматически устанавливается при создании PostgreSQL Database в Render.

### Опциональные переменные (можно установить вручную или оставить значения по умолчанию):

```bash
# KIE AI API
KIE_API_URL=https://api.kie.ai  # По умолчанию: https://api.kie.ai

# Runtime Configuration
ALLOW_REAL_GENERATION=1  # 1 для продакшн, 0 для тестирования
TEST_MODE=0  # 0 для продакшн, 1 для тестирования
DRY_RUN=0  # 0 для продакшн, 1 для симуляции

# Pricing
CREDIT_TO_RUB_RATE=0.1  # Курс кредита к рублю

# Timeouts и Limits
KIE_TIMEOUT_SECONDS=30
MAX_CONCURRENT_GENERATIONS_PER_USER=3
DB_MAXCONN=3

# Платежи (опционально, если нужны)
PAYMENT_BANK=your_bank_details
PAYMENT_CARD_HOLDER=card_holder_name
PAYMENT_PHONE=payment_phone_number

# Поддержка (опционально, если нужна)
SUPPORT_TELEGRAM=@support_username
SUPPORT_TEXT=Support contact information
```

---

## 🚀 ШАГ 2: СОЗДАНИЕ СЕРВИСА НА RENDER

### 2.1. Создание Web Service

1. В Render Dashboard нажмите **"New"** → **"Web Service"**
2. Подключите ваш Git репозиторий
3. Настройте сервис:

**Build Command:**
```bash
pip install -r requirements.txt
```

**Start Command:**
```bash
python entrypoints/run_bot.py
```

**Environment:** `Python 3`

**⚠️ ВАЖНО:** Это Python проект, НЕ Node.js!
- ❌ НЕ используйте `npm install`
- ❌ НЕ используйте `node index.js`
- ❌ НЕ используйте `npm start`
- ✅ Используйте только `pip install` и `python entrypoints/run_bot.py`

**Plan:** Выберите подходящий план (Free/Starter/Standard)

### 2.2. Создание PostgreSQL Database

1. В Render Dashboard нажмите **"New"** → **"PostgreSQL"**
2. Выберите план (Free/Starter/Standard)
3. Скопируйте **Internal Database URL**
4. Добавьте его в переменные окружения как `DATABASE_URL`

---

## 📝 ШАГ 3: НАСТРОЙКА БАЗЫ ДАННЫХ

### 3.1. Инициализация схемы

База данных инициализируется автоматически при первом запуске бота через `init_database()`.

### 3.2. Очистка перед деплоем (опционально)

Если нужно очистить старые данные:

```bash
python cleanup_database.py
```

---

## ✅ ШАГ 4: ФИНАЛЬНАЯ ПРОВЕРКА ПЕРЕД ДЕПЛОЕМ

Запустите скрипт финальной проверки:

```bash
python scripts/final_pre_deploy_check.py
```

Скрипт проверит:
- ✅ Синхронизацию всех моделей
- ✅ Обработку ошибок
- ✅ Тесты
- ✅ Логи и отчёты
- ✅ Подготовку к деплою
- ✅ Наличие всех необходимых файлов

---

## 🚀 ШАГ 5: ДЕПЛОЙ

### 5.1. Автоматический деплой

Render автоматически деплоит при каждом push в основную ветку:

```bash
git add .
git commit -m "Prepare for Render deploy"
git push origin main
```

### 5.2. Ручной деплой

В Render Dashboard:
1. Откройте ваш Web Service
2. Нажмите **"Manual Deploy"** → **"Deploy latest commit"**

---

## 🔍 ШАГ 6: ПРОВЕРКА ПОСЛЕ ДЕПЛОЯ

### 6.1. Проверка логов

В Render Dashboard → Logs проверьте:
- ✅ Бот запустился без ошибок
- ✅ Подключение к БД успешно
- ✅ Подключение к KIE API работает

### 6.2. Тестирование бота

1. Откройте бота в Telegram
2. Отправьте команду `/start`
3. Проверьте работу кнопок
4. Попробуйте создать тестовую генерацию (в TEST_MODE)

---

## 🛠️ ШАГ 7: МОНИТОРИНГ И ОБСЛУЖИВАНИЕ

### 7.1. Мониторинг ошибок

Проверяйте логи регулярно:
```bash
# В Render Dashboard → Logs
# Или через CLI (если настроен)
render logs
```

### 7.2. Генерация отчётов

Для анализа ошибок:
```bash
python scripts/generate_error_report.py
```

### 7.3. Синхронизация моделей

Для обновления моделей с KIE.ai:
```bash
python scripts/kie_market_crawler.py
python scripts/sync_kie_models_from_catalog.py
```

### 7.4. Очистка базы данных

Для очистки старых данных:
```bash
python cleanup_database.py
```

---

## ⚠️ ВАЖНЫЕ ЗАМЕЧАНИЯ

### Безопасность:
- ✅ **НИКОГДА** не коммитьте `.env` файл с реальными ключами
- ✅ Используйте переменные окружения в Render
- ✅ Регулярно обновляйте зависимости

### Производительность:
- ✅ Настройте автоматическую очистку БД
- ✅ Мониторьте размер БД (не должен превышать 1GB на Free плане)
- ✅ Используйте кеширование для частых запросов

### Тестирование:
- ✅ Перед продакшн деплоем протестируйте в TEST_MODE
- ✅ Убедитесь, что DRY_RUN работает корректно
- ✅ Проверьте все кнопки и callback'и

---

## 📞 ПОДДЕРЖКА

При возникновении проблем:
1. Проверьте логи в Render Dashboard
2. Запустите `scripts/final_pre_deploy_check.py`
3. Проверьте переменные окружения
4. Убедитесь, что все зависимости установлены

---

## ✅ ЧЕКЛИСТ ПЕРЕД ДЕПЛОЕМ

- [ ] Все переменные окружения настроены
- [ ] База данных создана и подключена
- [ ] Финальная проверка пройдена (`final_pre_deploy_check.py`)
- [ ] Тесты проходят (`make test`)
- [ ] Все модели синхронизированы
- [ ] Обработка ошибок работает
- [ ] README обновлён
- [ ] Git репозиторий готов к деплою

---

**Готово к деплою! 🚀**
