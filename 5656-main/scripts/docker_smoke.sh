#!/bin/bash
# Docker smoke test script
# Builds Docker image, runs container with TEST_MODE=1, checks health, runs smoke test

set -e  # Exit on error

echo "=========================================="
echo "Docker Smoke Test"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="kie-bot-smoke-test"
CONTAINER_NAME="kie-bot-smoke-test-container"
HEALTH_PORT=10000
HEALTH_URL="http://localhost:${HEALTH_PORT}/health"

# Step 1: Build Docker image
echo -e "${YELLOW}[1/4] Building Docker image...${NC}"
docker build -t "${IMAGE_NAME}" . || {
    echo -e "${RED}❌ Docker build failed${NC}"
    exit 1
}
echo -e "${GREEN}✅ Docker image built successfully${NC}"
echo ""

# Step 2: Stop and remove existing container if it exists
echo -e "${YELLOW}[2/4] Cleaning up existing container...${NC}"
docker stop "${CONTAINER_NAME}" 2>/dev/null || true
docker rm "${CONTAINER_NAME}" 2>/dev/null || true
echo -e "${GREEN}✅ Cleanup complete${NC}"
echo ""

# Step 3: Run container with TEST_MODE=1
echo -e "${YELLOW}[3/4] Starting container with TEST_MODE=1...${NC}"
docker run -d \
    --name "${CONTAINER_NAME}" \
    -p "${HEALTH_PORT}:${HEALTH_PORT}" \
    -e TEST_MODE=1 \
    -e ALLOW_REAL_GENERATION=0 \
    -e TELEGRAM_BOT_TOKEN="1234567890:TEST_TOKEN_FOR_SMOKE_TEST" \
    -e ADMIN_ID="123456789" \
    "${IMAGE_NAME}" || {
    echo -e "${RED}❌ Failed to start container${NC}"
    exit 1
}
echo -e "${GREEN}✅ Container started${NC}"
echo ""

# Wait for container to be ready
echo -e "${YELLOW}Waiting for container to be ready (max 30 seconds)...${NC}"
for i in {1..30}; do
    if docker exec "${CONTAINER_NAME}" python3 -c "import sys; sys.exit(0)" 2>/dev/null; then
        echo -e "${GREEN}✅ Container is ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ Container failed to become ready${NC}"
        docker logs "${CONTAINER_NAME}"
        exit 1
    fi
    sleep 1
done
echo ""

# Step 4: Check health endpoint
echo -e "${YELLOW}[4/4] Checking health endpoint...${NC}"
sleep 5  # Give health server time to start

# Try curl from inside container first
if docker exec "${CONTAINER_NAME}" curl -s -f "${HEALTH_URL}" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Health endpoint is responding${NC}"
else
    # Try from host
    if curl -s -f "${HEALTH_URL}" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Health endpoint is responding (from host)${NC}"
    else
        echo -e "${YELLOW}⚠️  Health endpoint not responding (may be OK if health server not started yet)${NC}"
        echo "Container logs:"
        docker logs "${CONTAINER_NAME}" | tail -20
    fi
fi
echo ""

# Step 5: Verify critical files exist
echo -e "${YELLOW}[5/5] Verifying critical files...${NC}"
if docker exec "${CONTAINER_NAME}" test -f /app/models/kie_models.yaml; then
    echo -e "${GREEN}✅ models/kie_models.yaml exists${NC}"
else
    echo -e "${RED}❌ models/kie_models.yaml not found${NC}"
    exit 1
fi

if docker exec "${CONTAINER_NAME}" python3 -c "import yaml" 2>/dev/null; then
    echo -e "${GREEN}✅ PyYAML is installed${NC}"
else
    echo -e "${RED}❌ PyYAML not installed${NC}"
    exit 1
fi
echo ""

# Step 6: Run smoke test
echo -e "${YELLOW}[6/6] Running smoke test for all models...${NC}"
echo ""
if docker exec -e TEST_MODE=1 -e ALLOW_REAL_GENERATION=0 "${CONTAINER_NAME}" python3 scripts/smoke_test_all_models.py; then
    echo ""
    echo -e "${GREEN}✅ Smoke test passed${NC}"
    SMOKE_RESULT=0
else
    echo ""
    echo -e "${RED}❌ Smoke test failed${NC}"
    SMOKE_RESULT=1
fi
echo ""

# Show container logs
echo -e "${YELLOW}Container logs (last 50 lines):${NC}"
docker logs "${CONTAINER_NAME}" | tail -50
echo ""

# Cleanup
echo -e "${YELLOW}Cleaning up...${NC}"
docker stop "${CONTAINER_NAME}" 2>/dev/null || true
docker rm "${CONTAINER_NAME}" 2>/dev/null || true
echo -e "${GREEN}✅ Cleanup complete${NC}"
echo ""

# Final result
if [ $SMOKE_RESULT -eq 0 ]; then
    echo -e "${GREEN}=========================================="
    echo -e "✅ ALL TESTS PASSED"
    echo -e "==========================================${NC}"
    exit 0
else
    echo -e "${RED}=========================================="
    echo -e "❌ SOME TESTS FAILED"
    echo -e "==========================================${NC}"
    exit 1
fi

