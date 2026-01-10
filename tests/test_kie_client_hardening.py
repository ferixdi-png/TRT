"""Tests for KIE client hardening with mocked network calls."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from kie_client import KIEClient


class _FailingSession:
    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        raise asyncio.TimeoutError()

    async def get(self, *args, **kwargs):
        raise asyncio.TimeoutError()


@pytest.mark.asyncio
async def test_create_task_timeout_returns_friendly_error(monkeypatch):
    monkeypatch.setenv("KIE_API_KEY", "test-key")
    monkeypatch.setenv("KIE_RETRY_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("KIE_RETRY_BASE_DELAY", "0")
    monkeypatch.setattr("aiohttp.ClientSession", _FailingSession)

    client = KIEClient()
    result = await client.create_task("test-model", {"prompt": "hi"})

    assert result["ok"] is False
    assert "Попробуйте позже" in result["error"]


@pytest.mark.asyncio
async def test_get_task_status_timeout_returns_friendly_error(monkeypatch):
    monkeypatch.setenv("KIE_API_KEY", "test-key")
    monkeypatch.setenv("KIE_RETRY_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("KIE_RETRY_BASE_DELAY", "0")
    monkeypatch.setattr("aiohttp.ClientSession", _FailingSession)

    client = KIEClient()
    result = await client.get_task_status("task-123")

    assert result["ok"] is False
    assert "Попробуйте позже" in result["error"]
