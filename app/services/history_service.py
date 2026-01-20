"""History events service with idempotent append and aggregates."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.storage.base import BaseStorage

HISTORY_EVENTS_FILE = "history_events.json"
LEGACY_HISTORY_FILE = "generations_history.json"


@dataclass(frozen=True)
class HistoryEvent:
    event_id: str
    user_id: int
    kind: str
    payload: Dict[str, Any]
    created_at: str


async def append_event(
    storage: BaseStorage,
    user_id: int,
    kind: str,
    payload: Dict[str, Any],
    event_id: str,
) -> bool:
    if not event_id:
        raise ValueError("event_id is required")

    def updater(data: Dict[str, Any]) -> Dict[str, Any]:
        updated = dict(data)
        user_key = str(user_id)
        events = list(updated.get(user_key, []))
        if any(event.get("event_id") == event_id for event in events):
            return updated
        events.append(
            {
                "event_id": event_id,
                "user_id": user_id,
                "kind": kind,
                "payload": payload,
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        updated[user_key] = events
        return updated

    before = await storage.read_json_file(HISTORY_EVENTS_FILE, default={})
    updated = await storage.update_json_file(HISTORY_EVENTS_FILE, updater)
    user_key = str(user_id)
    return len(updated.get(user_key, [])) > len(before.get(user_key, []))


async def get_recent(storage: BaseStorage, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    events = await storage.read_json_file(HISTORY_EVENTS_FILE, default={})
    user_events = list(events.get(str(user_id), []))
    if user_events:
        return user_events[-limit:]
    legacy = await storage.read_json_file(LEGACY_HISTORY_FILE, default={})
    legacy_events = list(legacy.get(str(user_id), []))
    return legacy_events[-limit:]


async def get_aggregates(storage: BaseStorage, user_id: int) -> Dict[str, Any]:
    events = await get_recent(storage, user_id, limit=1000)
    counts: Dict[str, int] = {}
    latest: Optional[Dict[str, Any]] = None
    for event in events:
        kind = event.get("kind") or "legacy"
        counts[kind] = counts.get(kind, 0) + 1
        latest = event
    return {"counts": counts, "latest": latest}
