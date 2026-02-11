# ENV Checklist: Required Environment Variables
## TRT Telegram Bot + Mini App

---

## Critical (Bot Won't Start)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BOT_TOKEN` | ✅ YES | - | Telegram Bot Token |
| `KIE_API_KEY` | ✅ YES | - | KIE.AI API Key |
| `DATABASE_URL` | ✅ YES | - | PostgreSQL connection string |
| `BOT_INSTANCE_ID` | ✅ YES | - | Unique partner ID for data isolation |

---

## Important (Features Disabled)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `WEBAPP_URL` | Optional | "" | Mini App URL. If not set, webapp button hidden |
| `ADMIN_ID` | Optional | - | Admin user ID for admin commands |
| `REDIS_URL` | Auto | "" | Redis URL (configured by author automatically) |

---

## Timeouts & Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `KIE_TIMEOUT_IMAGE` | 180 | Image generation timeout (seconds) |
| `KIE_TIMEOUT_VIDEO` | 600 | Video generation timeout (seconds) |
| `KIE_TIMEOUT_AUDIO` | 180 | Audio generation timeout (seconds) |
| `KIE_WAITING_TIMEOUT_SECONDS` | 120 | Max wait for provider response |
| `KIE_WAITING_MAX_RETRIES` | 2 | Retry attempts on timeout |
| `KIE_POLL_PROGRESS_INTERVAL_SECONDS` | 15 | Status poll interval |

---

## Billing & Pricing

| Variable | Default | Description |
|----------|---------|-------------|
| `FREE_GENERATIONS_PER_DAY` | 5 | Free generations per user per day |
| `REFERRAL_BONUS_GENERATIONS` | 3 | Bonus for referral |
| `BILLING_PREFLIGHT_STRICT` | true | Fail on billing check errors |

---

## Boot & Startup

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 10000 | Health check server port |
| `WEBHOOK_URL` | - | Webhook URL (if not polling) |
| `DB_STARTUP_RETRIES` | 2 | DB connection retries |
| `DB_STARTUP_RETRY_DELAY` | 1.5 | Retry delay (seconds) |
| `BOOT_WARMUP_BUDGET_SECONDS` | 5 | Max boot warmup time |
| `STORAGE_PREFLIGHT_STRICT` | true | Fail on storage check errors |

---

## Redis (Auto-configured by author)

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | "" | Redis connection URL |
| `REDIS_CONNECT_TIMEOUT_SECONDS` | 3 | Connection timeout |
| `REDIS_CONNECT_ATTEMPTS` | 3 | Connection attempts |
| `REDIS_CONNECT_DEADLINE_SECONDS` | 5 | Total deadline |

---

## Logging & Observability

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | INFO | Logging level |
| `STRUCTURED_LOGGING` | true | JSON logs |

---

## Fail-Fast Behavior

### If WEBAPP_URL not set:
- ✅ Bot works normally
- ⚠️ Mini App button hidden in menu
- ⚠️ `/webapp/*` routes return 404

### If REDIS_URL not set:
- ✅ Bot works (single instance)
- ⚠️ No distributed locks (Redis is configured by the author automatically)

### If DATABASE_URL not set:
- ❌ Bot fails to start
- ❌ Error: "Storage preflight failed"

### If BOT_TOKEN not set:
- ❌ Bot fails to start
- ❌ Error: "BOT_TOKEN required"

### If KIE_API_KEY not set:
- ⚠️ Bot starts
- ❌ All generations fail

---

## Example .env

```bash
# Required
BOT_TOKEN=your_telegram_bot_token
KIE_API_KEY=your_kie_api_key
DATABASE_URL=postgres://user:pass@host:5432/dbname
BOT_INSTANCE_ID=my-partner-id

# Optional
WEBAPP_URL=https://your-webapp.example.com
ADMIN_ID=123456789
# REDIS_URL is configured by the author automatically

# Timeouts
KIE_TIMEOUT_VIDEO=600
KIE_WAITING_TIMEOUT_SECONDS=120

# Billing
FREE_GENERATIONS_PER_DAY=5

# Port
PORT=10000
```

---

## Verification Commands

```bash
# Check required vars
python -c "import os; assert os.getenv('BOT_TOKEN'), 'BOT_TOKEN required'"
python -c "import os; assert os.getenv('KIE_API_KEY'), 'KIE_API_KEY required'"
python -c "import os; assert os.getenv('DATABASE_URL'), 'DATABASE_URL required'"
python -c "import os; assert os.getenv('BOT_INSTANCE_ID'), 'BOT_INSTANCE_ID required'"

# Check database connectivity
python -c "
import asyncio
from app.storage import get_storage
async def check():
    s = get_storage()
    return await s.ping() if hasattr(s, 'ping') else True
print('DB OK' if asyncio.run(check()) else 'DB FAIL')
"
```

