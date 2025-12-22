#!/usr/bin/env python3
"""
Сканирование использования ENV переменных
"""

import re
from pathlib import Path
from typing import Dict, Set, List

def scan_env_usage(file_path: Path) -> Dict:
    """Сканирует файл на использование ENV переменных"""
    env_vars = set()
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Паттерны для поиска ENV переменных
        patterns = [
            r"os\.getenv\(['\"]([^'\"]+)['\"]",  # os.getenv('VAR_NAME')
            r"os\.environ\[['\"]([^'\"]+)['\"]",  # os.environ['VAR_NAME']
            r"os\.environ\.get\(['\"]([^'\"]+)['\"]",  # os.environ.get('VAR_NAME')
            r"getenv\(['\"]([^'\"]+)['\"]",  # getenv('VAR_NAME')
            r"process\.env\.([A-Z_]+)",  # process.env.VAR_NAME (Node.js)
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                var_name = match.group(1)
                env_vars.add(var_name)
    except Exception as e:
        pass
    
    return {
        'file': str(file_path),
        'env_vars': env_vars
    }

def main():
    project_root = Path(__file__).parent.parent
    
    print("=" * 60)
    print("SCAN: Использование ENV переменных")
    print("=" * 60)
    print()
    
    all_env_vars: Dict[str, Set[str]] = {}  # var_name -> set of files
    
    # Сканируем все Python файлы
    for py_file in project_root.rglob("*.py"):
        if 'venv' in str(py_file) or '__pycache__' in str(py_file):
            continue
        
        result = scan_env_usage(py_file)
        for var_name in result['env_vars']:
            if var_name not in all_env_vars:
                all_env_vars[var_name] = set()
            all_env_vars[var_name].add(result['file'])
    
    # Показываем результаты
    if all_env_vars:
        print(f"[INFO] Найдено {len(all_env_vars)} уникальных ENV переменных:")
        print()
        for var_name in sorted(all_env_vars.keys()):
            files = all_env_vars[var_name]
            print(f"   {var_name}")
            print(f"      Используется в {len(files)} файле(ах):")
            for file_path in sorted(files)[:5]:  # Показываем первые 5
                rel_path = Path(file_path).relative_to(project_root)
                print(f"         - {rel_path}")
            if len(files) > 5:
                print(f"         ... и ещё {len(files) - 5}")
            print()
    else:
        print("[OK] ENV переменные не найдены")
        print()
    
    print("=" * 60)
    print("SCAN завершён")
    print("=" * 60)

if __name__ == "__main__":
    main()
