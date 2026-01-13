# 🚨 ITERATION 2.5: CRITICAL HOTFIX - Migration 006 chat_id

## 1️⃣ ROOT CAUSE

**Problem**: Migration 006 failed with `column "chat_id" does not exist`

**Root Cause Chain**:
```sql
DO $$
BEGIN
    IF NOT EXISTS (jobs table) THEN
        CREATE TABLE jobs (..., chat_id BIGINT, ...);  -- chat_id ONLY here
    END IF;
END $$;

-- ❌ Index created OUTSIDE DO block - assumes chat_id exists
CREATE INDEX idx_jobs_chat_id ON jobs(chat_id);  -- FAILS if table already exists without chat_id
```

**Why This Happened**:
- Database had `jobs` table from OLD migrations (before schema consolidation)
- Old jobs table **did NOT have** chat_id column
- Migration 006 saw "jobs exists" → skipped CREATE TABLE
- Then tried to create index on non-existent chat_id → **CRASH**

**Evidence from logs**:
```
[MIGRATIONS] ✅ Applied 005_add_columns.sql
[MIGRATIONS] ❌ Failed to apply 006_create_tables.sql: column "chat_id" does not exist
[MIGRATIONS] ❌ Schema NOT ready
[LOCK] ✅ ACTIVE MODE  ← Got lock, but schema broken!
```

---

## 2️⃣ FIX

**Strategy**: Add missing columns to existing jobs table BEFORE creating indexes

### Code Changes:

```sql
DO $$
BEGIN
    -- ... (existing jobs table creation logic)
    
    -- NEW: Ensure all V2 columns exist (for old jobs tables)
    IF EXISTS (jobs table) THEN
        IF NOT EXISTS (chat_id column) THEN
            ALTER TABLE jobs ADD COLUMN chat_id BIGINT;
        END IF;
        
        IF NOT EXISTS (delivered_at column) THEN
            ALTER TABLE jobs ADD COLUMN delivered_at TIMESTAMP;
        END IF;
        
        -- ... (other missing columns)
    END IF;
END $$;

-- NOW indexes are safe to create
CREATE INDEX idx_jobs_chat_id ON jobs(chat_id);
```

### Columns Added (if missing):
1. `chat_id BIGINT` - for Telegram chat ID tracking
2. `delivered_at TIMESTAMP` - when result was sent to user
3. `kie_status TEXT` - KIE API status
4. `finished_at TIMESTAMP` - job completion time

---

## 3️⃣ TESTS

### Manual Migration Test:
```sql
-- Simulate existing jobs table without chat_id
CREATE TABLE jobs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    model_id TEXT NOT NULL
);

-- Run migration 006
-- Expected: ALTER TABLE ADD COLUMN chat_id
-- Expected: CREATE INDEX idx_jobs_chat_id succeeds
```

### Automated Test (post-deploy):
```bash
$ python3 tools/webhook_diagnostic.py
# Should show:
# ✅ Migrations: 006_create_tables.sql applied
# ✅ Tables: jobs has chat_id column
```

### Production Verification:
```sql
-- After deploy, check schema:
SELECT column_name FROM information_schema.columns 
WHERE table_name='jobs' 
ORDER BY column_name;

-- Should include: chat_id, delivered_at, kie_status, finished_at
```

---

## 4️⃣ EXPECTED LOGS

### ✅ SUCCESS Scenario (next deploy):

