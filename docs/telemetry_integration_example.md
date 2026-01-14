"""
Пример интеграции телеметрии в callback handler.

Этот файл показывает ДО и ПОСЛЕ добавления логирования.
Используйте это как шаблон при обновлении остальных handlers.
"""

# ============================================================================
# ДО: Callback handler без телеметрии (что было)
# ============================================================================

async def handle_category_select_OLD(callback_query):
    """Старый способ - без логирования."""
    try:
        data = callback_query.data.split("&")
        category_id = data[1]
        
        # FSM check - но если не пройдёт, молча игнорируем
        user_state = fsm.get_state(callback_query.from_user.id)
        if user_state != "waiting_for_category":
            return  # МОЛЧАНИЕ - пользователь ничего не поймёт!
        
        # Show models
        models = get_models_for_category(category_id)
        keyboard = build_keyboard(models)
        await callback_query.message.edit_text("Select model:", reply_markup=keyboard)
        
    except Exception as e:
        # Молчание или cryptic error
        pass


# ============================================================================
# ПОСЛЕ: Callback handler с полной телеметрией
# ============================================================================

from aiogram import types
from app.telemetry import (
    log_event,
    new_correlation_id,
    ReasonCode,
    EventType,
    Domain,
    ScreenId,
    ButtonId,
)
from app.telemetry.telemetry_helpers import (
    log_callback_received,
    log_callback_routed,
    log_callback_accepted,
    log_callback_rejected,
    log_ui_render,
    log_answer_callback_query,
)


