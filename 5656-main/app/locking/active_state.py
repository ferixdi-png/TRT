"""Active state tracking for single instance mode."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ActiveState:
    active: bool = False
    lock_controller: object | None = None
