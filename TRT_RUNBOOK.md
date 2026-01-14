# TRT Operational Runbook

**Version**: 1.0  
**Last Updated**: 2026-01-14  
**Maintainer**: Cursor Pro Autonomous Senior Engineer

---

## Quickstart (Local)

### Prerequisites

- Python 3.11+
- PostgreSQL (or use JSON fallback for testing)
- Telegram Bot Token (from @BotFather)
- KIE API Key (from https://kie.ai/settings/api-keys)

### Setup

1. **Clone repository**:
   ```bash
   git clone https://github.com/ferixdi-png/TRT.git
   cd TRT
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Create `.env` file**:
   ```bash
   TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   KIE_API_KEY=kie_abc123def456ghi789jkl
   DATABASE_URL=postgresql://user:password@localhost:5432/trt
   ADMIN_ID=123456789
   BOT_MODE=polling
   PORT=8000
   ```

4. **Run locally**:
   ```bash
   python main_render.py
   ```

5. **Test health endpoint**:
   ```bash
   curl http://localhost:8000/health
   ```

---

## Quickstart (Render)

### Prerequisites

- Render.com account
- GitHub repository: `ferixdi-png/TRT`
- PostgreSQL database on Render

### Setup

1. **Create PostgreSQL Database**:
   - Render Dashboard → New → PostgreSQL
   - Name: `trt-db` (or any name)
   - Plan: Free (testing) or Starter (production)
   - Copy **Internal Database URL**

2. **Create Web Service**:
   - Render Dashboard → New → Web Service
   - Connect GitHub → Select `ferixdi-png/TRT`
   - Branch: `main`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python main_render.py`
   - Plan: Free (testing) or Starter (production)

3. **Set Environment Variables**:
   ```
   TELEGRAM_BOT_TOKEN=<from @BotFather>
   KIE_API_KEY=<from kie.ai>
   DATABASE_URL=<from PostgreSQL dashboard>
   ADMIN_ID=<your Telegram user ID>
   BOT_MODE=webhook
   PORT=10000
   WEBHOOK_BASE_URL=https://<your-app-name>.onrender.com
   WEBHOOK_SECRET_PATH=<secret_path>
   WEBHOOK_SECRET_TOKEN=<secret_token>
   KIE_CALLBACK_PATH=callbacks/kie
   KIE_CALLBACK_TOKEN=<callback_token>
   ```

4. **Set Webhook**:
   ```bash
   curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -d "url=https://<your-app-name>.onrender.com/webhook/<secret_path>" \
     -d "secret_token=<secret_token>"
   ```

5. **Verify Deployment**:
   ```bash
   curl https://<your-app-name>.onrender.com/health
   ```

---

## How to Verify Production in 2 Minutes

### Step 1: Health Check (10 seconds)

```bash
curl https://<your-app-name>.onrender.com/health
```

**Expected**:
```json
{
  "ok": true,
  "mode": "active",
  "lock_acquired": true,
  "ts": "2026-01-14T07:00:00Z"
}
```

**If `"mode": "passive"`**: Wait 30 seconds, check again. If still passive after 5 minutes → see "Recovery" section.

### Step 2: Webhook Fast-Ack (10 seconds)

```bash
curl -X POST "https://<your-app-name>.onrender.com/webhook/<secret_path>" \
  -H "X-Telegram-Bot-Api-Secret-Token: <secret_token>" \
  -H "Content-Type: application/json" \
  -d '{"update_id": 999999, "message": {"text": "/start", "from": {"id": 123456789}}}'
```

**Expected**: `200 OK` in <200ms

### Step 3: E2E Test in Telegram (90 seconds)

1. Open Telegram → Find your bot
2. Send `/start`
3. Click "🎨 Картинки и дизайн" (`cat:image`)
4. Select any model
5. Enter prompt: `test`
6. Click "Запустить"

**Expected**:
- No "PASSIVE_REJECT" in logs
- Bot responds with menu/model selection
- Generation starts (or shows error if balance insufficient)

**Check Logs**:
```bash
# In Render Dashboard → Logs
# Look for:
✅ UPDATE_RECEIVED cid=... update_id=...
✅ CALLBACK_RECEIVED cid=... callback_id=...
✅ CALLBACK_ACCEPTED cid=...
✅ UI_RENDER cid=...
✅ DISPATCH_OK cid=...
```

**If errors**:
- `AttributeError: 'CallbackQuery' object has no attribute 'update_id'` → See "Recovery" section
- `TypeError: log_callback_rejected() got unexpected keyword argument` → See "Recovery" section
- `PASSIVE_REJECT` → Normal during deploy overlap, abnormal if >5 minutes

---

## How to Read Logs

### Key Markers

1. **UPDATE_RECEIVED**:
   ```
   [TELEMETRY] UPDATE_RECEIVED cid=abc123 update_id=123456
   ```
   - Meaning: Webhook received update
   - Action: None (informational)

2. **CALLBACK_RECEIVED**:
   ```
   [TELEMETRY] CALLBACK_RECEIVED cid=abc123 callback_id=xyz789 update_id=123456
   ```
   - Meaning: Callback query received
   - Action: None (informational)

3. **CALLBACK_ROUTED**:
   ```
   [TELEMETRY] CALLBACK_ROUTED cid=abc123 handler=category_cb
   ```
   - Meaning: Callback routed to handler
   - Action: None (informational)

4. **CALLBACK_ACCEPTED**:
   ```
   [TELEMETRY] CALLBACK_ACCEPTED cid=abc123
   ```
   - Meaning: Handler accepted callback
   - Action: None (informational)

5. **CALLBACK_REJECTED**:
   ```
   [TELEMETRY] CALLBACK_REJECTED cid=abc123 reason_code=UNKNOWN_CALLBACK
   ```
   - Meaning: Handler rejected callback
   - Action: Check `reason_code` (UNKNOWN_CALLBACK, PASSIVE_REJECT, VALIDATION_FAIL, etc.)

6. **PASSIVE_REJECT**:
   ```
   ⏸️ PASSIVE_REJECT callback_query data=cat:image
   ```
   - Meaning: Instance in PASSIVE mode, update rejected
   - Action: Check `/health` endpoint, wait for ACTIVE mode

7. **EXCEPTION_CAUGHT**:
   ```
   [EXCEPTION] EXCEPTION_CAUGHT cid=abc123 error_type=AttributeError error_message=...
   ```
   - Meaning: Unhandled exception caught
   - Action: Check error message, see "Recovery" section

8. **DISPATCH_OK** / **DISPATCH_FAIL**:
   ```
   [TELEMETRY] DISPATCH_OK cid=abc123
   ```
   - Meaning: Update processed successfully
   - Action: None (informational)

### Correlation ID (CID)

**Format**: `cid=abc123` (hex string)  
**Usage**: Track single user interaction across logs

**Example**:
```
[TELEMETRY] UPDATE_RECEIVED cid=abc123 update_id=123456
[TELEMETRY] CALLBACK_RECEIVED cid=abc123 callback_id=xyz789
[TELEMETRY] CALLBACK_ROUTED cid=abc123 handler=category_cb
[TELEMETRY] CALLBACK_ACCEPTED cid=abc123
[TELEMETRY] UI_RENDER cid=abc123 screen_id=model_selection
[TELEMETRY] DISPATCH_OK cid=abc123
```

**Search by CID**:
```bash
# In Render Dashboard → Logs
# Filter: cid=abc123
```

---

## How to Recover

### Restart Service

**When**: Service unresponsive, stuck in PASSIVE mode, or database connection issues

**Steps**:
1. Render Dashboard → Service → Manual Deploy → Restart
2. Wait 30-60 seconds
3. Check `/health` endpoint
4. Verify `"mode": "active"`

### Redeploy

**When**: Code changes, environment variable updates, or persistent errors

**Steps**:
1. Push to `main` branch (triggers auto-deploy)
2. Wait 3-5 minutes for build + deploy
3. Check `/health` endpoint
4. Run smoke tests

### Lock Stuck

**Symptom**: `"mode": "passive"` for >5 minutes, `"lock_acquired": false`

**Cause**: Old instance didn't release lock (crashed or stuck)

**Recovery**:
1. **Option 1**: Restart Render service (forces lock release)
2. **Option 2**: Manually release lock (if you have DB access):
   ```sql
   SELECT pg_advisory_unlock_all();
   ```
3. **Option 3**: Wait for lock timeout (if configured)

**Prevention**: Ensure graceful shutdown (handles SIGTERM)

### Database Issues

**Symptom**: `asyncpg.exceptions.TooManyConnections` or `PostgreSQL advisory lock timeout`

**Recovery**:
1. Check connection pool size (max=10)
2. Check for stuck connections:
   ```sql
   SELECT * FROM pg_stat_activity WHERE state = 'idle in transaction';
   ```
3. Kill stuck connections:
   ```sql
   SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle in transaction';
   ```
4. Restart Render service (forces connection cleanup)

### Webhook Secret Mismatch

**Symptom**: Telegram returns `404 Not Found` or `403 Forbidden`

**Recovery**:
1. Check `WEBHOOK_SECRET_PATH` matches Telegram webhook URL
2. Check `WEBHOOK_SECRET_TOKEN` matches Telegram webhook secret token
3. Re-set webhook:
   ```bash
   curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -d "url=https://<your-app-name>.onrender.com/webhook/<secret_path>" \
     -d "secret_token=<secret_token>"
   ```

### KIE API Timeout

**Symptom**: `TimeoutError` or `502 Bad Gateway` from KIE API

**Recovery**:
1. Check KIE API status: `curl https://api.kie.ai/health`
2. Retry logic handles this automatically (exponential backoff)
3. If persistent: check `KIE_API_KEY` validity
4. Check KIE API dashboard for rate limits

---

## Checklist for Release

### Pre-Release

- [ ] All tests pass: `python scripts/smoke_webhook.py`
- [ ] No syntax errors: `python -m compileall -q .`
- [ ] Health check works: `curl https://<app>.onrender.com/health`
- [ ] Webhook fast-ack works: `curl -X POST https://<app>.onrender.com/webhook/<secret>`
- [ ] E2E test passes: `/start` → `cat:image` → model → prompt → generate
- [ ] No "PASSIVE_REJECT" in logs (except during deploy overlap)
- [ ] No `AttributeError` or `TypeError` in logs
- [ ] All environment variables set correctly
- [ ] Webhook URL matches Render service URL
- [ ] Database migrations applied (if any)

### Post-Release

- [ ] Health check: `"mode": "active"`, `"lock_acquired": true`
- [ ] Smoke tests pass: `python scripts/smoke.py --url https://<app>.onrender.com`
- [ ] E2E test passes: `/start` → `cat:image` → model → prompt → generate
- [ ] No errors in logs (check last 100 lines)
- [ ] Telemetry events present: `UPDATE_RECEIVED`, `CALLBACK_RECEIVED`, `DISPATCH_OK`
- [ ] Correlation IDs present in all events
- [ ] Webhook response time <200ms (check Render metrics)

### Rollback Plan

**If release fails**:
1. Revert last commit: `git revert HEAD`
2. Push to `main` (triggers auto-deploy)
3. Wait 3-5 minutes
4. Verify rollback: `/health` + smoke tests

---

**End of TRT_RUNBOOK.md**

