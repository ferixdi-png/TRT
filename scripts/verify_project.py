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

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CHECK_DIRS = ["app", "bot", "models", "pricing", "tests", "scripts"]
REQUIRED_MODULES = {
    "telegram": "python-telegram-bot",
    "yaml": "PyYAML",
}


def run_command(cmd: str) -> bool:
    print(f"\n$ {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"❌ Command failed: {cmd}")
    return result.returncode == 0


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def ensure_dependencies() -> None:
    bootstrap_enabled = os.getenv("VERIFY_BOOTSTRAP", "1").lower() not in ("0", "false", "no")
    if not bootstrap_enabled:
        return
    missing = [name for name in REQUIRED_MODULES if not _module_available(name)]
    if not missing:
        return
    print(f"ℹ️ Missing modules detected: {', '.join(missing)}. Installing requirements...")
    requirements_file = ROOT / "requirements.txt"
    subprocess.check_call(
        f"{sys.executable} -m pip install -r {requirements_file}",
        shell=True,
    )


EXCLUDE_DIRS = {".git", "node_modules"}
EXCLUDE_FILES = {Path("scripts/verify_project.py")}


def _python_secrets_scan(pattern: re.Pattern[str]) -> list[str]:
    matches: list[str] = []
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for filename in files:
            path = Path(root) / filename
            rel_path = path.relative_to(ROOT)
            if rel_path in EXCLUDE_FILES:
                continue
            try:
                with path.open("r", encoding="utf-8", errors="ignore") as handle:
                    for index, line in enumerate(handle, start=1):
                        if pattern.search(line):
                            matches.append(f"{rel_path}:{index}:{line.strip()}")
            except (OSError, UnicodeDecodeError):
                continue
    return matches


def run_secrets_scan() -> bool:
    pattern = "BEGIN PRIVATE KEY|AKIA[0-9A-Z]{16}"
    rg_cmd = f"rg -n \"{pattern}\" -g '!node_modules' -g '!.git' -g '!scripts/verify_project.py'"
    if shutil.which("rg"):
        print(f"\n$ {rg_cmd}")
        result = subprocess.run(
            rg_cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        engine = "rg"
    else:
        engine = "python"
        compiled = re.compile(pattern)
        matches = _python_secrets_scan(compiled)
        print(f"ℹ️ Secrets scan engine: {engine}")
        if matches:
            print("❌ Secret patterns found:")
            for entry in matches:
                print(entry)
            return False
        print("✅ No secrets detected.")
        return True
    print(f"ℹ️ Secrets scan engine: {engine}")
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
    ensure_dependencies()
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