```log
2026-01-12 14:30:00 - __main__ - INFO - STARTUP (aiogram)
2026-01-12 14:30:01 - __main__ - INFO - [BOT_VERIFY] ✅ Bot identity: @Ferixdi_bot_ai_bot (id=8524869517)
2026-01-12 14:30:02 - database - INFO - ✅ Пул соединений с БД создан успешно
2026-01-12 14:30:02 - app.storage.migrations - INFO - [MIGRATIONS] Found 6 migration file(s)
2026-01-12 14:30:03 - app.storage.migrations - INFO - [MIGRATIONS] ✅ Applied 001_initial_schema.sql
2026-01-12 14:30:03 - app.storage.migrations - INFO - [MIGRATIONS] ✅ Applied 002_balance_reserves.sql
2026-01-12 14:30:03 - app.storage.migrations - INFO - [MIGRATIONS] ✅ Applied 003_users_username.sql
2026-01-12 14:30:03 - app.storage.migrations - INFO - [MIGRATIONS] ✅ Applied 004_orphan_callbacks.sql
2026-01-12 14:30:04 - app.storage.migrations - INFO - [MIGRATIONS] ✅ Applied 005_add_columns.sql
2026-01-12 14:30:04 - app.storage.migrations - NOTICE - Added chat_id column to existing jobs table
2026-01-12 14:30:04 - app.storage.migrations - NOTICE - Added delivered_at column to existing jobs table
2026-01-12 14:30:04 - app.storage.migrations - INFO - [MIGRATIONS] ✅ Applied 006_create_tables.sql  ← SUCCESS!
2026-01-12 14:30:05 - __main__ - INFO - [MIGRATIONS] ✅ Schema ready  ← CRITICAL!
2026-01-12 14:30:05 - app.locking.single_instance - INFO - [LOCK] ✅ ACTIVE MODE
2026-01-12 14:30:06 - __main__ - INFO - [WEBHOOK] ✅ Webhook set to https://five656.onrender.com/webhook/...
==> Your service is live 🎉
```

**Key Indicators**:
- ✅ `[MIGRATIONS] ✅ Schema ready` - migrations complete
- ✅ `[LOCK] ✅ ACTIVE MODE` - bot processing updates
- ✅ No `column "chat_id" does not exist` error

### ❌ FAILURE Scenarios:

**If still fails on chat_id**:
```log
[MIGRATIONS] ❌ Failed to apply 006_create_tables.sql: column "chat_id" does not exist
```
→ **ACTION**: Check Render deployed commit 04852ce (not cached older version)

**If different error**:
```log
[MIGRATIONS] ❌ Failed to apply 006_create_tables.sql: <other error>
```
→ **ACTION**: Check specific error, may need different fix

---

## 5️⃣ ROLLBACK PLAN

### Option 1: Remove 006 from applied_migrations (fastest)
```sql
-- On Render PostgreSQL or via psql:
DELETE FROM applied_migrations WHERE filename = '006_create_tables.sql';

-- Restart service (Render will re-run 006)
```

### Option 2: Manual column addition
```sql
-- If migration still fails, add columns manually:
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS chat_id BIGINT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMP;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS kie_status TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS finished_at TIMESTAMP;

-- Mark migration as applied:
INSERT INTO applied_migrations (filename, applied_at) 
VALUES ('006_create_tables.sql', NOW());
```

### Option 3: Git revert (nuclear)
```bash
git revert 04852ce
git push
# Render redeploys without migration 006
```

### If Bot Still Not Responding After Migration Fix:

1. **Verify schema_ready**:
   ```
   Look for: [MIGRATIONS] ✅ Schema ready
   If missing → migrations still failing
   ```

2. **Check ACTIVE mode**:
   ```
   Look for: [LOCK] ✅ ACTIVE MODE
   If PASSIVE → bot won't process updates
   ```

3. **Manual webhook test**:
   ```bash
   curl -X POST https://five656.onrender.com/webhook/852486... \
     -H "Content-Type: application/json" \
     -d '{"update_id":1,"message":{"chat":{"id":123}}}'
   
   # Should return: {"ok": true} or similar
   ```

---

## ✅ SUCCESS CRITERIA

- [x] Commit 04852ce pushed
- [ ] Render deploy completed
- [ ] Logs show `[MIGRATIONS] ✅ Applied 006_create_tables.sql`
- [ ] Logs show `[MIGRATIONS] ✅ Schema ready`
- [ ] Logs show `[LOCK] ✅ ACTIVE MODE`
- [ ] Bot responds to /start in Telegram
- [ ] Bot shows AI menu (categories/models)
- [ ] No errors in logs for 10 minutes

---

## 🎯 NEXT STEPS

After successful deploy:

1. **Immediate**: Test /start in Telegram
2. **Within 5 min**: Monitor Render logs for errors
3. **Within 10 min**: Test FREE model generation (wan/2-5-standard)
4. **ITERATION 3**: Jobs→Callbacks→Delivery cycle testing

**Estimated time to resolution**: 2-3 minutes (Render redeploy)
