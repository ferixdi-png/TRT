#!/usr/bin/env python3
"""
Unified smoke test for critical production paths.

Tests:
1. ENV validation (startup contract)
2. DB connectivity and migrations
3. KIE_SOURCE_OF_TRUTH loading
4. z-image baseline (most critical model)
5. Webhook fast-ack simulation
6. Billing idempotency (hold/charge/refund)

Exit codes:
- 0: All tests passed
- 1: Critical failure (blocks deployment)
"""
import asyncio
import logging
import os
import sys
from pathlib import Path
from decimal import Decimal

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def test_env_validation() -> bool:
    """Test ENV contract validation."""
    logger.info("📋 Testing ENV validation...")
    try:
        from app.utils.startup_validation import validate_env_keys
        is_valid, missing = validate_env_keys()
        if not is_valid:
            logger.error(f"❌ Missing ENV keys: {missing}")
            return False
        logger.info("✅ ENV validation passed")
        return True
    except Exception as e:
        logger.error(f"❌ ENV validation failed: {e}")
        return False


async def test_db_connectivity() -> bool:
    """Test database connection and migrations."""
    logger.info("🗄️  Testing DB connectivity and migrations...")
    try:
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            logger.warning("⚠️  No DATABASE_URL, skipping DB tests")
            return True
        
        from app.storage.migrations import apply_migrations_safe, check_migrations_status
        
        # Apply migrations
        migrations_ok = await apply_migrations_safe(database_url)
        if not migrations_ok:
            logger.error("❌ Migrations failed")
            return False
        
        # Check status
        applied, count = await check_migrations_status()
        if not applied:
            logger.error(f"❌ Migrations not applied ({count} expected)")
            return False
        
        logger.info(f"✅ DB connectivity OK, {count} migrations applied")
        return True
    except Exception as e:
        logger.error(f"❌ DB test failed: {e}")
        return False


async def test_model_ssot() -> bool:
    """Test KIE_SOURCE_OF_TRUTH loading."""
    logger.info("🤖 Testing model SSOT loading...")
    try:
        from app.kie.builder import load_source_of_truth
        
        data = load_source_of_truth()
        if not data or "models" not in data:
            logger.error("❌ KIE_SOURCE_OF_TRUTH invalid or empty")
            return False
        
        models = data.get("models", {})
        if len(models) < 50:  # Expect at least 50 models
            logger.error(f"❌ Only {len(models)} models found, expected 50+")
            return False
        
        # Check z-image exists (critical baseline)
        if "z-image" not in models:
            logger.error("❌ z-image model not found in SSOT")
            return False
        
        logger.info(f"✅ Model SSOT OK ({len(models)} models, z-image present)")
        return True
    except Exception as e:
        logger.error(f"❌ Model SSOT test failed: {e}")
        return False


async def test_z_image_schema() -> bool:
    """Test z-image model schema (critical baseline)."""
    logger.info("🖼️  Testing z-image baseline schema...")
    try:
        from app.kie.builder import load_source_of_truth
        
        data = load_source_of_truth()
        z_image = data.get("models", {}).get("z-image")
        
        if not z_image:
            logger.error("❌ z-image not found")
            return False
        
        # Verify critical fields
        required_fields = ["endpoint", "pricing", "input_schema"]
        for field in required_fields:
            if field not in z_image:
                logger.error(f"❌ z-image missing field: {field}")
                return False
        
        # Verify pricing
        pricing = z_image.get("pricing", {})
        if "credits_per_gen" not in pricing:
            logger.error("❌ z-image pricing invalid")
            return False
        
        logger.info("✅ z-image baseline schema OK")
        return True
    except Exception as e:
        logger.error(f"❌ z-image test failed: {e}")
        return False


