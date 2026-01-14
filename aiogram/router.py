"""Minimal Router stub used in tests."""

from __future__ import annotations

from typing import Callable


class Router:
    def __init__(self, name: str | None = None):
        self.name = name

    def message(self, *args, **kwargs):
        def decorator(func: Callable):
            return func
        return decorator

    def callback_query(self, *args, **kwargs):
        def decorator(func: Callable):
            return func
        return decorator

    def error(self, *args, **kwargs):
        def decorator(func: Callable):
            return func
        return decorator
