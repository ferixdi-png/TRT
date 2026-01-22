#!/usr/bin/env python3
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def build_context_files(ignore_file: Path) -> set[Path]:
    patterns = []
    for line in ignore_file.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        patterns.append(raw)

    excluded = set()
    for pattern in patterns:
        excluded.update(REPO_ROOT.glob(pattern))

    files = set()
    for path in REPO_ROOT.rglob("*"):
        if path.is_dir():
            continue
        if path in excluded:
            continue
        files.add(path)
    return files


def total_size(paths: set[Path]) -> int:
    return sum(path.stat().st_size for path in paths if path.exists())


def main() -> None:
    correlation_id = str(uuid.uuid4())
    ignore_file = REPO_ROOT / ".dockerignore"
    files = build_context_files(ignore_file)
    size_bytes = total_size(files)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "docker_context_size",
        "error_code": "DOCKER_CONTEXT_SIZE",
        "correlation_id": correlation_id,
        "context_file_count": len(files),
        "context_size_bytes": size_bytes,
    }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