async def handle_category_select_NEW(callback_query: types.CallbackQuery, **kwargs):
    """Новый способ - с полным логированием каждого шага."""
    
    # ========================================================================
    # 1. SETUP
    # ========================================================================
    
    # correlation_id приходит из middleware
    cid = kwargs.get("cid", new_correlation_id())
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    bot_state = kwargs.get("bot_state", "ACTIVE")
    update_id = kwargs.get("update_id", callback_query.message.message_id)
    
    # ========================================================================
    # 2. LOG: CALLBACK_RECEIVED - дошла кнопка от пользователя
    # ========================================================================
    
    log_callback_received(
        cid=cid,
        update_id=update_id,
        user_id=user_id,
        chat_id=chat_id,
        callback_data=callback_query.data,
        bot_state=bot_state,
    )
    
    # ========================================================================
    # 3. PARSE callback_data
    # ========================================================================
    
    try:
        # Parse: "action=category&id=1"
        parts = callback_query.data.split("&")
        if len(parts) != 2:
            raise ValueError(f"Invalid callback format: {callback_query.data}")
        
        action = parts[0].split("=")[1]  # action
        category_id = parts[1].split("=")[1]  # id
        
    except (ValueError, IndexError) as e:
        # LOG: CALLBACK_REJECTED - не распарсили callback_data
        log_callback_rejected(
            cid=cid,
            user_id=user_id,
            chat_id=chat_id,
            reason_code=ReasonCode.CALLBACK_PARSE_ERROR,
            reason_text=f"Malformed callback_data: {str(e)[:100]}",
            bot_state=bot_state,
        )
        
        # Answer to user
        user_text = "❌ Button error (malformed data). Go back and try again."
        log_answer_callback_query(cid, user_id, chat_id, user_text, show_alert=True)
        await callback_query.answer(user_text, show_alert=True)
        return
    
    # ========================================================================
    # 4. LOG: CALLBACK_ROUTED - распарсили, знаем какой handler
    # ========================================================================
    
    log_callback_routed(
        cid=cid,
        user_id=user_id,
        chat_id=chat_id,
        handler=__name__,
        action_id="category",
        button_id=ButtonId.CAT_IMAGE,  # Mapping callback action → button_id
    )
    
    # ========================================================================
    # 5. VALIDATE STATE - FSM должен быть в правильном состоянии
    # ========================================================================
    
    # Get user's FSM state
    user_state = await fsm.get_state(user_id)
    
    # Expected state for this button
    expected_state = ScreenId.MAIN_MENU
    
    if user_state != expected_state:
        # LOG: CALLBACK_REJECTED - FSM state mismatch
        log_callback_rejected(
            cid=cid,
            user_id=user_id,
            chat_id=chat_id,
            reason_code=ReasonCode.STATE_MISMATCH,
            reason_text=f"User on wrong screen. Klik /start to reset.",
            expected_state=expected_state,
            actual_state=user_state,
            bot_state=bot_state,
        )
        
        user_text = "❌ Button expired. Use /start to reset."
        log_answer_callback_query(cid, user_id, chat_id, user_text, show_alert=True)
        await callback_query.answer(user_text, show_alert=True)
        return
    
    # ========================================================================
    # 6. PROCESS - логика обработки (с error handling)
    # ========================================================================
    
    try:
        # Get models for category
        models = await db.get_models_for_category(category_id)
        
        if not models:
            log_callback_rejected(
                cid=cid,
                user_id=user_id,
                chat_id=chat_id,
                reason_code=ReasonCode.DB_ERROR,
                reason_text=f"No models found for category {category_id}",
            )
            
            user_text = "❌ Category empty. Try another one."
            log_answer_callback_query(cid, user_id, chat_id, user_text, show_alert=True)
            await callback_query.answer(user_text, show_alert=True)
            return
        
        # Update FSM state
        await fsm.set_state(user_id, ScreenId.MODEL_PICK)
        
        # Build keyboard from models
        keyboard = build_models_keyboard(models)
        
    except Exception as e:
        # LOG: CALLBACK_REJECTED - exception during processing
        log_callback_rejected(
            cid=cid,
            user_id=user_id,
            chat_id=chat_id,
            reason_code=ReasonCode.INTERNAL_ERROR,
            reason_text=f"Error fetching models: {str(e)[:100]}",
        )
        
        user_text = "❌ Server error. Please try again."
        log_answer_callback_query(cid, user_id, chat_id, user_text, show_alert=True)
        await callback_query.answer(user_text, show_alert=True)
        return
    
    # ========================================================================
    # 7. LOG: CALLBACK_ACCEPTED - всё успешно
    # ========================================================================
    
    log_callback_accepted(
        cid=cid,
        user_id=user_id,
        chat_id=chat_id,
        next_screen=ScreenId.MODEL_PICK,
        action_id="category",
    )
    
    # ========================================================================
    # 8. SEND UI - отправить следующий экран
    # ========================================================================
    
    try:
        await callback_query.message.edit_text(
            text="📦 Select a model:",
            reply_markup=keyboard,
        )
        
        # LOG: UI_RENDER - отправили новый экран
        button_ids = [m["button_id"] for m in models]
        log_ui_render(
            cid=cid,
            user_id=user_id,
            chat_id=chat_id,
            screen_id=ScreenId.MODEL_PICK,
            buttons=button_ids,
        )
        
    except Exception as e:
        log_callback_rejected(
            cid=cid,
            user_id=user_id,
            chat_id=chat_id,
            reason_code=ReasonCode.INTERNAL_ERROR,
            reason_text=f"Error sending message: {str(e)[:100]}",
        )
        return
    
    # ========================================================================
    # 9. ANSWER CALLBACK_QUERY - notify user that button worked
    # ========================================================================
    
    user_text = "✅ Models loaded"
    log_answer_callback_query(cid, user_id, chat_id, user_text, show_alert=False)
    await callback_query.answer(user_text)


# ============================================================================
# SUMMARY
# ============================================================================

"""
ДО → ПОСЛЕ изменения:

ДО (молчаливые фейлы):
  ❌ Callback_data не распарсился → молчание
  ❌ FSM state неправильный → молчание
  ❌ DB error → молчание
  ❌ Пользователь не знает что произошло

ПОСЛЕ (явное логирование):
  ✅ Callback_data не распарсился → log reason_code=CALLBACK_PARSE_ERROR
  ✅ FSM state неправильный → log reason_code=STATE_MISMATCH
  ✅ DB error → log reason_code=DB_ERROR
  ✅ Пользователю сообщение об ошибке
  ✅ Админу можно найти по cid в логах в течение 60 сек

Интеграция:
1. Добавь cid = kwargs.get("cid") в начало handler
2. Log CALLBACK_RECEIVED
3. На каждый reject/error → log CALLBACK_REJECTED с reason_code
4. На success → log CALLBACK_ACCEPTED
5. После отправки экрана → log UI_RENDER

Шаблон выше показывает все 9 шагов. Используй как reference для остальных handlers.
"""
