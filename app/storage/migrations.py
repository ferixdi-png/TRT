"""Storage migration utilities."""
from __future__ import annotations

from typing import Iterable, List


def list_migrations() -> List[str]:
    return []


def run_migrations(migrations: Iterable[str]) -> List[str]:
    return list(migrations)
