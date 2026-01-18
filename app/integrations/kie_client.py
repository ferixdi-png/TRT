"""Backward-compatible import shim for the KIE client."""

from app.kie.kie_client import KIEClient, get_client, get_kie_client

__all__ = ["KIEClient", "get_client", "get_kie_client"]
