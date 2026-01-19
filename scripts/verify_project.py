#!/usr/bin/env python3
"""
Verify project readiness.
Runs:
 - python -m compileall .
 - pytest -q
 - python scripts/verify_ssot.py
 - python scripts/verify_no_placeholders.py
 - python scripts/verify_button_coverage.py
 - python scripts/verify_kie_single_entrypoint.py
 - python scripts/verify_model_specs.py
 - python scripts/verify_source_of_truth.py
 - secrets scan
Fails if any 0-byte files exist under app/, bot/, models/, pricing/, tests/, scripts/.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CHECK_DIRS = ["app", "bot", "models", "pricing", "tests", "scripts"]


def run_command(cmd: str) -> bool:
    print(f"\n$ {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"❌ Command failed: {cmd}")
    return result.returncode == 0


def run_secrets_scan() -> bool:
    print("\n$ rg -n \"BEGIN PRIVATE KEY|AKIA[0-9A-Z]{16}\" -g '!node_modules' -g '!.git' -g '!scripts/verify_project.py'")
    result = subprocess.run(
        "rg -n \"BEGIN PRIVATE KEY|AKIA[0-9A-Z]{16}\" -g '!node_modules' -g '!.git' -g '!scripts/verify_project.py'",
        shell=True,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("❌ Secret patterns found:")
        print(result.stdout)
        return False
    if result.returncode == 1:
        print("✅ No secrets detected.")
        return True
    print("❌ Secrets scan failed")
    print(result.stderr)
    return False


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
    print("ℹ️ Runtime SSOT: root /models + /app. Folder 5656-main is deprecated/ignored.")
    ok &= run_command("python -m compileall .")
    ok &= run_command("pytest -q")
    ok &= run_command("python scripts/verify_ssot.py")
    ok &= run_command("python scripts/verify_output_media_type.py")
    ok &= run_command("python scripts/verify_no_placeholders.py")
    ok &= run_command("python scripts/verify_button_coverage.py")
    ok &= run_command("python scripts/verify_kie_single_entrypoint.py")
    ok &= run_command("python scripts/verify_model_specs.py")
    ok &= run_command("python scripts/verify_source_of_truth.py")
    ok &= run_secrets_scan()

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
