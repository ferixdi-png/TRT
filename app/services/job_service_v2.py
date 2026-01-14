"""
Job Service - атомарные операции с jobs table (unified schema)

CRITICAL INVARIANTS:
1. Users MUST exist before jobs
2. Jobs created with idempotency_key (duplicate-safe)
3. Balance operations atomic with job creation
4. Callbacks never lost (orphan reconciliation)
5. Telegram delivery guaranteed (retry logic)
"""

import logging
import uuid
from typing import Dict, Any, Optional, List
from decimal import Decimal
from datetime import datetime

try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False

from app.storage.status import normalize_job_status

logger = logging.getLogger(__name__)


class JobServiceV2:
    """
    Production-ready job service following felores/kie-ai-mcp-server patterns.
    
    Key features:
    - Atomic job creation (user check → balance hold → job insert → KIE task)
    - Idempotent operations (duplicate requests handled gracefully)
    - No orphan jobs (strict lifecycle management)
    - Guaranteed delivery (chat_id + retry logic)
    """
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
    
    async def create_job_atomic(
        self,
        user_id: int,
        model_id: str,
        category: str,
        input_params: Dict[str, Any],
        price_rub: Decimal,
        chat_id: Optional[int] = None,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Atomic job creation following STRICT lifecycle:
        1. Validate user exists (FK enforcement)
        2. Check idempotency (duplicate safety)
        3. Hold balance (if price > 0)
        4. Insert job (status='pending')
        5. Return job for KIE task creation
        
        CRITICAL: Job created BEFORE calling KIE API to avoid orphan callbacks.
        
        Returns:
            {
                'id': int,
                'user_id': int,
                'model_id': str,
                'idempotency_key': str,
                'status': 'pending',
                ...
            }
        
        Raises:
            ValueError: User not found, invalid input
            InsufficientFundsError: Balance too low
        """
        if not idempotency_key:
            idempotency_key = f"job:{user_id}:{uuid.uuid4()}"
        
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # PHASE 1: Check if already exists (idempotency)
                existing = await conn.fetchrow(
                    "SELECT * FROM jobs WHERE idempotency_key = $1",
                    idempotency_key
                )
                if existing:
                    logger.info(f"[JOB] Idempotent duplicate: key={idempotency_key} id={existing['id']}")
                    return dict(existing)
                
                # PHASE 2: Validate user exists (enforces FK)
                user = await conn.fetchrow(
                    "SELECT user_id FROM users WHERE user_id = $1",
                    user_id
                )
                if not user:
                    raise ValueError(f"User {user_id} not found - create user first")
                
                # PHASE 3: Check balance if paid model
                if price_rub > 0:
                    wallet = await conn.fetchrow(
                        "SELECT balance_rub, hold_rub FROM wallets WHERE user_id = $1",
                        user_id
                    )
                    if not wallet:
                        # Auto-create wallet if missing
                        await conn.execute(
                            "INSERT INTO wallets (user_id, balance_rub) VALUES ($1, 0.00)",
                            user_id
                        )
                        wallet = {'balance_rub': Decimal('0.00'), 'hold_rub': Decimal('0.00')}
                    
                    available = wallet['balance_rub'] - wallet['hold_rub']
                    if available < price_rub:
                        raise InsufficientFundsError(
                            f"Insufficient funds: need {price_rub} RUB, have {available} RUB"
                        )
                    
                    # PHASE 4: Hold balance (prevents double-spend)
                    await conn.execute("""
                        UPDATE wallets
                        SET hold_rub = hold_rub + $2,
                            updated_at = NOW()
                        WHERE user_id = $1
                    """, user_id, price_rub)
                    
                    # Record hold in ledger (for audit trail)
                    await conn.execute("""
                        INSERT INTO ledger (user_id, kind, amount_rub, status, ref, meta)
                        VALUES ($1, 'hold', $2, 'done', $3, $4)
                    """, user_id, price_rub, idempotency_key, {
                        'model_id': model_id,
                        'category': category
                    })
                
                # PHASE 5: Create job (status='pending')
                job = await conn.fetchrow("""
                    INSERT INTO jobs (
                        user_id, model_id, category, input_json, price_rub,
                        status, idempotency_key, chat_id, created_at
                    )
                    VALUES ($1, $2, $3, $4, $5, 'pending', $6, $7, NOW())
                    RETURNING *
                """, user_id, model_id, category, input_params, price_rub,
                     idempotency_key, chat_id)
                
                logger.info(
                    f"[JOB_CREATE] id={job['id']} user={user_id} model={model_id} "
                    f"price={price_rub} status=pending"
                )
                
                return dict(job)
    
    async def update_with_kie_task(
        self,
        job_id: int,
        kie_task_id: str,
        status: str = 'running'
    ) -> None:
        """
        Update job with KIE task_id after successful API call.
        
        Lifecycle: pending → running
        """
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE jobs
                SET kie_task_id = $2,
                    status = $3,
                    updated_at = NOW()
                WHERE id = $1
            """, job_id, kie_task_id, normalize_job_status(status))
            
            logger.info(f"[JOB_UPDATE] id={job_id} task={kie_task_id} status={status}")
    
    async def update_from_callback(
        self,
        job_id: int,
        status: str,
        result_json: Optional[Dict[str, Any]] = None,
        error_text: Optional[str] = None,
        kie_status: Optional[str] = None
    ) -> None:
        """
        Update job from KIE callback.
        
        Lifecycle: running → done/failed
        
        CRITICAL: If status='done', also release held balance.
        """
        normalized_status = normalize_job_status(status)
        
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Update job
                await conn.execute("""
                    UPDATE jobs
                    SET status = $2,
                        kie_status = $3,
                        result_json = $4,
                        error_text = $5,
                        finished_at = CASE WHEN $2 IN ('done', 'failed', 'canceled') THEN NOW() ELSE finished_at END,
                        updated_at = NOW()
                    WHERE id = $1
                """, job_id, normalized_status, kie_status, result_json, error_text)
                
                # Release or charge balance
                job = await conn.fetchrow("SELECT user_id, price_rub, idempotency_key FROM jobs WHERE id = $1", job_id)
                if not job:
                    logger.warning(f"[JOB_UPDATE] Job {job_id} not found for balance update")
                    return
                
                user_id = job['user_id']
                price_rub = job['price_rub']
                
                if normalized_status == 'done' and price_rub > 0:
                    # SUCCESS: Release hold + charge balance
                    await conn.execute("""
                        UPDATE wallets
                        SET balance_rub = balance_rub - $2,
                            hold_rub = hold_rub - $2,
                            updated_at = NOW()
                        WHERE user_id = $1
                    """, user_id, price_rub)
                    
                    # Record charge in ledger
                    await conn.execute("""
                        INSERT INTO ledger (user_id, kind, amount_rub, status, ref, meta)
                        VALUES ($1, 'charge', $2, 'done', $3, $4)
                    """, user_id, price_rub, f"job:{job_id}", {
                        'job_id': job_id,
                        'idempotency_key': job['idempotency_key']
                    })
                    
                    logger.info(f"[BALANCE] user={user_id} charged={price_rub} job={job_id}")
                
                elif normalized_status in ('failed', 'canceled') and price_rub > 0:
                    # FAILURE: Release hold (no charge)
                    await conn.execute("""
                        UPDATE wallets
                        SET hold_rub = hold_rub - $2,
                            updated_at = NOW()
                        WHERE user_id = $1
                    """, user_id, price_rub)
                    
                    # Record release in ledger
                    await conn.execute("""
                        INSERT INTO ledger (user_id, kind, amount_rub, status, ref, meta)
                        VALUES ($1, 'release', $2, 'done', $3, $4)
                    """, user_id, price_rub, f"job:{job_id}:refund", {
                        'job_id': job_id,
                        'reason': 'job_failed'
                    })
                    
                    logger.info(f"[BALANCE] user={user_id} refunded={price_rub} job={job_id}")
                
                logger.info(f"[JOB_CALLBACK] id={job_id} status={normalized_status}")
    
    async def mark_delivered(self, job_id: int) -> None:
        """Mark job result as delivered to Telegram."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE jobs
                SET delivered_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1
            """, job_id)
            
            logger.info(f"[TELEGRAM_DELIVERY] job={job_id} delivered=True")
    
    async def get_by_id(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Get job by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id)
            return dict(row) if row else None
    
    async def get_by_task_id(self, kie_task_id: str) -> Optional[Dict[str, Any]]:
        """Get job by KIE task_id (for callbacks)."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM jobs WHERE kie_task_id = $1", kie_task_id)
            return dict(row) if row else None
    
    async def get_by_idempotency_key(self, key: str) -> Optional[Dict[str, Any]]:
        """Get job by idempotency_key."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM jobs WHERE idempotency_key = $1", key)
            return dict(row) if row else None
    
    async def list_user_jobs(
        self,
        user_id: int,
        limit: int = 20,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List user's jobs (for history)."""
        async with self.pool.acquire() as conn:
            if status:
                rows = await conn.fetch("""
                    SELECT * FROM jobs
                    WHERE user_id = $1 AND status = $2
                    ORDER BY created_at DESC
                    LIMIT $3
                """, user_id, normalize_job_status(status), limit)
            else:
                rows = await conn.fetch("""
                    SELECT * FROM jobs
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                """, user_id, limit)
            
            return [dict(row) for row in rows]
    
    async def list_undelivered(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get jobs that are done but not delivered (for retry).
        
        Use case: Telegram API was down, retry delivery.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM jobs
                WHERE status = 'done'
                  AND delivered_at IS NULL
                  AND chat_id IS NOT NULL
                  AND finished_at IS NOT NULL
                ORDER BY finished_at ASC
                LIMIT $1
            """, limit)
            
            return [dict(row) for row in rows]


class InsufficientFundsError(Exception):
    """Raised when user doesn't have enough balance."""
    pass
