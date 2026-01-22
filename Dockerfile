# Используем Python образ вместо Node.js
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

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=10000
ENV DATA_DIR=/app/data
ENV PYTHONPATH=/app

# Create data directory for persistent storage
RUN mkdir -p /app/data && chmod 755 /app/data

# Expose port for health check
EXPOSE 10000

# Start the bot using canonical entrypoint (Render-first startup)
CMD ["python3", "entrypoints/run_bot.py"]
