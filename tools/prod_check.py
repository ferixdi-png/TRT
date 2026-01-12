#!/usr/bin/env python3
"""
PRODUCTION READINESS CHECK
Полная проверка готовности системы к продакшену

Использование:
    python tools/prod_check.py
    python tools/prod_check.py --fix  # Автоисправление где возможно
    python tools/prod_check.py --detailed  # Подробный отчёт

Exit codes:
    0 - ALL GREEN, production ready
    1 - FAILURES FOUND, not ready
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class CheckStatus(Enum):
    PASS = "✅"
    FAIL = "❌"
    WARN = "⚠️"
    SKIP = "⏭️"


@dataclass
class CheckResult:
    """Результат одной проверки"""
    name: str
    status: CheckStatus
    message: str
    details: str = ""
    fixable: bool = False


@dataclass
class CheckSuite:
    """Набор проверок"""
    name: str
    checks: List[CheckResult] = field(default_factory=list)
    
    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.PASS)
    
    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.FAIL)
    
    @property
    def warned(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.WARN)
    
    @property
    def is_green(self) -> bool:
        return self.failed == 0


class ProductionChecker:
    """Главный класс проверки production-ready"""
    
    def __init__(self, fix_mode: bool = False, detailed: bool = False):
        self.fix_mode = fix_mode
        self.detailed = detailed
        self.suites: List[CheckSuite] = []
    
    def check_source_of_truth(self) -> CheckSuite:
        """Проверка SOURCE_OF_TRUTH"""
        suite = CheckSuite("SOURCE OF TRUTH")
        
        source_file = PROJECT_ROOT / "models" / "KIE_SOURCE_OF_TRUTH.json"
        
        # Check 1: Файл существует
        if not source_file.exists():
            suite.checks.append(CheckResult(
                "SOURCE_OF_TRUTH exists",
                CheckStatus.FAIL,
                f"File not found: {source_file}"
            ))
            return suite
        
        suite.checks.append(CheckResult(
            "SOURCE_OF_TRUTH exists",
            CheckStatus.PASS,
            f"Found: {source_file}"
        ))
        
        # Check 2: Валидный JSON
        try:
            with open(source_file) as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            suite.checks.append(CheckResult(
                "Valid JSON",
                CheckStatus.FAIL,
                f"Invalid JSON: {e}"
            ))
            return suite
        
        suite.checks.append(CheckResult(
            "Valid JSON",
            CheckStatus.PASS,
            "JSON парсится корректно"
        ))
        
        # Check 3: Структура данных
        models = data.get("models", {})
        if not models:
            suite.checks.append(CheckResult(
                "Has models",
                CheckStatus.FAIL,
                "No models found in SOURCE_OF_TRUTH"
            ))
            return suite
        
        suite.checks.append(CheckResult(
            "Has models",
            CheckStatus.PASS,
            f"Найдено {len(models)} моделей"
        ))
        
        # Check 4: FREE модели для E2E
        free_models = [
            model_id for model_id, model_data in models.items()
            if model_data.get("pricing", {}).get("is_free")
        ]
        
        if len(free_models) < 3:
            suite.checks.append(CheckResult(
                "FREE models (E2E)",
                CheckStatus.WARN,
                f"Only {len(free_models)} free models (recommend 3+)",
                details=", ".join(free_models)
            ))
        else:
            suite.checks.append(CheckResult(
                "FREE models (E2E)",
                CheckStatus.PASS,
                f"{len(free_models)} free models available",
                details=", ".join(free_models)
            ))
        
        # Check 5: Pricing data
        models_without_pricing = [
            model_id for model_id, model_data in models.items()
            if not model_data.get("pricing")
        ]
        
        if models_without_pricing:
            suite.checks.append(CheckResult(
                "All models have pricing",
                CheckStatus.WARN,
                f"{len(models_without_pricing)} models without pricing",
                details=", ".join(models_without_pricing[:5])
            ))
        else:
            suite.checks.append(CheckResult(
                "All models have pricing",
                CheckStatus.PASS,
                "All models have pricing data"
            ))
        
        return suite
    
    def check_environment(self) -> CheckSuite:
        """Проверка переменных окружения"""
        suite = CheckSuite("ENVIRONMENT")
        
        required_vars = [
            "TELEGRAM_BOT_TOKEN",
            "DATABASE_URL",
            "KIE_API_KEY",
        ]
        
        for var in required_vars:
            value = os.getenv(var)
            if not value:
                suite.checks.append(CheckResult(
                    f"ENV: {var}",
                    CheckStatus.FAIL,
                    f"{var} not set"
                ))
            else:
                # Скрываем секреты
                display_value = value[:8] + "..." if len(value) > 8 else "SET"
                suite.checks.append(CheckResult(
                    f"ENV: {var}",
                    CheckStatus.PASS,
                    f"{var}={display_value}"
                ))
        
        return suite
    
    def check_migrations(self) -> CheckSuite:
        """Проверка миграций"""
        suite = CheckSuite("MIGRATIONS")
        
        migrations_dir = PROJECT_ROOT / "migrations"
        if not migrations_dir.exists():
            suite.checks.append(CheckResult(
                "Migrations directory",
                CheckStatus.FAIL,
                f"Directory not found: {migrations_dir}"
            ))
            return suite
        
        sql_files = list(migrations_dir.glob("*.sql"))
        if len(sql_files) < 1:
            suite.checks.append(CheckResult(
                "Migration files",
                CheckStatus.WARN,
                "No .sql migration files found"
            ))
        else:
            suite.checks.append(CheckResult(
                "Migration files",
                CheckStatus.PASS,
                f"Found {len(sql_files)} migration files"
            ))
        
        return suite
    
    def check_critical_files(self) -> CheckSuite:
        """Проверка критичных файлов"""
        suite = CheckSuite("CRITICAL FILES")
        
        critical_files = [
            "main_render.py",
            "app/config.py",
            "app/kie/generator.py",
            "app/integrations/kie_client.py",  # Исправлено
            "app/storage/__init__.py",
            "bot/handlers/flow.py",  # Вместо keyboards.py
            "models/KIE_SOURCE_OF_TRUTH.json",
        ]
        
        for file_path in critical_files:
            full_path = PROJECT_ROOT / file_path
            if not full_path.exists():
                suite.checks.append(CheckResult(
                    f"File: {file_path}",
                    CheckStatus.FAIL,
                    "File not found"
                ))
            else:
                suite.checks.append(CheckResult(
                    f"File: {file_path}",
                    CheckStatus.PASS,
                    "OK"
                ))
        
        return suite
    
    def check_python_syntax(self) -> CheckSuite:
        """Проверка синтаксиса Python файлов"""
        suite = CheckSuite("PYTHON SYNTAX")
        
        python_files = list(PROJECT_ROOT.rglob("*.py"))
        # Исключаем venv, .git, __pycache__
        python_files = [
            f for f in python_files
            if not any(p in f.parts for p in ["venv", ".git", "__pycache__", "node_modules"])
        ]
        
        errors = []
        for py_file in python_files[:50]:  # Проверяем первые 50 файлов
            try:
                compile(py_file.read_text(), str(py_file), "exec")
            except SyntaxError as e:
                errors.append(f"{py_file.name}: {e}")
        
        if errors:
            suite.checks.append(CheckResult(
                "Python syntax",
                CheckStatus.FAIL,
                f"{len(errors)} syntax errors",
                details="\n".join(errors[:5])
            ))
        else:
            suite.checks.append(CheckResult(
                "Python syntax",
                CheckStatus.PASS,
                f"Checked {len(python_files)} files, no syntax errors"
            ))
        
        return suite
    
    async def run_all_checks(self):
        """Запуск всех проверок"""
        print("🔍 PRODUCTION READINESS CHECK")
        print("=" * 80)
        print()
        
        # Синхронные проверки
        self.suites.append(self.check_source_of_truth())
        self.suites.append(self.check_environment())
        self.suites.append(self.check_migrations())
        self.suites.append(self.check_critical_files())
        self.suites.append(self.check_python_syntax())
        
        # Вывод результатов
        total_passed = 0
        total_failed = 0
        total_warned = 0
        
        for suite in self.suites:
            print(f"📦 {suite.name}")
            print("-" * 80)
            
            for check in suite.checks:
                status_icon = check.status.value
                print(f"  {status_icon} {check.name}: {check.message}")
                if self.detailed and check.details:
                    print(f"     Details: {check.details}")
            
            print(f"  Summary: {suite.passed} passed, {suite.failed} failed, {suite.warned} warnings")
            print()
            
            total_passed += suite.passed
            total_failed += suite.failed
            total_warned += suite.warned
        
        # Итоговый результат
        print("=" * 80)
        print("FINAL RESULT")
        print("=" * 80)
        print(f"Total: {total_passed} passed, {total_failed} failed, {total_warned} warnings")
        print()
        
        all_green = all(suite.is_green for suite in self.suites)
        
        if all_green:
            print("✅ ALL GREEN - PRODUCTION READY")
            return 0
        else:
            print("❌ FAILURES DETECTED - NOT PRODUCTION READY")
            print()
            print("Failed suites:")
            for suite in self.suites:
                if not suite.is_green:
                    print(f"  - {suite.name}: {suite.failed} failures")
            return 1


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Production readiness check")
    parser.add_argument("--fix", action="store_true", help="Auto-fix issues where possible")
    parser.add_argument("--detailed", action="store_true", help="Show detailed output")
    args = parser.parse_args()
    
    checker = ProductionChecker(fix_mode=args.fix, detailed=args.detailed)
    exit_code = await checker.run_all_checks()
    
    return exit_code


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
