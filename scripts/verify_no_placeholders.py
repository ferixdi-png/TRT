#!/usr/bin/env python3
"""Fail if placeholder markers exist in runtime-reachable files."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent

MARKERS = [
    re.compile(r"\bplaceholder\b", re.IGNORECASE),
    re.compile(r"\bTODO\b"),
    re.compile(r"NotImplementedError"),
]


def _runtime_files() -> List[Path]:
    paths: List[Path] = []
    for base in (ROOT / "app", ROOT / "bot"):
        if not base.exists():
            continue
        paths.extend(base.rglob("*.py"))
    paths.extend([ROOT / "run_bot.py", ROOT / "bot_kie.py"])
    return sorted({path.resolve() for path in paths})


def main() -> int:
    offenders: Dict[str, List[str]] = {}

    for path in _runtime_files():
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        hits: List[str] = []
        for marker in MARKERS:
            if marker.search(content):
                hits.append(marker.pattern)
        if hits:
            offenders[str(path.relative_to(ROOT))] = hits

    if offenders:
        print("❌ Placeholder markers found in runtime files:")
        for file_path, markers in sorted(offenders.items()):
            print(f"- {file_path}: {', '.join(markers)}")
        return 1

    print("✅ No placeholder markers in runtime import graph")
    return 0


if __name__ == "__main__":
    sys.exit(main())
