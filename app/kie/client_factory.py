"""Factory helpers for the KIE client."""
from __future__ import annotations

from app.kie.kie_client import get_kie_client, KIEClient


def build_client() -> KIEClient:
    return get_kie_client()
