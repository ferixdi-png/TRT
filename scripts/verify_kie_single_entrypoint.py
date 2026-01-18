#!/usr/bin/env python3
"""Verify KIE HTTP usage is centralized in app/kie/kie_client.py."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
ALLOWED = {
    ROOT / "app" / "kie" / "kie_client.py",
    ROOT / "app" / "integrations" / "kie_client.py",
    ROOT / "app" / "kie" / "client_factory.py",
}

KIE_HINTS = ["KIE_API_URL", "kie.ai", "/task", "/create", "/submit"]
HTTP_HINTS = ["ClientSession", "requests.", "httpx.", "aiohttp"]


def main() -> int:
    offenders: List[str] = []

    for path in (ROOT / "app").rglob("*.py"):
        if path in ALLOWED:
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        if any(hint in content for hint in KIE_HINTS) and any(hint in content for hint in HTTP_HINTS):
            offenders.append(str(path.relative_to(ROOT)))

    for path in (ROOT / "bot").rglob("*.py"):
        content = path.read_text(encoding="utf-8", errors="ignore")
        if any(hint in content for hint in KIE_HINTS) and any(hint in content for hint in HTTP_HINTS):
            offenders.append(str(path.relative_to(ROOT)))

    if offenders:
        print("❌ KIE HTTP usage detected outside single entrypoint:")
        for offender in sorted(offenders):
            print(f"- {offender}")
        return 1

    print("✅ KIE single entrypoint verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
