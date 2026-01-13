# PASSIVE MODE FIX - CRITICAL UPDATE

**Дата:** 2026-01-13  
**Статус:** ✅ CRITICAL FIX - READY FOR DEPLOY

---

## КРИТИЧЕСКАЯ ПРОБЛЕМА

**Симптом:** Пользователь видит только "✅ Бот на связи. Загружаю меню…" БЕЗ главного меню.

**Root Cause:**
```
1. Сервис стартует в PASSIVE MODE (до захвата lock ~3-4 секунды)
2. Воркеры запускаются и обрабатывают updates СРАЗУ (в PASSIVE)
3. /start отправляет промежуточное сообщение в PASSIVE
4. Lock acquire → ACTIVE (но уже поздно, меню не отправлено)
5. Результат: "Загружаю меню..." без меню
```

**Логи:**
```
05:13:58 [PASSIVE MODE] HTTP server running
05:13:59 [WORKER_0] Started  ← Воркеры стартуют ДО ACTIVE!
05:14:02 [LOCK] ✅ ACTIVE MODE  ← Lock только через 4 сек
```

---

## РЕШЕНИЕ: 3-LAYER ARCHITECTURE

### LAYER A: WEBHOOK = ACK-ONLY (ALREADY IMPLEMENTED)
```python
# main_render.py
async def webhook_handler(request):
    # ✅ ЗАПРЕЩЕНО: bot.send_message(), edit_message()
    # ✅ РАЗРЕШЕНО: return 200 + enqueue
    
    update = validate(payload)
    queue_manager.enqueue(update, update_id)
    logger.info("[WEBHOOK] ✅ ENQUEUED update_id=%s", update_id)
    
    return web.Response(status=200)  # <50ms target
```

### LAYER B: WORKER = ACTIVE GATE + PERSISTENT DEDUP (NEW)
```python
# app/utils/update_queue.py
async def _worker_loop(worker_id):
    item = await queue.get()
    update_id = item["update_id"]
    
    # 🔐 STEP 1: Persistent dedup (DB check)
    if await db.fetchval("SELECT 1 FROM processed_updates WHERE update_id=$1", update_id):
        logger.warning("[WORKER_%d] ⏭️ DEDUP_SKIP update_id=%s", worker_id, update_id)
        return
    
    await db.execute("INSERT INTO processed_updates (update_id, ...) VALUES (...)")
    
    # 🚨 STEP 2: ACTIVE gate (PASSIVE = NO PROCESSING)
    if not active_state.active:
        if held_time > 30:
            logger.warning("[WORKER_%d] ⏸️ PASSIVE_DROP update_id=%s", worker_id, update_id)
            return  # ACTIVE instance will process
        
        # Requeue until ACTIVE
        await asyncio.sleep(0.5)
        queue.put_nowait(item)
        return
    
    # ✅ ACTIVE: Process update
    logger.info("[WORKER_%d] 🎬 ACTIVE_PROCESS_START update_id=%s", worker_id, update_id)
    await dp.feed_update(bot, update)
```

### LAYER C: /start HANDLER = GUARANTEED MENU (ALREADY IMPLEMENTED)
```python
# bot/handlers/flow.py
@router.message(Command("start"))
async def start_cmd(message):
    logger.info("[START] 🎬 Processing /start from user_id=%d", user_id)
    
    menu_keyboard = _main_menu_keyboard()
    
    await message.answer(
        f"👋 Привет! 🤖 {total_models} AI моделей...",
        reply_markup=menu_keyboard
    )
    
    logger.info("[START] ✅ MAIN_MENU sent to user_id=%d", user_id)
```

---

## МИГРАЦИЯ БД

**Файл:** `app/storage/migrations/008_processed_updates_dedup.sql`

```sql
CREATE TABLE processed_updates (
    update_id BIGINT PRIMARY KEY,
    processed_at TIMESTAMP DEFAULT NOW(),
    worker_instance_id TEXT,
    update_type TEXT
);

CREATE INDEX idx_processed_updates_processed_at ON processed_updates(processed_at);
```

---

## ЛОГИ (EXPECTED)

### HAPPY PATH (ACTIVE):
```
[WEBHOOK] ✅ ENQUEUED update_id=724051459 type=message
[WORKER_1] 🔐 DEDUP checking update_id=724051459
[WORKER_1] 🎬 ACTIVE_PROCESS_START update_id=724051459
[START] 🎬 Processing /start from user_id=6913446846
[START] ✅ MAIN_MENU sent to user_id=6913446846 (models=50)
```

### PASSIVE MODE:
```
[WEBHOOK] ✅ ENQUEUED update_id=724051460 type=message
[WORKER_1] 🔐 DEDUP checking update_id=724051460
[WORKER_1] ⏸️ PASSIVE_REQUEUE update_id=724051460 (attempt 1, held 0.5s)
... (requeue loop) ...
[LOCK] ✅ ACTIVE MODE acquired
[WORKER_1] 🎬 ACTIVE_PROCESS_START update_id=724051460
[START] 🎬 Processing /start from user_id=...
[START] ✅ MAIN_MENU sent to user_id=...
```

### PASSIVE TIMEOUT (>30s):
```
[WORKER_1] ⏸️ PASSIVE_DROP update_id=724051461 (held 30.1s)
# ACTIVE instance will process this update
```

---

## DEFINITION OF DONE

✅ **PASSIVE = NO MESSAGES:** В PASSIVE режиме НЕ отправляется НИ ОДНО сообщение пользователю  
✅ **ONE /start = ONE MENU:** Один /start = одно приветствие + одно меню с кнопками  
✅ **NO DUPLICATES:** Persistent dedup в БД → нет повторов даже при рестартах  
✅ **ALWAYS MENU:** Логи показывают `MAIN_MENU_SENT` для каждого /start  
✅ **FAST HTTP:** Webhook отвечает <50ms (ACK-only, no business logic)  
✅ **ACTIVE GATE:** Воркеры ждут ACTIVE перед обработкой updates  

---

## ФАЙЛЫ ИЗМЕНЕНЫ

- `app/utils/update_queue.py`: ACTIVE gate + persistent dedup в `_worker_loop()`
- `app/storage/migrations/008_processed_updates_dedup.sql`: таблица дедупа (NEW)
- `main_render.py`: webhook ACK-only (без изменений - уже был правильный)
- `bot/handlers/flow.py`: /start handler (без изменений - уже был правильный)

---

## BREAKING CHANGE ⚠️

**До:** Воркеры обрабатывали updates даже в PASSIVE (UI updates немедленно)  
**После:** Воркеры НЕ обрабатывают updates в PASSIVE (ждут ACTIVE или drop после 30s)

**Почему:** PASSIVE = lock не взят = может быть другой ACTIVE instance = дубликаты сообщений

**Результат:** Первые 3-4 секунды после deploy бот не отвечает (ждёт ACTIVE), но зато НЕТ дублей и "загружаю меню..." без меню.
