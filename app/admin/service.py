"""
Admin Service - управление моделями, пользователями, экономикой.
"""
import logging
from decimal import Decimal
from typing import Optional, Dict, List, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class AdminService:
    """Service for admin operations."""
    
    def __init__(self, db_service, free_manager):
        self.db_service = db_service
        self.free_manager = free_manager
    
    # ========== MODEL MANAGEMENT ==========
    
    async def set_model_free(
        self,
        admin_id: int,
        model_id: str,
        daily_limit: int = 5,
        hourly_limit: int = 2,
        meta: Optional[Dict] = None
    ):
        """Make model free with limits."""
        await self.free_manager.add_free_model(model_id, daily_limit, hourly_limit, meta)
        
        # Log admin action
        await self._log_action(
            admin_id=admin_id,
            action_type="model_free",
            target_type="model",
            target_id=model_id,
            new_value={"daily_limit": daily_limit, "hourly_limit": hourly_limit, "meta": meta}
        )
        
        logger.info(f"Admin {admin_id} made model {model_id} free")
    
    async def set_model_paid(self, admin_id: int, model_id: str):
        """Make model paid (remove from free)."""
        await self.free_manager.remove_free_model(model_id)
        
        await self._log_action(
            admin_id=admin_id,
            action_type="model_free",
            target_type="model",
            target_id=model_id,
            new_value={"free": False}
        )
        
        logger.info(f"Admin {admin_id} made model {model_id} paid")
    
    async def get_model_status(self, model_id: str) -> Dict[str, Any]:
        """Get model configuration and stats."""
        # Check if free
        free_config = await self.free_manager.get_free_model_config(model_id)
        is_free = free_config is not None
        
        # Get usage stats
        async with self.db_service.get_connection() as conn:
            total_uses = await conn.fetchval(
                """
                SELECT COUNT(*) FROM jobs
                WHERE model_id = $1 AND status IN ('succeeded', 'running')
                """,
                model_id
            )
            
            success_count = await conn.fetchval(
                "SELECT COUNT(*) FROM jobs WHERE model_id = $1 AND status = 'succeeded'",
                model_id
            )
            
            total_revenue = await conn.fetchval(
                """
                SELECT COALESCE(SUM(price_rub), 0) FROM jobs
                WHERE model_id = $1 AND status = 'succeeded'
                """,
                model_id
            ) or Decimal("0.00")
            
            free_uses = 0
            if is_free:
                free_uses = await conn.fetchval(
                    "SELECT COUNT(*) FROM free_usage WHERE model_id = $1",
                    model_id
                ) or 0
        
        return {
            "model_id": model_id,
            "is_free": is_free,
            "free_config": free_config,
            "stats": {
                "total_uses": total_uses,
                "success_count": success_count,
                "total_revenue": float(total_revenue),
                "free_uses": free_uses
            }
        }
    
    # ========== USER MANAGEMENT ==========
    
    async def topup_user(
        self,
        admin_id: int,
        user_id: int,
        amount: Decimal,
        reason: str = "admin_topup"
    ):
        """Admin topup for user."""
        from app.database.services import WalletService
        import uuid
        
        wallet_service = WalletService(self.db_service)
        ref = f"admin_topup_{admin_id}_{user_id}_{uuid.uuid4().hex[:8]}"
        
        success = await wallet_service.topup(
            user_id,
            amount,
            ref,
            meta={"admin_id": admin_id, "reason": reason}
        )
        
        if success:
            await self._log_action(
                admin_id=admin_id,
                action_type="user_topup",
                target_type="user",
                target_id=str(user_id),
                new_value={"amount": float(amount), "reason": reason}
            )
            
            logger.info(f"Admin {admin_id} topped up user {user_id} with {amount}")
        
        return success
    
    async def charge_user(
        self,
        admin_id: int,
        user_id: int,
        amount: Decimal,
        reason: str = "admin_charge"
    ):
        """Admin charge from user."""
        from app.database.services import WalletService
        import uuid
        
        wallet_service = WalletService(self.db_service)
        ref = f"admin_charge_{admin_id}_{user_id}_{uuid.uuid4().hex[:8]}"
        
        success = await wallet_service.charge(
            user_id,
            amount,
            ref,
            meta={"admin_id": admin_id, "reason": reason}
        )
        
        if success:
            await self._log_action(
                admin_id=admin_id,
                action_type="user_charge",
                target_type="user",
                target_id=str(user_id),
                new_value={"amount": float(amount), "reason": reason}
            )
            
            logger.info(f"Admin {admin_id} charged user {user_id} with {amount}")
        
        return success
    
    async def ban_user(self, admin_id: int, user_id: int, reason: str = ""):
        """Ban user."""
        async with self.db_service.get_connection() as conn:
            await conn.execute(
                """
                UPDATE users
                SET role = 'banned', metadata = jsonb_set(metadata, '{ban_reason}', $2::jsonb)
                WHERE user_id = $1
                """,
                user_id, f'"{reason}"'
            )
        
        await self._log_action(
            admin_id=admin_id,
            action_type="user_ban",
            target_type="user",
            target_id=str(user_id),
            new_value={"reason": reason}
        )
        
        logger.info(f"Admin {admin_id} banned user {user_id}: {reason}")
    
    async def unban_user(self, admin_id: int, user_id: int):
        """Unban user."""
        async with self.db_service.get_connection() as conn:
            await conn.execute(
                "UPDATE users SET role = 'user' WHERE user_id = $1",
                user_id
            )
        
        await self._log_action(
            admin_id=admin_id,
            action_type="user_unban",
            target_type="user",
            target_id=str(user_id)
        )
        
        logger.info(f"Admin {admin_id} unbanned user {user_id}")
    
    async def get_user_info(self, user_id: int) -> Dict[str, Any]:
        """Get detailed user info."""
        from app.database.services import WalletService
        
        wallet_service = WalletService(self.db_service)
        
        async with self.db_service.get_connection() as conn:
            user = await conn.fetchrow(
                """
                SELECT user_id, username, first_name, role, created_at, last_seen_at, metadata
                FROM users WHERE user_id = $1
                """,
                user_id
            )
            
            if not user:
                return None
            
            # Get balance
            balance_data = await wallet_service.get_balance(user_id)
            
            # Get jobs count
            jobs_count = await conn.fetchval(
                "SELECT COUNT(*) FROM jobs WHERE user_id = $1",
                user_id
            ) or 0
            
            success_count = await conn.fetchval(
                "SELECT COUNT(*) FROM jobs WHERE user_id = $1 AND status = 'succeeded'",
                user_id
            ) or 0
            
            total_spent = await conn.fetchval(
                """
                SELECT COALESCE(SUM(amount_rub), 0) FROM ledger
                WHERE user_id = $1 AND kind = 'charge'
                """,
                user_id
            ) or Decimal("0.00")
            
            # Free usage stats
            free_stats = await self.free_manager.get_user_stats(user_id)
        
        return {
            "user_id": user['user_id'],
            "username": user['username'],
            "first_name": user['first_name'],
            "role": user['role'],
            "created_at": user['created_at'],
            "last_seen_at": user['last_seen_at'],
            "metadata": user['metadata'],
            "balance": balance_data,
            "stats": {
                "total_jobs": jobs_count,
                "success_jobs": success_count,
                "total_spent": float(total_spent)
            },
            "free_usage": free_stats
        }
    
    # ========== LOGGING ==========
    
    async def _log_action(
        self,
        admin_id: int,
        action_type: str,
        target_type: str,
        target_id: Optional[str] = None,
        old_value: Optional[Dict] = None,
        new_value: Optional[Dict] = None,
        meta: Optional[Dict] = None
    ):
        """Log admin action."""
        async with self.db_service.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO admin_actions (
                    admin_id, action_type, target_type, target_id,
                    old_value, new_value, meta, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
                """,
                admin_id, action_type, target_type, target_id,
                old_value or {}, new_value or {}, meta or {}
            )
    
    async def get_admin_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent admin actions."""
        async with self.db_service.get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT 
                    id, admin_id, action_type, target_type, target_id,
                    old_value, new_value, meta, created_at
                FROM admin_actions
                ORDER BY created_at DESC
                LIMIT $1
                """,
                limit
            )
        
        return [
            {
                "id": row['id'],
                "admin_id": row['admin_id'],
                "action_type": row['action_type'],
                "target_type": row['target_type'],
                "target_id": row['target_id'],
                "old_value": row['old_value'],
                "new_value": row['new_value'],
                "meta": row['meta'],
                "created_at": row['created_at']
            }
            for row in rows
        ]


__all__ = ["AdminService"]
