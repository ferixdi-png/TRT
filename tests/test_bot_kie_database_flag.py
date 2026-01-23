from __future__ import annotations

import bot_kie


def test_bot_kie_exposes_database_available_flag() -> None:
    assert hasattr(bot_kie, "DATABASE_AVAILABLE")
