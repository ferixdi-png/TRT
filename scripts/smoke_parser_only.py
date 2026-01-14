#!/usr/bin/env python3
"""
Smoke test только для парсера V4 - без реальных API вызовов.
Проверяет parse_record_info на реалистичных примерах V4 ответов.
"""
import sys
import os

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.kie.parser import parse_record_info


def test_parser_v4_real_examples():
    """Тест парсера на реалистичных примерах V4 ответов."""
    
    print("🧪 Parser V4 Smoke Test")
    print("=" * 60)
    
    # Пример 1: V4 формат с state в data wrapper
    print("\n📝 Test 1: V4 format с state в data.state")
    response1 = {
        "data": {
            "taskId": "task_123",
            "state": "done",
            "resultJson": '{"result": {"imageUrl": "https://example.com/image.png"}}'
        }
    }
    
    parsed1 = parse_record_info(response1)
    print(f"   state: {parsed1.get('state')}")
    print(f"   is_done: {parsed1.get('is_done')}")
    print(f"   is_failed: {parsed1.get('is_failed')}")
    
    assert parsed1.get('state') == 'done', f"Expected 'done', got {parsed1.get('state')}"
    assert parsed1.get('is_done') is True, "Expected is_done=True"
    print("   ✅ PASSED")
    
    # Пример 2: V4 формат с status=success
    print("\n📝 Test 2: V4 format с status='success' (needs normalization)")
    response2 = {
        "data": {
            "taskId": "task_456",
            "status": "success",
            "resultJson": {"imageUrl": "https://example.com/image2.png"}
        }
    }
    
    parsed2 = parse_record_info(response2)
    print(f"   state: {parsed2.get('state')}")
    print(f"   is_done: {parsed2.get('is_done')}")
    
    assert parsed2.get('state') == 'done', f"Expected 'done', got {parsed2.get('state')}"
    assert parsed2.get('is_done') is True, "Expected is_done=True"
    print("   ✅ PASSED")
    
    # Пример 3: V4 формат с state=pending
    print("\n📝 Test 3: V4 format с state='pending'")
    response3 = {
        "data": {
            "taskId": "task_789",
            "state": "pending"
        }
    }
    
    parsed3 = parse_record_info(response3)
    print(f"   state: {parsed3.get('state')}")
    print(f"   is_done: {parsed3.get('is_done')}")
    print(f"   is_failed: {parsed3.get('is_failed')}")
    
    assert parsed3.get('state') == 'pending', f"Expected 'pending', got {parsed3.get('state')}"
    assert parsed3.get('is_done') is False, "Expected is_done=False"
    assert parsed3.get('is_failed') is False, "Expected is_failed=False"
    print("   ✅ PASSED")
    
    # Пример 4: V4 формат с state=failed
    print("\n📝 Test 4: V4 format с state='failed'")
    response4 = {
        "data": {
            "taskId": "task_error",
            "state": "failed",
            "error": "Out of quota"
        }
    }
    
    parsed4 = parse_record_info(response4)
    print(f"   state: {parsed4.get('state')}")
    print(f"   is_done: {parsed4.get('is_done')}")
    print(f"   is_failed: {parsed4.get('is_failed')}")
    print(f"   error: {parsed4.get('error')}")
    
    assert parsed4.get('state') == 'fail', f"Expected 'fail', got {parsed4.get('state')}"
    assert parsed4.get('is_failed') is True, "Expected is_failed=True"
    print("   ✅ PASSED")
    
    # Пример 5: Legacy формат (state на верхнем уровне)
    print("\n📝 Test 5: Legacy format (state в root)")
    response5 = {
        "taskId": "task_legacy",
        "state": "completed",
        "resultJson": '{"result": {"imageUrl": "https://example.com/legacy.png"}}'
    }
    
    parsed5 = parse_record_info(response5)
    print(f"   state: {parsed5.get('state')}")
    print(f"   is_done: {parsed5.get('is_done')}")
    
    assert parsed5.get('state') == 'done', f"Expected 'done', got {parsed5.get('state')}"
    assert parsed5.get('is_done') is True, "Expected is_done=True"
    print("   ✅ PASSED")
    
    # Пример 6: z-image callback формат
    print("\n📝 Test 6: z-image callback format")
    response6 = {
        "recordId": "rec_123",
        "data": {
            "state": "succeed",
            "result": {
                "imageUrl": "https://cdn.example.com/zimage.png",
                "width": 1920,
                "height": 1080
            }
        }
    }
    
    parsed6 = parse_record_info(response6)
    print(f"   state: {parsed6.get('state')}")
    print(f"   is_done: {parsed6.get('is_done')}")
    print(f"   resultJson: {parsed6.get('resultJson')}")
    
    assert parsed6.get('state') == 'done', f"Expected 'done', got {parsed6.get('state')}"
    assert parsed6.get('is_done') is True, "Expected is_done=True"
    print("   ✅ PASSED")
    
    print("\n" + "=" * 60)
    print("🎉 ALL PARSER SMOKE TESTS PASSED")
    print("=" * 60)
    return True


if __name__ == "__main__":
    try:
        success = test_parser_v4_real_examples()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ EXCEPTION: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
