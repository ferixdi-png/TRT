#!/usr/bin/env python3
import os, sys
ROOT = os.path.dirname(__file__)
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, ROOT)
TARGET = os.path.join(TOOLS, os.path.basename(__file__))
with open(TARGET, "rb") as f:
    code = compile(f.read(), TARGET, "exec")
exec(code, {"__name__": "__main__"})