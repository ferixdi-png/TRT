# Deployment Guide

**Last Updated**: 2026-01-13  
**Platform**: Render (Web Service)  
**Status**: Production-ready with known constraints

---

## 1. Environment Contract

### Required Variables (validated at startup)

See [startup_validation.py](../app/utils/startup_validation.py) for definitive list.

**Critical**:
```bash
DATABASE_URL=postgresql://...
TELEGRAM_BOT_TOKEN=123456:ABCDEF...
KIE_API_KEY=kie_...
ADMIN_ID=123456789
WEBHOOK_BASE_URL=https://your-app.onrender.com
BOT_MODE=webhook  # or 'polling' for development
```

**Optional but Recommended**:
```bash
LOCK_STALE_IDLE_SECONDS=120  # Lock takeover threshold (default: 120s)
DB_MAXCONN=10  # PostgreSQL pool size
LOG_LEVEL=INFO  # or DEBUG for troubleshooting
```

### ENV Validation

Application will **exit immediately** if required variables are missing.

Check logs for:
```
[STARTUP] ENV validation failed - exiting
```

---

## 2. Deployment Flow (Render)

### Normal Deployment

1. **Push to `main` branch** → triggers automatic deploy
2. **Build phase** (~2-3 min):
   - Installs dependencies from `requirements.txt`
   - No custom build steps
3. **Startup phase** (~30-60s):
   - ENV validation
   - Database migrations (idempotent)
   - Lock acquisition (singleton pattern)
   - Webhook setup (if BOT_MODE=webhook)
4. **Health check**: Render polls `/health` endpoint
5. **Ready**: Service marked as "live" when `/health` returns 200 OK

### Lock Behavior (Singleton Pattern)

**Problem**: Only ONE Telegram bot instance can run (409 Conflict otherwise)

**Solution**: PostgreSQL advisory lock

**How it works**:
1. Instance A starts, acquires lock
2. Instance B starts, sees lock held → enters PASSIVE mode
3. Instance B monitors Instance A via:
   - `pg_stat_activity.state_change` (idle time)
   - `lock_heartbeat.last_heartbeat` (if available)
4. If Instance A is stale (idle > 120s), Instance B:
   - Terminates Instance A (`pg_terminate_backend`)
   - Acquires lock
   - Becomes ACTIVE

**Thresholds** (tunable via ENV):
- `STALE_IDLE_SECONDS=120` (default: 2 minutes)
  - Detects hung/crashed processes
  - MUST be > normal startup time (~60s)
- `LOCK_HEARTBEAT_INTERVAL=15` (heartbeat update frequency)

**Logs to watch**:
```
[LOCK] ✅ ACTIVE MODE: PostgreSQL advisory lock acquired
[LOCK] ⚠️ PASSIVE MODE - another instance is ACTIVE, this instance will wait
[LOCK] ⚠️ STALE LOCK: pid=123 idle=130s heartbeat=N/A (idle>120s)
[LOCK] 🔥 Terminating stale process pid=123...
```

**Common Issues**:

❌ **Takeover loops** (instances keep killing each other):
- **Symptom**: Logs show lock acquisition → termination cycle every 30-120s
- **Root cause**: `STALE_IDLE_SECONDS` too low (startup takes longer than threshold)
- **Fix**: Increase to 180s or 300s

❌ **No ACTIVE instance** (all instances PASSIVE):
- **Symptom**: No instance processes updates
- **Root cause**: Lock deadlock or all instances waiting
- **Fix**: Restart service (clears advisory locks)

✅ **Normal startup**: Expect 1 ACTIVE + 0-1 PASSIVE instances

---

## 3. Database Migrations

### Location

**SSOT**: `/migrations/*.sql` (numbered sequentially)

**Current migrations**:
```
001_initial_schema.sql
002_balance_reserves.sql
003_users_username.sql
004_orphan_callbacks.sql
005_add_columns.sql
006_create_tables.sql
007_lock_heartbeat.sql
008_processed_updates.sql
009_add_delivering_at.sql
010_delivery_lock_platform_wide.sql
011_fix_heartbeat_type.sql  # HOTFIX 2026-01-13
```

### Auto-Apply

Migrations are applied automatically at startup via `app/storage/migrations.py::apply_migrations_safe()`.

**Idempotent**: Safe to re-run (uses `CREATE TABLE IF NOT EXISTS`, `ON CONFLICT DO NOTHING`, etc.)

**Logs**:
```
[MIGRATIONS] Found 11 migration file(s)
[MIGRATIONS] ✅ Applied 001_initial_schema.sql
[MIGRATIONS] ✅ All migrations applied successfully
```

**Failure**:
```
[MIGRATIONS] ❌ Failed to apply 007_lock_heartbeat.sql: ...
```
→ Check DATABASE_URL, network, PostgreSQL permissions

### Manual Migration (if needed)

```bash
psql $DATABASE_URL -f migrations/011_fix_heartbeat_type.sql
```

### Migration 011: Heartbeat Type Fix (2026-01-13)

**Issue**: `update_lock_heartbeat()` function had type signature mismatch
- psycopg2 passes Python strings as PostgreSQL `unknown` type
- Function expects explicit `TEXT` parameter
- Result: Heartbeat updates failed, lock staleness cascaded

**Fix**: Added explicit `::TEXT` cast in migration 011 and render_singleton_lock.py calls

