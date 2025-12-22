#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматический commit и push после каждого улучшения
Используется автопилотом для автоматического сохранения изменений
"""

import subprocess
import sys
import io
from pathlib import Path
from datetime import datetime

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

project_root = Path(__file__).parent.parent


def auto_commit_and_push(commit_message: str = None):
    """Автоматически коммитит и пушит изменения"""
    try:
        # Проверяем статус
        status_result = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True,
            text=True,
            cwd=project_root
        )
        
        if not status_result.stdout.strip():
            print("ℹ️ No changes to commit")
            return True
        
        # Добавляем все изменения
        subprocess.run(
            ['git', 'add', '-A'],
            cwd=project_root,
            check=True
        )
        print("✅ Changes staged")
        
        # Коммитим
        if not commit_message:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            commit_message = f"Auto-commit: {timestamp}"
        
        subprocess.run(
            ['git', 'commit', '-m', commit_message],
            cwd=project_root,
            check=True
        )
        print(f"✅ Committed: {commit_message}")
        
        # Пушим
        result = subprocess.run(
            ['git', 'push', 'origin', 'main'],
            capture_output=True,
            text=True,
            cwd=project_root,
            check=True
        )
        print(f"✅ Pushed to main")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Git error: {e}")
        if e.stderr:
            print(f"Error output: {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Auto-commit and push changes')
    parser.add_argument('--message', '-m', help='Commit message')
    args = parser.parse_args()
    
    success = auto_commit_and_push(args.message)
    sys.exit(0 if success else 1)





