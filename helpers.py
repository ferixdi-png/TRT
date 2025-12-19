"""
Вспомогательные функции для меню, клавиатур и проверки баланса
Убрано дублирование кода
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import logging
from typing import List, Optional, Dict, Any
from decimal import Decimal

logger = logging.getLogger(__name__)

# Импорты будут выполнены при первом использовании
_t = None
_get_user_balance = None
_get_is_admin = None
_get_user_language = None
_get_user_free_generations_remaining = None
_has_claimed_gift = None
_get_admin_limit = None
_get_admin_spent = None
_get_admin_remaining = None
_KIE_MODELS = None
_get_generation_types = None
_get_models_by_generation_type = None
_get_generation_type_info = None
_get_client = None

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
    """Ленивая инициализация импортов для избежания circular imports"""
    global _t, _get_user_balance, _get_is_admin, _get_user_language
    global _get_user_free_generations_remaining, _has_claimed_gift
    global _get_admin_limit, _get_admin_spent, _get_admin_remaining
    global _KIE_MODELS, _get_generation_types, _get_models_by_generation_type
    global _get_generation_type_info, _get_client, _get_usd_to_rub_rate
    
    if _t is None:
        from translations import t as _t_func
        # Импортируем функции из bot_kie.py (не из knowledge_storage)
        try:
            from bot_kie import (
                get_user_balance as _get_user_balance_func,
                get_is_admin as _get_is_admin_func,
                get_user_language as _get_user_language_func,
                get_user_free_generations_remaining as _get_user_free_generations_remaining_func,
                has_claimed_gift as _has_claimed_gift_func,
                get_admin_limit as _get_admin_limit_func,
                get_admin_spent as _get_admin_spent_func,
                get_admin_remaining as _get_admin_remaining_func
            )
        except ImportError:
            # Fallback: если bot_kie не импортируется, используем database
            try:
                from database import get_user_balance as _get_user_balance_func
                # Остальные функции должны быть в bot_kie
                logger.warning("⚠️ Используется fallback импорт из database для get_user_balance")
                # Для остальных функций используем заглушки или пробуем импортировать из bot_kie
                from bot_kie import (
                    get_is_admin as _get_is_admin_func,
                    get_user_language as _get_user_language_func,
                    get_user_free_generations_remaining as _get_user_free_generations_remaining_func,
                    has_claimed_gift as _has_claimed_gift_func,
                    get_admin_limit as _get_admin_limit_func,
                    get_admin_spent as _get_admin_spent_func,
                    get_admin_remaining as _get_admin_remaining_func
                )
            except ImportError as e:
                logger.error(f"❌ Не удалось импортировать функции: {e}")
                raise
        from kie_models import (
            KIE_MODELS as _KIE_MODELS_obj,
            get_generation_types as _get_generation_types_func,
            get_models_by_generation_type as _get_models_by_generation_type_func,
            get_generation_type_info as _get_generation_type_info_func
        )
        from kie_client import get_client as _get_client_func
        
        _t = _t_func
        _get_user_balance = _get_user_balance_func
        _get_is_admin = _get_is_admin_func
        _get_user_language = _get_user_language_func
        _get_user_free_generations_remaining = _get_user_free_generations_remaining_func
        _has_claimed_gift = _has_claimed_gift_func
        _get_admin_limit = _get_admin_limit_func
        _get_admin_spent = _get_admin_spent_func
        _get_admin_remaining = _get_admin_remaining_func
        _KIE_MODELS = _KIE_MODELS_obj
        _get_generation_types = _get_generation_types_func
        _get_models_by_generation_type = _get_models_by_generation_type_func
        _get_generation_type_info = _get_generation_type_info_func
        _get_client = _get_client_func
        
        # Импортируем get_usd_to_rub_rate из bot_kie
        try:
            import bot_kie
            _get_usd_to_rub_rate = bot_kie.get_usd_to_rub_rate
        except:
            def _default_rate():
                return 77.22
            _get_usd_to_rub_rate = _default_rate


async def build_main_menu_keyboard(
    user_id: int,
    user_lang: str = 'ru',
    is_new: bool = False
) -> List[List[InlineKeyboardButton]]:
    """
    Строит главное меню клавиатуры.
    Убрано дублирование - используется в start() и language_select.
    """
    _init_imports()
    keyboard = []
    
    # Получаем данные
    generation_types = _get_generation_types()
    total_models = len(_KIE_MODELS)
    remaining_free = _get_user_free_generations_remaining(user_id)
    is_admin = _get_is_admin(user_id)
    
    # Free generation button (ALWAYS prominent)
    if remaining_free > 0:
        button_text = _t('btn_generate_free', lang=user_lang,
                      remaining=remaining_free,
                      total=FREE_GENERATIONS_PER_DAY)
    else:
        button_text = _t('btn_generate_free_no_left', lang=user_lang,
                      total=FREE_GENERATIONS_PER_DAY)
    
    keyboard.append([
        InlineKeyboardButton(button_text, callback_data="select_model:z-image")
    ])
    
    # Add referral button
    keyboard.append([
        InlineKeyboardButton(_t('btn_invite_friend', lang=user_lang, bonus=REFERRAL_BONUS_GENERATIONS), callback_data="referral_info")
    ])
    keyboard.append([])  # Empty row for spacing
    
    # Generation types buttons (compact, 2 per row)
    text_to_image_type = None
    gen_type_rows = []
    gen_type_index = 0
    for gen_type in generation_types:
        gen_info = _get_generation_type_info(gen_type)
        models_count = len(_get_models_by_generation_type(gen_type))
        
        if models_count == 0:
            continue
        
        # Identify text-to-image type
        if gen_type == 'text-to-image':
            text_to_image_type = gen_type
            continue
            
        # Get translated name for generation type
        gen_type_key = f'gen_type_{gen_type.replace("-", "_")}'
        gen_type_name = _t(gen_type_key, lang=user_lang, default=gen_info.get('name', gen_type))
        button_text = f"{gen_type_name} ({models_count})"
        
        if gen_type_index % 2 == 0:
            gen_type_rows.append([InlineKeyboardButton(
                button_text,
                callback_data=f"gen_type:{gen_type}"
            )])
        else:
            if gen_type_rows:
                gen_type_rows[-1].append(InlineKeyboardButton(
                    button_text,
                    callback_data=f"gen_type:{gen_type}"
                ))
            else:
                gen_type_rows.append([InlineKeyboardButton(
                    button_text,
                    callback_data=f"gen_type:{gen_type}"
                )])
        gen_type_index += 1
    
    # Add text-to-image button after free generation (if it exists)
    if text_to_image_type:
        gen_info = _get_generation_type_info(text_to_image_type)
        models_count = len(_get_models_by_generation_type(text_to_image_type))
        if models_count > 0:
            gen_type_key = f'gen_type_{text_to_image_type.replace("-", "_")}'
            gen_type_name = _t(gen_type_key, lang=user_lang, default=gen_info.get('name', text_to_image_type))
            button_text = f"{gen_type_name} ({models_count})"
            keyboard.append([
                InlineKeyboardButton(button_text, callback_data=f"gen_type:{text_to_image_type}")
            ])
            keyboard.append([])  # Empty row for spacing
    
    keyboard.extend(gen_type_rows)
    
    # Add free tools button
    keyboard.append([])  # Empty row for spacing
    keyboard.append([
        InlineKeyboardButton(_t('btn_free_tools', lang=user_lang), callback_data="free_tools")
    ])
    
    # Add "All Models" button
    keyboard.append([])  # Empty row for spacing
    keyboard.append([
        InlineKeyboardButton(_t('btn_all_models', lang=user_lang, count=total_models), callback_data="show_models")
    ])
    keyboard.append([])  # Empty row for spacing
    
    # Add "Claim Gift" button for users who haven't claimed yet
    if not _has_claimed_gift(user_id):
        keyboard.append([
            InlineKeyboardButton(_t('btn_claim_gift', lang=user_lang), callback_data="claim_gift")
        ])
        keyboard.append([])  # Empty row for spacing
    
    # Bottom action buttons
    keyboard.append([
        InlineKeyboardButton(_t('btn_balance', lang=user_lang), callback_data="check_balance"),
        InlineKeyboardButton(_t('btn_my_generations', lang=user_lang), callback_data="my_generations")
    ])
    keyboard.append([
        InlineKeyboardButton(_t('btn_top_up', lang=user_lang), callback_data="topup_balance"),
        InlineKeyboardButton(_t('btn_invite_friend_short', lang=user_lang), callback_data="referral_info")
    ])
    
    # Add tutorial button for new users
    if is_new:
        keyboard.append([
            InlineKeyboardButton(_t('btn_how_it_works', lang=user_lang), callback_data="tutorial_start")
        ])
    
    keyboard.append([
        InlineKeyboardButton(_t('btn_help', lang=user_lang), callback_data="help_menu"),
        InlineKeyboardButton(_t('btn_support', lang=user_lang), callback_data="support_contact")
    ])
    
    # Add "Copy This Bot" button (always visible)
    keyboard.append([
        InlineKeyboardButton(_t('btn_copy_bot', lang=user_lang), callback_data="copy_bot")
    ])
    
    # Add language selection button (always visible)
    keyboard.append([
        InlineKeyboardButton(_t('btn_language', lang=user_lang), callback_data="change_language")
    ])
    
    # Add admin panel button ONLY for admin (at the end)
    if is_admin:
        keyboard.append([])  # Empty row for admin section
        keyboard.append([
            InlineKeyboardButton(_t('btn_admin_panel', lang=user_lang), callback_data="admin_stats")
        ])
    
    return keyboard


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
        user_lang = _get_user_language(user_id)
    
    user_balance = _get_user_balance(user_id)
    balance_str = f"{user_balance:.2f}".rstrip('0').rstrip('.')
    is_admin_user = _get_is_admin(user_id)
    is_main_admin = (user_id == ADMIN_ID)
    is_limited_admin = is_admin_user and not is_main_admin
    
    result = {
        'balance': user_balance,
        'balance_str': balance_str,
        'is_admin': is_admin_user,
        'is_main_admin': is_main_admin,
        'is_limited_admin': is_limited_admin,
        'remaining_free': _get_user_free_generations_remaining(user_id),
        'kie_credits': None,
        'kie_credits_rub': None
    }
    
    if is_limited_admin:
        result['limit'] = _get_admin_limit(user_id)
        result['spent'] = _get_admin_spent(user_id)
        result['remaining'] = _get_admin_remaining(user_id)
    
    # Get KIE credits for main admin
    if is_main_admin:
        try:
            kie = _get_client()
            balance_result = await kie.get_credits()
            if balance_result.get('ok'):
                credits = balance_result.get('credits', 0)
                credits_rub = credits * CREDIT_TO_USD * _get_usd_to_rub_rate()
                credits_rub_str = f"{credits_rub:.2f}".rstrip('0').rstrip('.')
                result['kie_credits'] = credits
                result['kie_credits_rub'] = credits_rub
                result['kie_credits_rub_str'] = credits_rub_str
        except Exception as e:
            logger.error(f"❌❌❌ KIE API ERROR in get_credits (get_balance_info): {e}", exc_info=True)
    
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
        return (
            f'👑 <b>Админ с лимитом</b>\n\n'
            f'💳 <b>Лимит:</b> {limit:.2f} ₽\n'
            f'💸 <b>Потрачено:</b> {spent:.2f} ₽\n'
            f'✅ <b>Осталось:</b> {remaining:.2f} ₽\n\n'
            f'💰 <b>Баланс пользователя:</b> {balance_str} ₽'
        )
    elif is_main_admin:
        balance_text = f'💳 <b>Ваш баланс:</b> {balance_str} ₽\n\n'
        if balance_info.get('kie_credits_rub_str'):
            balance_text += (
                f'🔧 <b>Баланс системы генерации:</b> {balance_info["kie_credits_rub_str"]} ₽\n'
                f'<i>({balance_info["kie_credits"]} кредитов)</i>'
            )
        else:
            balance_text += '⚠️ Баланс системы генерации недоступен'
        return balance_text
    else:
        # Regular user
        free_info = ""
        if remaining_free > 0:
            free_info = f"\n\n🎁 <b>Бесплатные генерации:</b> {remaining_free}/{FREE_GENERATIONS_PER_DAY} в день (модель Z-Image)"
        
        return (
            f'💳 <b>ВАШ БАЛАНС</b> 💳\n\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            f'💰 <b>Доступно средств:</b> {balance_str} ₽\n\n'
            f'{free_info if free_info else ""}'
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            f'💡 <b>Что можно сделать:</b>\n'
            f'• Использовать средства для генерации контента\n'
            f'• Пополнить баланс через кнопку ниже\n'
            f'• Использовать бесплатные генерации Z-Image\n'
            f'• Пригласить друга и получить бонусы\n\n'
            f'🎁 <b>Не забудьте:</b> У вас есть бесплатные генерации Z-Image каждый день!'
        )


def get_balance_keyboard(balance_info: Dict[str, Any], user_lang: str = 'ru') -> List[List[InlineKeyboardButton]]:
    """
    Создает клавиатуру для баланса.
    Убрано дублирование - используется в check_balance и button_callback.
    """
    _init_imports()
    keyboard = []
    
    if balance_info['is_limited_admin']:
        keyboard.append([
            InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_menu")
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
    Каждая кнопка имеет callback_data в формате model:<model_id>.
    """
    _init_imports()
    
    if models is None:
        models = _KIE_MODELS
    
    keyboard = []
    
    for model in models:
        # Используем нормализованную модель
        try:
            from kie_models import normalize_model_for_api
            normalized = normalize_model_for_api(model)
        except:
            normalized = model
        
        # Получаем название модели
        title = normalized.get('title') or normalized.get('name') or normalized.get('id', 'Unknown')
        emoji = normalized.get('emoji', '')
        
        # Формируем текст кнопки
        button_text = f"{emoji} {title}" if emoji else title
        
        # Создаем кнопку с callback_data в формате model:<model_id>
        button = InlineKeyboardButton(
            text=button_text,
            callback_data=f"model:{normalized['id']}"
        )
        keyboard.append([button])
    
    return InlineKeyboardMarkup(keyboard)


