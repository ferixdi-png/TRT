"""
Telemetry module for structured event logging.
All events include cid (correlation ID) and reason codes.
"""

from app.telemetry.events import (
    log_update_received,
    log_callback_received,
    log_command_received,
    log_callback_routed,
    log_callback_rejected,
    log_callback_accepted,
    log_ui_render,
    log_dispatch_ok,
    generate_cid,
)

__all__ = [
    "log_update_received",
    "log_callback_received",
    "log_command_received",
    "log_callback_routed",
    "log_callback_rejected",
    "log_callback_accepted",
    "log_ui_render",
    "log_dispatch_ok",
    "generate_cid",
]

