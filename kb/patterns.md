# Code Patterns & Best Practices

Обязательные паттерны для всего кода в `main_render.py` и `app/`.

## Error Handling

### Always wrap external calls
```python
try:
    result = await external_api_call()
except Exception as exc:
    logger.error(f"[TAG] Operation failed: {exc}", exc_info=True)
    # Recovery logic here (fallback, retry, or user notification)
    return default_value
```

### Never let exceptions crash the process
- Обработать или залогировать
- В handlers: всегда отправить user-friendly сообщение
- В background tasks: логировать и продолжать

### Rate-limit duplicate errors
```python
# Плохо: спамит логи одинаковыми ошибками
for item in items:
    try:
        process(item)
    except ValueError as e:
        logger.error(f"Failed: {e}")  # 1000x одна ошибка

# Хорошо: агрегация
error_counts = {}
for item in items:
    try:
        process(item)
    except ValueError as e:
        key = type(e).__name__
        error_counts[key] = error_counts.get(key, 0) + 1

for error_type, count in error_counts.items():
    logger.error(f"{error_type}: {count} occurrences")
```

## Async Patterns

### Never block the event loop
```python
# ❌ ПЛОХО
def blocking_operation():
    time.sleep(5)  # Блокирует весь event loop!

# ✅ ХОРОШО
async def non_blocking_operation():
    await asyncio.sleep(5)
```

### Use async context managers for resources
```python
# ❌ ПЛОХО
conn = await pool.acquire()
try:
    result = await conn.execute(query)
finally:
    await pool.release(conn)

# ✅ ХОРОШО
async with pool.acquire() as conn:
    result = await conn.execute(query)
```

### Timeout all external calls
```python
try:
    response = await asyncio.wait_for(
        client.post(url, json=payload),
        timeout=30.0
    )
except asyncio.TimeoutError:
    logger.error("[API] Request timed out after 30s")
    raise
```

## Retry Logic

### Exponential backoff with jitter
```python
async def retry_with_backoff(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await func()
        except RetryableError as e:
            if attempt == max_retries - 1:
                raise
            
            # Exponential backoff: 0.5s, 1s, 2s
            base_delay = 0.5 * (2 ** attempt)
            # Add jitter to prevent thundering herd
            jitter = random.uniform(0, 0.1 * base_delay)
            delay = base_delay + jitter
            
            logger.warning(f"Retry {attempt+1}/{max_retries} after {delay:.2f}s")
            await asyncio.sleep(delay)
```

### Never tight-loop retry
```python
# ❌ ПЛОХО: DDOS по своей БД
while True:
    try:
        conn = get_connection()
        break
    except ConnectionError:
        pass  # Retry immediately → миллионы попыток в секунду

# ✅ ХОРОШО
for _ in range(5):
    try:
        conn = get_connection()
        break
    except ConnectionError:
        await asyncio.sleep(1.0)  # Backoff
else:
    raise RuntimeError("Could not connect after 5 retries")
```

## Idempotency

### Deduplicate by unique ID
```python
# Для Telegram updates: update_id
processed_updates = set()

async def handle_update(update):
    if update.update_id in processed_updates:
        logger.debug(f"Skipping duplicate update_id={update.update_id}")
        return
    
    processed_updates.add(update.update_id)
    await process(update)
    
    # Cleanup old IDs (избежать memory leak)
    if len(processed_updates) > 10000:
        processed_updates.clear()
```

### Database operations: upsert pattern
```python
# ❌ ПЛОХО: race condition
user = db.get_user(user_id)
if user:
    db.update_balance(user_id, new_balance)
else:
    db.create_user(user_id, new_balance)

# ✅ ХОРОШО: atomic upsert
db.execute("""
    INSERT INTO users (user_id, balance)
    VALUES (%s, %s)
    ON CONFLICT (user_id) DO UPDATE
    SET balance = EXCLUDED.balance
""", (user_id, new_balance))
```

## Logging

