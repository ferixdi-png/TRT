"""
Configuration for Kie sync module.
"""

import os
from pathlib import Path
from typing import Optional

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Paths
CACHE_DIR = PROJECT_ROOT / "cache" / "kie_pages"
GENERATED_DIR = PROJECT_ROOT / "generated"
SOURCE_OF_TRUTH_PATH = PROJECT_ROOT / "models" / "KIE_SOURCE_OF_TRUTH.json"
UPSTREAM_JSON_PATH = GENERATED_DIR / "kie_upstream.json"

# Ensure directories exist
CACHE_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

# Pricing constants (from app/payments/pricing.py)
USD_TO_RUB = float(os.getenv("USD_RUB_RATE", "78.0"))  # Can be overridden by ENV
MARKUP_MULTIPLIER = 2.0  # Fixed, never changes

# Network settings
RATE_LIMIT_RPS = 1.0  # Requests per second
REQUEST_TIMEOUT = 15.0  # seconds
MAX_RETRIES = 2

# Sources
DOCS_INDEX_URL = "https://docs.kie.ai/llms.txt"
DOCS_BASE_URL = "https://docs.kie.ai"
API_BASE_URL = "https://api.kie.ai"

# Standard endpoints (fixed)
STANDARD_CREATE_ENDPOINT = "/api/v1/jobs/createTask"
STANDARD_RECORD_ENDPOINT = "/api/v1/jobs/recordInfo"

# Seed pages (manual list, if needed)
SEED_PAGES: list[str] = [
    # Add manual seed pages here if needed
]

