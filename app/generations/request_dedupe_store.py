"""Redis-backed (or in-memory) dedupe store for generation requests."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

from app.utils.distributed_lock import build_tenant_lock_key, get_redis_client


_DEFAULT_TTL_SECONDS = int(os.getenv("GEN_DEDUPE_TTL_SECONDS", "3600"))


@dataclass
class DedupeEntry:
    user_id: int
    model_id: str
    prompt_hash: str
    job_id: Optional[str]
    task_id: Optional[str]
    status: str
    media_type: Optional[str] = None
    result_urls: Optional[list[str]] = None
    result_text: Optional[str] = None
    updated_ts: float = 0.0


_memory_entries: Dict[str, tuple[DedupeEntry, float]] = {}


def _build_key(user_id: int, model_id: str, prompt_hash: str) -> str:
    raw_key = f"gen_dedupe:{user_id}:{model_id}:{prompt_hash}"
    return build_tenant_lock_key(raw_key)


def _serialize(entry: DedupeEntry) -> str:
    payload = asdict(entry)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _deserialize(raw: str) -> Optional[DedupeEntry]:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    return DedupeEntry(
        user_id=int(data.get("user_id", 0)),
        model_id=str(data.get("model_id") or ""),
        prompt_hash=str(data.get("prompt_hash") or ""),
        job_id=data.get("job_id"),
        task_id=data.get("task_id"),
        status=str(data.get("status") or "unknown"),
        media_type=data.get("media_type"),
        result_urls=data.get("result_urls"),
        result_text=data.get("result_text"),
        updated_ts=float(data.get("updated_ts") or 0.0),
    )


async def get_dedupe_entry(
    user_id: int,
    model_id: str,
    prompt_hash: str,
    *,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> Optional[DedupeEntry]:
    key = _build_key(user_id, model_id, prompt_hash)
    redis_client = await get_redis_client()
    if redis_client:
        raw = await redis_client.get(key)
        return _deserialize(raw) if raw else None
    entry = _memory_entries.get(key)
    if not entry:
        return None
    stored_entry, expires_at = entry
    if time.monotonic() > expires_at:
        _memory_entries.pop(key, None)
        return None
    return stored_entry


async def set_dedupe_entry(
    entry: DedupeEntry,
    *,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> DedupeEntry:
    entry.updated_ts = time.time()
    key = _build_key(entry.user_id, entry.model_id, entry.prompt_hash)
    redis_client = await get_redis_client()
    if redis_client:
        await redis_client.set(key, _serialize(entry), ex=ttl_seconds)
        return entry
    _memory_entries[key] = (entry, time.monotonic() + ttl_seconds)
    return entry


async def update_dedupe_entry(
    user_id: int,
    model_id: str,
    prompt_hash: str,
    *,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    **updates: Any,
) -> DedupeEntry:
    entry = await get_dedupe_entry(user_id, model_id, prompt_hash, ttl_seconds=ttl_seconds)
    if not entry:
        entry = DedupeEntry(
            user_id=user_id,
            model_id=model_id,
            prompt_hash=prompt_hash,
            job_id=updates.get("job_id"),
            task_id=updates.get("task_id"),
            status=str(updates.get("status") or "unknown"),
        )
    for field, value in updates.items():
        if hasattr(entry, field):
            setattr(entry, field, value)
    return await set_dedupe_entry(entry, ttl_seconds=ttl_seconds)
