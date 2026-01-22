"""
Конфигурация маршрутизации callback-ов
Единый источник истины для всех кнопок бота
"""

from typing import Dict, List, Tuple
from app.buttons.registry import CallbackType

# Формат: (callback_data, callback_type, description, handler_function_name)
# handler_function_name будет импортирован из bot_kie.py

CALLBACK_ROUTES: List[Tuple[str, CallbackType, str, str]] = [
    # ==================== ГЛАВНОЕ МЕНЮ ====================
    ("back_to_menu", CallbackType.EXACT, "Главное меню", "handle_back_to_menu"),
    ("show_models", CallbackType.EXACT, "Показать модели", "handle_show_models"),
    ("all_models", CallbackType.EXACT, "Все модели (алиас)", "handle_show_models"),
    ("show_all_models_list", CallbackType.EXACT, "Список всех моделей", "handle_show_all_models_list"),
    
    # ==================== НАВИГАЦИЯ ====================
    ("cancel", CallbackType.EXACT, "Отмена", "handle_cancel"),
    ("reset_step", CallbackType.EXACT, "Сбросить шаг", "handle_reset_step"),
    ("reset_wizard", CallbackType.EXACT, "Сбросить визард", "handle_reset_wizard"),
    ("back_to_confirmation", CallbackType.EXACT, "Назад к подтверждению", "handle_back_to_confirmation"),
    ("back_to_previous_step", CallbackType.EXACT, "Назад к предыдущему шагу", "handle_back_to_previous_step"),
    
    # ==================== ГЕНЕРАЦИЯ ====================
    ("confirm_generate", CallbackType.EXACT, "Подтвердить генерацию", "handle_confirm_generate"),
    ("generate_again", CallbackType.EXACT, "Сгенерировать еще раз", "handle_generate_again"),
    ("show_parameters", CallbackType.EXACT, "Показать параметры", "handle_show_parameters"),
    
    # ==================== ТИПЫ ГЕНЕРАЦИИ ====================
    ("gen_type:", CallbackType.PREFIX, "Выбор типа генерации", "handle_gen_type"),
    ("category:", CallbackType.PREFIX, "Выбор категории", "handle_category"),
    ("free_tools", CallbackType.EXACT, "Бесплатные инструменты", "handle_free_tools"),
    ("other_models", CallbackType.EXACT, "Другие модели", "handle_other_models"),
    
    # ==================== ВЫБОР МОДЕЛИ ====================
    ("m:", CallbackType.PREFIX, "Выбор модели (короткий формат)", "handle_model_select"),
    ("model:", CallbackType.PREFIX, "Выбор модели", "handle_model_select"),
    ("modelk:", CallbackType.PREFIX, "Выбор модели с карточкой", "handle_model_select"),
    ("select_model:", CallbackType.PREFIX, "Выбор модели", "handle_model_select"),
    ("sel:", CallbackType.PREFIX, "Выбор модели (ultra-short)", "handle_model_select"),
    ("sku:", CallbackType.PREFIX, "Выбор SKU", "handle_sku_select"),
    ("sk:", CallbackType.PREFIX, "Выбор SKU (короткий)", "handle_sku_select"),
    ("select_mode:", CallbackType.PREFIX, "Выбор режима модели", "handle_select_mode"),
    
    # ==================== ПАРАМЕТРЫ ====================
    ("edit_param:", CallbackType.PREFIX, "Редактировать параметр", "handle_edit_param"),
    ("confirm_param:", CallbackType.PREFIX, "Подтвердить параметр", "handle_confirm_param"),
    ("set_param:", CallbackType.PREFIX, "Установить параметр", "handle_set_param"),
    
    # ==================== МЕДИА ====================
    ("add_image", CallbackType.EXACT, "Добавить изображение", "handle_add_image"),
    ("skip_image", CallbackType.EXACT, "Пропустить изображение", "handle_skip_image"),
    ("image_done", CallbackType.EXACT, "Изображение готово", "handle_image_done"),
    ("add_audio", CallbackType.EXACT, "Добавить аудио", "handle_add_audio"),
    ("skip_audio", CallbackType.EXACT, "Пропустить аудио", "handle_skip_audio"),
    
    # ==================== БАЛАНС И ОПЛАТА ====================
    ("check_balance", CallbackType.EXACT, "Проверить баланс", "handle_check_balance"),
    ("topup_balance", CallbackType.EXACT, "Пополнить баланс", "handle_topup_balance"),
    ("topup_amount:", CallbackType.PREFIX, "Выбор суммы пополнения", "handle_topup_amount"),
    ("topup_custom", CallbackType.EXACT, "Пополнить на произвольную сумму", "handle_topup_custom"),
    ("pay_stars:", CallbackType.PREFIX, "Оплата звездами", "handle_pay_stars"),
    ("pay_sbp:", CallbackType.PREFIX, "Оплата через СБП", "handle_pay_sbp"),
    ("pay_card:", CallbackType.PREFIX, "Оплата картой", "handle_pay_card"),
    
    # ==================== ИСТОРИЯ ====================
    ("my_generations", CallbackType.EXACT, "Мои генерации", "handle_my_generations"),
    ("gen_view:", CallbackType.PREFIX, "Просмотр генерации", "handle_gen_view"),
    ("gen_repeat:", CallbackType.PREFIX, "Повторить генерацию", "handle_gen_repeat"),
    ("gen_history:", CallbackType.PREFIX, "История генераций", "handle_gen_history"),
    
    # ==================== СТАРТ И ПРИМЕРЫ ====================
    ("start:", CallbackType.PREFIX, "Стартовая кнопка", "handle_start_button"),
    ("example:", CallbackType.PREFIX, "Пример использования", "handle_example"),
    ("info:", CallbackType.PREFIX, "Информация о модели", "handle_info"),
    ("type_header:", CallbackType.PREFIX, "Заголовок типа", "handle_type_header"),
    
    # ==================== ПОМОЩЬ И ОБУЧЕНИЕ ====================
    ("tutorial_start", CallbackType.EXACT, "Начать обучение", "handle_tutorial_start"),
    ("tutorial_step1", CallbackType.EXACT, "Шаг обучения 1", "handle_tutorial_step1"),
    ("tutorial_step2", CallbackType.EXACT, "Шаг обучения 2", "handle_tutorial_step2"),
    ("tutorial_step3", CallbackType.EXACT, "Шаг обучения 3", "handle_tutorial_step3"),
    ("tutorial_step4", CallbackType.EXACT, "Шаг обучения 4", "handle_tutorial_step4"),
    ("tutorial_complete", CallbackType.EXACT, "Обучение завершено", "handle_tutorial_complete"),
    ("help_menu", CallbackType.EXACT, "Меню помощи", "handle_help_menu"),
    ("support_contact", CallbackType.EXACT, "Связаться с поддержкой", "handle_support_contact"),
    
    # ==================== ДОПОЛНИТЕЛЬНО ====================
    ("claim_gift", CallbackType.EXACT, "Получить подарок", "handle_claim_gift"),
    ("copy_bot", CallbackType.EXACT, "Скопировать бота", "handle_copy_bot"),
    ("referral_info", CallbackType.EXACT, "Реферальная программа", "handle_referral_info"),
    ("set_language:", CallbackType.PREFIX, "Изменить язык", "handle_set_language"),
    ("retry_generate:", CallbackType.PREFIX, "Повторить генерацию", "handle_retry_generate"),
    ("retry_delivery:", CallbackType.PREFIX, "Повторить доставку", "handle_retry_delivery"),
    
    # ==================== АДМИНКА ====================
    ("admin_user_mode", CallbackType.EXACT, "Режим пользователя (админ)", "handle_admin_user_mode"),
    ("admin_stats", CallbackType.EXACT, "Статистика (админ)", "handle_admin_stats"),
    ("admin_settings", CallbackType.EXACT, "Настройки (админ)", "handle_admin_settings"),
    ("admin_config_check", CallbackType.EXACT, "Проверка конфига (админ)", "handle_admin_config_check"),
    ("admin_promocodes", CallbackType.EXACT, "Промокоды (админ)", "handle_admin_promocodes"),
    ("admin_broadcast", CallbackType.EXACT, "Рассылка (админ)", "handle_admin_broadcast"),
    ("admin_create_broadcast", CallbackType.EXACT, "Создать рассылку (админ)", "handle_admin_create_broadcast"),
    ("admin_set_currency_rate", CallbackType.EXACT, "Курс валюты (админ)", "handle_admin_set_currency_rate"),
    ("admin_broadcast_stats", CallbackType.EXACT, "Статистика рассылок (админ)", "handle_admin_broadcast_stats"),
    ("admin_search", CallbackType.EXACT, "Поиск (админ)", "handle_admin_search"),
    ("admin_add", CallbackType.EXACT, "Добавить (админ)", "handle_admin_add"),
    ("admin_test_ocr", CallbackType.EXACT, "Тест OCR (админ)", "handle_admin_test_ocr"),
    ("admin_view_generations", CallbackType.EXACT, "Просмотр генераций (админ)", "handle_admin_view_generations"),
    ("admin_back_to_admin", CallbackType.EXACT, "Назад в админку", "handle_admin_back_to_admin"),
    ("admin_payments_back", CallbackType.EXACT, "Назад к платежам (админ)", "handle_admin_payments_back"),
    ("view_payment_screenshots", CallbackType.EXACT, "Скриншоты платежей (админ)", "handle_view_payment_screenshots"),
    
    ("admin_user_info:", CallbackType.PREFIX, "Информация о пользователе (админ)", "handle_admin_user_info"),
    ("admin_topup_user:", CallbackType.PREFIX, "Пополнить пользователя (админ)", "handle_admin_topup_user"),
    ("admin_gen_nav:", CallbackType.PREFIX, "Навигация по генерациям (админ)", "handle_admin_gen_nav"),
    ("admin_gen_view:", CallbackType.PREFIX, "Просмотр генерации (админ)", "handle_admin_gen_view"),
    ("payment_screenshot_nav:", CallbackType.PREFIX, "Навигация по скриншотам (админ)", "handle_payment_screenshot_nav"),
]


def get_callback_map() -> Dict[str, Tuple[CallbackType, str, str]]:
    """
    Возвращает словарь: callback_data -> (callback_type, description, handler_name)
    """
    return {
        route[0]: (route[1], route[2], route[3])
        for route in CALLBACK_ROUTES
    }


def get_handlers_list() -> List[str]:
    """Возвращает список всех имен обработчиков"""
    return list(set(route[3] for route in CALLBACK_ROUTES))