### Structured logs with tags
```python
logger.info(f"[LOCK] Acquired lock for instance={instance_id}")
logger.warning(f"[QUEUE] Queue depth={depth} exceeds threshold")
logger.error(f"[DB] Connection failed: {error}", exc_info=True)
```

### Never log secrets
```python
# ❌ ПЛОХО
logger.info(f"Starting with token={bot_token}")

# ✅ ХОРОШО
masked_token = f"{bot_token[:8]}***"
logger.info(f"Starting with token={masked_token}")
```

### Rate-limit repetitive logs
```python
_last_log_time = {}

def rate_limited_log(key, message, interval=30):
    """Log once per interval seconds."""
    now = time.time()
    last = _last_log_time.get(key, 0)
    
    if now - last >= interval:
        logger.info(message)
        _last_log_time[key] = now
```

## Database Patterns

### Always use connection pool
```python
# ✅ Через DatabaseService
db = get_storage()  # Returns DatabaseService instance
with db.connection() as conn:
    result = conn.execute(query, params)
```

### Transactions for multi-step operations
```python
async def transfer_balance(from_user, to_user, amount):
    async with db.transaction() as txn:
        await txn.execute(
            "UPDATE users SET balance = balance - %s WHERE user_id = %s",
            (amount, from_user)
        )
        await txn.execute(
            "UPDATE users SET balance = balance + %s WHERE user_id = %s",
            (amount, to_user)
        )
        # Commit происходит автоматически, если нет exception
```

### Migrations: always idempotent
```python
# ✅ IF NOT EXISTS
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    balance NUMERIC(10, 2) DEFAULT 0
);

# ✅ IF NOT EXISTS для индексов
CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance);
```

### asyncpg: SQL parameters (CRITICAL)
```python
# ❌ ПЛОХО: параметр внутри INTERVAL строки
await conn.execute(
    "UPDATE jobs SET stale = TRUE WHERE updated_at < NOW() - INTERVAL '$1 minutes'",
    timeout_minutes
)
# ОШИБКА: the server expects 0 arguments for this query, 1 were passed

# ✅ ХОРОШО: параметр через конкатенацию + ::INTERVAL
await conn.execute(
    "UPDATE jobs SET stale = TRUE WHERE updated_at < NOW() - ($1 || ' minutes')::INTERVAL",
    timeout_minutes
)

# ✅ Альтернатива: make_interval()
await conn.execute(
    "UPDATE jobs SET stale = TRUE WHERE updated_at < NOW() - make_interval(mins => $1)",
    timeout_minutes
)
```

**Правило**: PostgreSQL не поддерживает параметры внутри строковых литералов INTERVAL.
Всегда используй конкатенацию `($N || ' unit')::INTERVAL` или функцию `make_interval()`.

### Database INSERT statements (CRITICAL)
```python
# ❌ ПЛОХО: missing PRIMARY KEY field
await conn.execute(
    "INSERT INTO users (user_id, username) VALUES ($1, $2)",
    user_id, username
)
# ОШИБКА: null value in column "id" violates not-null constraint

# ✅ ХОРОШО: all required fields including PK
await conn.execute(
    "INSERT INTO users (id, user_id, username) VALUES ($1, $1, $2)",
    user_id, username
)

# ✅ Альтернатива: check schema for SERIAL/DEFAULT
# If id is BIGSERIAL PRIMARY KEY, you don't need to specify it
```

**Правило**: Всегда проверяй CREATE TABLE для NOT NULL constraints без DEFAULT.
При INSERT указывай ВСЕ обязательные поля (PRIMARY KEY, NOT NULL без DEFAULT).

## Telegram HTML Safety

### Never use ₽ symbol in HTML messages
```python
# ❌ ПЛОХО: ₽ breaks HTML parser
await message.answer(
    "Цена: 10₽\nСкидка: (<5₽)",
    parse_mode="HTML"
)
# ОШИБКА: TelegramBadRequest: can't parse entities: Unsupported start tag "1₽)"

# ✅ ХОРОШО: use "руб." instead
await message.answer(
    "Цена: 10 руб.\nСкидка: (до 5 руб.)",
    parse_mode="HTML"
)
```

