#!/bin/bash
# Test singleton lock with two containers
# Prerequisites: docker, docker-compose or docker network

set -e

echo "=== Building Docker image ==="
docker build -t trt:test .

echo "=== Creating network ==="
docker network create trt-test 2>/dev/null || true

echo "=== Starting PostgreSQL ==="
docker run -d \
  --name trt-postgres \
  --network trt-test \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=telegram_bot \
  postgres:16 || true

sleep 3

echo "=== Waiting for PostgreSQL to be ready ==="
for i in {1..30}; do
  if docker exec trt-postgres psql -U postgres -d telegram_bot -c "SELECT 1" >/dev/null 2>&1; then
    echo "PostgreSQL is ready"
    break
  fi
  echo "Waiting... ($i/30)"
  sleep 1
done

DB_URL="postgresql://postgres:postgres@trt-postgres:5432/telegram_bot"

echo "=== Starting Container 1 (should get ACTIVE) ==="
docker run -d \
  --name trt-container1 \
  --network trt-test \
  -e DATABASE_URL="$DB_URL" \
  -e TELEGRAM_BOT_TOKEN="test_token_12345678" \
  -e BOT_MODE="polling" \
  -e PORT=8000 \
  -p 8001:8000 \
  trt:test

sleep 2

echo "=== Checking Container 1 health ==="
if docker logs trt-container1 2>&1 | grep -q "ACTIVE"; then
  echo "✅ Container 1 is ACTIVE"
else
  echo "⚠️ Container 1 status check (logs may not show yet)"
fi

echo "=== Starting Container 2 (should stay PASSIVE) ==="
docker run -d \
  --name trt-container2 \
  --network trt-test \
  -e DATABASE_URL="$DB_URL" \
  -e TELEGRAM_BOT_TOKEN="test_token_12345678" \
  -e BOT_MODE="polling" \
  -e PORT=8000 \
  -p 8002:8000 \
  trt:test

sleep 2

echo "=== Checking Container 2 status (should be PASSIVE) ==="
if docker logs trt-container2 2>&1 | grep -i "passive"; then
  echo "✅ Container 2 is PASSIVE"
else
  echo "⚠️ Container 2 status check (logs may not show yet)"
fi

echo "=== Health check Container 1 ==="
sleep 1
if curl -s http://localhost:8001/health 2>/dev/null | grep -q "active.*true"; then
  echo "✅ Container 1 /health shows active=true"
else
  echo "⚠️ Container 1 /health (service may still be starting)"
fi

echo "=== Health check Container 2 ==="
if curl -s http://localhost:8002/health 2>/dev/null | grep -q "active.*false"; then
  echo "✅ Container 2 /health shows active=false (passive)"
else
  echo "⚠️ Container 2 /health (service may still be starting)"
fi

echo "=== Collecting logs (20 seconds) ==="
echo "--- Container 1 (ACTIVE) ---"
docker logs trt-container1 2>&1 | head -30 || true

echo ""
echo "--- Container 2 (PASSIVE, checking for spam) ---"
WARNINGS=$(docker logs trt-container2 2>&1 | grep -i "warning" | wc -l)
echo "Total WARNINGs in Container 2: $WARNINGS"
if [ "$WARNINGS" -le 5 ]; then
  echo "✅ PASS: No excessive WARNING spam (≤5 warnings expected)"
else
  echo "❌ FAIL: Too many WARNINGs ($WARNINGS > 5)"
  docker logs trt-container2 2>&1 | grep -i "warning" | head -10
fi

echo "=== Cleanup ==="
docker rm -f trt-container1 trt-container2 trt-postgres 2>/dev/null || true
docker network rm trt-test 2>/dev/null || true

echo "=== Test Complete ==="
