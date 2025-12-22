#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUTO-FIX ENGINE (БЕЗ САБОТАЖА ПРОДУКТА)
Работает ТОЛЬКО через whitelist-паттерны
"""

import json
import re
from pathlib import Path
from typing import Dict, List

project_root = Path(__file__).parent.parent
diagnostics_dir = project_root / "artifacts" / "diagnostics"
incidents_file = diagnostics_dir / "incidents.json"
bot_file = project_root / "bot_kie.py"


def load_incidents() -> Dict:
    """Загружает инциденты"""
    if not incidents_file.exists():
        return {"incidents": []}
    with open(incidents_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def fix_unknown_callback(incident: Dict) -> bool:
    """Фикс для unknown callback"""
    # Проверяем что fallback handler уже есть
    if not bot_file.exists():
        return False
    
    content = bot_file.read_text(encoding='utf-8', errors='ignore')
    
    # Проверяем наличие fallback
    if 'fallback_callback_handler' in content or 'UNHANDLED CALLBACK' in content:
        return True  # Уже исправлено
    
    return False  # Требует ручного исправления


def fix_silence(incident: Dict) -> bool:
    """Фикс для тишины"""
    if not bot_file.exists():
        return False
    
    content = bot_file.read_text(encoding='utf-8', errors='ignore')
    
    # Проверяем наличие гарантированного ответа
    if '✅ Принято, обрабатываю' in content or 'Принято, обрабатываю' in content:
        return True  # Уже исправлено
    
    return False  # Требует ручного исправления


def fix_missing_env(incident: Dict) -> bool:
    """Фикс для missing env"""
    # Это требует ручного исправления - добавляем fallback
    return False  # Требует ручного исправления


def apply_safe_fixes(incidents: List[Dict]) -> Dict:
    """Применяет безопасные фиксы"""
    fixes_applied = []
    fixes_failed = []
    
    for incident in incidents:
        inc_type = incident.get("type", "")
        
        if inc_type == "unknown_callback":
            if fix_unknown_callback(incident):
                fixes_applied.append(f"unknown_callback: fallback handler exists")
            else:
                fixes_failed.append(f"unknown_callback: requires manual fix")
        
        elif inc_type == "silence":
            if fix_silence(incident):
                fixes_applied.append(f"silence: guaranteed reply exists")
            else:
                fixes_failed.append(f"silence: requires manual fix")
        
        elif inc_type == "missing_env":
            fixes_failed.append(f"missing_env: requires manual fix")
        
        elif inc_type == "syntax_error":
            fixes_failed.append(f"syntax_error: requires manual fix")
    
    return {
        "applied": fixes_applied,
        "failed": fixes_failed,
        "total_incidents": len(incidents),
        "fixed": len(fixes_applied),
        "requires_manual": len(fixes_failed)
    }


def main():
    """Главная функция"""
    print("Auto-fix engine...")
    
    data = load_incidents()
    incidents = data.get("incidents", [])
    
    if not incidents:
        print("OK No incidents to fix")
        return 0
    
    result = apply_safe_fixes(incidents)
    
    print(f"\nFixes applied: {result['fixed']}")
    print(f"Requires manual: {result['requires_manual']}")
    
    if result['applied']:
        print("\nApplied fixes:")
        for fix in result['applied']:
            print(f"  - {fix}")
    
    if result['failed']:
        print("\nRequires manual fixes:")
        for fix in result['failed']:
            print(f"  - {fix}")
    
    return 0 if result['requires_manual'] == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())







