#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматический деплой на Render и просмотр логов
Используется при любой команде для автоматического деплоя и мониторинга
"""

import os
import sys
import subprocess
import time
import requests
from datetime import datetime
from typing import Optional

# Render API endpoints
RENDER_API_BASE = "https://api.render.com/v1"

def get_render_api_key() -> Optional[str]:
    """Получает API ключ Render из переменных окружения"""
    api_key = os.getenv("RENDER_API_KEY")
    if not api_key:
        print("⚠️  RENDER_API_KEY не установлен в переменных окружения")
        print("💡 Установите: set RENDER_API_KEY=your_key_here (Windows)")
        return None
    return api_key

def get_service_id() -> Optional[str]:
    """Получает Service ID из переменных окружения"""
    service_id = os.getenv("RENDER_SERVICE_ID")
    if not service_id:
        print("⚠️  RENDER_SERVICE_ID не установлен")
        print("💡 Установите: set RENDER_SERVICE_ID=your_service_id (Windows)")
    return service_id

def git_commit_and_push(message: str = None):
    """Автоматически коммитит и пушит изменения в Git (запускает деплой на Render)"""
    if not message:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"Auto deploy: {timestamp}"
    
    print("=" * 80)
    print("🚀 АВТОМАТИЧЕСКИЙ ДЕПЛОЙ НА RENDER")
    print("=" * 80)
    print()
    
    try:
        # Проверяем, есть ли изменения
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True
        )
        
        if not result.stdout.strip():
            print("ℹ️  Нет изменений для коммита")
            return True
        
        print(f"📝 Найдены изменения, коммитим...")
        print(f"   Сообщение: {message}")
        print()
        
        # Добавляем все изменения
        subprocess.run(["git", "add", "."], check=True, capture_output=True)
        print("✅ Изменения добавлены в staging")
        
        # Коммитим
        subprocess.run(["git", "commit", "-m", message], check=True, capture_output=True)
        print("✅ Коммит создан")
        
        # Пушим
        print("📤 Отправляем изменения на GitHub...")
        result = subprocess.run(
            ["git", "push", "origin", "main"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Изменения отправлены на GitHub")
            print("🔄 Render автоматически начнет деплой...")
            return True
        else:
            print(f"❌ Ошибка при push: {result.stderr}")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка при выполнении git команды: {e}")
        return False
    except FileNotFoundError:
        print("❌ Git не найден. Убедитесь, что Git установлен и доступен в PATH")
        return False

def get_render_logs(api_key: str, service_id: str, lines: int = 50):
    """Получает логи с Render"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }
    
    try:
        url = f"{RENDER_API_BASE}/logs"
        params = {
            "resource": service_id,
            "limit": lines
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        logs_data = response.json()
        
        # Обрабатываем разные форматы ответа
        if isinstance(logs_data, list):
            logs = logs_data
        elif isinstance(logs_data, dict):
            logs = logs_data.get("logs", logs_data.get("data", logs_data.get("items", [])))
        else:
            logs = []
        
        return logs
        
    except Exception as e:
        print(f"❌ Ошибка при получении логов: {e}")
        return None

def display_logs(logs, show_errors: bool = True):
    """Отображает логи с подсветкой ошибок"""
    if not logs:
        print("ℹ️  Логи пусты или недоступны")
        return
    
    print("=" * 80)
    print("📊 ЛОГИ RENDER")
    print("=" * 80)
    print()
    
    errors_found = []
    warnings_found = []
    
    for log_entry in logs[-30:]:  # Последние 30 строк
        if isinstance(log_entry, dict):
            timestamp = log_entry.get("timestamp", "")
            message = log_entry.get("message", log_entry.get("text", ""))
            level = log_entry.get("level", "INFO")
            
            message_str = str(message)
            level_upper = str(level).upper()
            
            # Определяем тип сообщения
            if "error" in message_str.lower() or level_upper == "ERROR":
                errors_found.append(message_str)
                print(f"❌ [{timestamp}] {message_str[:200]}")
            elif "warning" in message_str.lower() or level_upper == "WARNING":
                warnings_found.append(message_str)
                print(f"⚠️  [{timestamp}] {message_str[:200]}")
            else:
                print(f"ℹ️  [{timestamp}] {message_str[:200]}")
        else:
            print(f"ℹ️  {str(log_entry)[:200]}")
    
    print()
    print("=" * 80)
    
    if errors_found:
        print(f"🚨 Найдено {len(errors_found)} ошибок в логах!")
        if show_errors:
            print("\nПоследние ошибки:")
            for error in errors_found[-5:]:
                print(f"   • {error[:150]}")
    elif warnings_found:
        print(f"⚠️  Найдено {len(warnings_found)} предупреждений")
    else:
        print("✅ Критических ошибок не найдено")

def monitor_deploy(api_key: str, service_id: str, max_wait: int = 300):
    """Мониторит процесс деплоя и показывает логи"""
    print()
    print("=" * 80)
    print("🔄 МОНИТОРИНГ ДЕПЛОЯ")
    print("=" * 80)
    print()
    print(f"⏳ Ожидание начала деплоя (максимум {max_wait} секунд)...")
    print("   Нажмите Ctrl+C для остановки")
    print()
    
    start_time = time.time()
    last_log_count = 0
    
    try:
        while time.time() - start_time < max_wait:
            logs = get_render_logs(api_key, service_id, lines=100)
            
            if logs:
                current_log_count = len(logs)
                
                # Если появились новые логи
                if current_log_count > last_log_count:
                    print(f"\n📊 Новые логи ({current_log_count} строк):")
                    print("-" * 80)
                    display_logs(logs[-10:], show_errors=True)  # Последние 10 строк
                    last_log_count = current_log_count
                
                # Проверяем на завершение деплоя
                last_messages = [str(log.get("message", "")) if isinstance(log, dict) else str(log) 
                                for log in logs[-5:]]
                
                deploy_complete = any(
                    "live" in msg.lower() or 
                    "started" in msg.lower() or 
                    "running" in msg.lower() or
                    "application started" in msg.lower()
                    for msg in last_messages
                )
                
                if deploy_complete:
                    print("\n✅ Деплой завершен!")
                    break
            
            time.sleep(5)  # Проверяем каждые 5 секунд
            print(".", end="", flush=True)
        
        print()
        print("\n📊 Финальные логи:")
        print("=" * 80)
        final_logs = get_render_logs(api_key, service_id, lines=50)
        if final_logs:
            display_logs(final_logs, show_errors=True)
        
    except KeyboardInterrupt:
        print("\n\n🛑 Мониторинг остановлен пользователем")
        print("\n📊 Текущие логи:")
        print("=" * 80)
        final_logs = get_render_logs(api_key, service_id, lines=30)
        if final_logs:
            display_logs(final_logs, show_errors=True)

def main():
    """Главная функция: деплой + логи"""
    print("=" * 80)
    print("🚀 АВТОМАТИЧЕСКИЙ ДЕПЛОЙ И ПРОСМОТР ЛОГОВ")
    print("=" * 80)
    print()
    
    # 1. Деплой (git push)
    deploy_success = git_commit_and_push()
    
    if not deploy_success:
        print("\n⚠️  Деплой не выполнен, но продолжаем проверку логов...")
    
    # 2. Получаем API ключ и Service ID
    api_key = get_render_api_key()
    service_id = get_service_id()
    
    if not api_key or not service_id:
        print("\n⚠️  Не удалось получить данные для просмотра логов")
        print("💡 Установите переменные окружения:")
        print("   set RENDER_API_KEY=your_key")
        print("   set RENDER_SERVICE_ID=your_service_id")
        return
    
    # 3. Ждем немного перед проверкой логов
    if deploy_success:
        print("\n⏳ Ожидание начала деплоя (10 секунд)...")
        time.sleep(10)
    
    # 4. Мониторим деплой и показываем логи
    monitor_deploy(api_key, service_id, max_wait=300)
    
    print()
    print("=" * 80)
    print("✅ ЗАВЕРШЕНО")
    print("=" * 80)
    print()
    print("💡 Для просмотра логов вручную:")
    print("   python get_render_logs.py --service-id", service_id)
    print("   python get_render_logs.py --service-id", service_id, "--follow")

if __name__ == "__main__":
    main()




