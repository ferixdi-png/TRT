#!/usr/bin/env python3
"""
Verify that no database usage is possible in runtime code paths.
"""
from __future__ import annotations

import sys
from pathlib import Path


DISALLOWED_DB_LIBS = ("asyncpg", "psycopg", "psycopg2", "sqlalchemy", "alembic")
DISALLOWED_ENV_KEYS = ("DATABASE_URL",)

RUNTIME_PATHS = (
    "bot_kie.py",
    "main_render.py",
    "app",
)


def iter_runtime_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for rel in RUNTIME_PATHS:
        path = root / rel
        if path.is_dir():
            files.extend(path.rglob("*.py"))
        elif path.is_file():
            files.append(path)
    return files


def check_runtime_for_db(root: Path) -> list[str]:
    violations: list[str] = []
    for file_path in iter_runtime_files(root):
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        for key in DISALLOWED_ENV_KEYS:
            if key in content:
                violations.append(f"Env var reference '{key}' found in {file_path.relative_to(root)}")
        for lib in DISALLOWED_DB_LIBS:
            if f"import {lib}" in content or f"from {lib}" in content:
                violations.append(f"DB library import '{lib}' found in {file_path.relative_to(root)}")
    return violations


def check_requirements(root: Path) -> list[str]:
    violations: list[str] = []
    req_file = root / "requirements.txt"
    if not req_file.exists():
        return violations
    content = req_file.read_text(encoding="utf-8", errors="ignore")
    for lib in DISALLOWED_DB_LIBS:
        if lib in content:
            violations.append(f"DB dependency '{lib}' found in requirements.txt")
    return violations


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    violations = []
    violations.extend(check_runtime_for_db(root))
    violations.extend(check_requirements(root))
    if violations:
        print("❌ verify_no_db: violations found")
        for item in violations:
            print(f" - {item}")
        return 1
    print("✅ verify_no_db: no database usage detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
