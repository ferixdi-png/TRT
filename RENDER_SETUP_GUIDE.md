# 🚀 Render Deployment Checklist

**Status:** ✅ READY FOR PRODUCTION  
**Version:** 2026-01-11  
**Python:** 3.11  

---

## Pre-Deployment ✅

- [x] All tests pass: `make verify` (216 tests)
- [x] Syntax check: `python -m compileall .` 
- [x] Project verification: `python scripts/verify_project.py` (20/20)
- [x] Health endpoint: `GET /health` returns 200
- [x] Security audit: no hardcoded secrets, no eval/exec
- [x] Webhook validation: strict token checking
- [x] KIE callback integration: real URL + token validation
- [x] Payment idempotency: tested and working

---

## Render Setup (5 mins)

### 1. Create PostgreSQL Database
```
Render Dashboard → New+ → PostgreSQL
- Database: free-tier
- Region: choose closest to you
- After creation: save Internal Database URL
```

### 2. Create Web Service
```
Render Dashboard → New+ → Web Service
- Repository: ferixdi-png/TRT
- Branch: main
- Environment: Python 3
- Plan: Free (or Starter for production)
```

### 3. Build Command
```bash
pip install -r requirements.txt
```

### 4. Start Command
```bash
python main_render.py
```

### 5. Set Environment Variables

**Copy-paste these into Render Dashboard → Environment:**

```
# Required
TELEGRAM_BOT_TOKEN=<YOUR_BOT_TOKEN_FROM_BOTFATHER>
KIE_API_KEY=<YOUR_KIE_API_KEY>
DATABASE_URL=<POSTGRES_INTERNAL_URL_FROM_ABOVE>
ADMIN_ID=<YOUR_TELEGRAM_ID>
BOT_MODE=webhook
PORT=10000

# Recommended (safety + monitoring)
WEBHOOK_SECRET_PATH=secret_path_123
WEBHOOK_SECRET_TOKEN=secret_token_xyz
KIE_CALLBACK_PATH=callbacks/kie
KIE_CALLBACK_TOKEN=callback_token_secret
WEBHOOK_BASE_URL=https://<YOUR_APP_NAME>.onrender.com

# Optional
PAYMENT_BANK=Your Bank
PAYMENT_CARD_HOLDER=Card Holder Name
PAYMENT_PHONE=+7999999999
SUPPORT_TELEGRAM=@support_bot
SUPPORT_TEXT=Contact @support_bot for help
DB_MAXCONN=5
LOG_LEVEL=INFO
```

**How to get each value:**

| Variable | How to Get | Example |
|----------|-----------|---------|
| TELEGRAM_BOT_TOKEN | Message @BotFather, /newbot | `123456789:ABCDefgh...` |
| KIE_API_KEY | From Kie.ai dashboard | `kie_prod_xxxxx` |
| DATABASE_URL | Copy from PostgreSQL service | `postgresql://user:pass@host/db` |
| ADMIN_ID | Your Telegram user ID (from @userinfobot) | `123456789` |
| WEBHOOK_SECRET_PATH | Create yourself (random string) | `secret_abc123` |
| WEBHOOK_SECRET_TOKEN | Create yourself (random string) | `token_xyz789` |

### 6. Deploy
```
Click "Create Web Service"
→ Wait for build (2-3 mins)
→ Check logs for "Server started on port"
```

---

## Post-Deployment Verification ✅

### Health Check
```bash
curl https://<YOUR_APP_NAME>.onrender.com/health
```

Expected response:
```json
{
  "status": "ok",
  "uptime": 123,
  "storage": "postgres",
  "kie_mode": "real"
}
```

### Webhook Setup (Telegram)
```bash
curl -X POST https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://<YOUR_APP_NAME>.onrender.com/webhook/secret_path_123",
    "secret_token": "secret_token_xyz"
  }'
```

Expected: `{"ok":true,"result":true,"description":"Webhook was set"}`

### Webhook URL Format
```
https://<YOUR_APP_NAME>.onrender.com/webhook/{WEBHOOK_SECRET_PATH}

Headers (Telegram sends):
  X-Telegram-Bot-Api-Secret-Token: {WEBHOOK_SECRET_TOKEN}
```

### KIE Callback Setup
KIE will call your endpoint with:
```
POST https://<YOUR_APP_NAME>.onrender.com/{KIE_CALLBACK_PATH}
Headers:
  X-KIE-Callback-Token: {KIE_CALLBACK_TOKEN}
  Content-Type: application/json

Body:
{
  "taskId": "task_123",
  "state": "done",
  "resultUrls": ["https://..."],
  "resultJson": "{...}"
}
```

---

## Monitoring & Troubleshooting 🔍

### Check Logs
```bash
Render Dashboard → Service → Logs
# Look for:
# - "[LOCK] Acquired - ACTIVE" = running normally
# - "[HEALTH] Server started on port" = health check working
# - "[WEBHOOK]" = receiving Telegram updates
# - "[KIE_CALLBACK]" = receiving KIE callbacks
```

### Common Issues

**"Cannot connect to PostgreSQL"**
- Check DATABASE_URL is correct Internal URL (from PostgreSQL service)
- Check if PostgreSQL service is running (Render Dashboard)
- Wait 30 seconds after creating PostgreSQL

**"Webhook not received"**
- Verify webhook URL: `curl https://api.telegram.org/bot{TOKEN}/getWebhookInfo`
- Check WEBHOOK_SECRET_PATH matches in setWebhook call
- Check WEBHOOK_SECRET_TOKEN matches X-Telegram-Bot-Api-Secret-Token header
- Check bot is started and /health returns 200

**"Health check failing"**
- Check logs for startup errors
- Verify all required ENV vars are set
- Check Python version (should be 3.11+)

**"KIE API errors"**
- Verify KIE_API_KEY is correct
- Check KIE_CALLBACK_PATH and KIE_CALLBACK_TOKEN are set
- Check token header X-KIE-Callback-Token is validated

---

## Scaling & Production Tips 📈

### High Traffic
1. Upgrade from Free → Standard tier
2. Increase DB_MAXCONN (e.g., 10-20)
3. Monitor lock contention (advisory lock may need tuning)

### Availability
1. Use external monitoring (e.g., Uptime Robot)
2. Set up alerts for 503 errors (rolling deploy indicators)
3. Monitor `/health` endpoint (should always return 200)

### Security
1. ✅ Never commit .env files
2. ✅ Rotate WEBHOOK_SECRET_PATH and TOKEN periodically
3. ✅ Use strong random values (not "secret123")
4. ✅ Keep KIE_API_KEY private (don't share)

---

## Rollback
```bash
# In case something goes wrong:

1. Pause Web Service (Render Dashboard)
2. Fix code in git
3. Push to main
4. Render auto-redeploys

# Or manually:
git revert <bad_commit>
git push
# Render will rebuild automatically
```

---

## Maintenance

### Weekly
- Check logs for errors
- Monitor health endpoint

### Monthly
- Review payment transactions
- Update models list (if using live Kie.ai)

### On Code Changes
- Run `make verify` locally
- All tests should pass
- Push to main
- Wait for Render deploy

---

## Support
- Issues: GitHub Issues
- Telegram: @support_telegram (from ENV)
- Render Docs: https://render.com/docs

---

**Last Updated:** 2026-01-11  
**Status:** ✅ Production Ready
