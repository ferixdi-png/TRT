import asyncio

import pytest

import bot_kie
from app.observability import correlation_store


@pytest.mark.asyncio
async def test_boot_warmup_skips_correlation_store_persist(monkeypatch, tmp_path):
    calls = []

    class FakeStorage:
        async def update_json_file(self, filename, update_fn):  # pragma: no cover - should not be called
            calls.append(filename)
            raise AssertionError("correlation store should not persist during BOOT warmup")

    monkeypatch.setattr(correlation_store, "_resolve_storage", lambda storage=None: FakeStorage())
    monkeypatch.setattr(
        bot_kie,
        "GEN_TYPE_MENU_WARMUP_CACHE_PATH",
        str(tmp_path / "gen_type_menu_warmup.json"),
    )

    async def warmup_fn():
        await asyncio.sleep(0)
        return {"text-to-image": {"count": 0, "cache": "hit"}}

    await bot_kie.warm_generation_type_menu_cache(timeout_s=0.5, warmup_fn=warmup_fn)

    assert calls == []
