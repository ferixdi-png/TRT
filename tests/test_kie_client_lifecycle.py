from unittest.mock import AsyncMock

import pytest

from app.bootstrap import create_application
from app.config import Settings


@pytest.mark.asyncio
async def test_kie_client_closed_on_shutdown(monkeypatch, test_env):
    close_called = AsyncMock()

    class DummyClient:
        def __init__(self):
            self.api_key = "test"
            self.base_url = "https://api.kie.ai"

        async def close(self):
            await close_called()

    monkeypatch.setattr("app.kie.kie_client.get_kie_client", lambda: DummyClient())

    settings = Settings(validate=False)
    app = await create_application(settings)
    await app.initialize()
    await app.shutdown()

    close_called.assert_awaited()
