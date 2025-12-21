#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматический push изменений в GitHub
Использует токен из переменной окружения GITHUB_TOKEN
"""

import os
import subprocess
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent


def get_github_token() -> str:
    """Получает GitHub токен из ENV или файла"""
    # Сначала пробуем из ENV
    token = os.getenv('GITHUB_TOKEN')
    if token:
        return token
    
    # Пробуем из файла (если есть)
    token_file = project_root / '.github_token'
    if token_file.exists():
        return token_file.read_text(encoding='utf-8').strip()
    
    raise RuntimeError("GITHUB_TOKEN not found in ENV or .github_token file")


def setup_git_remote_with_token(token: str):
    """Настраивает git remote с токеном"""
    repo_url = f"https://{token}@github.com/ferixdi-png/5656.git"
    
    # Проверяем текущий remote
    result = subprocess.run(
        ['git', 'remote', 'get-url', 'origin'],
        capture_output=True,
        text=True,
        cwd=project_root
    )
    
    if result.returncode == 0:
        current_url = result.stdout.strip()
        if token not in current_url:
            # Обновляем remote с токеном
            subprocess.run(
                ['git', 'remote', 'set-url', 'origin', repo_url],
                cwd=project_root,
                check=True
            )
            print("✅ Git remote updated with token")
    else:
        # Добавляем remote
        subprocess.run(
            ['git', 'remote', 'add', 'origin', repo_url],
            cwd=project_root,
            check=True
        )
        print("✅ Git remote added with token")


def auto_push(branch: str = 'main', commit_message: str = None):
    """Автоматически пушит изменения в GitHub"""
    try:
        # Получаем токен
        token = get_github_token()
        
        # Настраиваем remote
        setup_git_remote_with_token(token)
        
        # Проверяем статус
        status_result = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True,
            text=True,
            cwd=project_root
        )
        
        if not status_result.stdout.strip():
            print("ℹ️ No changes to commit")
            return
        
        # Добавляем все изменения
        subprocess.run(
            ['git', 'add', '.'],
            cwd=project_root,
            check=True
        )
        print("✅ Changes staged")
        
        # Коммитим
        if not commit_message:
            commit_message = f"Auto-commit: {subprocess.run(['git', 'status', '--short'], capture_output=True, text=True, cwd=project_root).stdout[:50]}"
        
        subprocess.run(
            ['git', 'commit', '-m', commit_message],
            cwd=project_root,
            check=True
        )
        print(f"✅ Committed: {commit_message}")
        
        # Пушим
        subprocess.run(
            ['git', 'push', 'origin', branch],
            cwd=project_root,
            check=True
        )
        print(f"✅ Pushed to {branch}")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Git error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Auto-push changes to GitHub')
    parser.add_argument('--branch', default='main', help='Branch to push to')
    parser.add_argument('--message', '-m', help='Commit message')
    args = parser.parse_args()
    
    auto_push(args.branch, args.message)





