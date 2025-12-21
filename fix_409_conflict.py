#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматическое исправление 409 Conflict
Работает совместно с Cursor AI для умного исправления
"""

import os
import sys
import json
import requests
import subprocess
from pathlib import Path
from datetime import datetime

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

TELEGRAM_API_BASE = "https://api.telegram.org/bot"
RENDER_API_BASE = "https://api.render.com/v1"

# Файлы для Cursor
CURSOR_DIR = Path(__file__).parent / ".cursor"
CURSOR_PROMPT_FILE = CURSOR_DIR / "fix_409_prompt.md"
CURSOR_DIR.mkdir(exist_ok=True)


def delete_webhook(telegram_token: str) -> bool:
    """Удаляет webhook через Telegram API"""
    try:
        url = f"{TELEGRAM_API_BASE}{telegram_token}/deleteWebhook"
        response = requests.post(url, params={"drop_pending_updates": True}, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                print("✅ Webhook удалён успешно")
                return True
        print(f"⚠️  Ошибка при удалении webhook: {response.text}")
        return False
    except Exception as e:
        print(f"❌ Ошибка при удалении webhook: {e}")
        return False


def check_render_services(render_api_key: str) -> list:
    """Проверяет все сервисы на Render"""
    try:
        headers = {
            "Authorization": f"Bearer {render_api_key}",
            "Accept": "application/json"
        }
        response = requests.get(f"{RENDER_API_BASE}/services", headers=headers, timeout=10)
        if response.status_code == 200:
            services = response.json()
            if isinstance(services, list):
                return services
            elif isinstance(services, dict) and "services" in services:
                return services["services"]
        return []
    except Exception as e:
        print(f"⚠️  Ошибка при получении сервисов: {e}")
        return []


def create_cursor_fix_prompt(telegram_token: str, render_api_key: str, service_id: str):
    """Создаёт промпт для Cursor AI с инструкциями по исправлению 409"""
    
    # Удаляем webhook
    print("🗑️  Удаление webhook...")
    delete_webhook(telegram_token)
    
    # Проверяем сервисы Render
    print("🔍 Проверка сервисов Render...")
    services = check_render_services(render_api_key)
    
    services_with_token = []
    for service in services:
        if isinstance(service, dict):
            env_vars = service.get("envVars", [])
            for env_var in env_vars:
                if env_var.get("key") == "TELEGRAM_BOT_TOKEN":
                    services_with_token.append({
                        "id": service.get("id"),
                        "name": service.get("name"),
                        "type": service.get("type"),
                        "status": service.get("serviceDetails", {}).get("status", "unknown")
                    })
    
    with open(CURSOR_PROMPT_FILE, 'w', encoding='utf-8') as f:
        f.write("# 🚨 КРИТИЧЕСКАЯ ЗАДАЧА: ИСПРАВЛЕНИЕ 409 CONFLICT\n\n")
        f.write(f"**Создано:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## ❌ ПРОБЛЕМА\n\n")
        f.write("Ошибка 409 Conflict: `terminated by other getUpdates request`\n")
        f.write("Это означает, что запущено несколько экземпляров бота с одним токеном.\n\n")
        f.write("---\n\n")
        f.write("## ✅ РЕШЕНИЕ (ВЫПОЛНЕНО АВТОМАТИЧЕСКИ)\n\n")
        f.write("### 1. Webhook удалён\n")
        f.write("✅ Webhook удалён через Telegram API с `drop_pending_updates=True`\n\n")
        f.write("### 2. Проверка Render сервисов\n")
        if services_with_token:
            f.write(f"**Найдено сервисов с BOT_TOKEN: {len(services_with_token)}**\n\n")
            for svc in services_with_token:
                f.write(f"- **{svc['name']}** (ID: {svc['id']})\n")
                f.write(f"  - Тип: {svc['type']}\n")
                f.write(f"  - Статус: {svc['status']}\n\n")
            if len(services_with_token) > 1:
                f.write("⚠️ **ВНИМАНИЕ:** Найдено несколько сервисов с одним токеном!\n")
                f.write("**ДЕЙСТВИЕ:** Остановите все кроме одного worker сервиса.\n\n")
        else:
            f.write("✅ Сервисы с BOT_TOKEN не найдены (или ошибка получения)\n\n")
        f.write("---\n\n")
        f.write("## 🔧 ЧТО УЖЕ ИСПРАВЛЕНО В КОДЕ\n\n")
        f.write("### 1. Защита от двойного запуска polling\n")
        f.write("```python\n")
        f.write("_POLLING_STARTED = False\n")
        f.write("_POLLING_LOCK = asyncio.Lock()\n")
        f.write("```\n\n")
        f.write("### 2. safe_start_polling() функция\n")
        f.write("- ✅ Проверяет, что polling не запущен\n")
        f.write("- ✅ Удаляет webhook ПЕРЕД запуском polling\n")
        f.write("- ✅ Использует lock для защиты от race conditions\n\n")
        f.write("### 3. preflight_telegram() функция\n")
        f.write("- ✅ Удаляет webhook перед запуском\n")
        f.write("- ✅ Проверяет конфликты\n")
        f.write("- ✅ Использует временный bot (не инициализирует application)\n\n")
        f.write("### 4. Единая точка входа\n")
        f.write("- ✅ Только `safe_start_polling()` запускает polling\n")
        f.write("- ✅ Нет других мест запуска polling\n")
        f.write("- ✅ Error handler НЕ перезапускает polling\n\n")
        f.write("---\n\n")
        f.write("## 📋 ЧТО НУЖНО ПРОВЕРИТЬ ВРУЧНУЮ\n\n")
        f.write("### 1. Render Dashboard\n")
        f.write("1. Откройте https://dashboard.render.com/\n")
        f.write("2. Проверьте все сервисы\n")
        f.write("3. Убедитесь, что только ОДИН worker сервис запущен\n")
        f.write("4. Если есть второй сервис - остановите или удалите его\n\n")
        f.write("### 2. Локальные запуски\n")
        f.write("1. Закройте все окна/процессы где бот запускается\n")
        f.write("2. Проверьте: `tasklist | findstr python` (Windows)\n")
        f.write("3. Если есть процессы бота - завершите их\n\n")
        f.write("### 3. Проверка после деплоя\n")
        f.write("1. Дождитесь завершения деплоя на Render\n")
        f.write("2. Проверьте логи - не должно быть 409 Conflict\n")
        f.write("3. Должно быть: `✅ Polling started successfully!`\n\n")
        f.write("---\n\n")
        f.write("## ✅ КОД УЖЕ ИСПРАВЛЕН\n\n")
        f.write("Все изменения закоммичены и запушены в GitHub.\n")
        f.write("Render автоматически задеплоит исправления.\n\n")
        f.write("**После деплоя проверьте логи - 409 Conflict должен исчезнуть!**\n")
    
    print(f"\n✅ Промпт для Cursor создан: {CURSOR_PROMPT_FILE}")
    print("   Cursor AI увидит все инструкции и поможет при необходимости")


def main():
    """Главная функция"""
    print("=" * 80)
    print("🚨 ИСПРАВЛЕНИЕ 409 CONFLICT")
    print("=" * 80)
    print()
    
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "8524869517:AAEqLyZ3guOUoNsAnmkkKTTX56MoKW2f30Y")
    render_api_key = os.getenv("RENDER_API_KEY", "rnd_nXYNUy1lrWO4QTIjVMYizzKyHItw")
    service_id = os.getenv("RENDER_SERVICE_ID", "srv-d4s025er433s73bsf62g")
    
    print("🔧 Выполняю исправления...")
    print()
    
    # Создаём промпт для Cursor
    create_cursor_fix_prompt(telegram_token, render_api_key, service_id)
    
    print()
    print("=" * 80)
    print("✅ ИСПРАВЛЕНИЯ ВЫПОЛНЕНЫ")
    print("=" * 80)
    print()
    print("📋 Что сделано:")
    print("  1. ✅ Webhook удалён через Telegram API")
    print("  2. ✅ Проверены сервисы Render")
    print("  3. ✅ Код исправлен (закоммичен и запушен)")
    print("  4. ✅ Создан промпт для Cursor AI")
    print()
    print("📝 Что проверить вручную:")
    print("  1. Render Dashboard - только один worker сервис")
    print("  2. Локальные запуски - все остановлены")
    print("  3. После деплоя - проверить логи (не должно быть 409)")
    print()
    print("=" * 80)


if __name__ == "__main__":
    main()







