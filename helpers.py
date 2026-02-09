"""
Вспомогательные функции для меню, клавиатур и проверки баланса
Убрано дублирование кода
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from decimal import Decimal

logger = logging.getLogger(__name__)

# Импорты для user state (БЕЗ bot_kie!)
from app.state.user_state import (
    get_user_balance_async,
    get_user_language_async,
    get_is_admin,
    get_user_free_generations_remaining_async,
    has_claimed_gift,
    get_admin_limit_async,
    get_admin_spent_async,
    get_admin_remaining_async,
)

# Ленивые импорты для остальных модулей (не user state)
_t = None
_KIE_MODELS = None
_get_generation_types = None
_get_models_by_generation_type = None
_get_generation_type_info = None
_get_client = None
_KIE_CREDITS_UNAVAILABLE_UNTIL: Optional[datetime] = None
_KIE_CREDITS_CACHE: Dict[str, Any] = {"timestamp": None, "value": None}
KIE_CREDITS_CACHE_TTL_SECONDS = int(os.getenv("KIE_CREDITS_CACHE_TTL_SECONDS", "120"))
KIE_CREDITS_TIMEOUT_SECONDS = float(os.getenv("KIE_CREDITS_TIMEOUT_SECONDS", "2.0"))

# Константы (будут установлены из bot_kie.py)
FREE_GENERATIONS_PER_DAY = 3
REFERRAL_BONUS_GENERATIONS = 3
ADMIN_ID = None
CREDIT_TO_USD = 0.005
_get_usd_to_rub_rate = None


def set_constants(free_gen_per_day: int, ref_bonus: int, admin_id: int):
    """Устанавливает константы из bot_kie.py"""
    global FREE_GENERATIONS_PER_DAY, REFERRAL_BONUS_GENERATIONS, ADMIN_ID
    FREE_GENERATIONS_PER_DAY = free_gen_per_day
    REFERRAL_BONUS_GENERATIONS = ref_bonus
    ADMIN_ID = admin_id


def _init_imports():
    """Ленивая инициализация импортов для остальных модулей (не user state)"""
    global _t, _KIE_MODELS, _get_generation_types, _get_models_by_generation_type
    global _get_generation_type_info, _get_client, _get_usd_to_rub_rate
    
    if _t is None:
        from translations import t as _t_func
        
        # Используем registry как единый источник моделей
        from app.models.registry import (
            get_models_sync,
            get_generation_types as _get_generation_types_func,
            get_models_by_generation_type as _get_models_by_generation_type_func,
            get_generation_type_info as _get_generation_type_info_func,
        )
        
        from kie_client import get_client as _get_client_func
        
        _t = _t_func
        _KIE_MODELS = get_models_sync()  # Используем registry
        _get_generation_types = _get_generation_types_func
        _get_models_by_generation_type = _get_models_by_generation_type_func
        _get_generation_type_info = _get_generation_type_info_func
        _get_client = _get_client_func
        
        # Импортируем get_usd_to_rub_rate из app/services/payments_service (БЕЗ bot_kie!)
        try:
            from app.services.payments_service import get_usd_to_rub_rate as _get_usd_to_rub_rate_func
            _get_usd_to_rub_rate = _get_usd_to_rub_rate_func
        except ImportError:
            def _default_rate():
                return 77.83
            _get_usd_to_rub_rate = _default_rate
            logger.warning("⚠️ app.services.payments_service not found, using default rate")


async def build_main_menu_keyboard(
    user_id: int,
    user_lang: str = 'ru',
    is_new: bool = False
) -> List[List[InlineKeyboardButton]]:
    """
    Строит главное меню клавиатуры.
    Обновлено согласно скриншоту идеального меню.
    """
    # Mini App URL (optional - if set, show webapp button)
    webapp_url = os.getenv("WEBAPP_URL", "").strip()
    
    if user_lang == "ru":
        buttons = [
            [InlineKeyboardButton("⚡ Бесплатные генерации", callback_data="fast_tools")],
            [InlineKeyboardButton("🖼️ Текст → Фото", callback_data="gen_type:text-to-image")],
            [InlineKeyboardButton("🧩 Редактор фото", callback_data="gen_type:image-to-image")],
            [InlineKeyboardButton("🎬 Видео по сценарию", callback_data="gen_type:text-to-video")],
            [InlineKeyboardButton("🎬 Фото → Видео", callback_data="gen_type:image-to-video")],
            [InlineKeyboardButton("🧰 Другие модели", callback_data="special_tools")],
            [InlineKeyboardButton("💳 Баланс / Доступ", callback_data="check_balance")],
            [InlineKeyboardButton("🤝 Партнёрка", callback_data="referral_info")],
            [InlineKeyboardButton("🌐 Язык / Language", callback_data="change_language")],
        ]
        if webapp_url:
            buttons.insert(0, [InlineKeyboardButton("🚀 Открыть приложение", web_app=WebAppInfo(url=webapp_url))])
        return buttons
    else:
        buttons = [
            [InlineKeyboardButton("⚡ Free generations", callback_data="fast_tools")],
            [InlineKeyboardButton("🖼️ Text → Photo", callback_data="gen_type:text-to-image")],
            [InlineKeyboardButton("🧩 Photo editor", callback_data="gen_type:image-to-image")],
            [InlineKeyboardButton("🎬 Video by Script", callback_data="gen_type:text-to-video")],
            [InlineKeyboardButton("🎬 Photo → Video", callback_data="gen_type:image-to-video")],
            [InlineKeyboardButton("🧰 More models", callback_data="special_tools")],
            [InlineKeyboardButton("💳 Balance / Access", callback_data="check_balance")],
            [InlineKeyboardButton("🤝 Referral", callback_data="referral_info")],
            [InlineKeyboardButton("🌐 Language / Язык", callback_data="change_language")],
        ]
        if webapp_url:
            buttons.insert(0, [InlineKeyboardButton("🚀 Open App", web_app=WebAppInfo(url=webapp_url))])
        return buttons


async def get_balance_info(user_id: int, user_lang: str = None) -> Dict[str, Any]:
    """
    Получает информацию о балансе пользователя.
    Убрано дублирование - используется в check_balance и button_callback.
    
    Returns:
        dict: {
            'balance': Decimal,
            'balance_str': str,
            'is_admin': bool,
            'is_main_admin': bool,
            'is_limited_admin': bool,
            'limit': Decimal (if limited admin),
            'spent': Decimal (if limited admin),
            'remaining': Decimal (if limited admin),
            'remaining_free': int,
            'kie_credits': float (if main admin, None otherwise),
            'kie_credits_rub': float (if main admin, None otherwise)
        }
    """
    _init_imports()
    if user_lang is None:
        user_lang = await get_user_language_async(user_id)
    
    user_balance = await get_user_balance_async(user_id)
    balance_str = f"{user_balance:.2f}".rstrip('0').rstrip('.')
    is_admin_user = get_is_admin(user_id)
    is_main_admin = (user_id == ADMIN_ID)
    is_limited_admin = is_admin_user and not is_main_admin
    
    result = {
        'balance': user_balance,
        'balance_str': balance_str,
        'is_admin': is_admin_user,
        'is_main_admin': is_main_admin,
        'is_limited_admin': is_limited_admin,
        'remaining_free': await get_user_free_generations_remaining_async(user_id),
        'kie_credits': None,
        'kie_credits_rub': None,
        'kie_credits_error': None
    }
    
    if is_limited_admin:
        result['limit'] = await get_admin_limit_async(user_id)
        result['spent'] = await get_admin_spent_async(user_id)
        result['remaining'] = await get_admin_remaining_async(user_id)
    
    # Get KIE credits for main admin
    if is_main_admin:
        now = datetime.now(timezone.utc)
        global _KIE_CREDITS_UNAVAILABLE_UNTIL
        if _KIE_CREDITS_UNAVAILABLE_UNTIL and now < _KIE_CREDITS_UNAVAILABLE_UNTIL:
            result["kie_credits_error"] = "💰 <b>Баланс KIE API:</b> временно недоступно"
            return result
        cache_ts = _KIE_CREDITS_CACHE.get("timestamp")
        cached_value = _KIE_CREDITS_CACHE.get("value")
        if cache_ts and isinstance(cache_ts, datetime):
            if (now - cache_ts).total_seconds() < KIE_CREDITS_CACHE_TTL_SECONDS and cached_value:
                if cached_value.get("ok"):
                    credits = cached_value.get("credits", 0)
                    credits_rub = credits * CREDIT_TO_USD * _get_usd_to_rub_rate()
                    credits_rub_str = f"{credits_rub:.2f}".rstrip('0').rstrip('.')
                    result['kie_credits'] = credits
                    result['kie_credits_rub'] = credits_rub
                    result['kie_credits_rub_str'] = credits_rub_str
                    return result
                result["kie_credits_error"] = "💰 <b>Баланс KIE API:</b> временно недоступно"
                return result
        try:
            kie = _get_client()
            get_credits = getattr(kie, "get_credits", None)
            if not callable(get_credits):
                logger.warning("KIE client has no get_credits method. Hint: update KIE client integration.")
            else:
                try:
                    balance_result = await asyncio.wait_for(get_credits(), timeout=KIE_CREDITS_TIMEOUT_SECONDS)
                except Exception as exc:
                    correlation_id = uuid.uuid4().hex
                    logger.warning(
                        "KIE credits request timed out or failed (corr_id=%s): %s",
                        correlation_id,
                        exc,
                    )
                    balance_result = {
                        "ok": False,
                        "status": 0,
                        "error": "timeout",
                        "correlation_id": correlation_id,
                    }
                _KIE_CREDITS_CACHE["timestamp"] = now
                _KIE_CREDITS_CACHE["value"] = balance_result
                if balance_result and balance_result.get('ok'):
                    credits = balance_result.get('credits', 0)
                    credits_rub = credits * CREDIT_TO_USD * _get_usd_to_rub_rate()
                    credits_rub_str = f"{credits_rub:.2f}".rstrip('0').rstrip('.')
                    result['kie_credits'] = credits
                    result['kie_credits_rub'] = credits_rub
                    result['kie_credits_rub_str'] = credits_rub_str
                else:
                    status = balance_result.get("status") if balance_result else None
                    if status == 404:
                        _KIE_CREDITS_UNAVAILABLE_UNTIL = now + timedelta(hours=6)
                        logger.warning("KIE credits endpoint unavailable (404). Suppressing for 6 hours.")
                    result["kie_credits_error"] = "💰 <b>Баланс KIE API:</b> временно недоступно"
                    from app.observability.structured_logs import log_structured_event

                    log_structured_event(
                        correlation_id=balance_result.get("correlation_id") if balance_result else None,
                        action="KIE_CREDITS",
                        action_path="helpers.get_balance_info",
                        stage="KIE_CREDITS",
                        outcome="failed",
                        error_code="CREDITS_UNAVAILABLE",
                        fix_hint="Проверьте доступность /api/v1/chat/credit",
                        param={"status": status},
                    )
        except Exception as e:
            correlation_id = uuid.uuid4().hex
            logger.error(
                "❌❌❌ KIE API ERROR in get_credits (get_balance_info) corr_id=%s error=%s",
                correlation_id,
                e,
                exc_info=True,
            )
            result["kie_credits_error"] = "💰 <b>Баланс KIE API:</b> временно недоступно"
    
    return result


async def format_balance_message(balance_info: Dict[str, Any], user_lang: str = 'ru') -> str:
    """
    Форматирует сообщение о балансе.
    Убрано дублирование - используется в check_balance и button_callback.
    """
    balance_str = balance_info['balance_str']
    is_admin = balance_info['is_admin']
    is_main_admin = balance_info['is_main_admin']
    is_limited_admin = balance_info['is_limited_admin']
    remaining_free = balance_info['remaining_free']
    
    if is_limited_admin:
        limit = balance_info.get('limit', 0)
        spent = balance_info.get('spent', 0)
        remaining = balance_info.get('remaining', 0)
        if user_lang == 'en':
            return (
                f'👑 <b>Admin with limit</b>\n\n'
                f'💳 <b>Limit:</b> {limit:.2f} RUB\n'
                f'💸 <b>Spent:</b> {spent:.2f} RUB\n'
                f'✅ <b>Remaining:</b> {remaining:.2f} RUB\n\n'
                f'💰 <b>User balance:</b> {balance_str} RUB'
            )
        else:
            return (
                f'👑 <b>Админ с лимитом</b>\n\n'
                f'💳 <b>Лимит:</b> {limit:.2f} ₽\n'
                f'💸 <b>Потрачено:</b> {spent:.2f} ₽\n'
                f'✅ <b>Осталось:</b> {remaining:.2f} ₽\n\n'
                f'💰 <b>Баланс пользователя:</b> {balance_str} ₽'
            )
    elif is_main_admin:
        if user_lang == 'en':
            balance_text = f'💳 <b>Your balance:</b> {balance_str} RUB\n\n'
            if balance_info.get('kie_credits_rub_str'):
                balance_text += (
                    f'🔧 <b>Generation system balance:</b> {balance_info["kie_credits_rub_str"]} RUB\n'
                    f'<i>({balance_info["kie_credits"]} credits)</i>'
                )
            elif balance_info.get("kie_credits_error"):
                balance_text += balance_info["kie_credits_error"]
            else:
                balance_text += 'ℹ️ Internal balance available, external unavailable'
        else:
            balance_text = f'💳 <b>Ваш баланс:</b> {balance_str} ₽\n\n'
            if balance_info.get('kie_credits_rub_str'):
                balance_text += (
                    f'🔧 <b>Баланс системы генерации:</b> {balance_info["kie_credits_rub_str"]} ₽\n'
                    f'<i>({balance_info["kie_credits"]} кредитов)</i>'
                )
            elif balance_info.get("kie_credits_error"):
                balance_text += balance_info["kie_credits_error"]
            else:
                balance_text += 'ℹ️ Внутренний баланс доступен, внешний недоступен'
        return balance_text
    else:
        # Regular user
        if user_lang == 'en':
            free_info = ""
            if remaining_free > 0:
                free_info = f"\n\n🎁 <b>Free Generations:</b> {remaining_free}/{FREE_GENERATIONS_PER_DAY} per day (free models)"
            
            balance_message = (
                f"╔═══════════════════════════════════╗\n"
                f"║  💳 YOUR BALANCE 💳               ║\n"
                f"╚═══════════════════════════════════╝\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 <b>Available funds:</b> <b>{balance_str} ₽</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )
            
            if free_info:
                balance_message += free_info + '\n'
            
            balance_message += (
                f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 <b>What you can do:</b>\n"
                f"✅ Use funds for content generation\n"
                f"✅ Top up balance via button below\n"
            )
            
            if remaining_free > 0:
                balance_message += f"✅ Free models generations ({remaining_free} available)\n"
            
            balance_message += (
                f"✅ Invite a friend and get bonuses\n\n"
                f"🎁 <b>Tip:</b> Start with free generations!"
            )
            
            return balance_message
        else:
            # Russian version
            free_info = ""
            if remaining_free > 0:
                free_info = f"\n\n🎁 <b>Бесплатные генерации:</b> {remaining_free}/{FREE_GENERATIONS_PER_DAY} в день (пул free models)"
            
            balance_message = (
                f"╔═══════════════════════════════════════════╗\n"
                f"║  💳 ВАШ БАЛАНС 💳                        ║\n"
                f"╚═══════════════════════════════════════════╝\n\n"
                f"╔═══════════════════════════════════════════╗\n"
                f"║  💰 ДОСТУПНО: <b>{balance_str} ₽</b> 💰            ║\n"
                f"╚═══════════════════════════════════════════╝\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )
            
            if free_info:
                balance_message += (
                    f"\n╔═══════════════════════════════════════════╗\n"
                    f"║  🎁 БЕСПЛАТНЫЕ ГЕНЕРАЦИИ 🎁              ║\n"
                    f"╚═══════════════════════════════════════════╝\n"
                    f"{free_info}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                )
            
            balance_message += (
                f"\n╔═══════════════════════════════════════════╗\n"
                f"║  💡 ЧТО МОЖНО СДЕЛАТЬ 💡                  ║\n"
                f"╚═══════════════════════════════════════════╝\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ Использовать средства для генерации\n"
                f"✅ Пополнить баланс через кнопку ниже\n"
            )
            
            if remaining_free > 0:
                balance_message += f"✅ Бесплатные генерации free models ({remaining_free} доступно)\n"
            
            balance_message += (
                f"✅ Пригласить друга и получить бонусы\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🎁 <b>💡 Совет:</b> Начните с бесплатных генераций!"
            )
            
            return balance_message


def get_balance_keyboard(balance_info: Dict[str, Any], user_lang: str = 'ru') -> List[List[InlineKeyboardButton]]:
    """
    Создает клавиатуру для баланса.
    Убрано дублирование - используется в check_balance и button_callback.
    """
    _init_imports()
    keyboard = []
    
    if balance_info['is_limited_admin']:
        back_text = "◀️ Back to menu" if user_lang == 'en' else "◀️ Назад в меню"
        keyboard.append([
            InlineKeyboardButton(back_text, callback_data="back_to_menu")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton(_t('btn_top_up_balance', lang=user_lang), callback_data="topup_balance")
        ])
        keyboard.append([
            InlineKeyboardButton(_t('btn_back_to_menu', lang=user_lang), callback_data="back_to_menu")
        ])
    
    return keyboard


async def check_duplicate_task(user_id: int, model_id: str, params: dict) -> Optional[str]:
    """
    Проверяет, не создана ли уже задача с такими же параметрами.
    Предотвращает дублирование генераций.
    
    Returns:
        task_id (str) если найдена дублирующая задача, None иначе
    """
    # TODO: Реализовать проверку в БД или active_generations
    # Пока возвращаем None - проверка будет добавлена позже
    return None


def build_model_keyboard(models: list = None, user_lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Автоматически строит клавиатуру с кнопками для каждой модели.
    Каждая кнопка имеет callback_data в формате model:<model_id> (ограничен до 64 байт).
    Canonical формат для тестов и меню.
    """
    _init_imports()
    
    if models is None:
        models = _KIE_MODELS
    
    keyboard = []
    
    for model in models:
        # Модели уже нормализованы из registry
        model_id = model.get('id', '')
        name = model.get('name', model_id)
        emoji = model.get('emoji', '🤖')
        
        # Формируем текст кнопки (ограничение Telegram: ~64 символа)
        button_text = f"{emoji} {name}"
        if len(button_text.encode('utf-8')) > 64:
            # Обрезаем имя если слишком длинное
            max_name_len = 64 - len(emoji.encode('utf-8')) - 2  # -2 для пробела и эмодзи
            button_text = f"{emoji} {name[:max_name_len]}..."
        
        # Создаем callback_data в формате model:<model_id> (canonical для тестов)
        # Ограничение Telegram: 64 байта
        callback_data = f"model:{model_id}"
        callback_bytes = callback_data.encode('utf-8')
        if len(callback_bytes) > 64:
            # Если слишком длинный, используем короткий формат
            callback_data = f"m:{model_id[:55]}"
            # Проверяем еще раз
            if len(callback_data.encode('utf-8')) > 64:
                # Последний fallback - максимально обрезаем
                callback_data = f"m:{model_id[:50]}"
        
        button = InlineKeyboardButton(
            text=button_text,
            callback_data=callback_data
        )
        keyboard.append([button])
    
    return InlineKeyboardMarkup(keyboard)
