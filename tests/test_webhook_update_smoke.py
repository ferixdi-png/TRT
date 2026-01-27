import asyncio

import pytest


@pytest.mark.asyncio
async def test_webhook_update_smoke(webhook_harness):
    response = await webhook_harness.send_message(
        user_id=999,
        text="/start",
        update_id=901,
    )

    assert response.status == 200
    # Wait for background processing to complete
    for _ in range(20):
        if webhook_harness.outbox.messages or webhook_harness.outbox.edited_messages:
            break
        await asyncio.sleep(0.05)
    all_messages = webhook_harness.outbox.messages + webhook_harness.outbox.edited_messages
    assert all_messages, "Webhook should produce a response message"
