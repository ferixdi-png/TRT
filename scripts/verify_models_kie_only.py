#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка что все модели из KIE"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent

def main():
    try:
        sys.path.insert(0, str(project_root))
        from kie_models import KIE_MODELS
        
        if isinstance(KIE_MODELS, dict):
            count = len(KIE_MODELS)
        elif isinstance(KIE_MODELS, list):
            count = len(KIE_MODELS)
        else:
            print("FAIL KIE_MODELS format unknown")
            return 1
        
        if count == 0:
            print("FAIL No models in KIE_MODELS")
            return 1
        
        print(f"OK {count} models from KIE")
        return 0
    except Exception as e:
        print(f"FAIL Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
