# Production Dockerfile for Render
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (essential + OCR support)
RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    tesseract-ocr \
    tesseract-ocr-rus \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements first for better caching
COPY requirements.txt ./

# Upgrade pip and install Python dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# Copy all application files (using .dockerignore to exclude unnecessary files)
COPY . /app

# Create directories with empty __init__.py files if they don't exist
# Code has try/except for imports, so it will work without these modules
RUN mkdir -p ./bot_kie_services ./bot_kie_utils && \
    (test -f ./bot_kie_services/__init__.py || echo '"""Empty - modules not available in build context"""' > ./bot_kie_services/__init__.py) && \
    (test -f ./bot_kie_utils/__init__.py || echo '"""Empty - modules not available in build context"""' > ./bot_kie_utils/__init__.py)

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=10000
ENV DATA_DIR=/app/data
ENV PYTHONPATH=/app

# Create data directory for persistent storage
RUN mkdir -p /app/data && chmod 755 /app/data

# Expose port for health check
EXPOSE 10000

# Health check for Render.com (using Python instead of Node.js)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:10000/health').read()" || exit 1

# Verify critical files exist
RUN test -f /app/models/kie_models.yaml || (echo "ERROR: models/kie_models.yaml not found!" && exit 1) && \
    python3 -c "import yaml" || (echo "ERROR: PyYAML not installed!" && exit 1) && \
    test -f /app/app/config.py || (echo "ERROR: app/config.py not found!" && exit 1) && \
    python3 -c "from app.config import get_settings, Settings; print('✅ app.config import OK')" || (echo "ERROR: app.config import failed!" && exit 1) && \
    echo "✅ Critical files verified"

# Start the bot using Render-first entrypoint
CMD ["python3", "main_render.py"]