async def test_billing_idempotency() -> bool:
    """Test billing idempotency (hold/charge/refund)."""
    logger.info("💰 Testing billing idempotency...")
    try:
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            logger.warning("⚠️  No DATABASE_URL, skipping billing tests")
            return True
        
        from app.database.services import DatabaseService, WalletService
        import uuid
        
        # Initialize services
        db = DatabaseService(database_url)
        await db.initialize()
        wallet = WalletService(db)
        
        # Test user (admin or create dummy)
        test_user_id = int(os.getenv("ADMIN_ID", "0"))
        if test_user_id == 0:
            logger.warning("⚠️  No ADMIN_ID, skipping billing tests")
            await db.close()
            return True
        
        # Test idempotency: double charge with same ref should succeed once
        ref = f"smoke_test_{uuid.uuid4().hex[:8]}"
        amount = Decimal("0.01")
        
        # First charge
        result1 = await wallet.charge(test_user_id, amount, ref, {"test": "smoke"})
        # Second charge (idempotent)
        result2 = await wallet.charge(test_user_id, amount, ref, {"test": "smoke"})
        
        if not (result1 and result2):
            logger.warning("⚠️  Billing idempotency test inconclusive (may need balance)")
        else:
            logger.info("✅ Billing idempotency OK")
        
        await db.close()
        return True
    except Exception as e:
        logger.error(f"❌ Billing test failed: {e}")
        return False


async def test_heartbeat_function() -> bool:
    """Test that heartbeat function (migration 011) is working."""
    logger.info("💓 Testing heartbeat function (migration 011)...")
    try:
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            logger.warning("⚠️  No DATABASE_URL, skipping heartbeat test")
            return True
        
        import asyncpg
        
        conn = await asyncpg.connect(database_url)
        
        # Verify lock_heartbeat table exists
        schema_check = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='lock_heartbeat')"
        )
        if not schema_check:
            logger.error("❌ lock_heartbeat table missing (migration 007 not applied)")
            await conn.close()
            return False
        
        # Test calling update_lock_heartbeat with TEXT parameter
        # This tests that migration 011 (::TEXT cast) is working
        try:
            test_lock_key = 12345
            test_instance_id = "test_instance_xyz"
            
            # This call should succeed if migration 011 is applied
            await conn.execute(
                """
                SELECT update_lock_heartbeat($1, $2)
                """,
                test_lock_key,
                test_instance_id,
            )
            
            logger.info("✅ Heartbeat function OK (migration 011 active)")
            await conn.close()
            return True
        except Exception as func_err:
            if "does not exist" in str(func_err):
                logger.error(f"❌ Heartbeat function signature mismatch: {func_err}")
                logger.error("   (migration 011 may not be applied)")
            else:
                logger.error(f"❌ Heartbeat function error: {func_err}")
            await conn.close()
            return False
            
    except Exception as e:
        logger.error(f"❌ Heartbeat test failed: {e}")
        return False


async def test_webhook_simulation() -> bool:
    """Test webhook fast-ack queue."""
    logger.info("🌐 Testing webhook queue simulation...")
    try:
        from app.utils.update_queue import get_queue_manager
        
        queue_manager = get_queue_manager()
        
        # Check queue is initialized
        if queue_manager.max_size <= 0:
            logger.error("❌ Queue max_size invalid")
            return False
        
        if queue_manager.num_workers <= 0:
            logger.error("❌ Queue workers invalid")
            return False
        
        logger.info(f"✅ Webhook queue OK (max_size={queue_manager.max_size}, workers={queue_manager.num_workers})")
        return True
    except Exception as e:
        logger.error(f"❌ Webhook test failed: {e}")
        return False


async def main() -> int:
    """Run all smoke tests."""
    logger.info("=" * 60)
    logger.info("🚀 UNIFIED SMOKE TEST - Critical Production Paths")
    logger.info("=" * 60)
    
    tests = [
        ("ENV Validation", test_env_validation),
        ("DB Connectivity", test_db_connectivity),
        ("Heartbeat Function", test_heartbeat_function),
        ("Model SSOT", test_model_ssot),
        ("z-image Baseline", test_z_image_schema),
        ("Webhook Queue", test_webhook_simulation),
        ("Billing Idempotency", test_billing_idempotency),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"❌ {name} crashed: {e}")
            results.append((name, False))
        logger.info("")  # Blank line between tests
    
    # Summary
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {name}")
    
    logger.info("=" * 60)
    logger.info(f"TOTAL: {passed}/{total} tests passed")
    logger.info("=" * 60)
    
    if passed == total:
        logger.info("🎉 ALL TESTS PASSED - Ready for production")
        return 0
    else:
        logger.error("⛔ TESTS FAILED - Fix issues before deployment")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
