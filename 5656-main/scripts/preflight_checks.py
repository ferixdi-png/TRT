#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PREFLIGHT CHECKS - Запускается ДО verify_project.py
Проверяет критические зависимости и настройки
"""

import sys
import os
import io
import json
from pathlib import Path
from datetime import datetime, timedelta

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RESET = '\033[0m'

project_root = Path(__file__).parent.parent
errors = []


def check_pytest():
    """1. Проверка pytest как системной зависимости"""
    try:
        import pytest
        print(f"{GREEN}[PASS]{RESET} pytest доступен (v{pytest.__version__})")
        return True
    except ImportError:
        error_msg = "FAIL pytest не установлен - требуется для тестов"
        print(f"{RED}{error_msg}{RESET}")
        errors.append(error_msg)
        return False


def check_sync_kie_models():
    """2. Синхронизация моделей KIE перед проверками"""
    sync_script = project_root / "scripts" / "sync_kie_models.py"
    if not sync_script.exists():
        error_msg = "FAIL scripts/sync_kie_models.py не найден"
        print(f"{RED}{error_msg}{RESET}")
        errors.append(error_msg)
        return False
    
    # Проверяем наличие KIE_API_KEY
    kie_api_key = os.getenv("KIE_API_KEY")
    if not kie_api_key:
        print(f"{YELLOW}[SKIP]{RESET} KIE_API_KEY не установлен - пропуск синхронизации (требуется для полной проверки)")
        return True  # Не критично для первого запуска
    
    print(f"{YELLOW}[SYNC]{RESET} Запуск синхронизации моделей KIE...")
    import subprocess
    try:
        result = subprocess.run(
            [sys.executable, str(sync_script)],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=project_root
        )
        if result.returncode == 0:
            print(f"{GREEN}[PASS]{RESET} Синхронизация моделей завершена")
            return True
        else:
            # Проверяем что это не просто отсутствие API ключа
            if "KIE_API_KEY" in result.stderr or "API не вернул модели" in result.stderr:
                print(f"{YELLOW}[WARN]{RESET} Синхронизация пропущена (нет доступа к API) - не критично")
                return True  # Не критично если нет доступа к API
            error_msg = f"FAIL Синхронизация моделей завершилась с ошибкой: {result.stderr[:200]}"
            print(f"{RED}{error_msg}{RESET}")
            errors.append(error_msg)
            return False
    except subprocess.TimeoutExpired:
        error_msg = "FAIL Синхронизация моделей превысила таймаут"
        print(f"{RED}{error_msg}{RESET}")
        errors.append(error_msg)
        return False
    except Exception as e:
        error_msg = f"FAIL Ошибка при синхронизации моделей: {e}"
        print(f"{RED}{error_msg}{RESET}")
        errors.append(error_msg)
        return False


def check_regression_lock():
    """3. Проверка regression-lock (menu_diff.md)"""
    menu_diff = project_root / "artifacts" / "menu_diff.md"
    if not menu_diff.exists():
        print(f"{GREEN}[PASS]{RESET} menu_diff.md не существует (первый запуск)")
        return True
    
    content = menu_diff.read_text(encoding='utf-8', errors='ignore').strip()
    
    # Проверяем что diff пуст или содержит только "No changes"
    if not content or "No changes" in content or "## No changes" in content:
        print(f"{GREEN}[PASS]{RESET} menu_diff.md пуст (нет регрессий)")
        return True
    
    # Если есть изменения, требуем явного объяснения
    if "## Added" in content or "## Removed" in content:
        # Проверяем наличие объяснения в report
        report_file = project_root / "AUTOPILOT_FINAL_REPORT.md"
        if report_file.exists():
            report_content = report_file.read_text(encoding='utf-8', errors='ignore')
            if "explicit reason" in report_content.lower() or "регрессия" in report_content.lower():
                print(f"{YELLOW}[WARN]{RESET} menu_diff.md содержит изменения, но есть объяснение в отчёте")
                return True
        
        error_msg = "FAIL menu_diff.md содержит изменения - требуется явное объяснение в AUTOPILOT_FINAL_REPORT.md"
        print(f"{RED}{error_msg}{RESET}")
        errors.append(error_msg)
        return False
    
    print(f"{GREEN}[PASS]{RESET} menu_diff.md проверен")
    return True


def check_watchdog():
    """4. Проверка watchdog (verify_project.py запускался <N часов назад)"""
    # Проверяем флаг выключения watchdog
    watchdog_enabled = os.getenv("PREFLIGHT_WATCHDOG", "1") != "0"
    if not watchdog_enabled:
        print(f"{YELLOW}[SKIP]{RESET} Watchdog выключен через PREFLIGHT_WATCHDOG=0")
        return True
    
    # Получаем максимальное количество часов (по умолчанию 24)
    try:
        max_hours = float(os.getenv("PREFLIGHT_WATCHDOG_MAX_HOURS", "24"))
    except ValueError:
        max_hours = 24
    
    verify_timestamp_file = project_root / "artifacts" / "verify_last_pass.json"
    
    if not verify_timestamp_file.exists():
        # Первый запуск - не создаём файл (он будет создан verify_project.py)
        print(f"{YELLOW}[SKIP]{RESET} Watchdog файл не существует (первый запуск или чистое окружение)")
        print(f"{YELLOW}[INFO]{RESET} Файл будет создан после успешного запуска verify_project.py")
        return True
    
    try:
        with open(verify_timestamp_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            last_pass_str = data.get("last_pass", "")
            if not last_pass_str:
                print(f"{YELLOW}[SKIP]{RESET} Watchdog файл существует, но last_pass отсутствует")
                return True
            
            last_pass = datetime.fromisoformat(last_pass_str)
            now = datetime.now()
            hours_ago = (now - last_pass).total_seconds() / 3600
            
            if hours_ago > max_hours:
                # Предупреждение, но не ошибка на dev окружении
                env = os.getenv("ENV", os.getenv("APP_ENV", "prod")).lower()
                if env in ("dev", "development", "test"):
                    print(f"{YELLOW}[WARN]{RESET} verify_project.py не запускался {hours_ago:.1f} часов назад (требуется <{max_hours}h)")
                    print(f"{YELLOW}[INFO]{RESET} В dev окружении это предупреждение, не ошибка")
                    return True
                else:
                    error_msg = f"FAIL verify_project.py не запускался {hours_ago:.1f} часов назад (требуется <{max_hours}h)"
                    print(f"{RED}{error_msg}{RESET}")
                    errors.append(error_msg)
                    return False
            else:
                print(f"{GREEN}[PASS]{RESET} verify_project.py запускался {hours_ago:.1f} часов назад (<{max_hours}h)")
                return True
    except Exception as e:
        # На dev окружении не падаем на ошибках чтения
        env = os.getenv("ENV", os.getenv("APP_ENV", "prod")).lower()
        if env in ("dev", "development", "test"):
            print(f"{YELLOW}[WARN]{RESET} Ошибка при чтении watchdog файла: {e}")
            return True
        else:
            error_msg = f"FAIL Ошибка при чтении timestamp: {e}"
            print(f"{RED}{error_msg}{RESET}")
            errors.append(error_msg)
            return False


def check_production_sentinel():
    """5. Проверка production sentinel (APP_ENV и FAKE_KIE_MODE)"""
    app_env = os.getenv("APP_ENV", os.getenv("ENV", "prod")).lower()
    fake_kie_mode = os.getenv("FAKE_KIE_MODE", "0") == "1"
    test_mode = os.getenv("TEST_MODE", "0") == "1"
    
    # Проверка 1: prod + FAKE_KIE_MODE=1 → FAIL
    if app_env == "prod" and fake_kie_mode:
        error_msg = "FAIL APP_ENV=prod но FAKE_KIE_MODE=1 - недопустимо в production"
        print(f"{RED}{error_msg}{RESET}")
        errors.append(error_msg)
        return False
    
    # Проверка 2: test → REQUIRE FAKE_KIE_MODE=1
    if app_env == "test" and not fake_kie_mode:
        error_msg = "FAIL APP_ENV=test но FAKE_KIE_MODE=0 - требуется FAKE_KIE_MODE=1 для тестов"
        print(f"{RED}{error_msg}{RESET}")
        errors.append(error_msg)
        return False
    
    # Проверка 3: test_mode тоже требует FAKE_KIE_MODE
    if test_mode and not fake_kie_mode:
        error_msg = "FAIL TEST_MODE=1 но FAKE_KIE_MODE=0 - требуется FAKE_KIE_MODE=1"
        print(f"{RED}{error_msg}{RESET}")
        errors.append(error_msg)
        return False
    
    print(f"{GREEN}[PASS]{RESET} Production sentinel проверен (APP_ENV={app_env}, FAKE_KIE_MODE={fake_kie_mode})")
    return True


def main():
    """Главная функция"""
    print("\n" + "="*80)
    print("PREFLIGHT CHECKS - Критические проверки перед verify_project.py")
    print("="*80)
    
    os.chdir(project_root)
    
    checks = [
        ("Pytest Availability", check_pytest),
        ("Sync KIE Models", check_sync_kie_models),
        ("Regression Lock", check_regression_lock),
        ("Watchdog", check_watchdog),
        ("Production Sentinel", check_production_sentinel),
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\n[CHECK] {name}")
        success = check_func()
        results.append((name, success))
    
    print("\n" + "="*80)
    print("PREFLIGHT SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = f"{GREEN}[PASS]{RESET}" if success else f"{RED}[FAIL]{RESET}"
        print(f"{status} {name}")
    
    print(f"\n{passed}/{total} preflight checks passed")
    
    if passed == total:
        print(f"\n{GREEN}ALL PREFLIGHT CHECKS PASSED!{RESET}")
        return 0
    else:
        print(f"\n{RED}PREFLIGHT CHECKS FAILED!{RESET}")
        print("\nErrors:")
        for error in errors:
            print(f"  - {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
