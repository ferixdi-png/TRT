#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LOG CONNECTOR — RENDER (РЕАЛЬНЫЕ ЛОГИ)
Получает логи Render через API, сохраняет в artifacts
"""

import os
import sys
import argparse
import requests
import json
import re
import io
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

RENDER_API_BASE = "https://api.render.com/v1"

project_root = Path(__file__).parent.parent
artifacts_dir = project_root / "artifacts" / "render_logs"
artifacts_dir.mkdir(parents=True, exist_ok=True)


def mask_secrets(text: str) -> str:
    """Маскирует секреты в тексте"""
    # Маскируем токены бота
    text = re.sub(r'\d{10}:[A-Za-z0-9_-]{35}', 'BOT_TOKEN_MASKED', text)
    # Маскируем Render API ключи
    text = re.sub(r'rnd_[A-Za-z0-9_-]{30,}', 'RENDER_API_KEY_MASKED', text)
    # Маскируем KIE API ключи
    text = re.sub(r'[A-Za-z0-9]{32}', lambda m: 'KIE_API_KEY_MASKED' if len(m.group()) == 32 else m.group(), text)
    return text


def get_render_api_key() -> Optional[str]:
    """Получает API ключ Render с поддержкой алиасов"""
    api_key = os.getenv("RENDER_API_KEY") or os.getenv("RND")
    if not api_key:
        print("FAIL RENDER_API_KEY not set")
        return None
    return api_key


def get_service_id() -> Optional[str]:
    """Получает Service ID с поддержкой алиасов"""
    service_id = os.getenv("RENDER_SERVICE_ID") or os.getenv("SRV")
    if not service_id:
        # Пробуем из конфига
        try:
            config_file = project_root / "services_config.json"
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    services = config.get("services", [])
                    if services:
                        for service in services:
                            if service.get("enabled", True):
                                return service.get("service_id")
        except:
            pass
    return service_id


def get_owner_id(api_key: str, service_id: str) -> Optional[str]:
    """Получает Owner ID"""
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    try:
        response = requests.get(f"{RENDER_API_BASE}/services/{service_id}", headers=headers, timeout=10)
        if response.status_code == 200:
            service_data = response.json()
            service_info = service_data.get("service", service_data)
            return service_info.get("ownerId")
    except:
        pass
    return None


def parse_time_filter(since: str) -> Optional[datetime]:
    """Парсит фильтр времени"""
    if not since:
        return None
    try:
        since = since.lower().strip()
        if since.endswith('m'):
            return datetime.now() - timedelta(minutes=int(since[:-1]))
        elif since.endswith('h'):
            return datetime.now() - timedelta(hours=int(since[:-1]))
        elif since.endswith('d'):
            return datetime.now() - timedelta(days=int(since[:-1]))
    except:
        pass
    return None


def get_logs(
    api_key: str,
    service_id: str,
    since: Optional[str] = None,
    grep_pattern: Optional[str] = None,
    lines: int = 100
) -> List[Dict]:
    """Получает логи с фильтрами"""
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    
    try:
        owner_id = get_owner_id(api_key, service_id)
        url = f"{RENDER_API_BASE}/logs"
        params = {"resource": service_id, "limit": lines}
        if owner_id:
            params["ownerId"] = owner_id
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        logs_data = response.json()
        if isinstance(logs_data, list):
            logs = logs_data
        elif isinstance(logs_data, dict):
            logs = logs_data.get("logs", logs_data.get("data", logs_data.get("items", [])))
        else:
            logs = []
        
        # Применяем фильтры
        filtered_logs = []
        since_time = parse_time_filter(since) if since else None
        
        for log_entry in logs:
            if not isinstance(log_entry, dict):
                continue
            
            # Фильтр по времени
            if since_time:
                timestamp_str = log_entry.get("timestamp", "")
                if timestamp_str:
                    try:
                        log_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        if log_time < since_time:
                            continue
                    except:
                        pass
            
            # Фильтр по grep (regex)
            if grep_pattern:
                message = str(log_entry.get("message", log_entry.get("text", "")))
                try:
                    if not re.search(grep_pattern, message, re.IGNORECASE):
                        continue
                except re.error:
                    if grep_pattern.lower() not in message.lower():
                        continue
            
            filtered_logs.append(log_entry)
        
        return filtered_logs
    except Exception as e:
        print(f"FAIL Error getting logs: {mask_secrets(str(e))}")
        return []


def save_logs(logs: List[Dict], format: str = "text"):
    """Сохраняет логи в artifacts"""
    if format == "json":
        json_file = artifacts_dir / "latest.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)
        print(f"OK Saved {json_file}")
    else:
        log_file = artifacts_dir / "latest.log"
        with open(log_file, 'w', encoding='utf-8') as f:
            for log_entry in logs:
                timestamp = log_entry.get("timestamp", "")
                message = mask_secrets(str(log_entry.get("message", log_entry.get("text", ""))))
                level = log_entry.get("level", "INFO")
                f.write(f"[{timestamp}] {level}: {message}\n")
        print(f"OK Saved {log_file}")


def main():
    parser = argparse.ArgumentParser(description="Render Logs Tail")
    parser.add_argument("--since", help="Time filter (30m, 2h, 1d)")
    parser.add_argument("--grep", help="Regex pattern to filter")
    parser.add_argument("--json", action="store_true", help="Save as JSON")
    parser.add_argument("--text", action="store_true", help="Save as text (default)")
    parser.add_argument("--follow", action="store_true", help="Follow mode")
    parser.add_argument("--service-id", help="Service ID")
    
    args = parser.parse_args()
    
    api_key = get_render_api_key()
    if not api_key:
        return 1
    
    service_id = args.service_id or get_service_id()
    if not service_id:
        print("FAIL RENDER_SERVICE_ID not set")
        return 1
    
    if args.follow:
        import time
        print("Follow mode (Ctrl+C to stop)...")
        try:
            while True:
                logs = get_logs(api_key, service_id, since=args.since, grep_pattern=args.grep)
                if logs:
                    save_logs(logs, format="json" if args.json else "text")
                time.sleep(10)
        except KeyboardInterrupt:
            print("\nStopped")
    else:
        logs = get_logs(api_key, service_id, since=args.since, grep_pattern=args.grep)
        save_logs(logs, format="json" if args.json else "text")
        print(f"OK Retrieved {len(logs)} log entries")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())







