# Deployment Guide (Render)

## Environment Setup

1. **Создать PostgreSQL database** в Render Dashboard
2. **Создать Web Service** с настройками:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python main_render.py`
   - Environment: Python 3.11+

3. **Настроить Environment Variables** (из `product/truth.yaml` → `env_contract`):

### Required (MUST be set)
```bash
TELEGRAM_BOT_TOKEN=<bot token from @BotFather>
DATABASE_URL=<postgres://... from Render DB>
RENDER_EXTERNAL_URL=https://<app-name>.onrender.com
```

### Optional (have defaults)
```bash
BOT_MODE=AUTO              # AUTO | ACTIVE | PASSIVE
LOCK_KEY1=214748364        # Advisory lock key 1 (signed int32)
LOCK_KEY2=2                # Advisory lock key 2 (signed int32)
PASSIVE_MODE_WHITELIST=/start,/help,/balance  # PASSIVE mode allowed commands
KIE_API_KEY=<kie.ai key>   # Only if using KIE.ai API
```

### Forbidden (will cause verify.py to FAIL)
```bash
# ❌ DO NOT SET THESE:
USE_PTB=...              # Legacy flag
POLLING_MODE=...         # Webhook only
LOCAL_LOCK_FILE=...      # PostgreSQL advisory lock only
```

## Deployment Process

### Manual Deployment
1. Push to GitHub main branch
2. Render auto-deploys (if auto-deploy enabled)
3. Wait for build to complete (~3-5 minutes)
4. Check `/health` endpoint
5. Run smoke tests: `python scripts/smoke.py --env production`

### CI/CD Deployment (GitHub Actions)
```yaml
# .github/workflows/truth_gate.yml
name: Truth Gate
on:
  push:
    branches: [main]
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Verify architecture
        run: python scripts/verify.py
      - name: Smoke tests
        run: python scripts/smoke.py
```

## Post-Deployment Checklist

1. ✅ `/health` returns 200 OK with valid JSON
2. ✅ Bot responds to `/start` (test in Telegram)
3. ✅ Database migrations applied (check logs for `CREATE TABLE IF NOT EXISTS`)
4. ✅ Lock acquired (check logs for `Lock acquired: ACTIVE mode`)
5. ✅ No errors in Render logs (search for `ERROR`, `Traceback`, `Exception`)
6. ✅ Webhook registered (check logs for `Webhook set successfully`)
7. ✅ Fast-ack working (webhook response < 500ms in logs)
8. ✅ Queue processing (check logs for `Processing update`)

## Rollback Strategy

If deployment fails:
1. Render Dashboard → Deployments → Select previous deploy → "Rollback"
2. OR: `git revert <commit>` + push to main
3. Check `/health` after rollback
4. Investigate failure in Render logs

## Monitoring Deployment

### Render Dashboard
- **Metrics**: CPU, Memory, Response Time
- **Logs**: Real-time logs with search/filter
- **Events**: Deploy events, crashes, restarts

### Telegram Bot
- Send `/start` to bot (should respond in < 2 seconds)
- Check balance: `/balance` (database read test)
- Try generation (if ACTIVE mode)

### Health Endpoint
```bash
curl https://<app-name>.onrender.com/health
```
Expected response:
```json
{
  "status": "healthy",
  "lock_state": "ACTIVE",
  "queue_size": 0,
  "database": "connected"
}
```

## Troubleshooting

### "Web service unhealthy"
- Check `/health` returns 200 OK
- Verify DATABASE_URL is set correctly
- Check logs for connection errors

### "Bot not responding"
- Check TELEGRAM_BOT_TOKEN is correct
- Verify webhook is registered (logs: `Webhook set successfully`)
- Check RENDER_EXTERNAL_URL matches actual URL

### "Database connection failed"
- DATABASE_URL must be full connection string
- Check PostgreSQL service is running
- Verify IP allowlist (Render internal IP should be allowed)

### "Lock not acquired (PASSIVE mode)"
- Expected during deployment (old instance still holds lock)
- Wait 5-10 minutes for old instance to release
- Check lock_heartbeat table for stale locks

### "Import errors"
- Verify requirements.txt has all dependencies
- Check Python version (3.11+ required)
- Re-deploy with fresh build

### "Webhook returns 409 Conflict"
- Another instance already registered webhook
- Wait for old instance to shutdown
- Check Render Dashboard → Deployments (only one should be running)

## Environment-Specific URLs

### Staging
```
App: https://trt-staging.onrender.com
Health: https://trt-staging.onrender.com/health
Webhook: https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://trt-staging.onrender.com/webhook
```

### Production
```
App: https://<app-name>.onrender.com
Health: https://<app-name>.onrender.com/health
Webhook: https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<app-name>.onrender.com/webhook
```

## Cost Optimization

- Free tier: 750 hours/month (enough for single instance)
- Auto-suspend: Disabled (bot must always respond)
- Database: Free tier (256MB storage, shared CPU)
- Upgrade triggers:
  - > 100 active users/day → Standard plan
  - > 1M DB rows → Dedicated PostgreSQL
  - Response time > 1s → Scale up instance type

## Security Checklist

1. ✅ TELEGRAM_BOT_TOKEN in environment variables (not in code)
2. ✅ KIE_API_KEY in environment variables
3. ✅ Database credentials via DATABASE_URL (not hardcoded)
4. ✅ ADMIN_IDS set correctly (only trusted users)
5. ✅ No secrets in logs (check for `password=`, `token=`)
6. ✅ HTTPS only (Render enforces this)
7. ✅ Rate limiting enabled (per product/truth.yaml)
