#!/usr/bin/env python3
"""
Smoke test for webhook route.
Starts main_render.py in webhook mode on a local port and verifies /webhook is not 404.
"""

import os
import signal
import subprocess
import sys
import time
from typing import Dict

import requests

REQUIRED_ENV = [
    "GITHUB_TOKEN",
    "GITHUB_REPO",
    "GITHUB_BRANCH",
    "BOT_INSTANCE_ID",
    "STORAGE_PREFIX",
    "GITHUB_COMMITTER_NAME",
    "GITHUB_COMMITTER_EMAIL",
    "TELEGRAM_BOT_TOKEN",
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


def build_update_payload() -> Dict[str, object]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 1, "type": "private"},
            "text": "ping",
            "from": {"id": 1, "is_bot": False, "first_name": "Smoke"},
        },
    }


def main() -> None:
    require_env()
    port = int(os.getenv("SMOKE_PORT", "8098"))
    secret = "smoke-secret"
    env = os.environ.copy()
    env.update(
        {
            "STORAGE_MODE": "github",
            "BOT_MODE": "webhook",
            "WEBHOOK_BASE_URL": f"http://127.0.0.1:{port}",
            "WEBHOOK_URL": f"http://127.0.0.1:{port}/webhook",
            "WEBHOOK_SECRET_TOKEN": secret,
            "WEBHOOK_SKIP_SET": "1",
            "PORT": str(port),
            "DATABASE_URL": "",
        }
    )

    health_url = f"http://127.0.0.1:{port}/health"
    webhook_url = f"http://127.0.0.1:{port}/webhook"
    proc = start_main(env)
    try:
        wait_for_health(health_url, timeout_s=40)
        payload = build_update_payload()

        resp = requests.post(webhook_url, json=payload, timeout=5)
        if resp.status_code not in (401, 403):
            raise RuntimeError(f"Expected 401/403 without secret, got {resp.status_code}")

        headers = {"X-Telegram-Bot-Api-Secret-Token": secret}
        resp = requests.post(webhook_url, json=payload, headers=headers, timeout=5)
        if resp.status_code not in (200, 204):
            raise RuntimeError(f"Expected 200/204 with secret, got {resp.status_code}")
    finally:
        stop_main(proc)

    print("Smoke test passed: webhook route accepted updates and rejected missing secret.")


if __name__ == "__main__":
    main()
