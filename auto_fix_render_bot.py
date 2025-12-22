#!/usr/bin/env python3
"""
Автоматический скрипт для мониторинга и исправления проблем бота на Render
- Отслеживает логи
- Обнаруживает конфликты 409
- Удаляет webhook'и
- Перезапускает сервис при необходимости
"""

import os
import sys
import time
import requests
import asyncio
from datetime import datetime
from typing import Optional, Dict, List

# Render API
RENDER_API_BASE = "https://api.render.com/v1"

# Telegram API
TELEGRAM_API_BASE = "https://api.telegram.org/bot"

class RenderBotMonitor:
    def __init__(self, render_api_key: str, service_id: str, telegram_token: str, owner_id: Optional[str] = None):
        self.render_api_key = render_api_key
        self.service_id = service_id
        self.telegram_token = telegram_token
        self.owner_id = owner_id
        self.headers = {
            "Authorization": f"Bearer {render_api_key}",
            "Accept": "application/json"
        }
        self.conflicts_detected = 0
        self.webhooks_removed = 0
        
    def get_owner_id(self) -> Optional[str]:
        """Получает Owner ID из информации о сервисе"""
        try:
            # Получаем информацию о сервисе
            response = requests.get(f"{RENDER_API_BASE}/services/{self.service_id}", headers=self.headers, timeout=10)
            response.raise_for_status()
            
            service_data = response.json()
            service_info = service_data.get("service", {})
            
            # Owner ID может быть в разных местах
            owner_id = service_info.get("ownerId") or service_info.get("owner", {}).get("id")
            
            if owner_id:
                return owner_id
            
            # Если не найден, пробуем через список сервисов
            services_response = requests.get(f"{RENDER_API_BASE}/services", headers=self.headers, timeout=10)
            services_response.raise_for_status()
            services = services_response.json()
            
            if isinstance(services, list):
                for service in services:
                    service_info = service.get("service", {})
                    if service_info.get("id") == self.service_id:
                        owner_id = service_info.get("ownerId") or service_info.get("owner", {}).get("id")
                        if owner_id:
                            return owner_id
            
            return None
            
        except Exception as e:
            print(f"⚠️  Не удалось получить Owner ID: {e}")
            return None
    
    def verify_service_id(self) -> bool:
        """Проверяет, что Service ID существует и доступен"""
        try:
            # Получаем информацию о сервисе
            response = requests.get(f"{RENDER_API_BASE}/services/{self.service_id}", headers=self.headers, timeout=10)
            response.raise_for_status()
            
            service_data = response.json()
            service_info = service_data.get("service", {})
            
            if service_info.get("id") == self.service_id:
                service_name = service_info.get("name", "N/A")
                print(f"✅ Service ID подтверждён: {service_name}")
                return True
            
            print(f"⚠️  Service ID {self.service_id} не найден")
            return False
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"❌ Service ID {self.service_id} не найден")
            else:
                print(f"⚠️  Ошибка при проверке Service ID: {e}")
            return False
        except Exception as e:
            print(f"⚠️  Не удалось проверить Service ID: {e}")
            return True  # Продолжаем, возможно проблема временная
    
    def get_logs(self, lines: int = 200) -> Optional[List[Dict]]:
        """Получает логи с Render используя правильный endpoint /v1/logs"""
        try:
            # Получаем Owner ID (если еще не получен)
            if not hasattr(self, 'owner_id') or not self.owner_id:
                self.owner_id = self.get_owner_id()
                if not self.owner_id:
                    print("⚠️  Не удалось получить Owner ID, пробую без него...")
            
            # Правильный endpoint для получения логов
            url = f"{RENDER_API_BASE}/logs"
            params = {
                "resource": self.service_id,
                "limit": lines
            }
            
            # Добавляем ownerId если есть
            if self.owner_id:
                params["ownerId"] = self.owner_id
            
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            
            logs_data = response.json()
            
            # Обрабатываем разные форматы ответа
            if isinstance(logs_data, list):
                return logs_data
            elif isinstance(logs_data, dict):
                # Может быть обёрнут в объект
                if "logs" in logs_data:
                    return logs_data["logs"]
                elif "data" in logs_data:
                    return logs_data["data"]
                elif "items" in logs_data:
                    return logs_data["items"]
                else:
                    # Если это один лог-объект
                    return [logs_data]
            else:
                return [logs_data] if logs_data else []
                
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"❌ Логи не найдены для Service ID: {self.service_id}")
                print("💡 Проверьте:")
                print("   1. Правильность Service ID")
                print("   2. Что сервис существует и запущен")
                print("   3. Что есть логи для отображения")
            else:
                print(f"❌ Ошибка HTTP {e.response.status_code}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    print(f"   Детали: {error_detail}")
                except:
                    print(f"   Ответ: {e.response.text[:200]}")
            return None
        except Exception as e:
            print(f"❌ Ошибка при получении логов: {e}")
            return None
    
    def analyze_logs(self, logs: List[Dict]) -> Dict:
        """Анализирует логи на наличие проблем"""
        if not logs:
            return {"conflicts": 0, "errors": 0, "warnings": 0}
        
        conflicts = []
        errors = []
        warnings = []
        
        for log_entry in logs:
            message = ""
            if isinstance(log_entry, dict):
                message = str(log_entry.get("message", log_entry.get("text", "")))
                level = log_entry.get("level", "").upper()
            else:
                message = str(log_entry)
                level = "INFO"
            
            message_lower = message.lower()
            
            if "409" in message or "conflict" in message_lower or "terminated by other getUpdates" in message_lower:
                conflicts.append(message)
            if "error" in message_lower or level == "ERROR":
                errors.append(message)
            if "warning" in message_lower or level == "WARNING":
                warnings.append(message)
        
        return {
            "conflicts": len(conflicts),
            "errors": len(errors),
            "warnings": len(warnings),
            "conflict_messages": conflicts[:5]  # Первые 5 для отчета
        }
    
    def delete_webhook(self) -> bool:
        """Удаляет webhook через Telegram API"""
        try:
            url = f"{TELEGRAM_API_BASE}{self.telegram_token}/deleteWebhook"
            params = {"drop_pending_updates": True}
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            if result.get("ok"):
                print("✅ Webhook успешно удалён")
                self.webhooks_removed += 1
                return True
            else:
                print(f"⚠️  Webhook не был установлен или уже удалён: {result.get('description', 'Unknown')}")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка при удалении webhook: {e}")
            return False
    
    def check_webhook_status(self) -> Dict:
        """Проверяет статус webhook"""
        try:
            url = f"{TELEGRAM_API_BASE}{self.telegram_token}/getWebhookInfo"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            if result.get("ok"):
                webhook_info = result.get("result", {})
                return {
                    "url": webhook_info.get("url", ""),
                    "pending_updates": webhook_info.get("pending_update_count", 0),
                    "exists": bool(webhook_info.get("url"))
                }
            return {"url": "", "pending_updates": 0, "exists": False}
            
        except Exception as e:
            print(f"❌ Ошибка при проверке webhook: {e}")
            return {"url": "", "pending_updates": 0, "exists": False}
    
    def restart_service(self) -> bool:
        """Перезапускает сервис на Render"""
        try:
            url = f"{RENDER_API_BASE}/services/{self.service_id}/deploys"
            data = {"clearBuildCache": False}
            
            response = requests.post(url, headers=self.headers, json=data, timeout=30)
            response.raise_for_status()
            
            deploy = response.json()
            deploy_id = deploy.get("deploy", {}).get("id", "")
            
            if deploy_id:
                print(f"✅ Сервис перезапускается (Deploy ID: {deploy_id})")
                return True
            else:
                print("⚠️  Не удалось получить ID деплоя")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка при перезапуске сервиса: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Ответ сервера: {e.response.text}")
            return False
    
    def suspend_service(self) -> bool:
        """Временно останавливает сервис"""
        try:
            url = f"{RENDER_API_BASE}/services/{self.service_id}/suspend"
            response = requests.post(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            print("✅ Сервис приостановлен")
            return True
        except Exception as e:
            print(f"❌ Ошибка при приостановке сервиса: {e}")
            return False
    
    def resume_service(self) -> bool:
        """Возобновляет работу сервиса"""
        try:
            url = f"{RENDER_API_BASE}/services/{self.service_id}/resume"
            response = requests.post(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            print("✅ Сервис возобновлён")
            return True
        except Exception as e:
            print(f"❌ Ошибка при возобновлении сервиса: {e}")
            return False
    
    def fix_conflict_409(self) -> bool:
        """Автоматически исправляет конфликт 409"""
        print("\n" + "=" * 80)
        print("🔧 АВТОМАТИЧЕСКОЕ ИСПРАВЛЕНИЕ КОНФЛИКТА 409")
        print("=" * 80)
        
        # Шаг 1: Проверяем и удаляем webhook
        print("\n📋 Шаг 1: Проверка webhook...")
        webhook_status = self.check_webhook_status()
        if webhook_status["exists"]:
            print(f"⚠️  Обнаружен webhook: {webhook_status['url']}")
            print(f"   Ожидающих обновлений: {webhook_status['pending_updates']}")
            print("🗑️  Удаляю webhook...")
            self.delete_webhook()
            time.sleep(2)  # Ждем, чтобы Telegram API обработал запрос
        else:
            print("✅ Webhook не установлен")
        
        # Шаг 2: Приостанавливаем сервис
        print("\n📋 Шаг 2: Приостановка сервиса...")
        if self.suspend_service():
            print("⏳ Ожидание 15 секунд...")
            time.sleep(15)
        
        # Шаг 3: Убеждаемся, что webhook удалён
        print("\n📋 Шаг 3: Повторная проверка webhook...")
        webhook_status = self.check_webhook_status()
        if webhook_status["exists"]:
            print("🔄 Webhook всё ещё установлен, повторное удаление...")
            self.delete_webhook()
            time.sleep(2)
        
        # Шаг 4: Возобновляем сервис
        print("\n📋 Шаг 4: Возобновление сервиса...")
        if self.resume_service():
            print("⏳ Ожидание 10 секунд для запуска...")
            time.sleep(10)
        
        # Шаг 5: Проверяем результат
        print("\n📋 Шаг 5: Проверка результата...")
        logs = self.get_logs(lines=50)
        if logs:
            analysis = self.analyze_logs(logs)
            if analysis["conflicts"] == 0:
                print("✅ Конфликт 409 исправлен!")
                return True
            else:
                print(f"⚠️  Конфликт всё ещё присутствует ({analysis['conflicts']} случаев)")
                return False
        
        return True
    
    def monitor_loop(self, interval: int = 60, auto_fix: bool = True):
        """Основной цикл мониторинга"""
        print("=" * 80)
        print("🤖 АВТОМАТИЧЕСКИЙ МОНИТОРИНГ БОТА НА RENDER")
        print("=" * 80)
        print(f"📊 Интервал проверки: {interval} секунд")
        print(f"🔧 Автоисправление: {'Включено' if auto_fix else 'Выключено'}")
        print("Нажмите Ctrl+C для остановки")
        print("=" * 80)
        
        # Проверяем Service ID перед началом
        print("\n🔍 Проверка Service ID...")
        if not self.verify_service_id():
            print("\n❌ Неверный Service ID. Исправьте и попробуйте снова.")
            return
        
        iteration = 0
        
        try:
            while True:
                iteration += 1
                print(f"\n{'=' * 80}")
                print(f"🔄 Проверка #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print("=" * 80)
                
                # Получаем логи
                logs = self.get_logs(lines=200)
                if not logs:
                    print("⚠️  Не удалось получить логи")
                    print("💡 Убедитесь, что сервис запущен и есть логи для отображения")
                    time.sleep(interval)
                    continue
                
                # Анализируем
                analysis = self.analyze_logs(logs)
                
                print(f"\n📊 Статистика:")
                print(f"   Конфликты 409: {analysis['conflicts']}")
                print(f"   Ошибки: {analysis['errors']}")
                print(f"   Предупреждения: {analysis['warnings']}")
                
                # Проверяем webhook
                webhook_status = self.check_webhook_status()
                if webhook_status["exists"]:
                    print(f"\n⚠️  Webhook установлен: {webhook_status['url']}")
                    print(f"   Ожидающих обновлений: {webhook_status['pending_updates']}")
                else:
                    print("\n✅ Webhook не установлен (OK)")
                
                # Если обнаружены конфликты
                if analysis["conflicts"] > 0:
                    self.conflicts_detected += analysis["conflicts"]
                    print(f"\n🚨 ОБНАРУЖЕН КОНФЛИКТ 409!")
                    print(f"   Всего конфликтов за сессию: {self.conflicts_detected}")
                    
                    if analysis["conflict_messages"]:
                        print("\n   Примеры конфликтов:")
                        for msg in analysis["conflict_messages"]:
                            print(f"   - {msg[:100]}...")
                    
                    if auto_fix:
                        print("\n🔧 Запуск автоматического исправления...")
                        if self.fix_conflict_409():
                            print("\n✅ Автоисправление завершено успешно!")
                        else:
                            print("\n⚠️  Автоисправление завершено с предупреждениями")
                    else:
                        print("\n💡 Автоисправление выключено. Исправьте вручную.")
                
                # Если webhook установлен, удаляем его
                if webhook_status["exists"]:
                    print("\n🗑️  Удаляю webhook...")
                    self.delete_webhook()
                
                # Ждем перед следующей проверкой
                print(f"\n⏳ Следующая проверка через {interval} секунд...")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n" + "=" * 80)
            print("🛑 МОНИТОРИНГ ОСТАНОВЛЕН")
            print("=" * 80)
            print(f"📊 Итоговая статистика:")
            print(f"   Обнаружено конфликтов: {self.conflicts_detected}")
            print(f"   Удалено webhook'ов: {self.webhooks_removed}")
            print("=" * 80)


def main():
    """Главная функция"""
    print("=" * 80)
    print("🤖 АВТОМАТИЧЕСКИЙ МОНИТОРИНГ И ИСПРАВЛЕНИЕ БОТА НА RENDER")
    print("=" * 80)
    print()
    
    # Получаем переменные окружения
    render_api_key = os.getenv("RENDER_API_KEY")
    service_id = os.getenv("RENDER_SERVICE_ID")
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    # Если не установлены, запрашиваем
    if not render_api_key:
        print("⚠️  RENDER_API_KEY не установлен")
        render_api_key = input("Введите ваш Render API ключ: ").strip()
        if not render_api_key:
            print("❌ API ключ обязателен!")
            sys.exit(1)
    
    if not service_id:
        print("⚠️  RENDER_SERVICE_ID не установлен")
        service_id = input("Введите ваш Service ID (srv-xxxxx): ").strip()
        if not service_id:
            print("❌ Service ID обязателен!")
            sys.exit(1)
    
    if not telegram_token:
        print("⚠️  TELEGRAM_BOT_TOKEN не установлен")
        telegram_token = input("Введите ваш Telegram Bot Token: ").strip()
        if not telegram_token:
            print("❌ Bot Token обязателен!")
            sys.exit(1)
    
    # Получаем Owner ID (опционально)
    owner_id = os.getenv("RENDER_OWNER_ID")
    if not owner_id:
        # Попробуем получить автоматически
        temp_monitor = RenderBotMonitor(render_api_key, service_id, telegram_token)
        owner_id = temp_monitor.get_owner_id()
        if owner_id:
            print(f"✅ Owner ID получен автоматически: {owner_id}")
        else:
            print("⚠️  Owner ID не найден, будет получен автоматически при первом запросе")
    
    # Создаем монитор
    monitor = RenderBotMonitor(render_api_key, service_id, telegram_token, owner_id)
    
    # Запускаем мониторинг
    print("\n🚀 Запуск мониторинга...")
    print("   Интервал: 60 секунд")
    print("   Автоисправление: Включено")
    print()
    
    monitor.monitor_loop(interval=60, auto_fix=True)


if __name__ == "__main__":
    main()







