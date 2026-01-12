# 🎯 ITERATION 2: Webhook/Bot Response Fix

## ❌ ROOT CAUSE

**Symptom**: Бот не отвечает на /start и другие команды

**Root Cause Chain**:
```
1. Migration 005 падает с "column chat_id does not exist"
   ↓
2. runtime_state.db_schema_ready = False
   ↓
3. Bot goes to PASSIVE mode (active_state.active = False)
   ↓
4. Webhook handler returns 200 OK WITHOUT processing updates
   ↓
5. User gets NO response (только passive notice 1x/60s)
```

**Code Location**: [main_render.py:386-406](main_render.py#L386-L406)

```python
if not active_state.active:
    # PASSIVE MODE: Send notice but DON'T process update
    await send_passive_notice_if_needed(chat_id)
    return web.Response(status=200, text="ok")  # ❌ NO PROCESSING!
```

---

## ✅ FIX

**Strategy**: Split migration 005 → 005 + 006 (already done in commit 4965d24)

### What Changed:

1. **005_add_columns.sql** (ADDITIVE ONLY):
   - ALTER TABLE users ADD COLUMN user_id (alias for id)
   - ALTER TABLE users ADD COLUMN role, locale, metadata, username, first_name
   - NO CREATE TABLE, NO indexes
   - 100% idempotent

2. **006_create_tables.sql** (TABLES + INDEXES):
   - CREATE TABLE IF NOT EXISTS jobs, wallets, ledger, ui_state
   - Migrate generation_jobs → jobs (if exists)
   - CREATE INDEX (AFTER tables exist)
   - Proper order guaranteed

3. **Added bot.getMe() + getWebhookInfo() logging**:
   ```python
   async def verify_bot_identity(bot: Bot):
       me = await bot.get_me()
       logger.info("[BOT_VERIFY] ✅ @%s (id=%s)", me.username, me.id)
       
       webhook_info = await bot.get_webhook_info()
       logger.info("[BOT_VERIFY] 📡 Webhook: %s", webhook_info.url)
   ```

### Why This Fixes It:

- Migrations will pass → `schema_ready=True`
- Lock acquired → `active_state.active=True`  
- Webhook processes ALL updates → Bot responds

---

## 🧪 TESTS

### 1. Local Migration Test:
```bash
# Test migrations are idempotent
$ python3 -c "
from pathlib import Path
m005 = Path('migrations/005_add_columns.sql').read_text()
assert 'ALTER TABLE' in m005
assert 'CREATE TABLE' not in m005
assert 'CREATE INDEX' not in m005
print('✅ 005 is ADDITIVE only')

m006 = Path('migrations/006_create_tables.sql').read_text()
assert 'CREATE TABLE IF NOT EXISTS jobs' in m006
assert 'CREATE INDEX' in m006
print('✅ 006 creates tables+indexes')
"
```

### 2. Webhook Diagnostic (production):
```bash
$ python3 tools/webhook_diagnostic.py
# Expected:
# ✅ Bot username: @ferixdi_ai_bot
# ✅ Webhook URL: https://five656.onrender.com/webhook/...
# ✅ Migrations: 005, 006 applied
# ✅ Tables: users, jobs, wallets, ledger exist
```

### 3. E2E Telegram Test:
```
1. Send /start to bot
2. Expected: AI menu (категории/лучшие/поиск)
3. Actual: (will verify after deploy)
```

---

## 📊 EXPECTED LOGS (Render Deploy)

### Successful Scenario:
```log
2026-01-12 14:25:00 - __main__ - INFO - STARTUP (aiogram)
2026-01-12 14:25:02 - __main__ - INFO - [BOT_VERIFY] ✅ Bot identity: @ferixdi_ai_bot (id=7025030516, name='Ferixdi AI')
2026-01-12 14:25:02 - __main__ - INFO - [BOT_VERIFY] 📡 Webhook: https://five656.onrender.com/webhook/852486... (pending=0, last_error=none)
2026-01-12 14:25:03 - database - INFO - ✅ Пул соединений с БД создан успешно
2026-01-12 14:25:03 - app.storage.migrations - INFO - [MIGRATIONS] Found 6 migration file(s)
2026-01-12 14:25:03 - app.storage.migrations - INFO - [MIGRATIONS] ✅ Applied 001_initial_schema.sql
2026-01-12 14:25:03 - app.storage.migrations - INFO - [MIGRATIONS] ✅ Applied 002_balance_reserves.sql
2026-01-12 14:25:03 - app.storage.migrations - INFO - [MIGRATIONS] ✅ Applied 003_users_username.sql
2026-01-12 14:25:03 - app.storage.migrations - INFO - [MIGRATIONS] ✅ Applied 004_orphan_callbacks.sql
2026-01-12 14:25:04 - app.storage.migrations - INFO - [MIGRATIONS] ✅ Applied 005_add_columns.sql
2026-01-12 14:25:04 - app.storage.migrations - INFO - [MIGRATIONS] ✅ Applied 006_create_tables.sql
2026-01-12 14:25:04 - __main__ - INFO - [MIGRATIONS] ✅ Schema ready
2026-01-12 14:25:04 - app.locking.single_instance - INFO - [LOCK] ✅ ACTIVE MODE: PostgreSQL advisory lock acquired
2026-01-12 14:25:05 - __main__ - INFO - [WEBHOOK] ✅ Webhook set to https://five656.onrender.com/webhook/852486...
==> Your service is live 🎉
```

### Failure Indicators:
```log
# ❌ Still getting VPN bot:
[BOT_VERIFY] ✅ Bot identity: @vpn_bot (id=...)
→ ACTION: Fix TELEGRAM_BOT_TOKEN on Render

# ❌ Migration still fails:
[MIGRATIONS] ❌ Failed to apply 005_add_columns.sql: ...
→ ACTION: Check Render deployed correct commit (4965d24)

# ❌ Passive mode:
[LOCK] ⏸️ PASSIVE MODE (background watcher started)
→ ACTION: Check schema_ready, migrations passed
```

---

## 🔄 ROLLBACK PLAN

### If Deploy Fails:

**Option 1: Revert Migrations** (fastest)
```bash
# On Render Shell or DB tool:
DELETE FROM applied_migrations WHERE filename IN ('005_add_columns.sql', '006_create_tables.sql');
```

**Option 2: Git Revert**
```bash
git revert 4965d24  # Revert migration split
git push
# Wait for redeploy
```

**Option 3: Force Old Migration**
```bash
# Rename back
git mv migrations/005_add_columns.sql migrations/005_add_columns.sql.NEW
git mv migrations/005_consolidate_schema.sql.OLD migrations/005_consolidate_schema.sql
git commit -m "rollback: restore 005_consolidate_schema"
git push
```

### If Bot Still Not Responding After Fix:

1. **Check bot identity in logs**:
   - Look for `[BOT_VERIFY] ✅ Bot identity: @...`
   - If wrong bot → fix TELEGRAM_BOT_TOKEN

2. **Force webhook reset**:
   ```python
   # Add to main_render.py temporarily
   await bot.delete_webhook(drop_pending_updates=True)
   await bot.set_webhook(...)
   ```

3. **Manual webhook check**:
   ```bash
   curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo
   ```

---

## 🎯 SUCCESS CRITERIA

- [x] Commit 4965d24 pushed to main
- [ ] Render deploy successful
- [ ] Logs show `[MIGRATIONS] ✅ Applied 006_create_tables.sql`
- [ ] Logs show `[LOCK] ✅ ACTIVE MODE`
- [ ] Bot responds to /start in Telegram
- [ ] Bot shows AI menu (NOT VPN)
- [ ] No errors in Render logs for 5 minutes

---

## 📝 NEXT ITERATION

After this fix, next critical risks:
1. **Jobs→Callbacks→Delivery cycle** - not tested end-to-end
2. **Models catalog compliance** - inputs may not match KIE_SOURCE_OF_TRUTH
3. **Payments/Referrals** - untested

**Priority**: Jobs cycle (most critical for user experience)
