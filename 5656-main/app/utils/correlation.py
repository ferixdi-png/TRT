"""Correlation ID helpers."""
from __future__ import annotations

import uuid


def correlation_tag() -> str:
    return f"cid={uuid.uuid4().hex[:10]}"
