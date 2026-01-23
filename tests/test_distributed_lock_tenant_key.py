from __future__ import annotations

import os

from app.utils.distributed_lock import build_tenant_lock_key


def test_tenant_lock_key_prefers_partner_id(monkeypatch) -> None:
    monkeypatch.delenv("BOT_INSTANCE_ID", raising=False)
    monkeypatch.setenv("PARTNER_ID", "partner-42")

    assert build_tenant_lock_key("balance:1").startswith("tenant:partner-42:")


def test_tenant_lock_key_uses_bot_instance_id(monkeypatch) -> None:
    monkeypatch.setenv("BOT_INSTANCE_ID", "bot-01")
    monkeypatch.setenv("PARTNER_ID", "partner-42")

    assert build_tenant_lock_key("balance:1").startswith("tenant:bot-01:")
