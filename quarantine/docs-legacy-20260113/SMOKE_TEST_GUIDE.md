# TRT Bot Smoke Testing Guide

## Overview

The TRT bot includes a comprehensive smoke testing suite to ensure all critical components are working before deployment. This guide explains how to use the smoke tests.

## Quick Start

### Run Production Smoke Tests

```bash
# Full smoke test with report
make smoke-prod

# Or manually
python -m app.tools.smoke --report-file SMOKE_REPORT.md
```

### Generate Deployment Checklist

```bash
make deployment-checklist
```

This generates `DEPLOYMENT_CHECKLIST.md` with instructions.

## What Gets Tested

### 1. **Environment Variables** ✅
- Checks all required ENV variables are set:
  - ADMIN_ID, BOT_MODE, PORT
  - TELEGRAM_BOT_TOKEN, WEBHOOK_BASE_URL
  - KIE_API_KEY, Database credentials
  - PAYMENT_BANK, PAYMENT_CARD_HOLDER, PAYMENT_PHONE
  - SUPPORT_TELEGRAM

### 2. **Database Connection** ⏭️
- In SMOKE_MODE: Skipped (test DB used)
- In Production: Verifies PostgreSQL connectivity and schema

### 3. **KIE Models** ✅
- Loads KIE_SOURCE_OF_TRUTH.json
- Validates 72 models are present
- Checks each model has input_schema
- Categories verified: text, image, video, audio, music, avatar, enhance

### 4. **Telegram Webhook** ✅
- Verifies webhook URL is configured
- Checks secret path exists
- Validates webhook token format

### 5. **Button Handlers** ⚠️
- Extracts all button callback patterns
- Verifies essential buttons exist:
  - `back_to_menu` ✅
  - `show_models` ✅
  - `help` (optional)

### 6. **Payment Configuration** ✅
- Verifies payment variables are set
- Validates webhook schema
- Tests balance calculation logic

## Test Results Interpretation

### Status Codes

- **✅ PASS** - Component is working correctly
- **❌ FAIL** - Component has critical issue
- **⚠️  WARN** - Component works but has minor issue
- **⏭️  SKIP** - Component skipped in current mode

### Report Example

```
🧪 SMOKE TEST
═════════════════════════════════════════════════════════════════

✅ PASS Environment Variables: All 10 variables present
⏭️  SKIP Database Connection: Skipped in SMOKE_MODE
✅ PASS KIE Models: 72 models configured with valid schemas
✅ PASS Telegram Webhook: Webhook URL configured: https://...
⚠️  WARN Button Handlers: Some buttons missing: ['help']
✅ PASS Payment Configuration: Payment variables configured

═════════════════════════════════════════════════════════════════
✅ ALL CHECKS PASSED
```

## Smoke Mode Behavior

When `SMOKE_MODE=1`:
- **Database**: Skipped (uses test database)
- **Expensive Operations**: Not executed
- **Dry Runs**: Enabled (no real API calls)
- **Webhook Testing**: Schema only (no real callbacks)

### Running in CI/CD

GitHub Actions automatically runs smoke tests on:
- Every push to main
- Every pull request
- Manual trigger (workflow_dispatch)

Smoke report is uploaded as artifact: `smoke-report` artifact

## Troubleshooting

### Missing Environment Variables

Error: `Missing: KIE_API_KEY, TELEGRAM_BOT_TOKEN`

**Solution**: Set the missing variables before running tests:
```bash
export KIE_API_KEY="your_key"
export TELEGRAM_BOT_TOKEN="your_token"
make smoke-prod
```

### Database Connection Failed

Error: `Failed to connect to postgresql://...`

**Solution**: In local testing, skip database check:
```bash
SMOKE_MODE=1 make smoke-prod
```

In production, ensure PostgreSQL is running and DATABASE_URL is correct.

### Missing Button

Error: `Some buttons missing: ['generate']`

**Solution**: This is a warning. Verify the button exists in your UI:
1. Check `app/helpers/` files for callback_data patterns
2. Verify handlers are registered in `main_render.py`
3. If button is intentionally missing, update test expectations

## Advanced Usage

### Custom Report Path

```bash
python -m app.tools.smoke --report-file /path/to/report.md
```

### Integration Tests

```bash
python -m app.tools.integration_tests
```

### Button Validation Only

```python
from app.tools.button_validator import check_essential_buttons

buttons = check_essential_buttons()
print(buttons)  # {'back_to_menu': True, 'show_models': True, ...}
```

### Payment Validation

```python
from app.tools.payment_validator import PaymentFlowValidator, MockPaymentEvent
from decimal import Decimal

event = MockPaymentEvent(user_id=123, amount=Decimal("1.38"))
payload = event.to_dict()

valid, error = PaymentFlowValidator.validate_payment_webhook_schema(payload)
assert valid, f"Invalid schema: {error}"
```

## Deployment Workflow

1. **Local Testing**
   ```bash
   make smoke-prod
   # Verify all checks pass (🟢 GREEN)
   ```

2. **Push to GitHub**
   ```bash
   git push origin main
   ```

3. **CI/CD Runs**
   - GitHub Actions executes smoke tests
   - Download smoke-report artifact to verify

4. **Deploy to Render**
   - Use Render dashboard or manual deploy
   - Monitor logs for "✅ ACTIVE MODE"

5. **Post-Deployment Verification**
   ```bash
   # Test health endpoint
   curl https://your-render-app.onrender.com/health
   
   # Test webhook endpoint
   curl -X POST https://your-render-app.onrender.com/webhook/test
   ```

## Continuous Monitoring

After deployment, monitor these endpoints:

- `GET /health` - Service health status
- `POST /webhook/{secret_path}` - Telegram webhook
- `/api/test_webhook` - Manual webhook testing

## Architecture

```
app/tools/
├── smoke.py                 # Main smoke test runner
├── button_validator.py      # Button/handler validation
├── mock_updates.py         # Mock Telegram updates
├── payment_validator.py    # Payment schema validation
├── integration_tests.py    # Full flow integration tests
└── report_generator.py     # Deployment checklist generator
```

## Files Generated

After running smoke tests:
- `SMOKE_REPORT.md` - Detailed test results
- `DEPLOYMENT_CHECKLIST.md` - Deployment instructions

Both are tracked in Git and updated on each test run.

---

**For support**: Check logs in SMOKE_REPORT.md for detailed error messages and recommendations.
