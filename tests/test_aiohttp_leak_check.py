import gc

import pytest

from app.bootstrap import create_application
from app.config import Settings


@pytest.mark.asyncio
async def test_aiohttp_leak_check(capfd, test_env):
    settings = Settings(validate=False)
    app = await create_application(settings)
    await app.initialize()

    deps = app.bot_data["deps"]
    client = deps.get_kie_client()
    if client:
        await client._get_session()

    await app.shutdown()
    gc.collect()
    _, err = capfd.readouterr()
    assert "Unclosed client session" not in err
