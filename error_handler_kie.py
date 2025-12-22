"""
Обработка ошибок API системы генерации.
Обрабатывает статусы: waiting, queuing, generating, success, failed.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def handle_api_error(
    response: Dict[str, Any],
    model_id: str,
    mode: str,
    user_lang: str = 'ru'
) -> str:
    """
    Обрабатывает ошибку API и возвращает понятное сообщение для пользователя.
    
    Args:
        response: Ответ от API с ошибкой
        model_id: ID модели
        mode: ID mode
        user_lang: Язык пользователя
    
    Returns:
        Понятное сообщение об ошибке
    """
    error_code = response.get('failCode') or response.get('code') or 'UNKNOWN'
    error_msg = response.get('failMsg') or response.get('error') or response.get('msg') or 'Unknown error'
    
    # Логируем детальную ошибку
    logger.error(
        f"❌ API Error для {model_id}:{mode}: "
        f"code={error_code}, message={error_msg}"
    )
    
    # Переводим код ошибки в понятное сообщение для пользователя
    error_messages = {
        'INVALID_INPUT': 'Неверные параметры запроса. Проверьте введенные данные.',
        'INSUFFICIENT_CREDITS': 'Недостаточно средств для генерации. Пополните баланс.',
        'MODEL_NOT_FOUND': 'Выбранная модель временно недоступна. Попробуйте другую.',
        'RATE_LIMIT': 'Слишком много запросов. Подождите немного и попробуйте снова.',
        'TIMEOUT': 'Генерация заняла слишком много времени. Попробуйте еще раз.',
        'SERVER_ERROR': 'Временная проблема на сервере. Попробуйте через несколько секунд.',
        'VALIDATION_ERROR': 'Ошибка в параметрах. Проверьте правильность заполнения всех полей.',
        'NETWORK_ERROR': 'Проблема с сетью. Проверьте подключение и попробуйте снова.'
    }
    
    user_message = error_messages.get(error_code, error_msg)
    
    if user_lang == 'ru':
        # Улучшенное сообщение об ошибке с конкретными рекомендациями
        specific_advice = ""
        next_steps = ""
        
        if error_code == 'INSUFFICIENT_CREDITS':
            specific_advice = (
                "💡 <b>Что произошло:</b>\n"
                "На вашем балансе недостаточно средств для этой генерации.\n\n"
                "💳 <b>Быстрое решение:</b>\n"
                "• Пополните баланс через кнопку \"💳 Пополнить\" в главном меню\n"
                "• Или используйте бесплатные генерации (кнопка \"🎁 Генерировать бесплатно\")\n"
                "• Пригласите друга и получите бонусные генерации\n\n"
            )
            next_steps = (
                "🔄 <b>Рекомендуем:</b>\n"
                "• Нажмите \"◀️ Главное меню\" для пополнения баланса\n"
                "• Или попробуйте бесплатную модель Z-Image\n"
            )
        elif error_code == 'RATE_LIMIT':
            specific_advice = (
                "💡 <b>Что произошло:</b>\n"
                "Слишком много запросов за короткое время. Это временное ограничение для обеспечения стабильности.\n\n"
                "⏰ <b>Быстрое решение:</b>\n"
                "• Подождите 1-2 минуты перед следующей генерацией\n"
                "• Попробуйте другую модель из доступных\n"
                "• Или используйте бесплатные генерации Z-Image\n\n"
            )
            next_steps = (
                "🔄 <b>Рекомендуем:</b>\n"
                "• Вернитесь в главное меню и выберите другую модель\n"
                "• Или подождите минуту и попробуйте снова\n"
            )
        elif error_code == 'TIMEOUT' or error_code == 'NETWORK_ERROR':
            specific_advice = (
                "💡 <b>Что произошло:</b>\n"
                "Генерация заняла больше времени, чем обычно, или возникла проблема с подключением.\n\n"
                "🌐 <b>Быстрое решение:</b>\n"
                "• Проверьте ваше интернет-соединение\n"
                "• Подождите 10-15 секунд и попробуйте снова\n"
                "• Для сложных запросов генерация может занимать больше времени\n"
                "• Попробуйте упростить описание или параметры\n\n"
            )
            next_steps = (
                "🔄 <b>Рекомендуем:</b>\n"
                "• Проверьте подключение к интернету\n"
                "• Попробуйте еще раз через несколько секунд\n"
                "• Или выберите другую модель\n"
            )
        elif error_code == 'VALIDATION_ERROR' or error_code == 'INVALID_INPUT':
            specific_advice = (
                "💡 <b>Что произошло:</b>\n"
                "Некоторые параметры запроса некорректны или не соответствуют требованиям модели.\n\n"
                "📝 <b>Быстрое решение:</b>\n"
                "• Проверьте длину описания (рекомендуется до 500 символов)\n"
                "• Убедитесь, что все URL изображений начинаются с http:// или https://\n"
                "• Проверьте правильность числовых параметров (разрешение, количество и т.д.)\n"
                "• Попробуйте упростить запрос и убрать специальные символы\n\n"
            )
            next_steps = (
                "🔄 <b>Рекомендуем:</b>\n"
                "• Вернитесь назад и проверьте все введенные параметры\n"
                "• Попробуйте более простое описание\n"
                "• Или выберите другую модель\n"
            )
        elif error_code == 'MODEL_NOT_FOUND':
            specific_advice = (
                "💡 <b>Что произошло:</b>\n"
                "Выбранная модель временно недоступна или была обновлена.\n\n"
                "🔄 <b>Быстрое решение:</b>\n"
                "• Выберите другую модель из доступных в списке\n"
                "• Попробуйте модель Z-Image (она всегда доступна и бесплатна)\n"
                "• Вернитесь в главное меню и выберите другую категорию\n\n"
            )
            next_steps = (
                "🔄 <b>Рекомендуем:</b>\n"
                "• Нажмите \"◀️ Главное меню\" и выберите другую модель\n"
                "• Или используйте бесплатную генерацию Z-Image\n"
            )
        else:
            specific_advice = (
                "💡 <b>Что произошло:</b>\n"
                f"{user_message}\n\n"
                "🔧 <b>Быстрое решение:</b>\n"
                "• Подождите 10-15 секунд и попробуйте еще раз\n"
                "• Проверьте правильность всех параметров\n"
                "• Если проблема повторяется, выберите другую модель\n\n"
            )
            next_steps = (
                "🔄 <b>Рекомендуем:</b>\n"
                "• Попробуйте еще раз через несколько секунд\n"
                "• Или вернитесь в главное меню и выберите другую модель\n"
            )
        
        return (
            f"⚠️ <b>Генерация не выполнена</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{specific_advice}"
            f"{next_steps}\n"
            f"💬 Если проблема сохраняется, обратитесь в поддержку через кнопку \"🆘 Помощь\"\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    else:
        # Improved error message with specific recommendations
        specific_advice = ""
        next_steps = ""
        
        if error_code == 'INSUFFICIENT_CREDITS':
            specific_advice = (
                "💡 <b>What happened:</b>\n"
                "Your balance is insufficient for this generation.\n\n"
                "💳 <b>Quick solution:</b>\n"
                "• Top up your balance via \"💳 Top Up\" button in main menu\n"
                "• Or use free generations (\"🎁 Generate Free\" button)\n"
                "• Invite a friend and get bonus generations\n\n"
            )
            next_steps = (
                "🔄 <b>Recommended:</b>\n"
                "• Press \"◀️ Main Menu\" to top up balance\n"
                "• Or try free Z-Image model\n"
            )
        elif error_code == 'RATE_LIMIT':
            specific_advice = (
                "💡 <b>What happened:</b>\n"
                "Too many requests in a short time. This is a temporary limit for system stability.\n\n"
                "⏰ <b>Quick solution:</b>\n"
                "• Wait 1-2 minutes before next generation\n"
                "• Try a different model from available ones\n"
                "• Or use free Z-Image generations\n\n"
            )
            next_steps = (
                "🔄 <b>Recommended:</b>\n"
                "• Return to main menu and select another model\n"
                "• Or wait a minute and try again\n"
            )
        elif error_code == 'TIMEOUT' or error_code == 'NETWORK_ERROR':
            specific_advice = (
                "💡 <b>What happened:</b>\n"
                "Generation took longer than usual or connection issue occurred.\n\n"
                "🌐 <b>Quick solution:</b>\n"
                "• Check your internet connection\n"
                "• Wait 10-15 seconds and try again\n"
                "• For complex requests, generation may take more time\n"
                "• Try simplifying description or parameters\n\n"
            )
            next_steps = (
                "🔄 <b>Recommended:</b>\n"
                "• Check internet connection\n"
                "• Try again in a few seconds\n"
                "• Or select another model\n"
            )
        elif error_code == 'VALIDATION_ERROR' or error_code == 'INVALID_INPUT':
            specific_advice = (
                "💡 <b>What happened:</b>\n"
                "Some request parameters are incorrect or don't match model requirements.\n\n"
                "📝 <b>Quick solution:</b>\n"
                "• Check description length (recommended up to 500 characters)\n"
                "• Make sure all image URLs start with http:// or https://\n"
                "• Check numeric parameters correctness (resolution, count, etc.)\n"
                "• Try simplifying request and remove special characters\n\n"
            )
            next_steps = (
                "🔄 <b>Recommended:</b>\n"
                "• Go back and check all entered parameters\n"
                "• Try a simpler description\n"
                "• Or select another model\n"
            )
        elif error_code == 'MODEL_NOT_FOUND':
            specific_advice = (
                "💡 <b>What happened:</b>\n"
                "Selected model is temporarily unavailable or has been updated.\n\n"
                "🔄 <b>Quick solution:</b>\n"
                "• Select another model from available list\n"
                "• Try Z-Image model (it's always available and free)\n"
                "• Return to main menu and choose another category\n\n"
            )
            next_steps = (
                "🔄 <b>Recommended:</b>\n"
                "• Press \"◀️ Main Menu\" and select another model\n"
                "• Or use free Z-Image generation\n"
            )
        else:
            specific_advice = (
                "💡 <b>What happened:</b>\n"
                f"{user_message}\n\n"
                "🔧 <b>Quick solution:</b>\n"
                "• Wait 10-15 seconds and try again\n"
                "• Check all parameters are correct\n"
                "• If problem persists, select another model\n\n"
            )
            next_steps = (
                "🔄 <b>Recommended:</b>\n"
                "• Try again in a few seconds\n"
                "• Or return to main menu and select another model\n"
            )
        
        return (
            f"⚠️ <b>Generation not completed</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{specific_advice}"
            f"{next_steps}\n"
            f"💬 If problem persists, contact support via \"🆘 Help\" button\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )


def handle_task_status(
    status_response: Dict[str, Any],
    model_id: str,
    mode: str
) -> Dict[str, Any]:
    """
    Обрабатывает статус задачи и определяет следующее действие.
    
    Args:
        status_response: Ответ от get_task_status
        model_id: ID модели
        mode: ID mode
    
    Returns:
        Обработанный статус с рекомендациями
    """
    state = status_response.get('state', 'unknown')
    
    result = {
        'state': state,
        'should_continue': False,
        'should_retry': False,
        'error': None
    }
    
    if state == 'success':
        result['should_continue'] = True
        result['should_retry'] = False
        
    elif state == 'fail':
        result['should_continue'] = False
        result['should_retry'] = False
        result['error'] = handle_api_error(status_response, model_id, mode)
        
    elif state in ['waiting', 'queuing', 'generating']:
        result['should_continue'] = True
        result['should_retry'] = True
        
    else:
        result['should_continue'] = False
        result['should_retry'] = True
        result['error'] = f"Неизвестный статус: {state}"
    
    return result


def log_api_error(
    error: Exception,
    context: Dict[str, Any],
    model_id: str,
    mode: str
):
    """
    Логирует ошибку API с полным контекстом.
    
    Args:
        error: Исключение
        context: Контекст ошибки
        model_id: ID модели
        mode: ID mode
    """
    logger.error(
        f"❌ API Error для {model_id}:{mode}: {type(error).__name__}: {str(error)}",
        exc_info=True
    )
    logger.error(f"❌ Контекст: {context}")

