"""Early update buffer for webhook startup gating."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from app.utils.distributed_lock import build_tenant_lock_key, get_redis_client


@dataclass(frozen=True)
class EarlyUpdateItem:
    update_id: int
    payload: Dict[str, Any]
    correlation_id: str
    received_ts: float


class EarlyUpdateBuffer:
    def __init__(
        self,
        ttl_seconds: float,
        max_size: int,
        *,
        time_fn: Callable[[], float] | None = None,
        redis_client_provider: Callable[[], Awaitable[Optional[Any]]] | None = None,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._time_fn = time_fn or time.monotonic
        self._memory: Dict[int, EarlyUpdateItem] = {}
        self._redis_client_provider = redis_client_provider or get_redis_client
        self._order_key = build_tenant_lock_key("webhook:early_updates:order")
        self._payload_key = build_tenant_lock_key("webhook:early_updates:payload")

    def _cleanup_memory(self, now: float) -> None:
        expired = [key for key, item in self._memory.items() if now - item.received_ts > self.ttl_seconds]
        for key in expired:
            self._memory.pop(key, None)

    def _trim_memory(self) -> List[int]:
        if len(self._memory) <= self.max_size:
            return []
        to_remove = len(self._memory) - self.max_size
        oldest = sorted(self._memory.values(), key=lambda item: (item.received_ts, item.update_id))
        removed_ids = [item.update_id for item in oldest[:to_remove]]
        for update_id in removed_ids:
            self._memory.pop(update_id, None)
        return removed_ids

    async def add(
        self,
        update_id: int,
        payload: Dict[str, Any],
        *,
        correlation_id: str,
    ) -> Tuple[bool, int]:
        now = self._time_fn()
        self._cleanup_memory(now)
        if update_id in self._memory:
            return False, len(self._memory)
        self._memory[update_id] = EarlyUpdateItem(
            update_id=update_id,
            payload=payload,
            correlation_id=correlation_id,
            received_ts=now,
        )
        self._trim_memory()
        await self._sync_redis(update_id, payload, correlation_id)
        return True, len(self._memory)

    async def _sync_redis(
        self,
        update_id: int,
        payload: Dict[str, Any],
        correlation_id: str,
    ) -> None:
        redis_client = await self._redis_client_provider()
        if not redis_client:
            return
        payload_value = json.dumps(
            {
                "update_id": update_id,
                "payload": payload,
                "correlation_id": correlation_id,
                "received_ts": self._time_fn(),
            },
            ensure_ascii=False,
            default=str,
        )
        try:
            added = await redis_client.zadd(self._order_key, {str(update_id): float(update_id)}, nx=True)
            if added:
                await redis_client.hset(self._payload_key, mapping={str(update_id): payload_value})
            await redis_client.expire(self._order_key, int(self.ttl_seconds))
            await redis_client.expire(self._payload_key, int(self.ttl_seconds))
            await self._trim_redis(redis_client)
        except Exception:
            # Redis is optional; ignore failures.
            return

    async def _trim_redis(self, redis_client: Any) -> None:
        try:
            count = await redis_client.zcard(self._order_key)
            if count <= self.max_size:
                return
            excess = count - self.max_size
            old_ids = await redis_client.zrange(self._order_key, 0, excess - 1)
            if not old_ids:
                return
            await redis_client.zrem(self._order_key, *old_ids)
            await redis_client.hdel(self._payload_key, *old_ids)
        except Exception:
            return

    async def drain(self) -> List[EarlyUpdateItem]:
        now = self._time_fn()
        self._cleanup_memory(now)
        redis_items = await self._read_redis_items()
        seen_ids = {item.update_id for item in redis_items}
        memory_items = [item for item in self._memory.values() if item.update_id not in seen_ids]
        self._memory.clear()
        items = sorted(redis_items + memory_items, key=lambda item: item.update_id)
        return items

    async def _read_redis_items(self) -> List[EarlyUpdateItem]:
        redis_client = await self._redis_client_provider()
        if not redis_client:
            return []
        try:
            update_ids = await redis_client.zrange(self._order_key, 0, -1)
            if not update_ids:
                return []
            payloads = await redis_client.hmget(self._payload_key, update_ids)
            items = []
            for update_id_raw, payload_raw in zip(update_ids, payloads):
                if not payload_raw:
                    continue
                try:
                    data = json.loads(payload_raw)
                except Exception:
                    continue
                update_id_val = data.get("update_id") or update_id_raw
                try:
                    update_id_int = int(update_id_val)
                except Exception:
                    continue
                payload = data.get("payload")
                if not isinstance(payload, dict):
                    continue
                items.append(
                    EarlyUpdateItem(
                        update_id=update_id_int,
                        payload=payload,
                        correlation_id=str(data.get("correlation_id") or ""),
                        received_ts=float(data.get("received_ts") or 0.0),
                    )
                )
            await redis_client.delete(self._order_key, self._payload_key)
            return items
        except Exception:
            return []
