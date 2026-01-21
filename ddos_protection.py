"""
Модуль для защиты от DDOS-атак.
"""

import logging
import math
import time
from typing import Dict, Any, Optional, Tuple
from collections import defaultdict, deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Хранилище для отслеживания запросов
_request_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
_rate_limits: Dict[str, Dict[str, Any]] = {}
_user_state: Dict[int, Dict[str, Any]] = {}
_seen_updates: Dict[str, float] = {}

# Простая "железная" схема лимитов
RATE_LIMIT_INTERVAL_SECONDS = 2
RATE_LIMIT_WINDOW_SECONDS = 300
RATE_LIMIT_MAX_ACTIONS = 20
COOLDOWN_SECONDS = 60
COOLDOWN_REPEAT_SECONDS = 300
GEN_LIMIT_WINDOW_SECONDS = 600
GEN_LIMIT_MAX_ACTIONS = 3
BLOCK_SECONDS = 24 * 60 * 60
DEDUP_TTL_SECONDS = 60 * 60


def _get_state(user_id: int) -> Dict[str, Any]:
    if user_id not in _user_state:
        _user_state[user_id] = {
            'actions': deque(maxlen=200),
            'gen_attempts': deque(maxlen=50),
            'cooldown_until': 0.0,
            'cooldown_streak': 0,
            'blocked_until': 0.0,
        }
    return _user_state[user_id]


def _cleanup_deque(request_times: deque, now: float, window: int) -> None:
    while request_times and now - request_times[0] > window:
        request_times.popleft()


def _cleanup_seen_updates(now: float) -> None:
    expired = [key for key, ts in _seen_updates.items() if now - ts > DEDUP_TTL_SECONDS]
    for key in expired:
        _seen_updates.pop(key, None)


def _format_wait(seconds: float) -> str:
    wait_time = max(1, int(math.ceil(seconds)))
    return f"Слишком часто. Подожди {wait_time} сек."


def _is_duplicate_update(now: float, user_id: int, update_id: Optional[int], message_id: Optional[int]) -> bool:
    _cleanup_seen_updates(now)
    keys = []
    if update_id is not None:
        keys.append(f"update:{update_id}")
    if message_id is not None:
        keys.append(f"message:{user_id}:{message_id}")

    for key in keys:
        if key in _seen_updates:
            return True

    for key in keys:
        _seen_updates[key] = now
    return False


def check_rate_limit(
    user_id: int,
    action: str = 'generation',
    max_requests: int = 10,
    time_window: int = 60,
    update_id: Optional[int] = None,
    message_id: Optional[int] = None,
    is_generation: Optional[bool] = None
) -> Tuple[bool, Optional[str]]:
    """
    Проверяет, не превышен ли лимит запросов для пользователя.
    
    Args:
        user_id: ID пользователя
        action: Тип действия
        max_requests: Максимальное количество запросов (deprecated, фиксированные лимиты)
        time_window: Временное окно в секундах (deprecated, фиксированные лимиты)
        update_id: ID апдейта (для дедупликации)
        message_id: ID сообщения (для дедупликации)
        is_generation: Явный флаг тяжелой операции (генерации)
    
    Returns:
        (разрешено, сообщение_об_ошибке)
    """
    current_time = time.time()
    state = _get_state(user_id)

    if state['blocked_until'] > current_time:
        wait_time = state['blocked_until'] - current_time
        logger.warning("BLOCK user_id=%s action=%s", user_id, action)
        return False, _format_wait(wait_time)

    if _is_duplicate_update(current_time, user_id, update_id, message_id):
        logger.info("RATE_LIMIT duplicate_update user_id=%s action=%s", user_id, action)
        return False, None

    if state['cooldown_until'] > current_time:
        state['cooldown_until'] = max(state['cooldown_until'], current_time + COOLDOWN_REPEAT_SECONDS)
        state['cooldown_streak'] += 1
        if state['cooldown_streak'] >= 3:
            state['blocked_until'] = current_time + BLOCK_SECONDS
            state['cooldown_until'] = 0.0
            logger.warning("BLOCK user_id=%s action=%s", user_id, action)
            return False, _format_wait(state['blocked_until'] - current_time)
        logger.info("COOLDOWN user_id=%s action=%s", user_id, action)
        return False, _format_wait(state['cooldown_until'] - current_time)

    gen_action = is_generation if is_generation is not None else action == 'generation'
    if gen_action:
        _cleanup_deque(state['gen_attempts'], current_time, GEN_LIMIT_WINDOW_SECONDS)
        if len(state['gen_attempts']) >= GEN_LIMIT_MAX_ACTIONS:
            wait_time = GEN_LIMIT_WINDOW_SECONDS - (current_time - state['gen_attempts'][0])
            logger.info("GEN_LIMIT user_id=%s action=%s", user_id, action)
            return False, _format_wait(wait_time)

    _cleanup_deque(state['actions'], current_time, RATE_LIMIT_WINDOW_SECONDS)
    if state['actions'] and current_time - state['actions'][-1] < RATE_LIMIT_INTERVAL_SECONDS:
        state['cooldown_until'] = current_time + COOLDOWN_SECONDS
        state['cooldown_streak'] += 1
        if state['cooldown_streak'] >= 3:
            state['blocked_until'] = current_time + BLOCK_SECONDS
            state['cooldown_until'] = 0.0
            logger.warning("BLOCK user_id=%s action=%s", user_id, action)
            return False, _format_wait(state['blocked_until'] - current_time)
        logger.info("RATE_LIMIT user_id=%s action=%s", user_id, action)
        return False, _format_wait(state['cooldown_until'] - current_time)

    if len(state['actions']) >= RATE_LIMIT_MAX_ACTIONS:
        state['cooldown_until'] = current_time + COOLDOWN_SECONDS
        state['cooldown_streak'] += 1
        if state['cooldown_streak'] >= 3:
            state['blocked_until'] = current_time + BLOCK_SECONDS
            state['cooldown_until'] = 0.0
            logger.warning("BLOCK user_id=%s action=%s", user_id, action)
            return False, _format_wait(state['blocked_until'] - current_time)
        logger.info("RATE_LIMIT user_id=%s action=%s", user_id, action)
        return False, _format_wait(state['cooldown_until'] - current_time)

    state['actions'].append(current_time)
    if gen_action:
        state['gen_attempts'].append(current_time)
    key = f"{user_id}:{action}"
    _request_history[key].append(current_time)
    state['cooldown_streak'] = 0
    return True, None


