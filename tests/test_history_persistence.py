import pytest
from unittest.mock import AsyncMock

import app.payments.charges as charges


@pytest.mark.asyncio
async def test_get_user_history_async_uses_db(monkeypatch):
    class _FakeJobService:
        def __init__(self, db):
            self.db = db
        async def list_user_jobs(self, user_id: int, limit: int = 10):
            return [
                {
                    "id": 10,
                    "kie_task_id": "t-1",
                    "model_id": "z-image",
                    "status": "succeeded",
                    "result_json": {"resultUrls": ["u1"]},
                    "error_text": None,
                    "finished_at": "now",
                }
            ]

    from app import database
    monkeypatch.setattr(database.services, "JobService", _FakeJobService)

    cm = charges.ChargeManager(db_service="db")

    history = await cm.get_user_history_async(123, limit=5)

    assert history
    assert history[0]["model_id"] == "z-image"
    assert history[0]["task_id"] == "t-1"
    assert history[0]["result"] == {"resultUrls": ["u1"]}
