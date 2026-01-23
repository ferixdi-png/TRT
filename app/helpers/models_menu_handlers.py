"""
Обработчики для меню моделей из каталога.
Функции для замены в bot_kie.py.
"""

import logging
from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.helpers.models_menu import (
    build_models_menu_by_type,
    build_model_card_text,
    resolve_model_id_from_callback
)
from app.kie_catalog import get_model
from app.models.canonical import canonicalize_model_id
from app.config import get_settings
from app.observability.structured_logs import log_structured_event

logger = logging.getLogger(__name__)


async def handle_show_all_models_list(
    query,
    user_id: int,
    user_lang: str,
    default_model_id: Optional[str] = None,
    *,
    skip_answer: bool = False,
) -> None:
    """
    Обработчик для callback 'show_all_models_list'.
    Показывает все модели из каталога с ценами.
    """
    if not skip_answer:
        try:
            await query.answer()
        except Exception:
            pass
    
    logger.info(f"User {user_id} clicked 'show_all_models_list'")
    
    # Строим меню из каталога
    try:
        from app.kie_catalog import list_models
        catalog = list_models()
        
        if user_lang == 'ru':
            models_text = (
                f"╔═══════════════════════════════════════════╗\n"
                f"║  🤖 ВСЕ МОДЕЛИ KIE AI 🤖                  ║\n"
                f"╚═══════════════════════════════════════════╝\n\n"
                f"╔═══════════════════════════════════════════╗\n"
                f"║  📦 ДОСТУПНО: <b>{len(catalog)} МОДЕЛЕЙ</b> 📦        ║\n"
                f"╚═══════════════════════════════════════════╝\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 <b>Цены в рублях</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"💡 <b>Выберите модель для просмотра деталей и генерации</b>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
        else:
            models_text = (
                f"╔═══════════════════════════════════╗\n"
                f"║  🤖 ALL KIE AI MODELS 🤖          ║\n"
                f"╚═══════════════════════════════════╝\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📦 <b>Available:</b> <b>{len(catalog)} models</b>\n"
                f"💰 <b>Prices in RUB</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"💡 <b>Select a model to view details and generate</b>"
            )
        
        # Строим клавиатуру из каталога
        keyboard_markup = build_models_menu_by_type(
            user_lang,
            default_model_id=default_model_id,
        )
        
        await query.edit_message_text(
            models_text,
            reply_markup=keyboard_markup,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Error in handle_show_all_models_list: {e}", exc_info=True)
        if user_lang == 'ru':
            error_msg = "❌ Ошибка при загрузке моделей. Попробуйте позже."
        else:
            error_msg = "❌ Error loading models. Please try later."
        await query.answer(error_msg, show_alert=True)


async def handle_model_callback(
    query,
    user_id: int,
    user_lang: str,
    callback_data: str
) -> bool:
    """
    Обработчик для callback 'model:*'.
    Показывает карточку модели с ценой.
    
    Returns:
        True если обработано успешно, False если модель не найдена
    """
    try:
        await query.answer()
    except:
        pass
    
    # Разрешаем model_id из callback_data
    model_id = resolve_model_id_from_callback(callback_data)
    if model_id:
        model_id = canonicalize_model_id(model_id)
    
    if not model_id:
        logger.warning(f"Could not resolve model_id from callback_data: {callback_data}")
        if user_lang == 'ru':
            await query.answer("❌ Ошибка: неверный формат запроса", show_alert=True)
        else:
            await query.answer("❌ Error: invalid request format", show_alert=True)
        return False
    
    logger.info(f"Model card requested: model_id={model_id}, user_id={user_id}")
    
    # Получаем модель из каталога
    model = get_model(model_id)
    
    if not model:
        logger.warning(f"Model not found in catalog: {model_id}")
        if user_lang == 'ru':
            error_msg = f"❌ Модель {model_id} временно недоступна"
        else:
            error_msg = f"❌ Model {model_id} temporarily unavailable"
        
        keyboard = [
            [InlineKeyboardButton(
                "🔙 Назад к моделям" if user_lang == 'ru' else "🔙 Back to models",
                callback_data="show_all_models_list"
            )]
        ]
        
        try:
            await query.edit_message_text(
                error_msg,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
        except Exception as e:
            logger.warning(f"Could not edit message: {e}")
            try:
                await query.message.reply_text(
                    error_msg,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
                try:
                    await query.message.delete()
                except:
                    pass
            except:
                await query.answer(error_msg, show_alert=True)
        
        return False
    
    # Проверяем видимость модели по SSOT
    try:
        from app.ux.model_visibility import evaluate_model_visibility, STATUS_READY_VISIBLE
        visibility = evaluate_model_visibility(model.id)
        if visibility.status != STATUS_READY_VISIBLE:
            log_structured_event(
                correlation_id=None,
                user_id=user_id,
                action="MODEL_BLOCKED",
                action_path="models_menu.card",
                model_id=model.id,
                stage="MODEL_VISIBILITY",
                outcome="blocked",
                error_code=visibility.status,
                fix_hint="Проверьте требования модели и прайсинг.",
                param={
                    "issues": visibility.issues,
                    "required_fields": visibility.required_fields,
                },
            )
            if user_lang == 'ru':
                issues = "\n".join(f"• {issue}" for issue in visibility.issues) if visibility.issues else "• Причина не указана"
                blocked_text = (
                    "⛔️ <b>Модель недоступна</b>\n\n"
                    f"Причина: <code>{visibility.status}</code>\n"
                    f"{issues}"
                )
            else:
                issues = "\n".join(f"• {issue}" for issue in visibility.issues) if visibility.issues else "• No details available"
                blocked_text = (
                    "⛔️ <b>Model unavailable</b>\n\n"
                    f"Reason: <code>{visibility.status}</code>\n"
                    f"{issues}"
                )
            await query.edit_message_text(blocked_text, parse_mode='HTML')
            return False
    except Exception as exc:
        logger.warning("Visibility check failed for model %s: %s", model.id, exc)

    # Строим карточку модели
    try:
        card_text, keyboard_markup = build_model_card_text(model, mode_index=0, user_lang=user_lang)
        
        await query.edit_message_text(
            card_text,
            reply_markup=keyboard_markup,
            parse_mode='HTML'
        )
        
        return True
    except Exception as e:
        logger.error(f"Error building model card: {e}", exc_info=True)
        if user_lang == 'ru':
            await query.answer("❌ Ошибка при загрузке карточки модели", show_alert=True)
        else:
            await query.answer("❌ Error loading model card", show_alert=True)
        return False
