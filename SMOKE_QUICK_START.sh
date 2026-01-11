#!/bin/bash
# Quick start guide for smoke testing

echo "🔥 TRT Smoke Test - Quick Start"
echo "================================"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "Please create .env with required variables:"
    echo "  - ADMIN_ID"
    echo "  - BOT_MODE"
    echo "  - TELEGRAM_BOT_TOKEN"
    echo "  - WEBHOOK_BASE_URL"
    echo "  - WEBHOOK_SECRET_PATH"
    echo "  - KIE_API_KEY"
    echo "  - PAYMENT_BANK, PAYMENT_CARD_HOLDER, PAYMENT_PHONE"
    exit 1
fi

echo "✅ Running smoke tests..."
echo ""

# Run smoke test
make smoke-prod

# Capture exit code
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ SMOKE TESTS PASSED"
    echo ""
    echo "📊 Test report:"
    cat SMOKE_REPORT.md
    echo ""
    echo "🚀 Ready to deploy!"
    echo ""
    echo "Next steps:"
    echo "  1. make deployment-checklist"
    echo "  2. git push origin main"
    echo "  3. Check GitHub Actions"
else
    echo ""
    echo "❌ SMOKE TESTS FAILED"
    echo ""
    echo "📊 Test report:"
    cat SMOKE_REPORT.md
    echo ""
    echo "⚠️  Fix issues before deploying!"
fi
