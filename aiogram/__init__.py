"""aiogram import shim (production safety).

Why this exists
---------------
This repo once shipped a local *stub* package named `aiogram/` for tests.
In production, Python prefers local modules over `site-packages`, so
`from aiogram import Bot` would import the stub and crash.

This shim makes the local package self-heal:
  - It temporarily removes the project root from `sys.path`
  - Re-imports the real `aiogram` from `site-packages`
  - Replaces `sys.modules['aiogram']` with the real package

Result: even if the `aiogram/` directory accidentally remains in the build
context, the runtime always uses the installed aiogram.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _bootstrap_real_aiogram() -> None:
    # If we are already the real package, do nothing.
    this_file = Path(__file__).resolve()
    if "site-packages" in str(this_file):
        return

    project_root = this_file.parent.parent

    # Remove entries that can resolve to the project root.
    orig_sys_path = list(sys.path)
    cleaned: list[str] = []
    for p in orig_sys_path:
        if not p:
            continue
        try:
            if Path(p).resolve() == project_root:
                continue
        except Exception:
            # Keep unresolvable entries.
            pass
        cleaned.append(p)

    # Import the real package *as aiogram* by temporarily removing this module
    # from sys.modules and removing project-root entries from sys.path.
    current = sys.modules.get(__name__)
    sys.path = cleaned
    sys.modules.pop(__name__, None)
    try:
        real = importlib.import_module(__name__)
    except Exception as e:
        raise ImportError(
            "Real 'aiogram' package is not available. "
            "Ensure requirements.txt installs aiogram and that build succeeded."
        ) from e
    finally:
        sys.path = orig_sys_path
        if current is not None:
            sys.modules[__name__] = current

    # Overlay the real package onto this module object so submodules resolve
    # from the real package path, not from the repository.
    if current is not None:
        # Save sys reference before clearing __dict__
        _sys = sys
        current.__dict__.clear()
        current.__dict__.update(real.__dict__)
        # Defensive: keep our name consistent.
        current.__name__ = __name__
        _sys.modules[__name__] = current


_bootstrap_real_aiogram()

