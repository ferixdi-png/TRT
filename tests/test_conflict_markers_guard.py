import os
from pathlib import Path

# Directories to scan for accidental merge markers or branch-garbage strings.
SCAN_ROOTS = [
    Path("app"),
    Path("bot"),
    Path("docs"),
    Path("tests"),
    Path("main_render.py"),
]

CONFLICT_LINES = {"<<<<<<<", "=======", ">>>>>>>"}
FORBIDDEN_SNIPPETS = ["codex/"]
ALLOWED_EXTS = {".py", ".md", ".json", ".yaml", ".yml"}


def iter_files():
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        if root.is_file():
            yield root
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in ALLOWED_EXTS:
                yield path


def test_no_conflict_markers_or_branch_garbage():
    offenders = []
    for path in iter_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if stripped in CONFLICT_LINES:
                offenders.append((path, stripped))
                break
        else:
            for snippet in FORBIDDEN_SNIPPETS:
                if snippet in text:
                    # Allow this guard file to mention codex/ in constants without failing the suite.
                    if path.name == "test_conflict_markers_guard.py":
                        continue
                    offenders.append((path, snippet))
                    break
    assert not offenders, f"Forbidden merge markers/branch strings found: {offenders}"
