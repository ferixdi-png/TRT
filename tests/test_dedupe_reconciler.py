import time

import pytest

from app.generations import request_dedupe_store
from app.generations.dedupe_reconciler import reconcile_dedupe_orphans
from app.generations.request_dedupe_store import DedupeEntry, get_dedupe_entry, set_dedupe_entry
from app.observability.dedupe_metrics import metrics_snapshot


class DummyBot:
    def __init__(self) -> None:
        self.sent_messages: list[dict] = []

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None):
        self.sent_messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
            }
        )


@pytest.mark.asyncio
async def test_dedupe_reconciler_recovers_task_id_from_resolver(test_env):
    user_id = 7001
    model_id = "sora-2-text-to-video"
    prompt_hash = "dedupe-recover"
    job_id = "job-recover-7001"
    task_id = "task-recover-7001"

    await set_dedupe_entry(
        DedupeEntry(
            user_id=user_id,
            model_id=model_id,
            prompt_hash=prompt_hash,
            job_id=job_id,
            task_id=None,
            status="pending",
        )
    )

    async def resolve_task_id(job_id_value: str):
        assert job_id_value == job_id
        return task_id

    bot = DummyBot()
    await reconcile_dedupe_orphans(
        bot,
        object(),
        resolve_task_id=resolve_task_id,
        get_user_language=lambda _user_id: "ru",
        batch_limit=50,
        orphan_max_age_seconds=60,
        orphan_alert_threshold=1,
    )

    entry = await get_dedupe_entry(user_id, model_id, prompt_hash)
    assert entry and entry.task_id == task_id
    assert entry.status == "running"
    assert bot.sent_messages == []
    assert metrics_snapshot().get("dedupe_orphan_count") == 1


@pytest.mark.asyncio
async def test_dedupe_reconciler_marks_old_orphan_failed_and_notifies(monkeypatch, test_env):
    user_id = 7002
    model_id = "sora-2-text-to-video"
    prompt_hash = "dedupe-orphan-failed"
    job_id = "job-orphan-7002"

    original_time_fn = request_dedupe_store.time.time
    past_ts = time.time() - 3600
    monkeypatch.setattr(request_dedupe_store.time, "time", lambda: past_ts)
    await set_dedupe_entry(
        DedupeEntry(
            user_id=user_id,
            model_id=model_id,
            prompt_hash=prompt_hash,
            job_id=job_id,
            task_id=None,
            status="pending",
        )
    )
    monkeypatch.setattr(request_dedupe_store.time, "time", original_time_fn)

    async def resolve_task_id(_job_id_value: str):
        return None

    bot = DummyBot()
    await reconcile_dedupe_orphans(
        bot,
        object(),
        resolve_task_id=resolve_task_id,
        get_user_language=lambda _user_id: "ru",
        batch_limit=50,
        orphan_max_age_seconds=1,
        orphan_alert_threshold=1,
    )

    entry = await get_dedupe_entry(user_id, model_id, prompt_hash)
    assert entry and entry.status == "failed"
    assert entry.orphan_notified_ts > 0
    assert len(bot.sent_messages) == 1
    buttons = [
        button
        for row in bot.sent_messages[0]["reply_markup"].inline_keyboard
        for button in row
    ]
    assert any(button.callback_data == f"retry_generate:{model_id}" for button in buttons)
    assert metrics_snapshot().get("dedupe_orphan_count") == 1
