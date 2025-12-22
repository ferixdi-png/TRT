#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LOG PARSER → INCIDENT INTELLIGENCE
Парсит логи, извлекает инциденты, генерирует отчёты
"""

import json
import re
from pathlib import Path
from typing import Dict, List
from collections import Counter
from datetime import datetime

project_root = Path(__file__).parent.parent
artifacts_dir = project_root / "artifacts"
diagnostics_dir = artifacts_dir / "diagnostics"
diagnostics_dir.mkdir(parents=True, exist_ok=True)

log_file = artifacts_dir / "render_logs" / "latest.log"
json_file = artifacts_dir / "render_logs" / "latest.json"


def extract_stacktraces(content: str) -> List[str]:
    """Извлекает stacktrace блоки"""
    stacktraces = []
    # Ищем Traceback
    pattern = r'Traceback.*?(?=\n\n|\n[A-Z]|\Z)'
    for match in re.finditer(pattern, content, re.DOTALL):
        stacktraces.append(match.group())
    return stacktraces


def classify_incident(message: str) -> str:
    """Классифицирует инцидент по сигнатурам"""
    message_lower = message.lower()
    
    if "unknown callback" in message_lower or "unhandled callback" in message_lower:
        return "unknown_callback"
    elif "тишина" in message_lower or "silence" in message_lower or "no response" in message_lower:
        return "silence"
    elif "missing env" in message_lower or "env not set" in message_lower:
        return "missing_env"
    elif "badrequest" in message_lower or "bad request" in message_lower or "bad markup" in message_lower:
        return "bad_markup"
    elif "timeout" in message_lower:
        return "timeout"
    elif "db locked" in message_lower or "database locked" in message_lower:
        return "db_locked"
    elif "409" in message or "conflict" in message_lower:
        return "conflict_409"
    elif "indentationerror" in message_lower or "syntaxerror" in message_lower:
        return "syntax_error"
    elif "import" in message_lower and "error" in message_lower:
        return "import_error"
    else:
        return "other"


def parse_logs() -> Dict:
    """Парсит логи и извлекает инциденты"""
    incidents = []
    errors = []
    
    # Читаем JSON если есть
    if json_file.exists():
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except:
            logs = []
    elif log_file.exists():
        # Парсим текстовый лог
        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        logs = []
        for line in content.split('\n'):
            if line.strip():
                logs.append({"message": line, "level": "INFO"})
    else:
        return {"incidents": [], "errors": [], "summary": {}}
    
    # Анализируем логи
    error_counter = Counter()
    stacktraces = []
    
    for log_entry in logs:
        message = str(log_entry.get("message", log_entry.get("text", "")))
        level = log_entry.get("level", "INFO").upper()
        
        if level == "ERROR" or "error" in message.lower():
            errors.append({
                "message": message,
                "timestamp": log_entry.get("timestamp", ""),
                "level": level
            })
            
            incident_type = classify_incident(message)
            error_counter[incident_type] += 1
            
            incidents.append({
                "type": incident_type,
                "message": message[:200],  # Первые 200 символов
                "timestamp": log_entry.get("timestamp", ""),
                "full_message": message
            })
    
    # Извлекаем stacktraces
    if log_file.exists():
        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        stacktraces = extract_stacktraces(content)
    
    return {
        "incidents": incidents,
        "errors": errors[:50],  # Первые 50 ошибок
        "summary": {
            "total_errors": len(errors),
            "incident_types": dict(error_counter),
            "stacktraces_count": len(stacktraces)
        },
        "stacktraces": stacktraces[:10]  # Первые 10 stacktrace
    }


def generate_report(data: Dict) -> str:
    """Генерирует markdown отчёт"""
    md = "# 📊 INCIDENT REPORT\n\n"
    md += f"**Дата:** {datetime.now().isoformat()}\n\n"
    
    summary = data.get("summary", {})
    md += "## 📈 Сводка\n\n"
    md += f"- Всего ошибок: {summary.get('total_errors', 0)}\n"
    md += f"- Stacktrace'ов: {summary.get('stacktraces_count', 0)}\n\n"
    
    incident_types = summary.get("incident_types", {})
    if incident_types:
        md += "## 🔍 Типы инцидентов\n\n"
        for inc_type, count in sorted(incident_types.items(), key=lambda x: x[1], reverse=True):
            md += f"- `{inc_type}`: {count}\n"
        md += "\n"
    
    incidents = data.get("incidents", [])
    if incidents:
        md += "## 🚨 Последние инциденты\n\n"
        for inc in incidents[:20]:  # Первые 20
            md += f"### {inc['type']}\n"
            md += f"**Время:** {inc.get('timestamp', 'N/A')}\n\n"
            md += f"**Сообщение:** {inc['message']}\n\n"
    
    stacktraces = data.get("stacktraces", [])
    if stacktraces:
        md += "## 📜 Stacktraces\n\n"
        for i, st in enumerate(stacktraces[:5], 1):  # Первые 5
            md += f"### Stacktrace {i}\n\n"
            md += "```\n"
            md += st[:500] + ("..." if len(st) > 500 else "")  # Первые 500 символов
            md += "\n```\n\n"
    
    return md


def main():
    """Главная функция"""
    print("Parsing logs...")
    
    data = parse_logs()
    
    # Сохраняем JSON
    incidents_file = diagnostics_dir / "incidents.json"
    with open(incidents_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"OK Saved {incidents_file}")
    
    # Генерируем отчёт
    report = generate_report(data)
    report_file = diagnostics_dir / "incident_report.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"OK Saved {report_file}")
    
    # Выводим краткую сводку
    summary = data.get("summary", {})
    print(f"\nSummary:")
    print(f"  Total errors: {summary.get('total_errors', 0)}")
    print(f"  Incident types: {len(summary.get('incident_types', {}))}")
    print(f"  Stacktraces: {summary.get('stacktraces_count', 0)}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())