def check_suspicious_activity(user_id: int) -> bool:
    """
    Проверяет наличие подозрительной активности.
    
    Args:
        user_id: ID пользователя
    
    Returns:
        True, если активность подозрительна
    """
    current_time = time.time()
    
    # Проверяем различные типы действий
    actions = ['generation', 'api_call', 'message']
    suspicious_count = 0
    
    for action in actions:
        key = f"{user_id}:{action}"
        if key in _request_history:
            request_times = _request_history[key]
            
            # Проверяем количество запросов за последнюю минуту
            recent_requests = [
                t for t in request_times
                if current_time - t < 60
            ]
            
            if len(recent_requests) > 20:  # Более 20 запросов в минуту
                suspicious_count += 1
    
    # Если подозрительная активность в нескольких типах действий
    return suspicious_count >= 2


def require_captcha(user_id: int, action: str = 'generation') -> bool:
    """
    Определяет, требуется ли CAPTCHA для действия.
    
    Args:
        user_id: ID пользователя
        action: Тип действия
    
    Returns:
        True, если требуется CAPTCHA
    """
    # CAPTCHA требуется для:
    # - Подозрительной активности
    # - Высоких цен генераций
    # - Важных операций
    
    if check_suspicious_activity(user_id):
        return True
    
    important_actions = ['settings_change', 'balance_transfer', 'admin_action']
    if action in important_actions:
        return True
    
    return False


def verify_captcha(user_id: int, captcha_response: str) -> bool:
    """
    Проверяет ответ CAPTCHA.
    
    Args:
        user_id: ID пользователя
        captcha_response: Ответ пользователя на CAPTCHA
    
    Returns:
        True, если CAPTCHA верна
    """
    # В реальной реализации здесь будет проверка через сервис CAPTCHA
    # Пока простая проверка
    if captcha_response and len(captcha_response) > 0:
        logger.info(f"✅ CAPTCHA проверена для пользователя {user_id}")
        return True
    
    return False


def get_rate_limit_info(user_id: int, action: str = 'generation') -> Dict[str, Any]:
    """
    Возвращает информацию о лимитах для пользователя.
    
    Args:
        user_id: ID пользователя
        action: Тип действия
    
    Returns:
        Словарь с информацией о лимитах
    """
    state = _get_state(user_id)
    current_time = time.time()
    _cleanup_deque(state['actions'], current_time, RATE_LIMIT_WINDOW_SECONDS)
    _cleanup_deque(state['gen_attempts'], current_time, GEN_LIMIT_WINDOW_SECONDS)
    gen_action = action == 'generation'

    return {
        'current_requests': len(state['actions']),
        'max_requests': RATE_LIMIT_MAX_ACTIONS,
        'time_window': RATE_LIMIT_WINDOW_SECONDS,
        'remaining': max(0, RATE_LIMIT_MAX_ACTIONS - len(state['actions'])),
        'cooldown_seconds_left': max(0, int(state['cooldown_until'] - current_time)),
        'blocked_seconds_left': max(0, int(state['blocked_until'] - current_time)),
        'gen_current_requests': len(state['gen_attempts']) if gen_action else 0,
        'gen_max_requests': GEN_LIMIT_MAX_ACTIONS if gen_action else 0,
        'gen_time_window': GEN_LIMIT_WINDOW_SECONDS if gen_action else 0,
    }
