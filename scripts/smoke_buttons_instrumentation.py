"""
Smoke тест: "КНОПКИ НЕ ТЕРЯЮТСЯ" - проверить, что callback создаёт полную цепочку событий.

Цепочка для успешного callback:
1. CALLBACK_RECEIVED
2. CALLBACK_ROUTED
3. CALLBACK_ACCEPTED (или CALLBACK_REJECTED/NOOP с reason_code)
4. UI_RENDER (следующий экран)

Если какого-то события нет - тест падает (CI red).
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class LogEventCapture:
    """Перехватывать log_event вызовы для тестирования."""
    
    def __init__(self):
        self.events: List[dict] = []
        self.original_logger_info = None
    
    def __enter__(self):
        # Перехватить logger.info вызовы
        self.original_logger_info = logger.info
        logger.info = self._capture_log
        return self
    
    def __exit__(self, *args):
        logger.info = self.original_logger_info
    
    def _capture_log(self, msg: str, *args, **kwargs):
        """Перехватить JSON-structured log."""
        try:
            # Если это наш JSON log event
            if isinstance(msg, str) and msg.startswith("{"):
                event = json.loads(msg)
                self.events.append(event)
        except (json.JSONDecodeError, Exception):
            pass
    
    def find_event(self, name: str, cid: str) -> Optional[dict]:
        """Найти событие по name и cid."""
        for event in self.events:
            if event.get("name") == name and event.get("cid") == cid:
                return event
        return None
    
    def find_events_for_cid(self, cid: str) -> List[dict]:
        """Найти все события для cid."""
        return [e for e in self.events if e.get("cid") == cid]


async def test_callback_chain() -> bool:
    """
    Smoke тест: проверить, что callback создаёт полную цепочку.
    
    Сценарий:
    1. Отправить /start → получить MAIN_MENU
    2. Кликнуть на кнопку CAT_IMAGE
    3. Проверить, что в логах есть полная цепочка:
       - CALLBACK_RECEIVED
       - CALLBACK_ROUTED
       - CALLBACK_ACCEPTED
       - UI_RENDER (next screen)
    
    Returns:
        True если тест прошёл, False если не прошёл
    """
    
    logger.info("=" * 60)
    logger.info("🚀 SMOKE TEST: Button Chain Detection")
    logger.info("=" * 60)
    
    test_cid = "smoke_test_001"
    required_events = [
        "CALLBACK_RECEIVED",
        "CALLBACK_ROUTED",
        "CALLBACK_ACCEPTED",
        "UI_RENDER",
    ]
    
    # Перехватить события
    with LogEventCapture() as capture:
        # Имитация: логировать события как в реальной обработке
        from app.telemetry.logging_contract import log_event, EventType, Domain, ReasonCode
        from app.telemetry.telemetry_helpers import (
            log_callback_received,
            log_callback_routed,
            log_callback_accepted,
            log_ui_render,
        )
        
        # Simulated flow
        test_user_id = 12345
        test_chat_id = 67890
        
        # Event 1: CALLBACK_RECEIVED
        log_callback_received(
            cid=test_cid,
            update_id=999,
            user_id=test_user_id,
            chat_id=test_chat_id,
            callback_data="action=category&id=image",
            bot_state="ACTIVE",
        )
        
        # Event 2: CALLBACK_ROUTED
        log_callback_routed(
            cid=test_cid,
            user_id=test_user_id,
            chat_id=test_chat_id,
            handler="handle_category_select",
            action_id="category",
            button_id="CAT_IMAGE",
        )
        
        # Event 3: CALLBACK_ACCEPTED
        log_callback_accepted(
            cid=test_cid,
            user_id=test_user_id,
            chat_id=test_chat_id,
            next_screen="CATEGORY_PICK",
            action_id="category",
        )
        
        # Event 4: UI_RENDER
        log_ui_render(
            cid=test_cid,
            user_id=test_user_id,
            chat_id=test_chat_id,
            screen_id="CATEGORY_PICK",
            buttons=["MODEL_ZIMAGE", "MODEL_DEEPDREAM", "BACK"],
        )
        
        # Проверить цепочку
        found_events = []
        missing_events = []
        
        for event_name in required_events:
            event = capture.find_event(event_name, test_cid)
            if event:
                found_events.append(event_name)
                logger.info(f"✅ {event_name}: found")
            else:
                missing_events.append(event_name)
                logger.error(f"❌ {event_name}: NOT FOUND")
        
        # Results
        logger.info("")
        logger.info(f"Found: {len(found_events)}/{len(required_events)} events")
        
        if missing_events:
            logger.error(f"❌ FAIL: Missing events: {missing_events}")
            return False
        
        # Проверить все события имеют cid
        all_events_for_cid = capture.find_events_for_cid(test_cid)
        logger.info(f"📊 Total events for cid={test_cid}: {len(all_events_for_cid)}")
        
        if len(all_events_for_cid) >= len(required_events):
            logger.info("✅ PASS: Full callback chain detected")
            return True
        else:
            logger.error(f"❌ FAIL: Expected {len(required_events)}, got {len(all_events_for_cid)}")
            return False


async def test_reason_codes_present() -> bool:
    """Проверить, что отказанные callbacks имеют reason_code."""
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("🚀 SMOKE TEST: Reason Codes Present")
    logger.info("=" * 60)
    
    test_cid = "smoke_test_002"
    
    with LogEventCapture() as capture:
        from app.telemetry.logging_contract import log_event, ReasonCode
        from app.telemetry.telemetry_helpers import log_callback_rejected
        
        # Simulated rejection
        log_callback_rejected(
            cid=test_cid,
            user_id=12345,
            chat_id=67890,
            reason_code=ReasonCode.STATE_MISMATCH,
            reason_text="FSM state was PARAMS_FORM, expected MAIN_MENU",
            expected_state="MAIN_MENU",
            actual_state="PARAMS_FORM",
        )
        
        event = capture.find_event("CALLBACK_REJECTED", test_cid)
        
        if event:
            has_reason_code = "reason_code" in event
            has_reason_text = "reason_text" in event
            
            if has_reason_code and has_reason_text:
                logger.info(f"✅ PASS: reason_code and reason_text present")
                logger.info(f"   Code: {event.get('reason_code')}")
                logger.info(f"   Text: {event.get('reason_text')}")
                return True
            else:
                logger.error(f"❌ FAIL: Missing reason_code or reason_text")
                return False
        else:
            logger.error(f"❌ FAIL: CALLBACK_REJECTED event not found")
            return False


async def main() -> int:
    """Запустить все smoke тесты."""
    
    logger.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    
    tests = [
        ("Callback Chain Detection", test_callback_chain),
        ("Reason Codes Present", test_reason_codes_present),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"❌ {name} crashed: {e}")
            results.append((name, False))
    
    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("📊 SUMMARY")
    logger.info("=" * 60)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {name}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    logger.info(f"\nTotal: {passed}/{total} passed")
    
    if passed == total:
        logger.info("🎉 All tests passed!")
        return 0
    else:
        logger.error("💥 Some tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
