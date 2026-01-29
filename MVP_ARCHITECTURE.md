# 🏗️ MVP Architecture - ЖЕЛЕЗОБЕТОННАЯ БАЗА

> **ВНИМАНИЕ**: Этот документ фиксирует критичную архитектуру MVP.
> Любые изменения в описанных компонентах требуют обсуждения!

## 📋 Содержание
- [Критичные компоненты](#критичные-компоненты)
- [Запуск бота](#запуск-бота)
- [Storage Layer](#storage-layer)
- [Balance Operations](#balance-operations)
- [Payment Flow](#payment-flow)
- [Language System](#language-system)
- [Generation Flow](#generation-flow)
- [Partner Isolation](#partner-isolation)

---

## 🔴 Критичные компоненты (НЕ ТРОГАТЬ!)

### 1. Balance Operations (Транзакционная целостность)
**Файл:** `app/storage/postgres_storage.py`

```python
# ВСЕ операции с балансом используют транзакции с FOR UPDATE
async def add_user_balance(user_id, amount):
    async with conn.transaction():
        payload = await conn.fetchval(
            "SELECT payload FROM storage_json WHERE partner_id=$1 AND filename=$2 FOR UPDATE",
            ...
        )
        # Атомарное обновление
```

**Почему критично:**
- `FOR UPDATE` блокирует строку до завершения транзакции
- Предотвращает race conditions при параллельных операциях
- Гарантирует консистентность баланса

### 2. Partner Isolation (Multi-tenancy)
**Файл:** `app/storage/postgres_storage.py`

```sql
CREATE TABLE storage_json (
    partner_id TEXT NOT NULL,
    filename   TEXT NOT NULL,
    payload    JSONB NOT NULL,
    PRIMARY KEY (partner_id, filename)
);
```

**Почему критично:**
- Каждый партнёр имеет изолированные данные
- `partner_id` = `BOT_INSTANCE_ID` из ENV
- Нельзя получить доступ к данным другого партнёра

### 3. Payment Handlers (Telegram Stars)
**Файл:** `bot_kie.py`

```python
# Регистрация handlers
application.add_handler(PreCheckoutQueryHandler(handle_pre_checkout_query))
application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))
```

**Почему критично:**
- `handle_pre_checkout_query` - валидирует платёж ПЕРЕД списанием
- `handle_successful_payment` - начисляет баланс ПОСЛЕ успешной оплаты
- Порядок регистрации важен!

### 4. Language Priority System
**Файл:** `bot_kie.py` → `show_main_menu()`

```python
# Приоритет получения языка:
if has_user_language_set(user_id):
    user_lang = get_user_language(user_id)  # 1) Явно установленный
else:
    cached_lang = _get_menu_dep_cache(...)  # 2) Кэш меню
    if not cached_lang:
        user_lang = telegram_lang             # 3) Язык Telegram клиента
```

**Почему критично:**
- Явно установленный язык имеет высший приоритет
- Изменение сразу отображается в UI

### 5. Free Generations System
**Файл:** `app/storage/postgres_storage.py` → `consume_free_generation_once()`

```python
# Защита от дублирования через deductions
if task_id in deductions:
    return {"status": "duplicate", ...}

# Атомарное списание с транзакцией
async with conn.transaction():
    # FOR UPDATE lock
    # Проверка лимита
    # Запись в deductions
```

---

## 🚀 Запуск бота

### Последовательность инициализации

```
1. ENV Validation (app/config_env.py)
   ├── REQUIRED: TELEGRAM_BOT_TOKEN, BOT_INSTANCE_ID, ADMIN_ID, WEBHOOK_BASE_URL
   └── OPTIONAL: KIE_API_KEY, PAYMENT_*, SUPPORT_*

2. Storage Initialization (app/storage/factory.py)
   ├── PostgresStorage(dsn, partner_id=BOT_INSTANCE_ID)
   └── ensure_schema() → создаёт storage_json таблицу

3. Boot Cache Warmup (bot_kie.py)
   ├── Загрузка user_languages.json → _user_language_cache
   ├── Загрузка gift_claimed.json → _gift_claimed_cache
   └── Таймаут: BOOT_CACHE_LOAD_TIMEOUT_SECONDS (default: 1s)

4. Webhook/Polling Setup
   ├── BOT_MODE=webhook → set_webhook()
   └── BOT_MODE=polling → start_polling()

5. Handler Registration
   └── Порядок важен! (см. ниже)
```

### Порядок регистрации handlers

```python
# 1. Payment handlers (ПЕРВЫЕ!)
application.add_handler(PreCheckoutQueryHandler(handle_pre_checkout_query))
application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))

# 2. Command handlers
application.add_handler(CommandHandler('start', start))
application.add_handler(CommandHandler('admin', admin_command))
...

# 3. ConversationHandlers (с fallbacks)
generation_handler = ConversationHandler(
    entry_points=[...],
    states={...},
    fallbacks=[...]  # Включают set_language, back_to_menu
)

# 4. Generic callback handler (ПОСЛЕДНИЙ!)
application.add_handler(CallbackQueryHandler(button_callback, block=True))
```

---

## 💾 Storage Layer

### Архитектура

```
PostgresStorage
├── partner_id (BOT_INSTANCE_ID)
├── storage_json table
│   ├── user_balances.json
│   ├── daily_free_generations.json
│   ├── user_languages.json
│   ├── gift_claimed.json
│   └── balance_deductions.json (idempotency)
└── Methods:
    ├── get_user_balance()
    ├── add_user_balance() ← ТРАНЗАКЦИЯ
    ├── subtract_user_balance() ← ТРАНЗАКЦИЯ
    ├── charge_balance_once() ← ТРАНЗАКЦИЯ + DEDUP
    └── consume_free_generation_once() ← ТРАНЗАКЦИЯ + DEDUP
```

### Idempotency (защита от дублирования)

```python
# Для платных генераций
if task_id in balance_deductions:
    return {"status": "duplicate"}

# Для бесплатных генераций
if task_id in free_deductions:
    return {"status": "duplicate"}
```

---

## 💰 Balance Operations

### Операции с балансом

| Метод | Транзакция | FOR UPDATE | Idempotency |
|-------|-----------|------------|-------------|
| `get_user_balance` | ❌ | ❌ | N/A |
| `set_user_balance` | ❌ | ❌ | N/A |
| `add_user_balance` | ✅ | ✅ | ❌ |
| `subtract_user_balance` | ✅ | ✅ | ❌ |
| `charge_balance_once` | ✅ | ✅ | ✅ (task_id) |

### Логирование

Все операции логируются:
```
BALANCE_ADD user_id=123 amount=100.00 balance_before=50.00 balance_after=150.00
BALANCE_SUBTRACT user_id=123 amount=10.00 balance_before=150.00 balance_after=140.00
BALANCE_CHARGE_OK user_id=123 task_id=abc123 amount=5.00 balance_after=135.00
BALANCE_CHARGE_DUPLICATE user_id=123 task_id=abc123  # Защита от повторного списания
```

---

## 💳 Payment Flow

### Telegram Stars

```
1. User clicks "⭐ Pay with Stars"
   └── pay_stars:{amount} callback

2. Bot creates invoice
   └── context.bot.send_invoice(currency="XTR", ...)

3. Telegram sends PreCheckoutQuery
   └── handle_pre_checkout_query()
       ├── Validate payload
       └── query.answer(ok=True)

4. User confirms payment in Telegram

5. Telegram sends SuccessfulPayment
   └── handle_successful_payment()
       ├── Extract amount from payload
       ├── add_user_balance(user_id, amount)
       └── Send confirmation message
```

### СБП (Manual Payment)

```
1. User clicks "💳 СБП"
   └── pay_sbp:{amount} callback

2. Bot shows payment instructions
   └── get_payment_details() → ENV variables

3. User sends screenshot

4. Admin confirms manually
   └── /admin → Confirm payment
   └── add_user_balance(user_id, amount)
```

---

## 🌍 Language System

### Кэширование

```python
_user_language_cache = {}       # {user_id: "ru"|"en"}
_user_language_cache_time = {}  # {user_id: timestamp}
CACHE_TTL_LANGUAGE = 300        # 5 минут
```

### Приоритет

1. **Explicit** - `set_user_language()` (кнопка смены языка)
2. **Menu Cache** - `_get_menu_dep_cache()`
3. **Telegram Client** - `update.effective_user.language_code`
4. **Default** - `'ru'`

### Storage

```python
# Сохранение
set_user_language(user_id, "en")
├── _user_language_cache[user_id] = "en"  # Сразу
└── storage.update_json_file("user_languages.json")  # В фоне

# Загрузка при boot
for user_key, lang in languages.items():
    _user_language_cache[user_key] = lang
```

---

## 🎨 Generation Flow

### Состояния

```
SELECTING_GEN_TYPE → SELECTING_MODEL → INPUTTING_PARAMS → CONFIRMING → WAITING_RESULT
```

### Проверка баланса

```python
# В confirm_generate()
balance = await get_user_balance_async(user_id)
if balance < price:
    # Показать "Недостаточно средств" + кнопка пополнения
    return

# Списание с защитой от дублирования
result = await storage.charge_balance_once(
    user_id=user_id,
    amount=price,
    task_id=task_id,  # Уникальный ID для idempotency
)
if result["status"] == "duplicate":
    # Уже списано - продолжаем без повторного списания
```

### Бесплатные генерации

```python
# Лимит: 5 в день (FREE_DAILY_GENERATIONS_LIMIT)
result = await storage.consume_free_generation_once(
    user_id=user_id,
    task_id=task_id,
)
# Возвращает: {status, used_today, remaining, limit_per_day}
```

---

## 🤝 Partner Isolation

### ENV Variables для партнёра

**Обязательные:**
```
TELEGRAM_BOT_TOKEN=123456:ABCDEF...
BOT_INSTANCE_ID=partner-ivan
ADMIN_ID=123456789
WEBHOOK_BASE_URL=https://my-bot.onrender.com
```

**Опциональные (для своих реквизитов):**
```
KIE_API_KEY=...
PAYMENT_PHONE=+79001234567
PAYMENT_BANK=Сбербанк
PAYMENT_CARD_HOLDER=Иван Иванов
SUPPORT_TELEGRAM=@ivan_support
SUPPORT_TEXT=Поддержка работает 10:00-22:00
```

### Изоляция данных

```sql
-- Все данные партнёра хранятся с его partner_id
SELECT * FROM storage_json WHERE partner_id = 'partner-ivan';

-- Партнёр А не видит данные партнёра Б
-- Это гарантируется на уровне PostgresStorage
```

---

## 🧪 Критичные тесты

### Файлы тестов

- `tests/test_partner_quickstart_integration.py` - изоляция партнёров
- `tests/test_partner_onboarding.py` - валидация ENV
- `tests/test_mvp_invariants.py` - инварианты MVP (создать!)

### Что тестируется

1. ✅ Tenant isolation (`tenant-a` ≠ `tenant-b`)
2. ✅ Balance persistence after restart
3. ✅ Free generations daily reset
4. ✅ Deduplication (charge_balance_once, consume_free_generation_once)
5. ✅ Required ENV validation

---

## 📝 Чеклист перед изменениями

- [ ] Изменение затрагивает balance операции? → Проверь транзакции!
- [ ] Изменение затрагивает partner_id? → Проверь изоляцию!
- [ ] Изменение затрагивает payment handlers? → Проверь порядок регистрации!
- [ ] Изменение затрагивает язык? → Проверь приоритет!
- [ ] Добавляешь новый handler? → Добавь в fallbacks ConversationHandler!

---

## 🔒 Версия MVP

**Дата фиксации:** 2026-01-29
**Commit:** (будет добавлен после коммита)

**Критичные файлы:**
- `bot_kie.py` - основная логика бота
- `app/storage/postgres_storage.py` - storage layer
- `app/storage/factory.py` - factory для storage
- `app/config_env.py` - валидация ENV
- `migrations/001_initial_schema.sql` - схема БД
