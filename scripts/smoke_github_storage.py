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
from typing import Dict, Any

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
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")


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
    await storage.set_user_balance(user_id, payment_amount)
    payment_id = await storage.add_payment(
        user_id=user_id,
        amount=payment_amount,
        payment_method="smoke",
        status="approved",
    )
    return {"payment_id": payment_id}


async def verify_storage(user_id: int, payment_id: str) -> Dict[str, Any]:
    from app.storage import get_storage
    from app.storage.factory import reset_storage

    reset_storage()
    storage = get_storage()
    balance = await storage.get_user_balance(user_id)
    payment = await storage.get_payment(payment_id)
    return {"balance": balance, "payment": payment}


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

    if abs(read_result["balance"] - payment_amount) > 0.001:
        raise RuntimeError(f"Balance mismatch: {read_result['balance']} vs {payment_amount}")
    if not read_result["payment"]:
        raise RuntimeError("Payment record missing after restart")

    print("Smoke test passed: GitHub storage persisted balance/payment.")


if __name__ == "__main__":
    main()
