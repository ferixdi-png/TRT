"""Canonical generation state machine helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


CANONICAL_STATES = (
    "create_start",
    "task_created",
    "queued",
    "waiting",
    "success",
    "result_validated",
    "tg_deliver",
)


CANONICAL_PENDING_STATES = {
    "pending",
    "queued",
    "waiting",
    "success",
    "result_validated",
    "delivery_pending",
    "tg_deliver",
    "timeout",
}


CANONICAL_SUCCESS_STATES = {"success", "result_validated", "delivered"}


CANONICAL_FAILED_STATES = {
    "failed",
    "fail",
    "error",
    "canceled",
    "cancelled",
    "timeout",
}


LEGACY_SUCCESS_STATES = {"success", "completed", "succeeded"}
LEGACY_FAILED_STATES = {"failed", "fail", "error", "canceled", "cancelled", "canceled"}


@dataclass(frozen=True)
class StateResolution:
    raw_state: str
    canonical_state: str


def normalize_provider_state(raw_state: Optional[str]) -> StateResolution:
    """Normalize provider-specific state into canonical state-machine states."""
    if not raw_state:
        return StateResolution(raw_state="", canonical_state="waiting")

    lowered = str(raw_state).strip().lower()
    if lowered in {"create_start", "task_created", "queued", "waiting", "success", "result_validated", "tg_deliver"}:
        return StateResolution(raw_state=lowered, canonical_state=lowered)

    if lowered in LEGACY_SUCCESS_STATES:
        return StateResolution(raw_state=lowered, canonical_state="success")
    if lowered in LEGACY_FAILED_STATES:
        return StateResolution(raw_state=lowered, canonical_state="failed")
    if lowered in {"cancel", "cancelled", "canceled"}:
        return StateResolution(raw_state=lowered, canonical_state="canceled")

    if lowered in {"pending", "queued", "queuing"}:
        return StateResolution(raw_state=lowered, canonical_state="queued")

    # Provider may report both "waiting" and "running/processing/generating"
    if lowered in {"waiting", "processing", "running", "generating", "in_progress"}:
        return StateResolution(raw_state=lowered, canonical_state="waiting")

    return StateResolution(raw_state=lowered, canonical_state="waiting")
