from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Tuple

INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1


@dataclass(frozen=True)
class AdvisoryLockKeyPair:
    key_a: int
    key_b: int
    hash_hex: str
    source: str
    payload: str


def split_int64_to_int32_pair(value: int) -> Tuple[int, int]:
    """Split an unsigned 64-bit int into two signed int32 values."""
    if value < 0 or value >= 2**64:
        raise ValueError("value must be within unsigned 64-bit range")
    data = value.to_bytes(8, "big", signed=False)
    return _split_hash_bytes_to_pair(data)


def _split_hash_bytes_to_pair(data: bytes) -> Tuple[int, int]:
    if len(data) != 8:
        raise ValueError("data must be exactly 8 bytes")
    key_a = int.from_bytes(data[:4], "big", signed=True)
    key_b = int.from_bytes(data[4:], "big", signed=True)
    if not (INT32_MIN <= key_a <= INT32_MAX):
        raise ValueError("key_a outside int32 range")
    if not (INT32_MIN <= key_b <= INT32_MAX):
        raise ValueError("key_b outside int32 range")
    return key_a, key_b


def build_advisory_lock_key_pair(*, source: str, payload: str) -> AdvisoryLockKeyPair:
    """Build a stable advisory lock key pair for Postgres (int4, int4)."""
    digest_full = hashlib.sha256(payload.encode("utf-8")).digest()
    key_a, key_b = _split_hash_bytes_to_pair(digest_full[:8])
    return AdvisoryLockKeyPair(
        key_a=key_a,
        key_b=key_b,
        hash_hex=digest_full.hex(),
        source=source,
        payload=payload,
    )
