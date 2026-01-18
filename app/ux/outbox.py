"""UX outbox for staged bot responses."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class OutboxMessage:
    text: str
    reply_markup: Optional[Any] = None
    parse_mode: str = "HTML"
    meta: Dict[str, Any] = field(default_factory=dict)


class Outbox:
    """Collects UI messages before sending."""

    def __init__(self) -> None:
        self._messages: List[OutboxMessage] = []

    def add(self, text: str, reply_markup: Optional[Any] = None, **meta: Any) -> None:
        self._messages.append(OutboxMessage(text=text, reply_markup=reply_markup, meta=meta))

    def flush(self) -> List[OutboxMessage]:
        messages = list(self._messages)
        self._messages.clear()
        return messages
