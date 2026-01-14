#!/bin/bash
set -e

echo "🔍 Post-Deploy Verification Script"
echo "=================================="
echo ""

# Check environment
if [ -z "$WEBHOOK_BASE_URL" ]; then
    echo "⚠️  WEBHOOK_BASE_URL not set - using placeholder"
    WEBHOOK_BASE_URL="https://your-app.onrender.com"
fi

echo "📊 Step 1: Test /health endpoint"
echo "--------------------------------"
HEALTH_URL="${WEBHOOK_BASE_URL}/health"
echo "Calling: $HEALTH_URL"

if command -v curl &> /dev/null; then
    HEALTH_RESPONSE=$(curl -s "$HEALTH_URL" || echo '{"error": "curl failed"}')
    echo "$HEALTH_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$HEALTH_RESPONSE"
    
    # Check critical fields
    ACTIVE=$(echo "$HEALTH_RESPONSE" | grep -o '"active":[^,}]*' | cut -d: -f2 | tr -d ' ')
    QUEUE_DEPTH=$(echo "$HEALTH_RESPONSE" | grep -o '"queue_depth":[0-9]*' | cut -d: -f2)
    
    echo ""
    if [ "$ACTIVE" = "true" ]; then
        echo "✅ Bot is ACTIVE"
    else
        echo "❌ Bot is PASSIVE (expected if just deployed, wait 10s)"
    fi
    
    if [ ! -z "$QUEUE_DEPTH" ]; then
        echo "✅ Queue depth: $QUEUE_DEPTH"
    fi
else
    echo "⚠️  curl not installed, skipping HTTP checks"
fi

echo ""
echo "📊 Step 2: Run verification tests"
echo "----------------------------------"
make verify

echo ""
echo "✅ Verification complete!"
echo ""
echo "Next steps:"
echo "1. Check Render logs for:"
echo "   - [HTTP] ✅ Server listening on 0.0.0.0:10000"
echo "   - [STATE_SYNC] ✅ active_state: False -> True"
echo "   - [WORKER_X] ✅ ACTIVE_ENTER"
echo ""
echo "2. Test /start in Telegram (should reply within 2s)"
echo ""
echo "3. Monitor /health endpoint:"
echo "   curl ${WEBHOOK_BASE_URL}/health | jq"
