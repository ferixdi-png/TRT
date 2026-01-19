#!/usr/bin/env python3
"""Verify callback_data coverage for all UI buttons."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Set

ROOT = Path(__file__).resolve().parent.parent
SCAN_FILES = [
    ROOT / "bot_kie.py",
    ROOT / "app" / "helpers" / "models_menu.py",
    ROOT / "app" / "observability" / "no_silence_guard.py",
    ROOT / "app" / "generations" / "failure_ui.py",
]

IGNORED_CALLBACKS = {
    "type_header:ignore",
}

DYNAMIC_CALLBACK_PREFIXES = {
    "modelk:",
    "reset_wizard",
}

CALLBACK_PATTERNS = [
    re.compile(r"callback_data\s*[=:]\s*f?[\"']([^\"']+)[\"']"),
]

HANDLER_EQ_PATTERNS = [
    re.compile(r"data\s*==\s*[\"']([^\"']+)[\"']"),
]

HANDLER_STARTSWITH_PATTERNS = [
    re.compile(r"data\.startswith\([\"']([^\"']+)[\"']\)"),
]

HANDLER_IN_LIST_PATTERN = re.compile(r"data\s*in\s*\[([^\]]+)\]")
STRING_LITERAL = re.compile(r"[\"']([^\"']+)[\"']")


def _extract_callbacks(content: str) -> Set[str]:
    callbacks: Set[str] = set()
    for pattern in CALLBACK_PATTERNS:
        for match in pattern.finditer(content):
            raw = match.group(1)
            if "{" in raw:
                base = raw.split("{")[0]
                if base:
                    callbacks.add(base)
            else:
                callbacks.add(raw)
    return callbacks


def _extract_handlers(content: str) -> Dict[str, Set[str]]:
    exact: Set[str] = set()
    prefixes: Set[str] = set()

    for pattern in HANDLER_EQ_PATTERNS:
        exact.update(pattern.findall(content))

    for pattern in HANDLER_STARTSWITH_PATTERNS:
        prefixes.update(pattern.findall(content))

    for match in HANDLER_IN_LIST_PATTERN.finditer(content):
        list_body = match.group(1)
        exact.update(STRING_LITERAL.findall(list_body))

    return {"exact": exact, "prefixes": prefixes}


def main() -> int:
    callbacks: Set[str] = set()
    handler_exact: Set[str] = set()
    handler_prefixes: Set[str] = set()

    for path in SCAN_FILES:
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        callbacks.update(_extract_callbacks(content))
        handlers = _extract_handlers(content)
        handler_exact.update(handlers["exact"])
        handler_prefixes.update(handlers["prefixes"])

    callbacks.update(DYNAMIC_CALLBACK_PREFIXES)

    def is_covered(callback: str) -> bool:
        if callback in handler_exact:
            return True
        for prefix in handler_prefixes:
            if callback.startswith(prefix) or prefix.startswith(callback):
                return True
        return False

    orphan_callbacks = sorted(cb for cb in callbacks if cb not in IGNORED_CALLBACKS and not is_covered(cb))

    unused_handlers = sorted(
        h for h in handler_prefixes.union(handler_exact)
        if not any(cb == h or cb.startswith(h) or h.startswith(cb) for cb in callbacks)
    )

    ambiguous_prefixes = []
    prefixes = sorted(handler_prefixes)
    for i, prefix in enumerate(prefixes):
        for other in prefixes[i + 1:]:
            if prefix.startswith(other) or other.startswith(prefix):
                if prefix != other:
                    ambiguous_prefixes.append((prefix, other))

    if orphan_callbacks or unused_handlers or ambiguous_prefixes:
        print("❌ Button coverage verification failed:")
        if orphan_callbacks:
            print(f"- Orphan callbacks: {orphan_callbacks}")
        if unused_handlers:
            print(f"- Unused handlers: {unused_handlers}")
        if ambiguous_prefixes:
            print("- Ambiguous handler prefixes:")
            for pair in ambiguous_prefixes:
                print(f"  - {pair[0]} vs {pair[1]}")
        return 1

    print(f"✅ Button coverage OK: {len(callbacks)} callbacks covered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
