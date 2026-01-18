#!/usr/bin/env python3
"""
Verify project readiness.
Runs:
 - python -m compileall .
 - pytest -q
 - python scripts/verify_ssot.py
Fails if any 0-byte files exist under app/, bot/, models/, pricing/, tests/.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CHECK_DIRS = ["app", "bot", "models", "pricing", "tests"]


def run_command(cmd: str) -> bool:
    print(f"\n$ {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"❌ Command failed: {cmd}")
    return result.returncode == 0


def find_zero_byte_files() -> list[Path]:
    zero_files: list[Path] = []
    for rel in CHECK_DIRS:
        base = ROOT / rel
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.stat().st_size == 0:
                zero_files.append(path)
    return zero_files


def main() -> int:
    ok = True
    ok &= run_command("python -m compileall .")
    ok &= run_command("pytest -q")
    ok &= run_command("python scripts/verify_ssot.py")

    zero_files = find_zero_byte_files()
    if zero_files:
        ok = False
        print("\n❌ Zero-byte files detected:")
        for path in zero_files:
            print(f"- {path.relative_to(ROOT)}")
    else:
        print("\n✅ No zero-byte files detected.")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
