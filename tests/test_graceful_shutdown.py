import asyncio
import logging

import pytest

from entrypoints import run_bot as run_bot_entrypoint


class _DummyStorage:
    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None


async def test_entrypoint_main_cancelled_is_graceful(monkeypatch, caplog, test_env, tmp_path):
    monkeypatch.setenv("STORAGE_MODE", "github")
    monkeypatch.setenv("GITHUB_STORAGE_STUB", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "stub-token")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("RUNTIME_STORAGE_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("BILLING_PREFLIGHT_STRICT", "0")

    import app.storage
    import app.diagnostics.billing_preflight as billing_preflight

    monkeypatch.setattr(app.storage, "get_storage", lambda: _DummyStorage())

    async def fake_run_billing_preflight(storage, db_pool=None):
        return {"result": "PASS"}

    monkeypatch.setattr(billing_preflight, "run_billing_preflight", fake_run_billing_preflight)
    monkeypatch.setattr(billing_preflight, "format_billing_preflight_report", lambda report: "ok")

    async def fake_start_healthcheck(port: int) -> bool:
        return False

    async def fake_stop_healthcheck(started: bool) -> None:
        return None

    monkeypatch.setattr(run_bot_entrypoint, "start_healthcheck", fake_start_healthcheck)
    monkeypatch.setattr(run_bot_entrypoint, "stop_healthcheck", fake_stop_healthcheck)

    started = asyncio.Event()

    async def fake_run_bot() -> None:
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(run_bot_entrypoint, "run_bot", fake_run_bot)

    caplog.set_level(logging.INFO)

    task = asyncio.create_task(run_bot_entrypoint.main())
    await started.wait()
    await asyncio.sleep(0)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pytest.fail("entrypoint main leaked CancelledError")
    except Exception as exc:
        pytest.fail(f"entrypoint main raised unexpected exception: {exc}")

    assert "Fatal error in entrypoint" not in caplog.text
