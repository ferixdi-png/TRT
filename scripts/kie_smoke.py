#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minimal Kie.ai smoke test.

Runs ONLY when RUN_KIE_SMOKE=1 and KIE_API_KEY is set.
Performs 1 cheap text-to-image request (z-image) and logs the task id.
"""
import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict

import aiohttp

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("kie_smoke")


async def create_task(model_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.getenv("KIE_API_KEY", "").strip()
    base_url = os.getenv("KIE_API_URL", "https://api.kie.ai").rstrip("/")
    timeout = int(os.getenv("KIE_TIMEOUT_SECONDS", "30"))
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    url = f"{base_url}/api/v1/jobs/createTask"
    data = {"model": model_id, "input": payload}

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
        async with session.post(url, headers=headers, json=data) as response:
            text = await response.text()
            if response.status != 200:
                return {"ok": False, "status": response.status, "error": text[:300]}
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return {"ok": False, "status": response.status, "error": "invalid_json"}
            if parsed.get("code") != 200:
                return {"ok": False, "status": response.status, "error": parsed.get("msg", "unknown_error")}
            task_id = parsed.get("data", {}).get("taskId")
            return {"ok": True, "task_id": task_id}


async def main() -> int:
    run_smoke = os.getenv("RUN_KIE_SMOKE", "").strip() in {"1", "true", "yes"}
    api_key = os.getenv("KIE_API_KEY", "").strip()
    if not run_smoke:
        logger.info("RUN_KIE_SMOKE not set - skipping KIE smoke test.")
        return 0
    if not api_key:
        logger.warning("KIE_API_KEY missing - skipping KIE smoke test.")
        return 0

    payload = {
        "prompt": "Minimal smoke prompt",
        "aspect_ratio": "1:1",
    }
    logger.info("Running KIE smoke test (text-to-image).")
    result = await create_task("z-image", payload)
    if not result.get("ok"):
        logger.error("KIE smoke failed: %s", result)
        return 1

    logger.info("KIE smoke ok: task_id=%s", result.get("task_id"))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
