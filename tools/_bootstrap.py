from __future__ import annotations
import os
import sys

def ensure_repo_root_on_path() -> None:
    """Ensure project root (one level above tools/) is on sys.path."""
    here = os.path.dirname(__file__)
    root = os.path.dirname(here)
    if root not in sys.path:
        sys.path.insert(0, root)