### Use HTML sanitizer for user content
```python
from bot.utils import sanitize_message_html, format_price_rub

# ❌ ПЛОХО: raw user input in HTML
prompt = user_input  # May contain < > & "
await message.answer(f"<b>Prompt:</b> {prompt}", parse_mode="HTML")

# ✅ ХОРОШО: sanitize first
safe_prompt = sanitize_message_html(user_input)
await message.answer(f"<b>Prompt:</b> {safe_prompt}", parse_mode="HTML")

# ✅ Use helper for prices
price_text = format_price_rub(10.50)  # "10.5 руб."
await message.answer(f"<b>Цена:</b> {price_text}", parse_mode="HTML")
```

**Правило**: В Telegram HTML:
- НИКОГДА не используй символ ₽ (ломает парсер)
- ВСЕГДА экранируй пользовательский ввод через `sanitize_message_html()`
- Используй `format_price_rub()` для цен
- Проверяй сообщения через `scripts/verify.py` (обнаруживает ₽)

---

## Model Parameter Validation

Правила валидации входных параметров для KIE AI моделей:

### Источники правды

1. **models/KIE_SOURCE_OF_TRUTH.json** - примеры из документации KIE
2. **Production error logs** - реальные ошибки валидации
3. **app/kie/field_options.py** - маппинг user-friendly → API enum values
4. **app/kie/model_defaults.py** - дефолтные значения required полей

### Частые ошибки валидации

#### 1. Missing required field

```python
# ERROR из логов:
# "Missing required field: guidance_scale"

# ПРИЧИНА: Пользователь не выбрал параметр через UI,
# но поле required в API схеме

# РЕШЕНИЕ: Добавить default в app/kie/model_defaults.py
MODEL_DEFAULTS = {
    "bytedance/seedream": {
        "guidance_scale": 2.5,  # From SOURCE_OF_TRUTH examples
    }
}
```

#### 2. Invalid enum value

```python
# ERROR из логов:
# "Invalid value for image_size: portrait_4_3.
#  Must be one of: square_hd, square, portrait, portrait_hd, landscape, landscape_hd"

# ПРИЧИНА: app/kie/field_options.py содержит старые enum значения
# (например, portrait_4_3 вместо portrait)

# РЕШЕНИЕ: Обновить маппинг согласно ошибке API
"bytedance/seedream.image_size": [
    "square_hd",
    "square",
    "portrait",      # НЕ portrait_4_3
    "portrait_hd",
    "landscape",
    "landscape_hd",
]
```

#### 3. aspect_ratio rejection

```python
# ERROR из логов:
# "aspect_ratio is not within the range of allowed options"

# ПРИЧИНА: Модель использует специфичный набор aspect_ratio значений
# (например, grok-imagine использует "3:2" вместо "4:3")

# РЕШЕНИЕ 1: Проверить SOURCE_OF_TRUTH для точных значений
jq '.models."grok-imagine/text-to-image".input_schema.input.examples[0]' \\
  models/KIE_SOURCE_OF_TRUTH.json

# РЕШЕНИЕ 2: Добавить model-specific маппинг
"grok-imagine/text-to-image.aspect_ratio": [
    "1:1",
    "3:2",   # Default from SOURCE_OF_TRUTH
    "2:3",
    "16:9",
    "9:16",
]
```

### Workflow при новой validation error

1. **Читай production logs** → находи точную ошибку
2. **Определи root cause**:
   - Missing field → добавь в MODEL_DEFAULTS
   - Invalid enum → обнови FIELD_OPTIONS
3. **Проверь SOURCE_OF_TRUTH** → найди правильные значения
4. **Обнови forbidden_log_patterns** в product/truth.yaml
5. **Commit + push** → деплой исправления

### Forbidden patterns (product/truth.yaml)

```yaml
forbidden_log_patterns:
  - pattern: "Input validation failed.*Missing required field"
    severity: P0
    description: "Model parameter validation error - check app/kie/model_defaults.py"
    
  - pattern: "Invalid value for .* Must be one of"
    severity: P0
    description: "Enum value mismatch - check app/kie/field_options.py mapping"
```

