import pytest

from app.storage.github_storage import GitHubStorage
from app.storage.json_storage import JsonStorage


@pytest.mark.asyncio
async def test_github_payment_idempotent_credit(monkeypatch):
    monkeypatch.setenv("GITHUB_STORAGE_STUB", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "stub-token")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("BOT_INSTANCE_ID", "partner-01")
    monkeypatch.setenv("STORAGE_BRANCH", "storage")
    monkeypatch.setenv("GITHUB_BRANCH", "main")

    storage = GitHubStorage()
    payment_id = await storage.add_payment(1, 50.0, "sbp", status="pending")

    await storage.mark_payment_status(payment_id, "approved")
    await storage.mark_payment_status(payment_id, "approved")

    balance = await storage.get_user_balance(1)
    assert balance == 50.0

    payment = await storage.get_payment(payment_id)
    assert payment.get("balance_charged") is True


@pytest.mark.asyncio
async def test_json_payment_idempotent_credit(tmp_path):
    storage = JsonStorage(str(tmp_path))
    payment_id = await storage.add_payment(7, 25.0, "manual", status="pending")

    await storage.mark_payment_status(payment_id, "approved")
    await storage.mark_payment_status(payment_id, "approved")

    balance = await storage.get_user_balance(7)
    assert balance == 25.0

    payment = await storage.get_payment(payment_id)
    assert payment.get("balance_charged") is True
