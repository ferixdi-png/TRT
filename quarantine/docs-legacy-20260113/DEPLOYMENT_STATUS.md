# 🚀 Deployment Status - Iteration 1

## Current Deploy (2026-01-12 13:24)

### ❌ Migration Error (FIXED)
```
ERROR: column "role" does not exist
Migration 005 failed on existing database
```

**Cause**: Migration 005 tried to `CREATE TABLE users` with new columns, but table already exists from migration 001.

**Fix Applied** (commit 32c3621):
- ✅ Use `ALTER TABLE ADD COLUMN IF NOT EXISTS` for new columns
- ✅ Idempotent migration (safe to run multiple times)
- ✅ Atomic `generation_jobs → jobs` migration

---

## Next Deploy (After Fix)

### Expected Logs:
```
[MIGRATIONS] ✅ Applied 001_initial_schema.sql
[MIGRATIONS] ✅ Applied 002_balance_reserves.sql
[MIGRATIONS] ✅ Applied 003_users_username.sql
[MIGRATIONS] ✅ Applied 004_orphan_callbacks.sql
[MIGRATIONS] ✅ Applied 005_consolidate_schema.sql
[MIGRATIONS] ✅ Schema ready
```

### What Will Happen:
1. ✅ Add missing columns to `users` table (role, locale, metadata)
2. ✅ Create `jobs` table (if not exists)
3. ✅ Migrate `generation_jobs → jobs` (if generation_jobs exists)
4. ✅ Create UNIQUE index on `idempotency_key`
5. ✅ All other tables (wallets, ledger, ui_state, etc.)

---

## Post-Deploy Verification

### 1. Check Migration Success
```bash
# In Render logs, look for:
[MIGRATIONS] ✅ Applied 005_consolidate_schema.sql
[MIGRATIONS] ✅ Schema ready
```

### 2. Test Database Schema
```sql
-- Verify jobs table exists
SELECT COUNT(*) FROM jobs;

-- Verify idempotency constraint
SELECT COUNT(*) FROM pg_indexes WHERE indexname = 'idx_jobs_idempotency';

-- Verify users columns
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'users' 
ORDER BY column_name;
-- Should include: role, locale, metadata
```

### 3. Test Bot Functionality
1. Send `/start` to bot
2. Try FREE model generation
3. Verify callback arrives
4. Check balance unchanged
5. Confirm result delivered to Telegram

---

## Rollback Plan (if needed)

If migration 005 still fails:

### Option 1: Manual Fix (via Render Shell)
```sql
-- Add missing columns manually
ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'user';
ALTER TABLE users ADD COLUMN IF NOT EXISTS locale TEXT DEFAULT 'ru';
ALTER TABLE users ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

-- Create jobs table manually
CREATE TABLE IF NOT EXISTS jobs (...);
```

### Option 2: Revert Migration
```bash
# Remove 005 from applied_migrations table
DELETE FROM applied_migrations WHERE filename = '005_consolidate_schema.sql';

# Redeploy with migration fix
```

---

## Success Criteria

- ✅ All 5 migrations applied successfully
- ✅ `jobs` table exists with all columns
- ✅ UNIQUE constraint on `idempotency_key`
- ✅ Bot responds to `/start`
- ✅ FREE generation works end-to-end
- ✅ No errors in logs

---

## Monitoring Checklist

After successful deploy:

- [ ] Check Render logs for migration success
- [ ] Verify bot responds (send /start)
- [ ] Test FREE model (wan/2-5-standard)
- [ ] Check callback arrives (watch logs)
- [ ] Verify result delivered to Telegram
- [ ] Check balance operations work
- [ ] Monitor for any errors in next 1 hour

**Status**: Waiting for redeploy with fixed migration...
