#!/usr/bin/env python3
"""
Render-mode smoke test for webhook readiness.

Starts main_render.py in webhook mode, waits for /health readiness, posts a minimal
update to /webhook, and verifies the process stays alive.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

import requests

DEFAULT_PORT = 8099
DEFAULT_SECRET = "smoke-secret"


def _mask(value: Optional[str]) -> str:
    if not value:
        return "[NOT SET]"
    return "[SET]"


def build_env(port: int, storage_dir: str) -> Dict[str, str]:
    env = os.environ.copy()

    if not env.get("TELEGRAM_BOT_TOKEN"):
        env["TELEGRAM_BOT_TOKEN"] = "000:TEST"

    if not env.get("GITHUB_TOKEN"):
        env.setdefault("STORAGE_MODE", "json")
        env.setdefault("DRY_RUN", "1")
        env.setdefault("TEST_MODE", "1")
        env.setdefault("STORAGE_DATA_DIR", storage_dir)

    env.setdefault("BOT_MODE", "webhook")
    env.setdefault("PORT", str(port))
    env.setdefault("WEBHOOK_BASE_URL", f"http://127.0.0.1:{port}")
    env.setdefault("WEBHOOK_SECRET_TOKEN", DEFAULT_SECRET)
    env.setdefault("WEBHOOK_SKIP_SET", "1")
    env.setdefault("KIE_STUB", "1")
    env.setdefault("ALLOW_REAL_GENERATION", "0")
    env.setdefault("SMOKE_NO_PROCESS", "1")

    return env


def start_main(env: Dict[str, str]) -> Tuple[subprocess.Popen, Deque[str], threading.Thread]:
    proc = subprocess.Popen(
        [sys.executable, "main_render.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output: Deque[str] = deque(maxlen=200)

    def _reader() -> None:
        if proc.stdout is None:
            return
        for line in proc.stdout:
            output.append(line.rstrip())

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    return proc, output, thread


def stop_main(proc: subprocess.Popen, thread: threading.Thread) -> None:
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    thread.join(timeout=1)


def wait_for_health(
    url: str,
    proc: subprocess.Popen,
    output: Deque[str],
    timeout_s: int = 60,
) -> Dict[str, object]:
    deadline = time.time() + timeout_s
    last_err: str = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            tail = "\n".join(output)
            raise RuntimeError(
                f"main_render.py exited early code={proc.returncode} logs:\n{tail}"
            )
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                return resp.json()
            last_err = f"status={resp.status_code}"
        except Exception as exc:  # pragma: no cover - best effort polling
            last_err = str(exc)
        time.sleep(1)
    raise TimeoutError(f"Healthcheck not ready: {last_err}")


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


def log_env(env: Dict[str, str]) -> None:
    print(
        json.dumps(
            {
                "telegram_bot_token": _mask(env.get("TELEGRAM_BOT_TOKEN")),
                "github_token": _mask(env.get("GITHUB_TOKEN")),
                "storage_mode": env.get("STORAGE_MODE", "[NOT SET]"),
                "bot_mode": env.get("BOT_MODE", "[NOT SET]"),
                "port": env.get("PORT", "[NOT SET]"),
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    port = int(os.getenv("SMOKE_PORT", str(DEFAULT_PORT)))
    with tempfile.TemporaryDirectory(prefix="render_smoke_") as storage_dir:
        env = build_env(port, storage_dir)
        log_env(env)

        health_url = f"http://127.0.0.1:{port}/health"
        webhook_url = f"http://127.0.0.1:{port}/webhook"
        secret = env.get("WEBHOOK_SECRET_TOKEN", DEFAULT_SECRET)

        proc, output, thread = start_main(env)
        try:
            health_payload = wait_for_health(health_url, proc, output)
            if health_payload.get("status") != "ok":
                raise RuntimeError(f"Unexpected health status: {health_payload}")
            if not health_payload.get("webhook_route_registered"):
                raise RuntimeError("webhook_route_registered=false")

            payload = build_update_payload()
            headers = {"X-Telegram-Bot-Api-Secret-Token": secret}
            resp = requests.post(webhook_url, json=payload, headers=headers, timeout=5)
            if resp.status_code not in (200, 204):
                raise RuntimeError(f"Expected 200/204 from /webhook, got {resp.status_code}")

            if proc.poll() is not None:
                raise RuntimeError("main_render.py exited unexpectedly")
        finally:
            stop_main(proc, thread)

    print("Render webhook smoke passed: /health ok, route registered, webhook accepted.")


if __name__ == "__main__":
    main()
