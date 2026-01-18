import pytest

from app.bootstrap import create_application


@pytest.mark.asyncio
async def test_error_handler_registered_in_bootstrap(test_env):
    application = await create_application()
    assert application.error_handlers
    await application.shutdown()
