#!/usr/bin/env python3
"""
Release verification script.

Checks:
- python compileall
- pytest smoke suite
- menu/welcome texts do not expose internal warnings
- storage branch guard (storage branch must differ from code branch)
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
logger = logging.getLogger("verify_release")

BANNED_SUBSTRINGS = ("file-lock", "резервный")


def run_command(args: list[str]) -> bool:
    logger.info("Running: %s", " ".join(args))
    result = subprocess.run(args, cwd=ROOT_DIR)
    if result.returncode != 0:
        logger.error("Command failed with code %s: %s", result.returncode, " ".join(args))
        return False
    return True


def check_menu_texts() -> bool:
    from translations import t
    from app.utils import singleton_lock as lock_utils

    messages = [
        t("welcome_new", lang="ru", name="Тест"),
        t("welcome_returning", lang="ru", name="Тест"),
        t("welcome_new", lang="en", name="Test"),
        t("welcome_returning", lang="en", name="Test"),
    ]

    lock_utils._set_lock_state("file", True, reason="file_lock_fallback")
    try:
        messages.append(lock_utils.get_lock_admin_notice("ru"))
        messages.append(lock_utils.get_lock_admin_notice("en"))
    finally:
        lock_utils._set_lock_state("none", True, reason=None)

    for message in messages:
        lowered = (message or "").lower()
        if any(banned in lowered for banned in BANNED_SUBSTRINGS):
            logger.error("Menu text contains internal warning substring: %s", message)
            return False
    return True


def check_storage_branch_guard() -> bool:
    github_branch = os.getenv("GITHUB_BRANCH", "").strip()
    storage_branch = os.getenv("STORAGE_BRANCH", os.getenv("STORAGE_GITHUB_BRANCH", "")).strip()

    missing = []
    if not github_branch:
        missing.append("GITHUB_BRANCH")
    if not storage_branch:
        missing.append("STORAGE_BRANCH/STORAGE_GITHUB_BRANCH")

    if missing:
        logger.error("Missing env for storage branch guard: %s", ", ".join(missing))
        return False

    if github_branch == storage_branch:
        logger.error(
            "Storage branch guard failed: STORAGE_BRANCH == GITHUB_BRANCH (%s)",
            github_branch,
        )
        return False

    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ok = True

    ok = run_command([sys.executable, "-m", "compileall", "-q", "."]) and ok
    ok = run_command(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_main_menu.py",
            "tests/test_menu_no_internal_warnings.py",
        ]
    ) and ok
    ok = check_menu_texts() and ok
    ok = check_storage_branch_guard() and ok

    if ok:
        logger.info("OK: release verification passed")
        return 0
    logger.error("FAIL: release verification failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
