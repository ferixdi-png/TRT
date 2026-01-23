from __future__ import annotations

from pathlib import Path

import scripts.verify_project as verify_project


def _write_file(base: Path, relative: str, content: str) -> None:
    target = base / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def test_secrets_scan_python_fallback_no_hits(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(verify_project, "ROOT", tmp_path)
    monkeypatch.setattr(verify_project.shutil, "which", lambda _name: None)

    _write_file(tmp_path, "safe.txt", "hello world")

    assert verify_project.run_secrets_scan() is True


def test_secrets_scan_python_fallback_detects_hits(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(verify_project, "ROOT", tmp_path)
    monkeypatch.setattr(verify_project.shutil, "which", lambda _name: None)

    _write_file(tmp_path, "leak.txt", "BEGIN PRIVATE KEY abc")

    assert verify_project.run_secrets_scan() is False
