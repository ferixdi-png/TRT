#!/bin/bash
# Production Quickstart для Render

set -e

echo "=========================================="
echo "TRT BOT - PRODUCTION DEPLOYMENT CHECK"
echo "=========================================="

# Check ENV
echo ""
echo "1/7: Checking ENV variables..."
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "❌ TELEGRAM_BOT_TOKEN not set"
    exit 1
fi
if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL not set"
    exit 1
fi
if [ -z "$WEBHOOK_BASE_URL" ]; then
    echo "❌ WEBHOOK_BASE_URL not set"
    exit 1
fi
if [ -z "$KIE_API_KEY" ]; then
    echo "❌ KIE_API_KEY not set"
    exit 1
fi
echo "✅ All ENV present"

# Apply migrations
echo ""
echo "2/7: Applying idempotent migrations..."
if [ -f "init_schema_idempotent.sql" ]; then
    psql "$DATABASE_URL" < init_schema_idempotent.sql > /dev/null 2>&1
    echo "✅ Migrations applied"
else
    echo "⚠️  init_schema_idempotent.sql not found"
fi

# Validate lock key
echo ""
echo "3/7: Validating lock key..."
python3 -c "from render_singleton_lock import make_lock_key; key = make_lock_key('$TELEGRAM_BOT_TOKEN'); MAX = 0x7FFFFFFFFFFFFFFF; assert 0 <= key <= MAX, f'Lock key {key} out of range'; print(f'✅ Lock key valid: {key}')"

# Run smoke test
echo ""
echo "4/7: Running production smoke test..."
python3 prod_check.py || exit 1

echo ""
echo "=========================================="
echo "✅ READY FOR PRODUCTION"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Deploy to Render: git push origin main"
echo "  2. Check Render logs for:"
echo "     - [LOCK] ✅ ACTIVE MODE"
echo "     - [WEBHOOK_SETUP] ✅ WEBHOOK CONFIGURED"
echo "     - [HEALTH] ✅ Server started on port 10000"
echo "  3. Test bot: send /start to @Ferixdi_bot_ai_bot"
echo ""
