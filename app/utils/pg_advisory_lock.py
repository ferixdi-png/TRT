from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional, Tuple

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


def log_advisory_lock_key(
    logger: object,
    lock_key: AdvisoryLockKeyPair,
    *,
    correlation_id: Optional[str] = None,
    action: str = "pg_advisory_lock",
) -> None:
    if not hasattr(logger, "info"):
        return
    correlation = correlation_id or "corr-na"
    logger.info(
        "ADVISORY_LOCK_KEY action=%s lock_key_source=%s lock_key_raw=%s lock_key_hash=%s "
        "lock_key_pair_a=%s lock_key_pair_b=%s correlation_id=%s",
        action,
        lock_key.source,
        lock_key.payload,
        lock_key.hash_hex,
        lock_key.key_a,
        lock_key.key_b,
        correlation,
    )


async def acquire_advisory_xact_lock(conn: object, lock_key: AdvisoryLockKeyPair) -> None:
    """Acquire pg_advisory_xact_lock(int4,int4) for a given key pair."""
    await conn.execute("SELECT pg_advisory_xact_lock($1, $2)", lock_key.key_a, lock_key.key_b)
