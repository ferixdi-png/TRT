#!/usr/bin/env python3
"""
Скрипт для поиска блокирующих операций в async функциях
"""

import ast
import sys
import re
from pathlib import Path
from typing import List, Tuple

# Цвета для вывода
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
RESET = '\033[0m'

# Блокирующие операции для поиска
BLOCKING_PATTERNS = [
    (r'open\(', 'open() - используйте aiofiles.open() или asyncio.to_thread()'),
    (r'requests\.(get|post|put|delete|patch)', 'requests.* - используйте aiohttp'),
    (r'Image\.open\(', 'Image.open() - используйте asyncio.to_thread()'),
    (r'pytesseract\.', 'pytesseract.* - используйте asyncio.to_thread()'),
    (r'PIL\.Image\.open\(', 'PIL.Image.open() - используйте asyncio.to_thread()'),
    (r'time\.sleep\(', 'time.sleep() - используйте asyncio.sleep()'),
    (r'subprocess\.', 'subprocess.* - используйте asyncio.create_subprocess_exec()'),
    (r'urllib\.', 'urllib.* - используйте aiohttp'),
]


class BlockingOperationFinder(ast.NodeVisitor):
    """Находит блокирующие операции в async функциях"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.issues: List[Tuple[int, str, str]] = []
        self.current_function = None
        self.is_async = False
    
    def visit_FunctionDef(self, node):
        old_function = self.current_function
        old_is_async = self.is_async
        
        self.current_function = node.name
        self.is_async = isinstance(node, ast.AsyncFunctionDef)
        
        self.generic_visit(node)
        
        self.current_function = old_function
        self.is_async = old_is_async
    
    def visit_Call(self, node):
        if not self.is_async:
            self.generic_visit(node)
            return
        
        # Проверяем вызов функции
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = f"{self._get_attr_name(node.func)}"
        else:
            self.generic_visit(node)
            return
        
        # Проверяем на блокирующие операции
        call_str = ast.unparse(node) if hasattr(ast, 'unparse') else str(node)
        
        for pattern, message in BLOCKING_PATTERNS:
            if re.search(pattern, call_str):
                self.issues.append((
                    node.lineno,
                    call_str[:100],  # Первые 100 символов
                    message
                ))
        
        self.generic_visit(node)
    
    def _get_attr_name(self, node: ast.Attribute) -> str:
        """Получает полное имя атрибута"""
        if isinstance(node.value, ast.Name):
            return f"{node.value.id}.{node.attr}"
        elif isinstance(node.value, ast.Attribute):
            return f"{self._get_attr_name(node.value)}.{node.attr}"
        else:
            return node.attr


def analyze_file(file_path: Path) -> List[Tuple[int, str, str]]:
    """Анализирует файл на блокирующие операции"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content, filename=str(file_path))
        finder = BlockingOperationFinder(str(file_path))
        finder.visit(tree)
        
        return finder.issues
    except Exception as e:
        print(f"{RED}[ERROR]{RESET} Failed to analyze {file_path}: {e}")
        return []


def main():
    """Главная функция"""
    project_root = Path(__file__).parent.parent
    
    print("=" * 60)
    print("SCAN: Блокирующие операции в async функциях")
    print("=" * 60)
    print()
    
    # Находим все Python файлы
    python_files = []
    for py_file in project_root.rglob('*.py'):
        if '__pycache__' in str(py_file) or 'venv' in str(py_file) or '.venv' in str(py_file):
            continue
        if 'scripts' in str(py_file) and py_file.name.startswith('scan_'):
            continue  # Пропускаем сами скрипты сканирования
        python_files.append(py_file)
    
    print(f"{YELLOW}[SCAN]{RESET} Анализ {len(python_files)} файлов...")
    print()
    
    all_issues = []
    for py_file in python_files:
        issues = analyze_file(py_file)
        if issues:
            rel_path = py_file.relative_to(project_root)
            all_issues.append((rel_path, issues))
    
    # Выводим результаты
    if all_issues:
        print(f"{RED}[FOUND]{RESET} Найдено блокирующих операций:")
        print()
        
        for file_path, issues in all_issues:
            print(f"{YELLOW}File:{RESET} {file_path}")
            for line_num, call_str, message in issues:
                print(f"  Line {line_num}: {message}")
                print(f"    {call_str}")
            print()
        
        print("=" * 60)
        print(f"{RED}[FAIL]{RESET} Найдено {sum(len(issues) for _, issues in all_issues)} блокирующих операций")
        return 1
    else:
        print(f"{GREEN}[OK]{RESET} Блокирующих операций не найдено")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())
