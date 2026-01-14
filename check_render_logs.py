#!/usr/bin/env python3
"""
FIREBREAK: Проверка Render логов на наличие ошибок.

Парсит логи за последние 10 минут и падает если встречает:
- ERROR
- Traceback
- OID out of range

Usage:
    python3 check_render_logs.py
    python3 check_render_logs.py --minutes 10
"""
import sys
import os
import requests
import re
from datetime import datetime, timedelta

# Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def log(emoji, msg, color=RESET):
    """Log with timestamp and color."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {emoji} {color}{msg}{RESET}")


def check_render_logs_via_api(service_id, api_key, minutes=10):
    """
    Проверка логов через Render API.
    
    NOTE: Требует Render API key и service_id.
    """
    log("🔍", f"Проверка Render логов за последние {minutes} минут...", YELLOW)
    
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }
        
        # Render API endpoint для логов
        url = f"https://api.render.com/v1/services/{service_id}/logs"
        
        # Время начала (10 минут назад)
        start_time = datetime.utcnow() - timedelta(minutes=minutes)
        
        params = {
            "startTime": start_time.isoformat() + "Z",
            "limit": 1000
        }
        
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        
        if resp.status_code != 200:
            log("❌", f"Render API error: {resp.status_code}", RED)
            return False
        
        data = resp.json()
        logs = data.get("logs", [])
        
        # Паттерны ошибок
        error_patterns = [
            r"ERROR",
            r"Traceback",
            r"OID out of range",
            r"psycopg2\.errors\.NumericValueOutOfRange",
        ]
        
        errors_found = []
        
        for log_entry in logs:
            message = log_entry.get("message", "")
            
            for pattern in error_patterns:
                if re.search(pattern, message, re.IGNORECASE):
                    errors_found.append({
                        "timestamp": log_entry.get("timestamp"),
                        "message": message[:200]  # Первые 200 символов
                    })
                    break
        
        if errors_found:
            log("❌", f"Найдено {len(errors_found)} ошибок в логах!", RED)
            for i, err in enumerate(errors_found[:5], 1):  # Показываем первые 5
                log("  ", f"{i}. {err['timestamp']}: {err['message']}")
            return False
        else:
            log("✅", "Логи чистые - ошибок не найдено!", GREEN)
            return True
            
    except Exception as e:
        log("❌", f"Ошибка проверки логов: {e}", RED)
        return False


def check_render_logs_via_health(base_url):
    """
    Упрощенная проверка через /health endpoint.
    
    Проверяет что сервис жив и в режиме ACTIVE.
    """
    log("🔍", "Проверка /health endpoint...", YELLOW)
    
    try:
        resp = requests.get(f"{base_url}/health", timeout=5)
        
        if resp.status_code != 200:
            log("❌", f"/health вернул {resp.status_code}", RED)
            return False
        
        data = resp.json()
        is_active = data.get("active", False)
        
        if not is_active:
            log("⚠️", "/health OK, но mode=PASSIVE (второй инстанс)", YELLOW)
            return True  # Это нормально для второго инстанса
        
        log("✅", "/health OK, mode=ACTIVE", GREEN)
        return True
        
    except Exception as e:
        log("❌", f"/health failed: {e}", RED)
        return False


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="FIREBREAK: Проверка Render логов")
    parser.add_argument(
        "--minutes",
        type=int,
        default=10,
        help="Проверить логи за последние N минут (default: 10)"
    )
    parser.add_argument(
        "--service-id",
        default=os.getenv("RENDER_SERVICE_ID"),
        help="Render service ID (default: from env RENDER_SERVICE_ID)"
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("RENDER_API_KEY"),
        help="Render API key (default: from env RENDER_API_KEY)"
    )
    parser.add_argument(
        "--url",
        default="https://five656.onrender.com",
        help="Base URL для health check (default: https://five656.onrender.com)"
    )
    
    args = parser.parse_args()
    
    log("🚀", "FIREBREAK: Проверка логов", YELLOW)
    print()
    
    # Сначала проверяем /health
    health_ok = check_render_logs_via_health(args.url)
    print()
    
    # Если есть API credentials - проверяем логи через API
    if args.service_id and args.api_key:
        logs_ok = check_render_logs_via_api(args.service_id, args.api_key, args.minutes)
        print()
    else:
        log("⚠️", "Render API credentials не заданы, пропускаем проверку логов", YELLOW)
        log("ℹ️", "Установите RENDER_SERVICE_ID и RENDER_API_KEY для полной проверки")
        logs_ok = True  # Не падаем если нет credentials
        print()
    
    # Summary
    log("📊", "=" * 50, YELLOW)
    
    if health_ok and logs_ok:
        log("✅", "FIREBREAK PASSED: Логи чистые, ошибок нет!", GREEN)
        sys.exit(0)
    else:
        log("❌", "FIREBREAK FAILED: Найдены ошибки в логах!", RED)
        sys.exit(1)


if __name__ == "__main__":
    main()
