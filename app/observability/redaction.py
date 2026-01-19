"""Utilities for redacting sensitive payloads in logs."""
from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlparse, urlunparse


_SENSITIVE_KEYS = {"token", "authorization", "api_key", "apikey", "secret", "signature"}


def _strip_query(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(query="", fragment=""))


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        if value.startswith("http://") or value.startswith("https://"):
            return _strip_query(value)
        if len(value) > 500:
            return value[:500] + "...<truncated>"
    return value


def redact_payload(payload: Any, *, max_depth: int = 4) -> Any:
    """Return a redacted, size-limited snapshot of payload data."""
    if max_depth <= 0:
        return "<truncated>"
    if isinstance(payload, dict):
        redacted: Dict[str, Any] = {}
        for key, value in payload.items():
            lowered = key.lower()
            if any(token in lowered for token in _SENSITIVE_KEYS):
                redacted[key] = "***"
            else:
                redacted[key] = redact_payload(value, max_depth=max_depth - 1)
        return redacted
    if isinstance(payload, list):
        return [redact_payload(item, max_depth=max_depth - 1) for item in payload[:20]]
    return _redact_value(payload)
