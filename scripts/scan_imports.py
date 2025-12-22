#!/usr/bin/env python3
"""
Скрипт для поиска циклических импортов и тяжёлых импортов
"""

import ast
import sys
import os
from pathlib import Path
from typing import Dict, Set, List, Tuple
from collections import defaultdict

# Цвета для вывода
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
RESET = '\033[0m'


class ImportAnalyzer(ast.NodeVisitor):
    """Анализатор импортов в Python файлах"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.imports: Set[str] = set()
        self.from_imports: Dict[str, Set[str]] = defaultdict(set)
        self.is_heavy = False
        
    def visit_Import(self, node):
        for alias in node.names:
            self.imports.add(alias.name)
    
    def visit_ImportFrom(self, node):
        if node.module:
            if node.names:
                for alias in node.names:
                    self.from_imports[node.module].add(alias.name or '*')
            else:
                self.from_imports[node.module].add('*')
    
    def check_heavy_imports(self):
        """Проверяет наличие тяжёлых импортов"""
        heavy_modules = {
            'PIL', 'Pillow', 'Image',
            'pytesseract',
            'numpy', 'pandas',
            'tensorflow', 'torch',
            'cv2', 'opencv',
            'sklearn', 'scipy'
        }
        
        for module in self.imports:
            if any(heavy in module for heavy in heavy_modules):
                self.is_heavy = True
                return True
        
        for module in self.from_imports:
            if any(heavy in module for heavy in heavy_modules):
                self.is_heavy = True
                return True
        
        return False


def analyze_file(file_path: Path) -> Tuple[Set[str], Dict[str, Set[str]], bool]:
    """Анализирует файл и возвращает импорты"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content, filename=str(file_path))
        analyzer = ImportAnalyzer(str(file_path))
        analyzer.visit(tree)
        analyzer.check_heavy_imports()
        
        return analyzer.imports, dict(analyzer.from_imports), analyzer.is_heavy
    except Exception as e:
        print(f"{RED}[ERROR]{RESET} Failed to analyze {file_path}: {e}")
        return set(), {}, False


def build_import_graph(project_root: Path) -> Dict[str, Set[str]]:
    """Строит граф импортов"""
    graph = defaultdict(set)
    file_to_module = {}
    
    # Собираем все Python файлы
    python_files = list(project_root.rglob('*.py'))
    
    for py_file in python_files:
        # Пропускаем __pycache__ и виртуальные окружения
        if '__pycache__' in str(py_file) or 'venv' in str(py_file) or '.venv' in str(py_file):
            continue
        
        # Получаем модуль из пути
        rel_path = py_file.relative_to(project_root)
        module_parts = list(rel_path.parts[:-1]) + [rel_path.stem]
        module_name = '.'.join(module_parts)
        file_to_module[str(py_file)] = module_name
        
        # Анализируем импорты
        imports, from_imports, _ = analyze_file(py_file)
        
        # Добавляем в граф
        for imp in imports:
            # Пытаемся найти файл для импорта
            if imp in file_to_module.values():
                graph[module_name].add(imp)
        
        for module, names in from_imports.items():
            if module in file_to_module.values() or module.startswith('app.') or module.startswith('bot_'):
                graph[module_name].add(module)
    
    return graph


def find_cycles(graph: Dict[str, Set[str]]) -> List[List[str]]:
    """Находит циклы в графе импортов"""
    cycles = []
    visited = set()
    rec_stack = set()
    path = []
    
    def dfs(node: str):
        if node in rec_stack:
            # Найден цикл
            cycle_start = path.index(node)
            cycle = path[cycle_start:] + [node]
            cycles.append(cycle)
            return
        
        if node in visited:
            return
        
        visited.add(node)
        rec_stack.add(node)
        path.append(node)
        
        for neighbor in graph.get(node, set()):
            dfs(neighbor)
        
        rec_stack.remove(node)
        path.pop()
    
    for node in graph:
        if node not in visited:
            dfs(node)
    
    return cycles


def find_heavy_imports(project_root: Path) -> List[Tuple[str, bool]]:
    """Находит файлы с тяжёлыми импортами"""
    heavy_files = []
    
    python_files = list(project_root.rglob('*.py'))
    
    for py_file in python_files:
        if '__pycache__' in str(py_file) or 'venv' in str(py_file) or '.venv' in str(py_file):
            continue
        
        _, _, is_heavy = analyze_file(py_file)
        if is_heavy:
            heavy_files.append((str(py_file.relative_to(project_root)), is_heavy))
    
    return heavy_files


def main():
    """Главная функция"""
    project_root = Path(__file__).parent.parent
    
    print("=" * 60)
    print("SCAN: Циклические импорты и тяжёлые импорты")
    print("=" * 60)
    print()
    
    # 1. Поиск циклических импортов
    print(f"{YELLOW}[1/2]{RESET} Построение графа импортов...")
    graph = build_import_graph(project_root)
    print(f"   Найдено {len(graph)} модулей с импортами")
    
    print(f"{YELLOW}[2/2]{RESET} Поиск циклов...")
    cycles = find_cycles(graph)
    
    if cycles:
        print(f"{RED}[FOUND]{RESET} Найдено {len(cycles)} циклов:")
        for i, cycle in enumerate(cycles, 1):
            print(f"   Цикл {i}: {' -> '.join(cycle)}")
    else:
        print(f"{GREEN}[OK]{RESET} Циклических импортов не найдено")
    
    print()
    
    # 2. Поиск тяжёлых импортов
    print(f"{YELLOW}[1/1]{RESET} Поиск тяжёлых импортов...")
    heavy_files = find_heavy_imports(project_root)
    
    if heavy_files:
        print(f"{YELLOW}[FOUND]{RESET} Найдено {len(heavy_files)} файлов с тяжёлыми импортами:")
        for file_path, _ in heavy_files:
            print(f"   - {file_path}")
        print(f"   {YELLOW}Примечание:{RESET} Проверьте, что эти импорты ленивые (внутри функций)")
    else:
        print(f"{GREEN}[OK]{RESET} Тяжёлых импортов не найдено")
    
    print()
    print("=" * 60)
    
    # Итоги
    if cycles:
        print(f"{RED}[FAIL]{RESET} Найдены циклические импорты")
        return 1
    else:
        print(f"{GREEN}[PASS]{RESET} Циклических импортов нет")
        return 0


if __name__ == "__main__":
    sys.exit(main())
