"""Version helpers."""
from __future__ import annotations

import os
from pathlib import Path


def _read_git_sha() -> str | None:
    git_dir = Path(__file__).resolve().parents[2] / ".git"
    head = git_dir / "HEAD"
    if not head.exists():
        return None
    content = head.read_text().strip()
    if content.startswith("ref:"):
        ref_path = content.split(" ", 1)[1].strip()
        ref_file = git_dir / ref_path
        if ref_file.exists():
            return ref_file.read_text().strip()
        return None
    return content


def get_app_version() -> str:
    return os.getenv("GIT_SHA", "") or os.getenv("RENDER_GIT_COMMIT", "") or _read_git_sha() or "unknown"


def get_version_info() -> dict:
    return {
        "version": get_app_version(),
        "source": "git" if get_app_version() != "unknown" else "unknown",
        "git_sha": get_app_version(),
    }