---

## Security

### Validate all user input
```python
def validate_prompt(text: str) -> str:
    if not text or len(text) > 1000:
        raise ValueError("Prompt must be 1-1000 characters")
    
    # Sanitize dangerous patterns
    forbidden = ["<script>", "DROP TABLE", "'; --"]
    for pattern in forbidden:
        if pattern.lower() in text.lower():
            raise ValueError("Invalid prompt content")
    
    return text.strip()
```

### Check admin privileges
```python
def is_admin(user_id: int) -> bool:
    admin_ids_str = os.getenv("ADMIN_IDS", "")
    if not admin_ids_str:
        return False
    
    admin_ids = [int(x.strip()) for x in admin_ids_str.split(",")]
    return user_id in admin_ids
```

### Rate limiting per user
```python
from collections import defaultdict
import time

_user_request_times = defaultdict(list)

def check_rate_limit(user_id: int, max_requests=10, window_seconds=60):
    """Allow max_requests per window_seconds."""
    now = time.time()
    times = _user_request_times[user_id]
    
    # Remove old timestamps outside window
    times[:] = [t for t in times if now - t < window_seconds]
    
    if len(times) >= max_requests:
        raise RateLimitError(f"Max {max_requests} requests per {window_seconds}s")
    
    times.append(now)
```

## Fast-Ack Pattern (Critical for Webhook)

### ALWAYS return 200 OK quickly
```python
async def webhook_handler(request):
    # 1. Parse update
    update = await request.json()
    
    # 2. Enqueue (non-blocking)
    queue_manager.enqueue(update)
    
    # 3. IMMEDIATELY return 200 OK
    return web.Response(status=200, text="ok")
    # Total time: < 500ms

# Processing happens in background workers
async def worker():
    while True:
        update = await queue.get()
        await process_update(update)  # Can take minutes
        queue.task_done()
```

## Type Safety

### Use type hints everywhere
```python
from typing import Optional, Dict, List

async def get_user_balance(user_id: int) -> float:
    """Returns user balance in RUB."""
    result = await db.query(...)
    return float(result["balance"])

def build_menu(buttons: List[str]) -> Dict[str, Any]:
    """Builds inline keyboard markup."""
    return {"inline_keyboard": [[{"text": b}] for b in buttons]}
```

### Validate types at runtime (for external data)
```python
def parse_callback_data(data: str) -> Dict[str, str]:
    """Parse callback_data from Telegram."""
    if not isinstance(data, str):
        raise TypeError(f"Expected str, got {type(data)}")
    
    parts = data.split(":")
    if len(parts) != 2:
        raise ValueError("Invalid callback_data format")
    
    return {"action": parts[0], "param": parts[1]}
```

## Performance

### Cache expensive operations
```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_model_metadata(model_id: str) -> Dict:
    """Cached model metadata (doesn't change often)."""
    return db.query("SELECT * FROM models WHERE id = %s", (model_id,))
```

### Batch database operations
```python
# ❌ ПЛОХО: N queries
for user_id in user_ids:
    db.execute("UPDATE users SET balance = balance + 10 WHERE user_id = %s", (user_id,))

# ✅ ХОРОШО: 1 query
db.execute("UPDATE users SET balance = balance + 10 WHERE user_id = ANY(%s)", (user_ids,))
```

## Testing Helpers

### Use pytest fixtures for database
```python
@pytest.fixture
def db():
    """Test database with rollback."""
    conn = get_test_connection()
    conn.execute("BEGIN")
    yield conn
    conn.execute("ROLLBACK")
    conn.close()
```

### Mock external APIs
```python
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_generation():
    mock_kie_api = AsyncMock(return_value={"url": "http://result.jpg"})
    result = await generate_image(prompt="test", api=mock_kie_api)
    
    assert result["url"] == "http://result.jpg"
    mock_kie_api.assert_called_once()
```
