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
    request_id: Optional[str] = None
    media_type: Optional[str] = None
    result_urls: Optional[list[str]] = None
    result_text: Optional[str] = None
    updated_ts: float = 0.0
    recovery_attempts: int = 0
    last_recovery_ts: float = 0.0
    orphan_notified_ts: float = 0.0


_memory_entries: Dict[str, tuple[DedupeEntry, float]] = {}
_memory_job_tasks: Dict[str, tuple[dict[str, Any], float]] = {}
_memory_request_map: Dict[str, tuple[dict[str, Any], float]] = {}


def _build_key(user_id: int, model_id: str, prompt_hash: str) -> str:
    raw_key = f"gen_dedupe:{user_id}:{model_id}:{prompt_hash}"
    return build_tenant_lock_key(raw_key)


def _build_job_task_key(job_id: str) -> str:
    raw_key = f"gen_job_task:{job_id}"
    return build_tenant_lock_key(raw_key)


def _build_request_key(request_id: str) -> str:
    raw_key = f"gen_request:{request_id}"
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
        request_id=data.get("request_id"),
        media_type=data.get("media_type"),
        result_urls=data.get("result_urls"),
        result_text=data.get("result_text"),
        updated_ts=float(data.get("updated_ts") or 0.0),
        recovery_attempts=int(data.get("recovery_attempts") or 0),
        last_recovery_ts=float(data.get("last_recovery_ts") or 0.0),
        orphan_notified_ts=float(data.get("orphan_notified_ts") or 0.0),
    )


def _deserialize_request_mapping(raw: str) -> Optional[dict[str, Any]]:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    user_id = data.get("user_id")
    model_id = data.get("model_id")
    prompt_hash = data.get("prompt_hash")
    if user_id is None or not model_id or not prompt_hash:
        return None
    return {
        "user_id": int(user_id),
        "model_id": str(model_id),
        "prompt_hash": str(prompt_hash),
        "updated_ts": float(data.get("updated_ts") or 0.0),
    }


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


async def get_request_mapping(request_id: Optional[str]) -> Optional[dict[str, Any]]:
    if not request_id:
        return None
    key = _build_request_key(request_id)
    redis_client = await get_redis_client()
    if redis_client:
        raw = await redis_client.get(key)
        return _deserialize_request_mapping(raw) if raw else None
    entry = _memory_request_map.get(key)
    if not entry:
        return None
    payload, expires_at = entry
    if time.monotonic() > expires_at:
        _memory_request_map.pop(key, None)
        return None
    return dict(payload)


async def get_dedupe_entry_by_request_id(
    request_id: Optional[str],
    *,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> Optional[DedupeEntry]:
    mapping = await get_request_mapping(request_id)
    if not mapping:
        return None
    return await get_dedupe_entry(
        mapping["user_id"],
        mapping["model_id"],
        mapping["prompt_hash"],
        ttl_seconds=ttl_seconds,
    )


async def set_request_mapping(
    request_id: Optional[str],
    user_id: int,
    model_id: str,
    prompt_hash: str,
    *,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> None:
    if not request_id:
        return
    key = _build_request_key(request_id)
    payload = {
        "user_id": int(user_id),
        "model_id": str(model_id),
        "prompt_hash": str(prompt_hash),
        "updated_ts": time.time(),
    }
    redis_client = await get_redis_client()
    if redis_client:
        await redis_client.set(key, json.dumps(payload, ensure_ascii=False), ex=ttl_seconds)
        return
    _memory_request_map[key] = (payload, time.monotonic() + ttl_seconds)


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
    else:
        _memory_entries[key] = (entry, time.monotonic() + ttl_seconds)
    if entry.request_id:
        await set_request_mapping(entry.request_id, entry.user_id, entry.model_id, entry.prompt_hash, ttl_seconds=ttl_seconds)
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
            request_id=updates.get("request_id"),
        )
    for field, value in updates.items():
        if hasattr(entry, field):
            setattr(entry, field, value)
    return await set_dedupe_entry(entry, ttl_seconds=ttl_seconds)


async def delete_dedupe_entry(user_id: int, model_id: str, prompt_hash: str) -> None:
    key = _build_key(user_id, model_id, prompt_hash)
    redis_client = await get_redis_client()
    if redis_client:
        await redis_client.delete(key)
        return
    _memory_entries.pop(key, None)


async def list_dedupe_entries(*, limit: int = 500) -> list[DedupeEntry]:
    redis_client = await get_redis_client()
    entries: list[DedupeEntry] = []
    if redis_client:
        match_pattern = build_tenant_lock_key("gen_dedupe:*")
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(cursor=cursor, match=match_pattern, count=200)
            for key in keys:
                raw = await redis_client.get(key)
                entry = _deserialize(raw) if raw else None
                if entry:
                    entries.append(entry)
                if len(entries) >= limit:
                    return entries
            if cursor == 0:
                break
        return entries
    now = time.monotonic()
    for key, (entry, expires_at) in list(_memory_entries.items()):
        if now > expires_at:
            _memory_entries.pop(key, None)
            continue
        entries.append(entry)
        if len(entries) >= limit:
            break
    return entries


async def set_job_task_mapping(
    job_id: str,
    task_id: Optional[str],
    *,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> None:
    payload = {"job_id": job_id, "task_id": task_id, "updated_ts": time.time()}
    key = _build_job_task_key(job_id)
    redis_client = await get_redis_client()
    if redis_client:
        await redis_client.set(key, json.dumps(payload, ensure_ascii=False), ex=ttl_seconds)
        return
    _memory_job_tasks[key] = (payload, time.monotonic() + ttl_seconds)


async def get_task_id_for_job(job_id: Optional[str]) -> Optional[str]:
    if not job_id:
        return None
    key = _build_job_task_key(job_id)
    redis_client = await get_redis_client()
    if redis_client:
        raw = await redis_client.get(key)
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except Exception:
            return None
        return data.get("task_id")
    entry = _memory_job_tasks.get(key)
    if not entry:
        return None
    payload, expires_at = entry
    if time.monotonic() > expires_at:
        _memory_job_tasks.pop(key, None)
        return None
    return payload.get("task_id")


async def delete_job_task_mapping(job_id: Optional[str]) -> None:
    if not job_id:
        return
    key = _build_job_task_key(job_id)
    redis_client = await get_redis_client()
    if redis_client:
        await redis_client.delete(key)
        return
    _memory_job_tasks.pop(key, None)


def reset_memory_entries() -> None:
    _memory_entries.clear()
    _memory_job_tasks.clear()
    _memory_request_map.clear()
