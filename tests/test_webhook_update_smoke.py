import pytest


@pytest.mark.asyncio
async def test_webhook_update_smoke(webhook_harness):
    response = await webhook_harness.send_message(
        user_id=999,
        text="/start",
        update_id=901,
    )

    assert response.status == 200
    assert webhook_harness.outbox.messages, "Webhook should produce a response message"
