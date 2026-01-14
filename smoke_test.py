#!/usr/bin/env python3
"""
Smoke test для проверки S0-S2 сценариев.

S0 — Жизнь сервиса: /health всегда 200, показывает ACTIVE/PASSIVE, нет stacktrace
S1 — UX ядро: /start → меню → модель → промпт → результат
S2 — Деньги/кредиты: оплата → начисление → списание → выдача

Usage:
    python3 smoke_test.py
    python3 smoke_test.py --url https://five656.onrender.com
"""
import sys
import os
import requests
import time
from datetime import datetime

# Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def log(emoji, msg, color=RESET):
    """Log with timestamp and color."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {emoji} {color}{msg}{RESET}")

def check_s0_health(base_url):
    """S0: Проверка /health endpoint."""
    log("🔍", "S0: Проверка /health...", YELLOW)
    
    try:
        resp = requests.get(f"{base_url}/health", timeout=5)
        
        if resp.status_code != 200:
            log("❌", f"S0 FAILED: /health returned {resp.status_code}", RED)
            return False
        
        data = resp.json()
        
        # Проверяем наличие ключевых полей (SOURCE_OF_TRUTH.json contract)
        required_fields = ["status", "uptime", "active", "lock_state", "queue"]
        missing = [f for f in required_fields if f not in data]
        
        if missing:
            log("❌", f"S0 FAILED: /health missing fields: {missing}", RED)
            return False
        
        # Проверяем типы (JSON serializable — Decimal недопустим)
        if not isinstance(data.get("uptime"), int):
            log("❌", f"S0 FAILED: uptime must be int, got {type(data.get('uptime'))}", RED)
            return False
        
        if data.get("lock_idle_duration") is not None:
            if not isinstance(data["lock_idle_duration"], (int, float)):
                log("❌", f"S0 FAILED: lock_idle_duration must be number, got {type(data['lock_idle_duration'])}", RED)
                return False
        
        # Проверяем queue schema
        queue = data.get("queue", {})
        if not isinstance(queue.get("queue_depth"), int):
            log("❌", f"S0 FAILED: queue.queue_depth must be int", RED)
            return False
        
        is_active = data.get("active")
        mode = "ACTIVE" if is_active else "PASSIVE"
        
        log("✅", f"S0 PASSED: /health 200 OK, mode={mode}", GREEN)
        log("ℹ️", f"  queue_depth={data.get('queue_depth', 'N/A')}, uptime={data['uptime']}s")
        log("ℹ️", f"  All required fields present, JSON schema valid")
        
        return True
        
    except ValueError as e:
        log("❌", f"S0 FAILED: Invalid JSON response: {e}", RED)
        return False
    except Exception as e:
        log("❌", f"S0 FAILED: {e}", RED)
        return False


def check_s1_bot_responsive(base_url, bot_token=None):
    """S1: Проверка что бот отвечает (через Telegram API)."""
    log("🔍", "S1: Проверка отклика бота...", YELLOW)
    
    if not bot_token:
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not bot_token:
        log("⚠️", "S1 SKIPPED: TELEGRAM_BOT_TOKEN не задан", YELLOW)
        return None
    
    try:
        # Проверяем getMe (бот должен отвечать)
        resp = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getMe",
            timeout=5
        )
        
        if resp.status_code != 200:
            log("❌", f"S1 FAILED: Telegram API returned {resp.status_code}", RED)
            return False
        
        data = resp.json()
        if not data.get("ok"):
            log("❌", f"S1 FAILED: Telegram API error: {data}", RED)
            return False
        
        bot_username = data["result"]["username"]
        log("✅", f"S1 PASSED: Бот @{bot_username} отвечает", GREEN)
        
        # TODO: Можно добавить отправку /start и проверку ответа
        # Но это требует реального chat_id
        
        return True
        
    except Exception as e:
        log("❌", f"S1 FAILED: {e}", RED)
        return False


def check_s2_storage_available():
    """S2: Проверка что storage работает (локально)."""
    log("🔍", "S2: Проверка storage...", YELLOW)
    
    try:
        import asyncio
        from app.storage.json_storage import JsonStorage
        
        async def test_storage():
            storage = JsonStorage()
            test_user_id = 999999999
            balance = await storage.get_user_balance(test_user_id)
            return balance
        
        balance = asyncio.run(test_storage())
        
        log("✅", f"S2 PASSED: Storage доступен, test balance={balance}", GREEN)
        return True
        
    except Exception as e:
        log("❌", f"S2 FAILED: {e}", RED)
        return False


def check_render_logs_no_stacktrace(base_url):
    """Дополнительно: Проверка что в недавних логах нет stacktrace."""
    log("🔍", "Проверка логов на stacktrace...", YELLOW)
    
    # Это можно сделать только если есть доступ к Render API
    # Для упрощения - пропускаем
    log("⚠️", "SKIPPED: Требует Render API key", YELLOW)
    return None


def main():
    """Запуск всех smoke tests."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Smoke test S0-S2")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL сервиса (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--bot-token",
        default=None,
        help="Telegram bot token (default: from env TELEGRAM_BOT_TOKEN)"
    )
    
    args = parser.parse_args()
    
    log("🚀", f"Запуск smoke test для {args.url}", YELLOW)
    print()
    
    results = []
    
    # S0: Health check
    s0_ok = check_s0_health(args.url)
    results.append(("S0 /health", s0_ok))
    print()
    
    # S1: Bot responsive
    s1_ok = check_s1_bot_responsive(args.url, args.bot_token)
    if s1_ok is not None:
        results.append(("S1 Bot responsive", s1_ok))
    print()
    
    # S2: Storage
    s2_ok = check_s2_storage_available()
    results.append(("S2 Storage", s2_ok))
    print()
    
    # Summary
    log("📊", "=" * 50, YELLOW)
    log("📊", "SUMMARY:", YELLOW)
    
    passed = sum(1 for _, ok in results if ok is True)
    failed = sum(1 for _, ok in results if ok is False)
    skipped = sum(1 for _, ok in results if ok is None)
    
    for name, ok in results:
        if ok is True:
            log("✅", f"{name}: PASSED", GREEN)
        elif ok is False:
            log("❌", f"{name}: FAILED", RED)
        else:
            log("⚠️", f"{name}: SKIPPED", YELLOW)
    
    log("📊", "=" * 50, YELLOW)
    log("📊", f"Total: {passed} passed, {failed} failed, {skipped} skipped")
    
    # Exit code
    if failed > 0:
        log("❌", "SMOKE TEST FAILED", RED)
        sys.exit(1)
    elif passed == 0:
        log("⚠️", "SMOKE TEST SKIPPED (all tests skipped)", YELLOW)
        sys.exit(2)
    else:
        log("✅", "SMOKE TEST PASSED", GREEN)
        sys.exit(0)


if __name__ == "__main__":
    main()
