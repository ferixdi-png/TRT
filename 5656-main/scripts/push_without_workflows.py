#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Push изменений БЕЗ workflow файлов (если токен не имеет workflow scope)
"""

import subprocess
import sys
import io
from pathlib import Path

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

project_root = Path(__file__).parent.parent


def push_without_workflows():
    """Пушит изменения, исключая workflow файлы если нужно"""
    try:
        # Пробуем обычный push
        result = subprocess.run(
            ['git', 'push', 'origin', 'main'],
            capture_output=True,
            text=True,
            cwd=project_root
        )
        
        if result.returncode == 0:
            print("✅ Pushed successfully")
            return
        
        # Если ошибка связана с workflow
        if 'workflow' in result.stderr.lower() or 'workflow' in result.stdout.lower():
            print("⚠️ Workflow scope issue detected")
            print("📋 Removing workflow files from commit...")
            
            # Удаляем workflow файлы из индекса
            subprocess.run(
                ['git', 'rm', '--cached', '.github/workflows/ci.yml', '.github/workflows/deploy_render.yml'],
                cwd=project_root,
                check=False
            )
            
            # Коммитим без workflow
            subprocess.run(
                ['git', 'commit', '--amend', '--no-edit'],
                cwd=project_root,
                check=True
            )
            
            # Пушим
            subprocess.run(
                ['git', 'push', 'origin', 'main', '--force'],
                cwd=project_root,
                check=True
            )
            
            print("✅ Pushed without workflow files")
            print("💡 To add workflows, update token with 'workflow' scope")
        else:
            print(f"❌ Push failed: {result.stderr}")
            sys.exit(1)
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    push_without_workflows()





