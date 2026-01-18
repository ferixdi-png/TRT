"""Runtime mode helpers."""
from __future__ import annotations

import os


def get_runtime_mode() -> str:
    return os.getenv("BOT_MODE", "auto").lower()


def is_bot_mode() -> bool:
    return get_runtime_mode() in {"bot", "auto"}


def is_worker_mode() -> bool:
    return get_runtime_mode() == "worker"


def is_web_mode() -> bool:
    return get_runtime_mode() == "web"
