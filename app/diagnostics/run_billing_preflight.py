from __future__ import annotations

import asyncio
import json
import logging

from app.diagnostics.billing_preflight import (
    build_billing_preflight_log_payload,
    run_billing_preflight,
)
from app.storage.factory import get_storage

logger = logging.getLogger(__name__)


async def _run_once() -> dict:
    storage = get_storage()
    db_pool = None
    if hasattr(storage, "_get_pool") and asyncio.iscoroutinefunction(storage._get_pool):
        db_pool = await storage._get_pool()
    report = await run_billing_preflight(storage, db_pool, emit_logs=False)
    payload = build_billing_preflight_log_payload(report)
    logger.info(
        "BILLING_PREFLIGHT_RUNTIME %s",
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    )
    return payload


def main() -> None:
    asyncio.run(_run_once())


if __name__ == "__main__":
    main()
