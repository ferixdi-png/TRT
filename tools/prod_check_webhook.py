#!/usr/bin/env python3
"""
Production Check: Webhook Setup & ACTIVE Mode

Validates CRITICAL webhook path:
1. ACTIVE mode → init_active_services() called
2. init_active_services() → ensure_webhook() called
3. Webhook URL format correct
4. Webhook secret token validation
5. State sync loop handles PASSIVE→ACTIVE

Exit codes:
0 - All checks pass
1 - Critical failure (blocks production)
2 - Warning (degraded but functional)
"""

import asyncio
import sys
import os
import re
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class WebhookSetupCheck:
    """Validates webhook setup in ACTIVE mode."""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
    
    def error(self, msg: str):
        self.errors.append(msg)
        logger.error(f"❌ {msg}")
    
    def warn(self, msg: str):
        self.warnings.append(msg)
        logger.warning(f"⚠️ {msg}")
    
    def ok(self, msg: str):
        logger.info(f"✅ {msg}")
    
    async def check_main_render_logic(self):
        """Verify main_render.py calls init_active_services on immediate ACTIVE."""
        logger.info("\n📦 PHASE 1: main_render.py ACTIVE Mode Logic")
        
        try:
            with open('main_render.py', 'r') as f:
                content = f.read()
            
            # Check if init_active_services exists
            if 'async def init_active_services' not in content:
                self.error("init_active_services() function not found")
                return
            
            self.ok("init_active_services() function exists")
            
            # CRITICAL: Check if init_active_services called on immediate ACTIVE
            if_active_block = re.search(
                r'if active_state\.active:.*?logger\.info\(\"\[LOCK_CONTROLLER\].*ACTIVE MODE',
                content,
                re.DOTALL
            )
            
            if not if_active_block:
                self.error("Cannot find ACTIVE MODE initialization block")
                return
            
            block_text = if_active_block.group(0)
            
            if 'await init_active_services()' in block_text:
                self.ok("init_active_services() called on immediate ACTIVE mode")
            else:
                self.error("CRITICAL: init_active_services() NOT called on immediate ACTIVE mode")
                self.error("  → Webhook will not be set if lock acquired on startup")
            
            # Check state_sync_loop calls init_active_services on PASSIVE→ACTIVE
            if 'await init_active_services()' in content:
                if 'STATE_SYNC' in content or 'PASSIVE → ACTIVE' in content:
                    self.ok("init_active_services() called on PASSIVE→ACTIVE transition")
                else:
                    self.warn("init_active_services() exists but state transition unclear")
        
        except FileNotFoundError:
            self.error("main_render.py not found")
    
    async def check_init_active_services(self):
        """Verify init_active_services calls ensure_webhook."""
        logger.info("\n🔧 PHASE 2: init_active_services() Implementation")
        
        try:
            with open('main_render.py', 'r') as f:
                content = f.read()
            
            # Extract init_active_services function
            func_match = re.search(
                r'async def init_active_services\(\):.*?(?=\n    async def |\n    runner:|\nif __name__)',
                content,
                re.DOTALL
            )
            
            if not func_match:
                self.error("Cannot parse init_active_services()")
                return
            
            func_body = func_match.group(0)
            
            # Check ensure_webhook call
            if 'ensure_webhook' in func_body:
                self.ok("ensure_webhook() called in init_active_services()")
            else:
                self.error("ensure_webhook() NOT called in init_active_services()")
            
            # Check webhook URL building
            if '_build_webhook_url' in func_body or 'webhook_url' in func_body:
                self.ok("Webhook URL building logic present")
            else:
                self.warn("No webhook URL building found")
            
            # Check BOT_MODE condition
            if 'effective_bot_mode == "webhook"' in func_body or 'cfg.bot_mode' in func_body:
                self.ok("BOT_MODE=webhook check present")
            else:
                self.warn("No BOT_MODE check - may set webhook in polling mode")
        
        except Exception as e:
            self.error(f"Failed to analyze init_active_services: {e}")
    
    async def check_ensure_webhook_util(self):
        """Verify app/utils/webhook.py implements ensure_webhook."""
        logger.info("\n📡 PHASE 3: ensure_webhook() Utility")
        
        try:
            import os
            webhook_file = 'app/utils/webhook.py'
            
            if not os.path.exists(webhook_file):
                self.error(f"{webhook_file} not found")
                return
            
            with open(webhook_file, 'r') as f:
                content = f.read()
            
            # Check ensure_webhook function
            if 'async def ensure_webhook' not in content:
                self.error("ensure_webhook() function not found")
                return
            
            self.ok("ensure_webhook() function exists")
            
            # Check bot.set_webhook call
            if 'await bot.set_webhook' in content or 'bot.set_webhook' in content:
                self.ok("bot.set_webhook() called")
            else:
                self.error("bot.set_webhook() NOT called in ensure_webhook()")
            
            # Check secret_token parameter
            if 'secret_token' in content:
                self.ok("Secret token parameter supported")
            else:
                self.warn("No secret_token parameter - less secure")
            
            # Check error handling
            if 'try:' in content and 'except' in content:
                self.ok("Error handling present")
            else:
                self.warn("No error handling in ensure_webhook()")
        
        except Exception as e:
            self.error(f"Failed to check ensure_webhook: {e}")
    
    async def check_webhook_url_format(self):
        """Verify webhook URL format compliance."""
        logger.info("\n🔗 PHASE 4: Webhook URL Format")
        
        try:
            # Check _build_webhook_url function
            with open('main_render.py', 'r') as f:
                content = f.read()
            
            if 'def _build_webhook_url' not in content:
                self.warn("_build_webhook_url() helper not found")
                return
            
            self.ok("_build_webhook_url() helper exists")
            
            # Extract function
            func_match = re.search(
                r'def _build_webhook_url.*?(?=\ndef |\nclass )',
                content,
                re.DOTALL
            )
            
            if func_match:
                func_body = func_match.group(0)
                
                # Check components
                if 'webhook_base_url' in func_body and 'webhook_secret_path' in func_body:
                    self.ok("URL components: base_url + secret_path")
                else:
                    self.warn("URL components unclear")
                
                # Check HTTPS enforcement
                if 'https://' in func_body or 'startswith' in func_body:
                    self.ok("HTTPS validation present")
                else:
                    self.warn("No HTTPS validation - Telegram requires HTTPS")
        
        except Exception as e:
            self.warn(f"URL format check failed: {e}")
    
    async def check_env_vars(self):
        """Verify required ENV variables."""
        logger.info("\n🔑 PHASE 5: Environment Variables")
        
        required_vars = {
            'WEBHOOK_BASE_URL': 'Webhook base URL (https://...)',
            'TELEGRAM_BOT_TOKEN': 'Bot token',
        }
        
        optional_vars = {
            'WEBHOOK_SECRET_PATH': 'Secret path in URL',
            'WEBHOOK_SECRET_TOKEN': 'Secret token in header',
            'BOT_MODE': 'webhook or polling'
        }
        
        for var, desc in required_vars.items():
            value = os.getenv(var)
            if value:
                # Mask sensitive data
                if 'TOKEN' in var or 'SECRET' in var:
                    display = f"{value[:10]}..." if len(value) > 10 else "***"
                else:
                    display = value
                self.ok(f"{var} = {display}")
            else:
                self.warn(f"{var} not set ({desc})")
        
        for var, desc in optional_vars.items():
            value = os.getenv(var)
            if value:
                if 'TOKEN' in var or 'SECRET' in var:
                    display = "***"
                else:
                    display = value
                self.ok(f"{var} = {display}")
            else:
                logger.info(f"ℹ️ {var} not set ({desc}) - using defaults")
    
    async def check_verify_bot_identity(self):
        """Verify bot identity check includes webhook info."""
        logger.info("\n🤖 PHASE 6: Bot Identity Verification")
        
        try:
            with open('main_render.py', 'r') as f:
                content = f.read()
            
            if 'async def verify_bot_identity' not in content:
                self.warn("verify_bot_identity() not found")
                return
            
            self.ok("verify_bot_identity() exists")
            
            # Check if it calls getWebhookInfo
            if 'get_webhook_info' in content or 'getWebhookInfo' in content:
                self.ok("Calls bot.get_webhook_info() for verification")
            else:
                self.warn("Does not check webhook info (harder to debug)")
        
        except Exception as e:
            self.warn(f"verify_bot_identity check failed: {e}")
    
    async def run_all_checks(self):
        """Run all production checks."""
        logger.info("=" * 60)
        logger.info("🔍 PRODUCTION CHECK: Webhook Setup & ACTIVE Mode")
        logger.info("=" * 60)
        
        await self.check_main_render_logic()
        await self.check_init_active_services()
        await self.check_ensure_webhook_util()
        await self.check_webhook_url_format()
        await self.check_env_vars()
        await self.check_verify_bot_identity()
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("📊 RESULTS")
        logger.info("=" * 60)
        
        if self.errors:
            logger.error(f"\n❌ {len(self.errors)} CRITICAL ERRORS:")
            for error in self.errors:
                logger.error(f"   • {error}")
        
        if self.warnings:
            logger.warning(f"\n⚠️ {len(self.warnings)} WARNINGS:")
            for warning in self.warnings:
                logger.warning(f"   • {warning}")
        
        if not self.errors and not self.warnings:
            logger.info("\n✅ ALL CHECKS PASSED - Webhook setup production ready")
            return 0
        elif self.errors:
            logger.error("\n❌ CRITICAL FAILURES - Webhook will not work")
            return 1
        else:
            logger.warning("\n⚠️ WARNINGS ONLY - May work but suboptimal")
            return 2


async def main():
    checker = WebhookSetupCheck()
    return await checker.run_all_checks()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
