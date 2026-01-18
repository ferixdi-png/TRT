"""Startup validation helpers for runtime readiness."""
from __future__ import annotations

import os
from typing import List, Tuple


def validate_required_env(required: List[str]) -> Tuple[bool, List[str]]:
    missing = [key for key in required if not os.getenv(key)]
    return len(missing) == 0, missing


def build_startup_report(required: List[str]) -> str:
    ok, missing = validate_required_env(required)
    if ok:
        return "✅ Startup validation passed"
    return f"❌ Missing required env vars: {', '.join(missing)}"
