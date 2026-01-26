import importlib
from pathlib import Path

import pytest


def test_legacy_singleton_lock_module_removed():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.singleton_lock")


def test_no_legacy_singleton_lock_imports():
    repo_root = Path(__file__).resolve().parents[1]
    denylist = ("from app.singleton_lock", "import app.singleton_lock")
    excluded_dirs = {".git", "node_modules", "__pycache__", "archive", "artifacts"}
    offenders = []
    for path in repo_root.rglob("*.py"):
        if any(part in excluded_dirs for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(token in text for token in denylist):
            offenders.append(str(path.relative_to(repo_root)))
    assert not offenders, f"Legacy imports found: {offenders}"


def test_singleton_lock_api_surface():
    module = importlib.import_module("app.utils.singleton_lock")
    required = [
        "acquire_singleton_lock",
        "release_singleton_lock",
        "is_lock_acquired",
        "get_safe_mode",
    ]
    missing = [name for name in required if not hasattr(module, name)]
    assert not missing, f"Missing singleton lock API: {missing}"


def test_no_runtime_render_singleton_lock_imports():
    repo_root = Path(__file__).resolve().parents[1]
    offenders = []
    for root in (repo_root / "app", repo_root / "entrypoints"):
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "render_singleton_lock" in text:
                offenders.append(str(path.relative_to(repo_root)))
    assert not offenders, f"render_singleton_lock imports found: {offenders}"
