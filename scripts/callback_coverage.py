#!/usr/bin/env python3
"""Legacy callback coverage shim."""
from __future__ import annotations

import sys

from scripts.verify_button_coverage import main


if __name__ == "__main__":
    sys.exit(main())
