#!/usr/bin/env python3
"""CI strict smoke entrypoint."""
from __future__ import annotations

import sys


def main() -> int:
    print("ci_strict_smoke: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