**Verification**: Check logs for:
```
[LOCK] ✅ Heartbeat updated successfully  (periodic, ~hourly)
[LOCK] 💓 Heartbeat monitor started (instance=...)
```

**If migration 011 not applied** (early after deploy):
- Temporary mitigation: Heartbeat check disabled, only idle time checked
- Production logs will show: `[LOCK] ⚠️ PASSIVE MODE - another instance is ACTIVE`
- Expected: No more than 1 instance ACTIVE during normal operation

**Automated check**:
```bash
./scripts/smoke_unified.py  # includes heartbeat function test
```


---

## 4. Health Endpoints

### `/health` (Primary)

**Purpose**: Render health check + monitoring

**Response**:
```json
{
  "status": "ok",
  "uptime": 3600,
  "storage": "postgres",
  "kie_mode": "real",
  "migrations_applied": true,
  "migrations_count": 11,
  "lock_state": "ACTIVE",
  "lock_holder_pid": 12345,
  "lock_idle_duration": 10.5,
  "lock_heartbeat_age": 5.2,
  "lock_takeover_event": null
}
```

**Status codes**:
- `200 OK`: Service healthy
- `500 Error`: Critical failure (rare)

**Render config**:
```yaml
healthCheckPath: /health
```

### `/webhook/{secret}` (Telegram)

**Purpose**: Receive Telegram updates

**Security**:
- Path includes secret token (derived from bot token)
- Header check: `X-Telegram-Bot-Api-Secret-Token`

**Fast-ack**: Returns 200 OK immediately, processes update in background queue

---

## 5. Rollback Procedure

### If deployment breaks production:

1. **Revert on GitHub**:
   ```bash
   git revert HEAD
   git push origin main
   ```
   → Render auto-deploys previous version

2. **Manual rollback** (Render Dashboard):
   - Go to service → Deploys
   - Click "Rollback" on last stable deploy

3. **Database migrations**:
   - Migrations are ADDITIVE (no DROP/ALTER destructive)
   - Rollback is safe (old code ignores new columns/tables)

**Critical**: Never deploy breaking schema changes without migration plan

---

## 6. Troubleshooting

### App won't start

**Check logs for**:
1. `[STARTUP] ENV validation failed` → missing required variables
2. `[MIGRATIONS] ❌ Failed to apply` → database connection issue
3. `[LOCK] ❌ Error acquiring advisory lock` → database permissions

### Updates not processing

**Check**:
1. `/health` returns `lock_state: "ACTIVE"` (not PASSIVE)
2. Logs show `[WEBHOOK_ACTIVE] ✅ Webhook ensured`
3. No errors in `/webhook/{secret}` endpoint

**Test webhook**:
```bash
curl -X POST https://your-app.onrender.com/webhook/YOUR_SECRET \
  -H "Content-Type: application/json" \
  -d '{"update_id":1,"message":{"text":"test"}}'
```
→ Should return `200 OK`

### Heartbeat errors (legacy issue, fixed 2026-01-13)

```
[LOCK] Heartbeat update failed: function update_lock_heartbeat(bigint, unknown) does not exist
```

**Fix**: Ensure migration 011 applied
```sql
SELECT proname FROM pg_proc WHERE proname = 'update_lock_heartbeat';
```
→ Should return 1 row

If missing:
```bash
psql $DATABASE_URL -f migrations/011_fix_heartbeat_type.sql
```

---

## 7. Monitoring

### Metrics to track

**Health endpoint**:
- `migrations_applied: true`
- `lock_state: "ACTIVE"` (exactly 1 instance)
- `uptime > 600` (stable for >10min)

**Logs**:
- No `[LOCK] 🔥 Terminating stale process` loops
- No `[MIGRATIONS] ❌ Failed` errors
- No `[WEBHOOK] ⚠️ Invalid JSON` spam

**Database**:
```sql
SELECT COUNT(*) FROM processed_updates WHERE processed_at > NOW() - INTERVAL '1 hour';
```
→ Should show activity if bot is receiving messages

---

## 8. Performance

### Expected startup time

- **ENV validation**: <100ms
- **Database migrations**: 1-3s
- **Lock acquisition**: 0.5-5s (depends on passive mode retries)
- **Webhook setup**: 1-2s
- **Total**: 30-60s to first request

### Resource usage

- **Memory**: 100-250 MB (depends on active users)
- **CPU**: <5% idle, 10-30% under load
- **DB connections**: 2-10 (pool size)

### Scaling limits

**Current**: Single instance (enforced by singleton lock)

**Future**: Multiple instances require:
- Webhook mode (not polling)
- Dedup via `processed_updates` table
- Load balancer with session affinity (not recommended)

---

## 9. Security

### Secrets management

- All secrets in Render environment variables
- Never commit to git
- Rotate on compromise

### Database

- Read/write access to `DATABASE_URL`
- Advisory lock requires `pg_advisory_lock` privilege (standard)

### Telegram

- Webhook secret path derived from bot token
- Header validation on all webhook requests

---

## 10. Known Constraints

1. **Single instance only** (by design, via lock)
2. **Startup time sensitive** (lock timeout must accommodate migrations)
3. **PostgreSQL required** (no fallback to JSON storage in production)
4. **Render-specific** (health check, advisory lock assumptions)

---

## References

- [SSOT Architecture](architecture/SSOT.md)
- [ENV Contract](../app/utils/startup_validation.py)
- [Migrations](../migrations/)
- [Lock Implementation](../render_singleton_lock.py)
