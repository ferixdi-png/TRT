"""Telemetry enums."""
from __future__ import annotations

from enum import Enum


class ReasonCode(str, Enum):
    UNKNOWN = "unknown"
    VALID = "valid"
    INVALID = "invalid"
