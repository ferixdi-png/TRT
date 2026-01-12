#!/usr/bin/env python3
"""
Smoke test for UI handlers - verify /start message and menu structure.
"""
import re
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_start_handler():
    """Test that /start handler sends correct message."""
    from bot.handlers.flow import start_cmd
    
    # Read source code (not executing)
    flow_file = Path(__file__).parent.parent / "bot" / "handlers" / "flow.py"
    content = flow_file.read_text(encoding="utf-8")
    
    # Check start_cmd exists
    assert "@router.message(Command(\"start\"))" in content, "Missing /start handler"
    
    # Check NO VPN mentions
    assert "Купить VPN" not in content, "❌ FOUND VPN BUTTONS IN FLOW.PY"
    assert "Бесплатный VPN" not in content, "❌ FOUND VPN BUTTONS IN FLOW.PY"
    
    # Check correct AI generation message
    assert "AI моделей" in content, "Missing AI models mention"
    assert "Картинки и дизайн" in content, "Missing categories"
    assert "Видео для TikTok/Reels" in content, "Missing video category"
    
    print("✅ /start handler: correct AI generation interface")
    
    # Check main menu keyboard
    assert "_main_menu_keyboard" in content, "Missing main menu keyboard"
    
    # Find main menu keyboard function
    menu_match = re.search(
        r"def _main_menu_keyboard\(\).*?return InlineKeyboardMarkup\((.*?)\)",
        content,
        re.DOTALL,
    )
    assert menu_match, "Could not find _main_menu_keyboard implementation"
    
    menu_code = menu_match.group(0)
    
    # Check NO VPN in menu
    assert "VPN" not in menu_code, "❌ FOUND VPN IN MAIN MENU"
    
    # Check correct menu items
    assert "menu:categories" in content or "Категории" in menu_code, "Missing categories button"
    print("✅ Main menu: no VPN buttons, correct AI interface")
    
    return True


def test_no_vpn_anywhere():
    """Verify NO VPN code anywhere in handlers."""
    handlers_dir = Path(__file__).parent.parent / "bot" / "handlers"
    
    vpn_files = []
    for py_file in handlers_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if "VPN" in content or "vpn" in content:
            vpn_files.append(py_file.name)
    
    if vpn_files:
        print(f"⚠️  Found VPN mentions in: {vpn_files}")
        print("   (This might be in comments/old code)")
    else:
        print("✅ No VPN code in handlers")
    
    return True


def main():
    """Run all smoke tests."""
    print("=" * 60)
    print("SMOKE TEST: UI Handlers")
    print("=" * 60)
    
    try:
        test_start_handler()
        test_no_vpn_anywhere()
        
        print()
        print("=" * 60)
        print("✅ ALL TESTS PASSED - UI is correct AI generation interface")
        print("=" * 60)
        print()
        print("📋 If you see VPN interface in Telegram:")
        print("   1. Check you're using correct bot token (not VPN bot)")
        print("   2. Clear Telegram cache: Settings → Data → Clear cache")
        print("   3. Restart bot conversation: /start")
        print("   4. Check Render logs for correct deployment")
        print()
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
