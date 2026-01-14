#!/usr/bin/env python3
"""
PRODUCTION CHECK: Webhook Diagnostics After Token Change

Validates webhook setup and provides diagnostics for common issues:
- PHASE 1: Environment variables check (BOT_TOKEN, WEBHOOK_BASE_URL)
- PHASE 2: Bot identity verification (get_me)
- PHASE 3: Current webhook state (get_webhook_info)
- PHASE 4: Expected webhook URL calculation
- PHASE 5: Webhook mismatch detection
- PHASE 6: Force webhook reset option

Usage:
    python3 tools/prod_check_webhook_token_change.py
    python3 tools/prod_check_webhook_token_change.py --force-reset  # Reset webhook

Expected result: Webhook correctly configured for current BOT_TOKEN
"""
import sys
import os
import asyncio
import argparse
from pathlib import Path

# Add project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def phase1_env_check():
    """PHASE 1: Environment variables."""
    print("\n" + "="*80)
    print("PHASE 1: Environment Variables Check")
    print("="*80)
    
    errors = []
    warnings = []
    
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    webhook_base_url = os.getenv("WEBHOOK_BASE_URL", "").strip()
    
    if not bot_token:
        errors.append("❌ CRITICAL: TELEGRAM_BOT_TOKEN not set!")
        return errors, warnings
    
    # Mask token for security
    masked_token = bot_token[:10] + "..." + bot_token[-10:] if len(bot_token) > 20 else "***"
    print(f"✅ TELEGRAM_BOT_TOKEN: {masked_token}")
    
    if not webhook_base_url:
        errors.append("❌ CRITICAL: WEBHOOK_BASE_URL not set! Webhook cannot be configured.")
    else:
        print(f"✅ WEBHOOK_BASE_URL: {webhook_base_url}")
    
    # Validate token format (should be like 123456789:ABC-DEF...)
    if ":" not in bot_token:
        errors.append(f"❌ CRITICAL: Invalid token format (missing ':'): {masked_token}")
    
    return errors, warnings


async def phase2_bot_identity():
    """PHASE 2: Bot identity verification."""
    print("\n" + "="*80)
    print("PHASE 2: Bot Identity Verification")
    print("="*80)
    
    errors = []
    warnings = []
    
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        errors.append("❌ CRITICAL: Cannot verify bot without token")
        return errors, warnings
    
    try:
        from aiogram import Bot
        bot = Bot(token=bot_token)
        
        # Call get_me
        me = await bot.get_me()
        
        print(f"✅ Bot ID: {me.id}")
        print(f"✅ Bot Username: @{me.username}")
        print(f"✅ Bot Name: {me.first_name}")
        print(f"✅ Can Join Groups: {me.can_join_groups}")
        print(f"✅ Can Read All Group Messages: {me.can_read_all_group_messages}")
        
        await bot.session.close()
        
    except Exception as e:
        errors.append(f"❌ CRITICAL: Failed to verify bot identity: {e}")
        errors.append("   Possible causes:")
        errors.append("   - Invalid/expired BOT_TOKEN")
        errors.append("   - Network issues")
        errors.append("   - Telegram API down")
    
    return errors, warnings


async def phase3_current_webhook():
    """PHASE 3: Current webhook state."""
    print("\n" + "="*80)
    print("PHASE 3: Current Webhook State")
    print("="*80)
    
    errors = []
    warnings = []
    
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        errors.append("❌ CRITICAL: Cannot check webhook without token")
        return errors, warnings
    
    try:
        from aiogram import Bot
        bot = Bot(token=bot_token)
        
        # Get webhook info
        webhook_info = await bot.get_webhook_info()
        
        print(f"Current Webhook URL: {webhook_info.url or '(not set)'}")
        print(f"Pending Updates: {webhook_info.pending_update_count}")
        print(f"Last Error Date: {webhook_info.last_error_date or 'N/A'}")
        print(f"Last Error Message: {webhook_info.last_error_message or 'N/A'}")
        print(f"Max Connections: {webhook_info.max_connections}")
        
        if webhook_info.last_error_message:
            warnings.append(f"⚠️ Webhook has errors: {webhook_info.last_error_message}")
        
        if not webhook_info.url:
            warnings.append("⚠️ Webhook NOT SET - bot is in polling mode or not configured")
        
        await bot.session.close()
        
        return errors, warnings, webhook_info
        
    except Exception as e:
        errors.append(f"❌ CRITICAL: Failed to get webhook info: {e}")
        return errors, warnings, None


async def phase4_expected_webhook():
    """PHASE 4: Calculate expected webhook URL."""
    print("\n" + "="*80)
    print("PHASE 4: Expected Webhook URL")
    print("="*80)
    
    errors = []
    warnings = []
    
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    webhook_base_url = os.getenv("WEBHOOK_BASE_URL", "").strip()
    
    if not bot_token or not webhook_base_url:
        errors.append("❌ CRITICAL: Missing ENV vars")
        return errors, warnings, None
    
    # Derive secret path from token (same as main_render.py)
    cleaned = bot_token.strip().replace(":", "")
    if len(cleaned) > 64:
        cleaned = cleaned[-64:]
    
    secret_path = cleaned
    expected_url = f"{webhook_base_url.rstrip('/')}/webhook/{secret_path}"
    
    print(f"✅ Secret Path: {secret_path[:10]}...{secret_path[-10:]}")
    print(f"✅ Expected Webhook URL: {expected_url}")
    
    return errors, warnings, expected_url


