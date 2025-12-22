#!/usr/bin/env python3
"""
Скрипт для поиска callback handlers без query.answer()
"""

import ast
import sys
import re
from pathlib import Path
from typing import List, Tuple, Set

# Цвета для вывода
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
RESET = '\033[0m'


class CallbackHandlerFinder(ast.NodeVisitor):
    """Находит callback handlers и проверяет наличие query.answer()"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.handlers: List[Tuple[int, str, bool]] = []  # (line, name, has_answer)
        self.current_function = None
        self.has_query_answer = False
        self.has_query = False
    
    def visit_FunctionDef(self, node):
        old_function = self.current_function
        old_has_answer = self.has_query_answer
        old_has_query = self.has_query
        
        self.current_function = node.name
        self.has_query_answer = False
        self.has_query = False
        
        # Проверяем параметры функции
        for arg in node.args.args:
            if arg.arg in ('update', 'query', 'context'):
                self.has_query = True
        
        self.generic_visit(node)
        
        # Если это async функция с параметрами update/query, это handler
        if isinstance(node, ast.AsyncFunctionDef) and self.has_query:
            self.handlers.append((
                node.lineno,
                node.name,
                self.has_query_answer
            ))
        
        self.current_function = old_function
        self.has_query_answer = old_has_answer
        self.has_query = old_has_query
    
    def visit_Call(self, node):
        # Проверяем вызов query.answer()
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == 'query':
                if node.func.attr == 'answer':
                    self.has_query_answer = True
        
        # Также проверяем update.callback_query.answer()
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == 'answer':
                # Проверяем цепочку атрибутов
                value = node.func.value
                if isinstance(value, ast.Attribute):
                    if value.attr == 'callback_query':
                        if isinstance(value.value, ast.Name) and value.value.id == 'update':
                            self.has_query_answer = True
        
        self.generic_visit(node)


def analyze_file(file_path: Path) -> List[Tuple[int, str, bool]]:
    """Анализирует файл на callback handlers"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content, filename=str(file_path))
        finder = CallbackHandlerFinder(str(file_path))
        finder.visit(tree)
        
        return finder.handlers
    except Exception as e:
        print(f"{RED}[ERROR]{RESET} Failed to analyze {file_path}: {e}")
        return []


def find_callback_handlers_by_pattern(file_path: Path) -> Set[str]:
    """Находит callback handlers по паттернам в коде"""
    handlers = set()
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Ищем async def функции с update или query в параметрах
        for i, line in enumerate(lines, 1):
            if re.search(r'async def \w+\(.*(update|query).*\):', line):
                # Извлекаем имя функции
                match = re.search(r'async def (\w+)', line)
                if match:
                    handlers.add(match.group(1))
    except Exception as e:
        print(f"{RED}[ERROR]{RESET} Failed to read {file_path}: {e}")
    
    return handlers


def main():
    """Главная функция"""
    project_root = Path(__file__).parent.parent
    
    print("=" * 60)
    print("SCAN: Callback handlers без query.answer()")
    print("=" * 60)
    print()
    
    # Анализируем bot_kie.py (основной файл с handlers)
    bot_kie_file = project_root / 'bot_kie.py'
    
    if not bot_kie_file.exists():
        print(f"{RED}[ERROR]{RESET} bot_kie.py not found")
        return 1
    
    print(f"{YELLOW}[SCAN]{RESET} Анализ bot_kie.py...")
    handlers = analyze_file(bot_kie_file)
    
    # Также ищем по паттернам
    pattern_handlers = find_callback_handlers_by_pattern(bot_kie_file)
    
    # Фильтруем handlers без query.answer()
    missing_answer = [h for h in handlers if not h[2]]
    
    if missing_answer:
        print(f"{RED}[FOUND]{RESET} Найдено {len(missing_answer)} handlers без query.answer():")
        print()
        
        for line_num, func_name, has_answer in missing_answer:
            print(f"  Line {line_num}: {func_name}() - {RED}НЕТ query.answer(){RESET}")
        
        print()
        print(f"{YELLOW}Примечание:{RESET} Все callback handlers должны вызывать await query.answer() в начале")
        print("=" * 60)
        print(f"{RED}[FAIL]{RESET} Найдено {len(missing_answer)} handlers без query.answer()")
        return 1
    else:
        print(f"{GREEN}[OK]{RESET} Все callback handlers имеют query.answer()")
        print(f"   Проверено {len(handlers)} handlers")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())
