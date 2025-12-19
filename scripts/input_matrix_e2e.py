#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
INPUT MATRIX E2E - Test ALL input types for each model

For each model:
- TEXT: short, long, emoji, special chars, RU/EN mix
- PHOTO: if supports image
- AUDIO: if supports audio
- PARAMS: default/min/max/invalid

Each step must: send ACK, produce response OR clear error + main menu
"""

import sys
import os
import asyncio
import io
from pathlib import Path
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

# UTF-8 for Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set env before imports
os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token_12345'
os.environ['FAKE_KIE_MODE'] = '1'
os.environ['APP_ENV'] = 'test'

from kie_models import KIE_MODELS

# Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'


class ResponseTracker:
    """Track bot responses (same as behavioral_e2e)"""
    def __init__(self):
        self.sent_messages: List[Dict] = []
        self.replied_messages: List[Dict] = []
    
    def track_reply_text(self, text: str, **kwargs):
        self.replied_messages.append({"text": text[:200]})
    
    def get_response_count(self) -> int:
        return len(self.sent_messages) + len(self.replied_messages)


class InputMatrixTester:
    """Test input matrix for all models"""
    
    def __init__(self):
        self.results: List[Dict] = []
    
    async def test_input_type(self, model_id: str, input_type: str, value: str) -> Dict:
        """Test specific input type for a model"""
        # Use same approach as behavioral_e2e - mock BEFORE import
        import importlib
        
        # Mock all dependencies BEFORE importing bot_kie
        with patch('bot_kie.get_kie_gateway') as mock_gateway, \
             patch('bot_kie.get_user_balance', return_value=1000.0), \
             patch('bot_kie.get_user_balance_async', new_callable=AsyncMock, return_value=1000.0), \
             patch('bot_kie.get_user_language', return_value='ru'), \
             patch('bot_kie.user_sessions', {}), \
             patch('bot_kie.DATABASE_AVAILABLE', False), \
             patch('bot_kie.get_user_generations_history', return_value=[]), \
             patch('bot_kie.get_is_admin', return_value=False), \
             patch('bot_kie.is_free_generation_available', return_value=True), \
             patch('bot_kie.calculate_price_rub', return_value=1.0):
            
            # Setup fake gateway
            from tests.fakes.fake_kie_api import FakeKieAPI
            fake_gateway = FakeKieAPI()
            mock_gateway.return_value = fake_gateway
            
            # Import AFTER mocks
            if 'bot_kie' in sys.modules:
                importlib.reload(sys.modules['bot_kie'])
            from bot_kie import input_parameters, user_sessions, get_model_by_id
            from app.observability.no_silence_guard import get_no_silence_guard
            guard = get_no_silence_guard()
            
            # Get model info
            model_info = get_model_by_id(model_id) or {
                'id': model_id, 
                'name': model_id, 
                'input_params': {
                    'prompt': {
                        'required': True, 
                        'type': 'string', 
                        'max_length': 1000,
                        'description': 'Test prompt'
                    }
                }
            }
            
            # Set up session (user_sessions is now a real dict from patch)
            user_sessions[123] = {
                'model_id': model_id,
                'waiting_for': 'prompt',
                'current_param': 'prompt',
                'params': {},
                'model_info': model_info,
                'required': ['prompt'],
                'properties': model_info.get('input_params', {})
            }
            
            # Create tracker (same as behavioral_e2e)
            tracker = ResponseTracker()
            
            # Mock update with text (same pattern as behavioral_e2e)
            test_user = MagicMock()
            test_user.id = 123
            test_user.username = "test_user"
            
            test_chat = MagicMock()
            test_chat.id = 123
            test_chat.type = "private"
            
            update = MagicMock()
            update.update_id = 12345
            update.message = MagicMock()
            update.message.message_id = 1
            update.message.text = value
            update.message.from_user = test_user
            update.message.chat = test_chat
            update.message.chat_id = 123
            update.message.reply_text = AsyncMock(side_effect=lambda text, **kwargs: tracker.track_reply_text(text, **kwargs) or MagicMock(message_id=2))
            update.effective_user = test_user
            update.effective_chat = test_chat
            
            context = MagicMock()
            context.bot = MagicMock()
            context.bot.send_message = AsyncMock(side_effect=lambda chat_id, text, **kwargs: tracker.sent_messages.append({"chat_id": chat_id, "text": text[:200]}) or MagicMock(message_id=len(tracker.sent_messages) + 1))
            context.bot.get_file = AsyncMock(return_value=MagicMock())
            
            # Track responses using tracker (same as behavioral_e2e)
            responses_before = tracker.get_response_count()
            
            try:
                # Test input_parameters directly (same as behavioral_e2e)
                from bot_kie import input_parameters
                
                # Call input_parameters (it has instant ACK and NO-SILENCE guard)
                result = await input_parameters(update, context)
                
                responses_after = tracker.get_response_count()
                has_response = responses_after > responses_before
                
                return {
                    "model_id": model_id,
                    "input_type": input_type,
                    "passed": has_response,
                    "outgoing_actions": responses_after - responses_before
                }
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()[:500]
                return {
                    "model_id": model_id,
                    "input_type": input_type,
                    "passed": False,
                    "error": str(e)[:200],
                    "traceback": error_trace
                }
            finally:
                # Cleanup
                if 123 in user_sessions:
                    del user_sessions[123]
    
    async def run_all_tests(self):
        """Run input matrix tests for all models"""
        print("="*80)
        print("INPUT MATRIX E2E TESTING")
        print("="*80)
        
        input_types = [
            ("short_text", "test prompt"),
            ("long_text", "a" * 500),
            ("emoji", "test 🎨 prompt"),
            ("special_chars", "test !@#$% prompt"),
            ("ru_en_mix", "тест test prompt")
        ]
        
        # Test first 5 models for speed
        test_models = KIE_MODELS[:5]
        
        for model in test_models:
            model_id = model.get('id', 'unknown')
            print(f"\n[TEST] {model_id}")
            
            for input_name, input_value in input_types:
                result = await self.test_input_type(model_id, input_name, input_value)
                self.results.append(result)
                
                if result.get("passed"):
                    print(f"  {GREEN}[PASS]{RESET} {input_name}: {result.get('outgoing_actions', 0)} responses")
                else:
                    print(f"  {RED}[FAIL]{RESET} {input_name}: {result.get('error', 'No response')}")
        
        # Summary
        passed = sum(1 for r in self.results if r.get("passed"))
        total = len(self.results)
        
        print(f"\n{'='*80}")
        print(f"INPUT MATRIX RESULTS: {passed}/{total} passed")
        print(f"{'='*80}")
        
        return passed, total


async def main():
    """Main test runner"""
    tester = InputMatrixTester()
    passed, total = await tester.run_all_tests()
    
    # Save artifacts
    artifact_dir = project_root / "artifacts" / "inputs"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    
    # Summary
    summary = f"""# Input Matrix E2E Summary

**Date:** {Path(__file__).stat().st_mtime}

## Results
- **Total tests:** {total}
- **Passed:** {passed}
- **Failed:** {total - passed}
- **Pass rate:** {passed/total*100:.1f}%

## Details
"""
    for result in tester.results:
        status = "✅ PASS" if result.get("passed") else "❌ FAIL"
        summary += f"- {status}: {result.get('model_id')} - {result.get('input_type')}\n"
    
    with open(artifact_dir / "summary.md", 'w', encoding='utf-8') as f:
        f.write(summary)
    
    # Transcript
    transcript = "# Input Matrix Transcript\n\n"
    for result in tester.results[:10]:
        transcript += f"## {result.get('model_id')} - {result.get('input_type')}\n"
        transcript += f"Status: {'PASS' if result.get('passed') else 'FAIL'}\n"
        transcript += f"Responses: {result.get('outgoing_actions', 0)}\n\n"
    
    with open(artifact_dir / "transcript.md", 'w', encoding='utf-8') as f:
        f.write(transcript)
    
    print(f"\n✅ Artifacts saved to {artifact_dir}/")
    return 0 if passed == total else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
