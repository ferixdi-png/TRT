#!/usr/bin/env python3
"""
Smoke test for GitHub storage.
Starts main_render.py in SMOKE_MODE, checks health, writes balance/payment,
restarts, then verifies persistence via GitHub storage.
"""

import asyncio
import os
import signal
import subprocess
import sys
import time
from typing import Dict, Any, Optional

import requests


REQUIRED_ENV = [
    "GITHUB_TOKEN",
    "GITHUB_REPO",
    "GITHUB_BRANCH",
    "BOT_INSTANCE_ID",
    "STORAGE_PREFIX",
    "GITHUB_COMMITTER_NAME",
    "GITHUB_COMMITTER_EMAIL",
]


def require_env() -> None:
    missing = [key for key in REQUIRED_ENV if not os.getenv(key)]
    if missing:
        print(
            f"[SMOKE] missing_required_envs={','.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(2)


def wait_for_health(url: str, timeout_s: int = 30) -> None:
    deadline = time.time() + timeout_s
    last_err: str = ""
    while time.time() < deadline:
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                return
            last_err = f"status={resp.status_code}"
        except Exception as exc:
            last_err = str(exc)
        time.sleep(1)
    raise TimeoutError(f"Healthcheck not ready: {last_err}")


def start_main(env: Dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "main_render.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def stop_main(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


async def write_and_read_storage(user_id: int, payment_amount: float) -> Dict[str, Any]:
    from app.storage import get_storage
    from app.storage.factory import reset_storage

    reset_storage()
    storage = get_storage()
    connection_ok = await asyncio.to_thread(storage.test_connection)
    if not connection_ok:
        raise RuntimeError("GitHub storage test_connection failed")

    smoke_payload = {"smoke": True, "ts": time.time()}
    await storage._update_json("smoke.json", lambda data: {**data, **smoke_payload})
    smoke_data, _ = await storage._read_json("smoke.json")
    if not smoke_data.get("smoke"):
        raise RuntimeError("Smoke write/read failed for smoke.json")
    await storage.set_user_balance(user_id, payment_amount)
    await storage.set_user_balance(user_id + 1, payment_amount + 10)
    payment_id = await storage.add_payment(
        user_id=user_id,
        amount=payment_amount,
        payment_method="smoke",
        status="approved",
    )
    balances, _ = await storage._read_json(storage.balances_file)
    if str(user_id) not in balances or str(user_id + 1) not in balances:
        raise RuntimeError("Merge check failed: missing balance keys after write")

    from app.storage.github_storage import GitHubConflictError

    conflict_triggered = {"value": False}
    original_write = storage._write_json

    async def flaky_write(filename: str, data: Dict[str, Any], sha: Optional[str]) -> None:
        if not conflict_triggered["value"]:
            conflict_triggered["value"] = True
            raise GitHubConflictError("forced conflict for smoke test")
        await original_write(filename, data, sha)

    storage._write_json = flaky_write
    try:
        await storage._update_json(
            "smoke.json",
            lambda data: {**data, "conflict": True},
        )
    finally:
        storage._write_json = original_write

    if not conflict_triggered["value"]:
        raise RuntimeError("Conflict simulation did not trigger")

    return {"payment_id": payment_id, "balance_after_conflict": payment_amount + 1}


async def verify_storage(user_id: int, payment_id: str) -> Dict[str, Any]:
    from app.storage import get_storage
    from app.storage.factory import reset_storage

    reset_storage()
    storage = get_storage()
    balance = await storage.get_user_balance(user_id)
    payment = await storage.get_payment(payment_id)
    smoke_data, _ = await storage._read_json("smoke.json")
    return {"balance": balance, "payment": payment, "smoke": smoke_data}


def main() -> None:
    require_env()
    port = int(os.getenv("SMOKE_PORT", "8099"))
    env = os.environ.copy()
    env.update(
        {
            "STORAGE_MODE": "github",
            "SMOKE_MODE": "1",
            "PORT": str(port),
            "TELEGRAM_BOT_TOKEN": env.get("TELEGRAM_BOT_TOKEN", "smoke-token"),
            "BOT_MODE": "polling",
            "DATABASE_URL": "",
        }
    )

    health_url = f"http://127.0.0.1:{port}/health"
    proc = start_main(env)
    try:
        wait_for_health(health_url, timeout_s=40)
        user_id = 999001
        payment_amount = 123.45
        write_result = asyncio.run(write_and_read_storage(user_id, payment_amount))
    finally:
        stop_main(proc)

    proc = start_main(env)
    try:
        wait_for_health(health_url, timeout_s=40)
        read_result = asyncio.run(verify_storage(user_id, write_result["payment_id"]))
    finally:
        stop_main(proc)

    if abs(read_result["balance"] - write_result["balance_after_conflict"]) > 0.001:
        raise RuntimeError(
            f"Balance mismatch: {read_result['balance']} vs {write_result['balance_after_conflict']}"
        )
    if not read_result["payment"]:
        raise RuntimeError("Payment record missing after restart")
    if not read_result["smoke"].get("smoke"):
        raise RuntimeError("smoke.json missing after restart")

    print("Smoke test passed: GitHub storage persisted balance/payment with conflict retry.")


if __name__ == "__main__":
    main()
