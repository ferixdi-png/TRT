#!/usr/bin/env python3
"""Unified verification runner."""
from __future__ import annotations

import subprocess
import sys


def main() -> int:
    result = subprocess.run("python scripts/verify_project.py", shell=True)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
