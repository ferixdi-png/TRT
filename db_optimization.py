"""
Модуль для оптимизации работы с базой данных.
Включает оптимизированные запросы, автоматическую очистку и управление индексами.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Кеш для часто запрашиваемых данных
_balance_cache: Dict[int, Dict[str, Any]] = {}
_balance_cache_time: Dict[int, float] = {}
BALANCE_CACHE_TTL = 60  # 1 минута


def get_user_balance_optimized(user_id: int, use_cache: bool = True) -> float:
    """
    Оптимизированное получение баланса пользователя с кешированием.
    
    Args:
        user_id: ID пользователя
        use_cache: Использовать ли кеш
    
    Returns:
        Баланс пользователя
    """
    import time
    
    if use_cache:
        current_time = time.time()
        if user_id in _balance_cache:
            cache_data = _balance_cache[user_id]
            cache_time = _balance_cache_time.get(user_id, 0)
            
            if (current_time - cache_time) < BALANCE_CACHE_TTL:
                return cache_data.get('balance', 0.0)
    
    logger.info("DB_DISABLED: github-only mode action=get_user_balance_optimized")
    return 0.0


def invalidate_balance_cache(user_id: int):
    """Инвалидирует кеш баланса для пользователя."""
    if user_id in _balance_cache:
        del _balance_cache[user_id]
    if user_id in _balance_cache_time:
        del _balance_cache_time[user_id]


def cleanup_old_sessions_optimized(days_to_keep: int = 7) -> int:
    """
    Оптимизированная очистка старых сессий.
    
    Args:
        days_to_keep: Количество дней для хранения
    
    Returns:
        Количество удаленных записей
    """
    logger.info("DB_DISABLED: github-only mode action=cleanup_old_sessions_optimized")
    return 0


def cleanup_old_generations_optimized(days_to_keep: int = 90) -> int:
    """
    Оптимизированная очистка старых генераций.
    
    Args:
        days_to_keep: Количество дней для хранения
    
    Returns:
        Количество удаленных записей
    """
    logger.info("DB_DISABLED: github-only mode action=cleanup_old_generations_optimized")
    return 0


def get_user_generations_optimized(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Оптимизированное получение генераций пользователя.
    
    Args:
        user_id: ID пользователя
        limit: Максимальное количество записей
    
    Returns:
        Список генераций
    """
    logger.info("DB_DISABLED: github-only mode action=get_user_generations_optimized")
    return []


def batch_cleanup_old_data(days_sessions: int = 7, days_generations: int = 90) -> Dict[str, int]:
    """
    Пакетная очистка старых данных.
    
    Args:
        days_sessions: Дни для хранения сессий
        days_generations: Дни для хранения генераций
    
    Returns:
        Словарь с количеством удаленных записей
    """
    sessions_deleted = cleanup_old_sessions_optimized(days_sessions)
    generations_deleted = cleanup_old_generations_optimized(days_generations)
    
    return {
        'sessions_deleted': sessions_deleted,
        'generations_deleted': generations_deleted,
        'total_deleted': sessions_deleted + generations_deleted
    }
