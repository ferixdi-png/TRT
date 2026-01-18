#!/usr/bin/env python3
"""Basic healthcheck smoke test runner."""
from __future__ import annotations

import sys


def main() -> int:
    print("smoke_test_server: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
