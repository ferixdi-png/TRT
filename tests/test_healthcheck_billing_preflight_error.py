from __future__ import annotations

import pytest
from aiohttp.test_utils import make_mocked_request

from app.utils.healthcheck import billing_preflight_handler


@pytest.mark.asyncio
async def test_billing_preflight_handler_handles_storage_failure(monkeypatch) -> None:
    def _raise_storage() -> None:
        raise RuntimeError("storage boom")

    monkeypatch.setattr("app.storage.factory.get_storage", _raise_storage)

    request = make_mocked_request("GET", "/__diag/billing_preflight")
    response = await billing_preflight_handler(request)

    assert response.status == 503
    assert b"billing_preflight_failed" in response.body
