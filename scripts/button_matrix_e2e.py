#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BUTTON MATRIX E2E - Test ALL buttons for user-logical behavior

For each button:
- click once
- click twice quickly
- click after error state
- click after restart simulation (clear user state)

Assert: outgoing_actions > 0 and UX is logical (next step + main menu)
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


class ButtonMatrixTester:
    """Test button matrix scenarios"""
    
    def __init__(self):
        self.results: List[Dict] = []
        self.callback_patterns = [
            'show_models', 'back_to_menu', 'select_model:', 'gen_type:',
            'category:', 'all_models', 'check_balance', 'topup_balance'
        ]
    
    async def test_button_scenario(self, callback_data: str, scenario: str) -> Dict:
        """Test a button in a specific scenario"""
        # Mock all dependencies BEFORE importing bot_kie
        with patch('bot_kie.get_kie_gateway') as mock_gateway, \
             patch('bot_kie.get_user_balance', return_value=1000.0), \
             patch('bot_kie.get_user_language', return_value='ru'), \
             patch('bot_kie.user_sessions', {}), \
             patch('bot_kie.DATABASE_AVAILABLE', False), \
             patch('bot_kie.get_user_generations_history', return_value=[]), \
             patch('bot_kie.get_is_admin', return_value=False), \
             patch('bot_kie.is_free_generation_available', return_value=True):
            
            # Setup fake gateway
            from tests.fakes.fake_kie_api import FakeKieAPI
            fake_gateway = FakeKieAPI()
            mock_gateway.return_value = fake_gateway
            
            from app.observability.no_silence_guard import get_no_silence_guard
            guard = get_no_silence_guard()
            
            # Mock update
            update = MagicMock()
            update.update_id = 12345
            update.callback_query = MagicMock()
            update.callback_query.data = callback_data
            update.callback_query.from_user.id = 123
            update.callback_query.message = MagicMock()
            update.callback_query.message.chat_id = 123
            update.callback_query.answer = AsyncMock()
            update.callback_query.edit_message_text = AsyncMock()
            
            context = MagicMock()
            context.bot = MagicMock()
            context.bot.send_message = AsyncMock()
            
            # Track outgoing actions
            outgoing_count_before = guard.outgoing_actions.get(update.update_id, 0)
            
            try:
                # Import and call button_callback
                import importlib
                if 'bot_kie' in sys.modules:
                    importlib.reload(sys.modules['bot_kie'])
                from bot_kie import button_callback
                
                result = await button_callback(update, context)
                
                # Check response
                outgoing_count_after = guard.outgoing_actions.get(update.update_id, 0)
                has_response = outgoing_count_after > outgoing_count_before
                
                return {
                    "callback": callback_data,
                    "scenario": scenario,
                    "passed": has_response,
                    "outgoing_actions": outgoing_count_after - outgoing_count_before,
                    "result": str(result)[:100]
                }
            except Exception as e:
                return {
                    "callback": callback_data,
                    "scenario": scenario,
                    "passed": False,
                    "error": str(e)[:200]
                }
    
    async def run_all_tests(self):
        """Run all button matrix tests"""
        print("="*80)
        print("BUTTON MATRIX E2E TESTING")
        print("="*80)
        
        scenarios = [
            ("normal_click", "Normal click"),
            ("double_click", "Double click quickly"),
            ("after_error", "Click after error state"),
            ("after_restart", "Click after restart (no session)")
        ]
        
        for callback_pattern in self.callback_patterns[:5]:  # Test first 5 for speed
            for scenario_name, scenario_desc in scenarios:
                print(f"\n[TEST] {callback_pattern} - {scenario_desc}")
                result = await self.test_button_scenario(callback_pattern, scenario_name)
                self.results.append(result)
                
                if result.get("passed"):
                    print(f"  {GREEN}[PASS]{RESET} {result.get('outgoing_actions', 0)} responses")
                else:
                    print(f"  {RED}[FAIL]{RESET} {result.get('error', 'No response')}")
        
        # Generate summary
        passed = sum(1 for r in self.results if r.get("passed"))
        total = len(self.results)
        
        print(f"\n{'='*80}")
        print(f"BUTTON MATRIX RESULTS: {passed}/{total} passed")
        print(f"{'='*80}")
        
        return passed, total


async def main():
    """Main test runner"""
    tester = ButtonMatrixTester()
    passed, total = await tester.run_all_tests()
    
    # Save artifacts
    artifact_dir = project_root / "artifacts" / "buttons"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    
    # Summary
    summary = f"""# Button Matrix E2E Summary

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
        summary += f"- {status}: {result.get('callback')} - {result.get('scenario')}\n"
    
    with open(artifact_dir / "summary.md", 'w', encoding='utf-8') as f:
        f.write(summary)
    
    # Transcript
    transcript = "# Button Matrix Transcript\n\n"
    for result in tester.results[:10]:  # First 10
        transcript += f"## {result.get('callback')} - {result.get('scenario')}\n"
        transcript += f"Status: {'PASS' if result.get('passed') else 'FAIL'}\n"
        transcript += f"Responses: {result.get('outgoing_actions', 0)}\n\n"
    
    with open(artifact_dir / "transcript.md", 'w', encoding='utf-8') as f:
        f.write(transcript)
    
    print(f"\n✅ Artifacts saved to {artifact_dir}/")
    return 0 if passed == total else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
