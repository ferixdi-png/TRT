#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Обёртка для render_logs_tail.py"""

import sys
import subprocess
from pathlib import Path

def main():
    script = Path(__file__).parent / "render_logs_tail.py"
    cmd = ["python", str(script)] + sys.argv[1:]
    return subprocess.run(cmd).returncode

if __name__ == "__main__":
    sys.exit(main())







