#!/usr/bin/env python3
"""
Production Check: Jobs→Callbacks→Delivery Lifecycle

Validates CRITICAL paths:
1. Job creation (user exists → balance hold → job insert → KIE task)
2. Callback handling (task_id lookup → status update → balance ops)
3. Orphan reconciliation (orphan_callbacks table → job matching)
4. Telegram delivery (result → smart send → delivered_at)

Exit codes:
0 - All checks pass
1 - Critical failure (blocks production)
2 - Warning (degraded but functional)
"""

import asyncio
import sys
import os
import logging
from typing import Optional

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class JobLifecycleCheck:
    """Validates job lifecycle end-to-end."""
    
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
    
    async def check_storage_api(self):
        """Verify storage implements required methods."""
        logger.info("\n📦 PHASE 1: Storage API Compliance")
        
        try:
            from app.storage import get_storage
            storage = get_storage()
            
            required_methods = [
                'find_job_by_task_id',
                '_save_orphan_callback',
                'get_undelivered_jobs',
                'add_generation_job',
                'update_job_status'
            ]
            
            for method in required_methods:
                if not hasattr(storage, method):
                    self.error(f"Storage missing method: {method}")
                else:
                    self.ok(f"Storage has {method}")
        
        except ImportError as e:
            self.error(f"Cannot import storage: {e}")
    
    async def check_job_service_v2(self):
        """Verify JobServiceV2 implements atomic operations."""
        logger.info("\n🔧 PHASE 2: JobServiceV2 Atomic Operations")
        
        try:
            from app.services.job_service_v2 import JobServiceV2
            
            # Check critical methods exist
            methods = ['create_job_atomic', 'update_with_kie_task', 'update_from_callback']
            for method in methods:
                if not hasattr(JobServiceV2, method):
                    self.error(f"JobServiceV2 missing {method}")
                else:
                    self.ok(f"JobServiceV2 has {method}")
            
            # Verify InsufficientFundsError exists
            try:
                from app.services.job_service_v2 import InsufficientFundsError
                self.ok("InsufficientFundsError defined")
            except ImportError:
                self.warn("InsufficientFundsError not defined - may fail on balance checks")
        
        except ImportError as e:
            self.error(f"Cannot import JobServiceV2: {e}")
    
    async def check_callback_handler(self):
        """Verify KIE callback handler exists and is robust."""
        logger.info("\n📡 PHASE 3: KIE Callback Handler")
        
        try:
            with open('main_render.py', 'r') as f:
                content = f.read()
            
            # Check callback function exists
            if 'async def kie_callback' not in content:
                self.error("kie_callback function not found in main_render.py")
            else:
                self.ok("kie_callback handler exists")
            
            # Check critical features
            checks = [
                ('extract_task_id', 'Robust task_id extraction'),
                ('normalize_job_status', 'Status normalization'),
                ('_send_generation_result', 'Smart Telegram sender'),
                ('_save_orphan_callback', 'Orphan callback storage'),
                ('ALWAYS return 200', 'Prevents KIE retry storms')
            ]
            
            for pattern, description in checks:
                if pattern in content:
                    self.ok(description)
                else:
                    self.warn(f"Missing: {description}")
        
        except FileNotFoundError:
            self.error("main_render.py not found")
    
    async def check_telegram_delivery(self):
        """Verify Telegram delivery implementation."""
        logger.info("\n📨 PHASE 4: Telegram Delivery")
        
        try:
            with open('main_render.py', 'r') as f:
                content = f.read()
            
            # Check smart sender exists
            if 'async def _send_generation_result' not in content:
                self.error("_send_generation_result not implemented")
            else:
                self.ok("Smart sender implemented")
                
                # Check media type handling
                media_types = ['sendPhoto', 'sendVideo', 'sendAudio', 'sendMediaGroup']
                for media_type in media_types:
                    if media_type in content or f'send_{media_type[4:].lower()}' in content:
                        self.ok(f"Handles {media_type}")
            
            # Check delivery tracking
            if 'delivered_at' in content or 'mark_delivered' in content:
                self.ok("Delivery tracking implemented")
            else:
                self.warn("No delivery tracking - may duplicate sends")
        
        except FileNotFoundError:
            self.error("main_render.py not found")
    
    async def check_migrations(self):
        """Verify database migrations include jobs/callbacks tables."""
        logger.info("\n🗄️ PHASE 5: Database Migrations")
        
        try:
            import os
            migrations_dir = 'migrations'
            
            if not os.path.exists(migrations_dir):
                self.error("migrations/ directory not found")
                return
            
            migration_files = sorted(os.listdir(migrations_dir))
            
            # Check critical tables in migrations
            tables_needed = {
                'jobs': False,
                'wallets': False,
                'ledger': False,
                'orphan_callbacks': False
            }
            
            for file in migration_files:
                if not file.endswith('.sql'):
                    continue
                
                filepath = os.path.join(migrations_dir, file)
                with open(filepath, 'r') as f:
                    content = f.read().lower()
                
                for table in tables_needed:
                    if f'create table if not exists {table}' in content or \
                       f'create table {table}' in content:
                        tables_needed[table] = True
            
            for table, exists in tables_needed.items():
                if exists:
                    self.ok(f"Migration creates {table} table")
                else:
                    if table == 'orphan_callbacks':
                        self.warn(f"No migration for {table} - orphan handling may fail")
                    else:
                        self.error(f"Missing migration for {table}")
        
        except Exception as e:
            self.error(f"Migration check failed: {e}")
    
    async def check_idempotency(self):
        """Verify idempotency mechanisms."""
        logger.info("\n🔁 PHASE 6: Idempotency")
        
        try:
            from app.services.job_service_v2 import JobServiceV2
            import inspect
            
            # Check create_job_atomic signature
            sig = inspect.signature(JobServiceV2.create_job_atomic)
            if 'idempotency_key' in sig.parameters:
                self.ok("create_job_atomic accepts idempotency_key")
            else:
                self.warn("No idempotency_key parameter - duplicates possible")
            
            # Check source for idempotency logic
            source = inspect.getsource(JobServiceV2.create_job_atomic)
            if 'idempotency_key' in source and 'SELECT' in source:
                self.ok("Idempotency check implemented (SELECT existing)")
            else:
                self.warn("Idempotency check not found")
        
        except Exception as e:
            self.warn(f"Idempotency check failed: {e}")
    
    async def check_balance_operations(self):
        """Verify balance hold/release/charge logic."""
        logger.info("\n💰 PHASE 7: Balance Operations")
        
        try:
            from app.services.job_service_v2 import JobServiceV2
            import inspect
            
            # Check update_from_callback for balance operations
            source = inspect.getsource(JobServiceV2.update_from_callback)
            
            operations = {
                'hold balance': 'hold_rub' in source,
                'release on failure': "'failed'" in source and 'hold_rub -' in source,
                'charge on success': "'done'" in source and 'balance_rub -' in source,
                'ledger audit trail': 'ledger' in source.lower()
            }
            
            for operation, implemented in operations.items():
                if implemented:
                    self.ok(f"Balance operation: {operation}")
                else:
                    self.error(f"Missing balance operation: {operation}")
        
        except Exception as e:
            self.error(f"Balance operations check failed: {e}")
    
    async def run_all_checks(self):
        """Run all production checks."""
        logger.info("=" * 60)
        logger.info("🔍 PRODUCTION CHECK: Jobs→Callbacks→Delivery Lifecycle")
        logger.info("=" * 60)
        
        await self.check_storage_api()
        await self.check_job_service_v2()
        await self.check_callback_handler()
        await self.check_telegram_delivery()
        await self.check_migrations()
        await self.check_idempotency()
        await self.check_balance_operations()
        
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
            logger.info("\n✅ ALL CHECKS PASSED - Production ready")
            return 0
        elif self.errors:
            logger.error("\n❌ CRITICAL FAILURES - Not production ready")
            return 1
        else:
            logger.warning("\n⚠️ WARNINGS ONLY - Degraded but functional")
            return 2


async def main():
    checker = JobLifecycleCheck()
    return await checker.run_all_checks()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
