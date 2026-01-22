#!/usr/bin/env python3
"""Compatibility wrapper that forwards to the canonical entrypoint."""

from entrypoints.run_bot import run as main


if __name__ == "__main__":
    main()