async def phase5_webhook_mismatch(current_webhook_info, expected_url):
    """PHASE 5: Detect webhook mismatch."""
    print("\n" + "="*80)
    print("PHASE 5: Webhook Mismatch Detection")
    print("="*80)
    
    errors = []
    warnings = []
    
    if not current_webhook_info or not expected_url:
        errors.append("❌ CRITICAL: Cannot compare webhooks (missing data)")
        return errors, warnings
    
    current_url = (current_webhook_info.url or "").rstrip("/")
    expected_url_clean = expected_url.rstrip("/")
    
    if current_url == expected_url_clean:
        print("✅ Webhook MATCHES expected URL!")
        print("   Bot should be responding to updates.")
    elif not current_url:
        errors.append("❌ CRITICAL: Webhook NOT SET!")
        errors.append(f"   Expected: {expected_url_clean}")
        errors.append("   Action: Run with --force-reset to set webhook")
    else:
        errors.append("❌ CRITICAL: Webhook MISMATCH!")
        errors.append(f"   Current:  {current_url}")
        errors.append(f"   Expected: {expected_url_clean}")
        errors.append("")
        errors.append("   Possible causes:")
        errors.append("   1. BOT_TOKEN was changed (old webhook path in Telegram)")
        errors.append("   2. WEBHOOK_BASE_URL changed on Render")
        errors.append("   3. Webhook not reset after token change")
        errors.append("")
        errors.append("   Fix: Run with --force-reset to update webhook")
    
    return errors, warnings


async def phase6_force_reset(expected_url):
    """PHASE 6: Force reset webhook."""
    print("\n" + "="*80)
    print("PHASE 6: Force Webhook Reset")
    print("="*80)
    
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token or not expected_url:
        print("❌ Cannot reset webhook (missing token or URL)")
        return False
    
    try:
        from aiogram import Bot
        bot = Bot(token=bot_token)
        
        print(f"Setting webhook to: {expected_url}")
        
        await bot.set_webhook(expected_url)
        
        print("✅ Webhook SET successfully!")
        
        # Verify
        webhook_info = await bot.get_webhook_info()
        print(f"Verified URL: {webhook_info.url}")
        
        await bot.session.close()
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to set webhook: {e}")
        return False


async def main():
    """Run all diagnostic phases."""
    parser = argparse.ArgumentParser(description="Webhook diagnostics after token change")
    parser.add_argument(
        "--force-reset",
        action="store_true",
        help="Force reset webhook to expected URL"
    )
    args = parser.parse_args()
    
    print("\n" + "="*80)
    print("🔍 WEBHOOK DIAGNOSTICS - Token Change Detection")
    print("="*80)
    
    all_errors = []
    all_warnings = []
    
    # Phase 1: ENV
    errors, warnings = await phase1_env_check()
    all_errors.extend(errors)
    all_warnings.extend(warnings)
    
    if all_errors:
        # Cannot proceed without ENV
        print_summary(all_errors, all_warnings)
        return 1
    
    # Phase 2: Bot identity
    errors, warnings = await phase2_bot_identity()
    all_errors.extend(errors)
    all_warnings.extend(warnings)
    
    if all_errors:
        # Cannot proceed without valid bot
        print_summary(all_errors, all_warnings)
        return 1
    
    # Phase 3: Current webhook
    errors, warnings, webhook_info = await phase3_current_webhook()
    all_errors.extend(errors)
    all_warnings.extend(warnings)
    
    # Phase 4: Expected webhook
    errors, warnings, expected_url = await phase4_expected_webhook()
    all_errors.extend(errors)
    all_warnings.extend(warnings)
    
    # Phase 5: Mismatch detection
    errors, warnings = await phase5_webhook_mismatch(webhook_info, expected_url)
    all_errors.extend(errors)
    all_warnings.extend(warnings)
    
    # Phase 6: Force reset (if requested)
    if args.force_reset:
        success = await phase6_force_reset(expected_url)
        if success:
            print("\n✅ Webhook has been reset! Test bot with /start")
            return 0
        else:
            print("\n❌ Webhook reset failed!")
            return 1
    
    # Summary
    print_summary(all_errors, all_warnings)
    
    if all_errors:
        print("\n" + "="*80)
        print("💡 SUGGESTED FIX:")
        print("="*80)
        print("Run with --force-reset to update webhook:")
        print(f"    python3 {sys.argv[0]} --force-reset")
        return 1
    else:
        return 0


def print_summary(errors, warnings):
    """Print summary."""
    print("\n" + "="*80)
    print("📊 SUMMARY")
    print("="*80)
    
    if errors:
        print(f"\n❌ CRITICAL ERRORS: {len(errors)}")
        for error in errors:
            print(f"  {error}")
    
    if warnings:
        print(f"\n⚠️  WARNINGS: {len(warnings)}")
        for warning in warnings:
            print(f"  {warning}")
    
    if not errors and not warnings:
        print("\n✅ ALL CHECKS PASSED - Webhook is correctly configured!")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)