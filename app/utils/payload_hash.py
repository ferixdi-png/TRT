"""Stable payload hashing for log correlation.

We intentionally keep this tiny and dependency-free so it can be used from
hot paths (generation) and tests.

Contract:
- Deterministic for equivalent payloads (sort_keys=True)
- Never raises (falls back to str())
- Short token for log prefixes
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def payload_hash(payload: Any, *, length: int = 12) -> str:
    """Return a short deterministic hash for a payload.

    Args:
        payload: Any JSON-like structure.
        length: Prefix length to return.

    Returns:
        Hex hash prefix (default 12 chars). "-" if payload is None.
    """
    if payload is None:
        return "-"
    try:
        s = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
    except Exception:
        try:
            s = str(payload)
        except Exception:
            return "-"
    h = hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()
    return h[: max(4, int(length))]
