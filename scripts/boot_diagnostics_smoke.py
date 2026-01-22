#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import sys

from app.diagnostics.boot import format_boot_report, run_boot_diagnostics


async def _run() -> int:
    report = await run_boot_diagnostics(os.environ, storage=None, redis_client=None)
    print("BOOT_REPORT", json.dumps(report, ensure_ascii=False, default=str))
    print(format_boot_report(report))
    return 1 if report.get("result") == "FAIL" else 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
