"""
PostgreSQL storage implementation using json payloads per logical file.
Stores all logical JSON files inside a single table with partner_id + filename keys.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
import math
import time
from datetime import datetime, date
from typing import Any, Callable, Dict, List, Optional, Tuple

import asyncpg

from app.storage.base import BaseStorage
from app.observability.trace import get_correlation_id

logger = logging.getLogger(__name__)


class PostgresStorage(BaseStorage):
    """PostgreSQL-backed storage that mirrors JsonStorage semantics."""

    def __init__(self, dsn: str, partner_id: Optional[str] = None):
        self.dsn = dsn
        self.partner_id = (partner_id or os.getenv("PARTNER_ID") or os.getenv("BOT_INSTANCE_ID") or "").strip()
        if not self.partner_id:
            raise ValueError("BOT_INSTANCE_ID is required for multi-tenant storage")
        max_pool_env = os.getenv("DB_MAX_CONN", "5")
        try:
            self.max_pool_size = max(1, int(max_pool_env))
        except ValueError:
            logger.warning("Invalid DB_MAX_CONN=%s, using default 5", max_pool_env)
            self.max_pool_size = 5
        self._pools: Dict[int, asyncpg.Pool] = {}
        self._schema_ready_loops: set[int] = set()
        self._file_locks: Dict[Tuple[int, str], asyncio.Lock] = {}

        # logical filenames (same as JsonStorage/GitHubStorage)
        self.balances_file = "user_balances.json"
        self.languages_file = "user_languages.json"
        self.gift_claimed_file = "gift_claimed.json"
        self.free_generations_file = "daily_free_generations.json"
        self.hourly_free_usage_file = "hourly_free_usage.json"
        self.referral_free_bank_file = "referral_free_bank.json"
        self.admin_limits_file = "admin_limits.json"
        self.generations_history_file = "generations_history.json"
        self.payments_file = "payments.json"
        self.referrals_file = "referrals.json"
        self.jobs_file = "generation_jobs.json"
        self.balance_deductions_file = "balance_deductions.json"
        self.free_deductions_file = "free_deductions.json"

    @staticmethod
    def _coerce_payload(payload: Any, *, filename: str) -> Dict[str, Any]:
        if isinstance(payload, dict):
            return dict(payload)
        if isinstance(payload, str):
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                return parsed
        logger.warning("STORAGE_JSON_TYPE_INVALID filename=%s payload_type=%s", filename, type(payload).__name__)
        return {}

    async def _get_pool(self) -> asyncpg.Pool:
        loop = asyncio.get_running_loop()
        loop_id = id(loop)
        pool = self._pools.get(loop_id)
        if pool is None:
            pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=self.max_pool_size)
            self._pools[loop_id] = pool
        if loop_id not in self._schema_ready_loops:
            await self._ensure_schema(pool, loop_id)
        return pool

    async def _ensure_schema(self, pool: asyncpg.Pool, loop_id: int) -> None:
        if loop_id in self._schema_ready_loops:
            return
        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS storage_json (
                    partner_id TEXT NOT NULL,
                    filename   TEXT NOT NULL,
                    payload    JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (partner_id, filename)
                );
                CREATE TABLE IF NOT EXISTS migrations_meta (
                    key TEXT PRIMARY KEY,
                    completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS referrals (
                    partner_id TEXT NOT NULL,
                    referred_user_id BIGINT NOT NULL,
                    referrer_id BIGINT NOT NULL,
                    ref_param TEXT,
                    bonus_amount INTEGER,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    bonus_granted_at TIMESTAMPTZ,
                    PRIMARY KEY (partner_id, referred_user_id)
                );
                CREATE INDEX IF NOT EXISTS idx_referrals_referrer_id
                    ON referrals(partner_id, referrer_id);
                CREATE INDEX IF NOT EXISTS idx_referrals_created_at
                    ON referrals(partner_id, created_at DESC);
                """
            )
        self._schema_ready_loops.add(loop_id)
        logger.info("[STORAGE] schema_ready=true partner_id=%s", self.partner_id)

    def _get_file_lock(self, filename: str) -> asyncio.Lock:
        loop_id = id(asyncio.get_running_loop())
        key = (loop_id, filename)
        lock = self._file_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._file_locks[key] = lock
        return lock

    async def _load_json_unlocked(self, filename: str) -> Dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT payload FROM storage_json WHERE partner_id=$1 AND filename=$2",
                self.partner_id,
                filename,
            )
            if not row:
                return {}
            payload = row[0]
            if isinstance(payload, dict):
                return dict(payload)
            if isinstance(payload, str):
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    return parsed
            correlation_id = uuid.uuid4().hex[:8]
            logger.warning(
                "STORAGE_JSON_TYPE_INVALID correlation_id=%s filename=%s payload_type=%s",
                correlation_id,
                filename,
                type(payload).__name__,
            )
            return {}

    async def _load_json(self, filename: str) -> Dict[str, Any]:
        lock = self._get_file_lock(filename)
        async with lock:
            return await self._load_json_unlocked(filename)

    async def _save_json_unlocked(self, filename: str, data: Dict[str, Any]) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO storage_json (partner_id, filename, payload)
                VALUES ($1, $2, $3::jsonb)
                ON CONFLICT (partner_id, filename)
                DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()
                """,
                self.partner_id,
                filename,
                json.dumps(data) if data else "{}",
            )

    async def _save_json(self, filename: str, data: Dict[str, Any]) -> None:
        lock = self._get_file_lock(filename)
        async with lock:
            await self._save_json_unlocked(filename, data)

    async def _update_json(self, filename: str, update_fn: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
        lock = self._get_file_lock(filename)
        async with lock:
            current = await self._load_json_unlocked(filename)
            updated = update_fn(dict(current))
            await self._save_json_unlocked(filename, updated)
            return updated

    def _advisory_lock_key_pair(self, filename: str):
        from app.utils.pg_advisory_lock import build_advisory_lock_key_pair

        payload = f"{self.partner_id}:{filename}"
        return build_advisory_lock_key_pair(source="storage_json", payload=payload)

    # ==================== USER OPERATIONS ====================

    async def get_user(self, user_id: int, upsert: bool = True) -> Dict[str, Any]:
        balance = await self.get_user_balance(user_id)
        language = await self.get_user_language(user_id)
        gift_claimed = await self.has_claimed_gift(user_id)
        referrer_id = await self.get_referrer(user_id)

        return {
            "user_id": user_id,
            "balance": balance,
            "language": language,
            "gift_claimed": gift_claimed,
            "referrer_id": referrer_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

    async def get_user_balance(self, user_id: int) -> float:
        data = await self._load_json(self.balances_file)
        return float(data.get(str(user_id), 0.0))

    async def set_user_balance(self, user_id: int, amount: float) -> None:
        balance_before = await self.get_user_balance(user_id)
        data = await self._load_json(self.balances_file)
        data[str(user_id)] = amount
        await self._save_json(self.balances_file, data)
        logger.info(
            "BALANCE_SET user_id=%s balance_before=%.2f balance_after=%.2f delta=%.2f",
            user_id,
            balance_before,
            amount,
            amount - balance_before,
        )

    async def add_user_balance(self, user_id: int, amount: float) -> float:
        balance_before = await self.get_user_balance(user_id)
        new_balance = balance_before + amount
        await self.set_user_balance(user_id, new_balance)
        logger.info(
            "BALANCE_ADD user_id=%s amount=%.2f balance_before=%.2f balance_after=%.2f",
            user_id,
            amount,
            balance_before,
            new_balance,
        )
        return new_balance

    async def subtract_user_balance(self, user_id: int, amount: float) -> bool:
        balance_before = await self.get_user_balance(user_id)
        if balance_before < amount:
            logger.warning(
                "Insufficient balance: user_id=%s required=%.2f available=%.2f",
                user_id,
                amount,
                balance_before,
            )
            return False
        new_balance = balance_before - amount
        if new_balance < 0:
            logger.error("Negative balance prevented user_id=%s new_balance=%.2f", user_id, new_balance)
            return False
        await self.set_user_balance(user_id, new_balance)
        logger.info(
            "BALANCE_SUBTRACT user_id=%s amount=%.2f balance_before=%.2f balance_after=%.2f",
            user_id,
            amount,
            balance_before,
            new_balance,
        )
        return True

    async def charge_balance_once(
        self,
        user_id: int,
        amount: float,
        *,
        task_id: str,
        sku_id: str = "",
        model_id: str = "",
    ) -> Dict[str, Any]:
        if not task_id:
            return {"status": "missing_task_id"}
        if not math.isfinite(amount) or amount <= 0:
            balance_before = await self.get_user_balance(user_id)
            logger.warning(
                "INVALID_CHARGE_AMOUNT user_id=%s amount=%.4f task_id=%s",
                user_id,
                amount,
                task_id,
            )
            return {
                "status": "invalid_amount",
                "balance_before": balance_before,
                "balance_after": balance_before,
            }
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO storage_json (partner_id, filename, payload) VALUES ($1, $2, '{}'::jsonb) "
                    "ON CONFLICT DO NOTHING",
                    self.partner_id,
                    self.balances_file,
                )
                await conn.execute(
                    "INSERT INTO storage_json (partner_id, filename, payload) VALUES ($1, $2, '{}'::jsonb) "
                    "ON CONFLICT DO NOTHING",
                    self.partner_id,
                    self.balance_deductions_file,
                )

                balances_payload = await conn.fetchval(
                    "SELECT payload FROM storage_json WHERE partner_id=$1 AND filename=$2 FOR UPDATE",
                    self.partner_id,
                    self.balances_file,
                )
                deductions_payload = await conn.fetchval(
                    "SELECT payload FROM storage_json WHERE partner_id=$1 AND filename=$2 FOR UPDATE",
                    self.partner_id,
                    self.balance_deductions_file,
                )
                balances = self._coerce_payload(balances_payload, filename=self.balances_file)
                deductions = self._coerce_payload(deductions_payload, filename=self.balance_deductions_file)

                if task_id in deductions:
                    balance_before = float(balances.get(str(user_id), 0.0))
                    return {
                        "status": "duplicate",
                        "balance_before": balance_before,
                        "balance_after": balance_before,
                    }

                balance_before = float(balances.get(str(user_id), 0.0))
                if balance_before < amount:
                    return {
                        "status": "insufficient",
                        "balance_before": balance_before,
                        "balance_after": balance_before,
                    }

                balance_after = balance_before - amount
                if balance_after < 0:
                    return {
                        "status": "negative_blocked",
                        "balance_before": balance_before,
                        "balance_after": balance_before,
                    }

                balances[str(user_id)] = balance_after
                deductions[task_id] = {
                    "user_id": user_id,
                    "model_id": model_id,
                    "sku_id": sku_id,
                    "amount": amount,
                    "created_at": datetime.utcnow().isoformat(),
                }

                await conn.execute(
                    "UPDATE storage_json SET payload=$3::jsonb, updated_at=now() "
                    "WHERE partner_id=$1 AND filename=$2",
                    self.partner_id,
                    self.balances_file,
                    json.dumps(balances) if balances else "{}",
                )
                await conn.execute(
                    "UPDATE storage_json SET payload=$3::jsonb, updated_at=now() "
                    "WHERE partner_id=$1 AND filename=$2",
                    self.partner_id,
                    self.balance_deductions_file,
                    json.dumps(deductions) if deductions else "{}",
                )
                return {
                    "status": "charged",
                    "balance_before": balance_before,
                    "balance_after": balance_after,
                }

    async def get_user_language(self, user_id: int) -> str:
        data = await self._load_json(self.languages_file)
        return data.get(str(user_id), "ru")

    async def set_user_language(self, user_id: int, language: str) -> None:
        data = await self._load_json(self.languages_file)
        data[str(user_id)] = language
        await self._save_json(self.languages_file, data)

    async def has_claimed_gift(self, user_id: int) -> bool:
        data = await self._load_json(self.gift_claimed_file)
        return data.get(str(user_id), False)

    async def set_gift_claimed(self, user_id: int) -> None:
        data = await self._load_json(self.gift_claimed_file)
        data[str(user_id)] = True
        await self._save_json(self.gift_claimed_file, data)

    async def get_user_free_generations_today(self, user_id: int) -> int:
        data = await self._load_json(self.free_generations_file)
        user_key = str(user_id)
        today = datetime.now().strftime("%Y-%m-%d")
        if user_key not in data:
            return 0
        user_data = data[user_key]
        if user_data.get("date") == today:
            return user_data.get("count", 0)
        return 0

    async def get_user_free_generations_remaining(self, user_id: int) -> int:
        from app.pricing.free_policy import get_free_daily_limit

        free_per_day = get_free_daily_limit()
        used = await self.get_user_free_generations_today(user_id)
        return max(0, free_per_day - used)

    async def increment_free_generations(self, user_id: int) -> None:
        data = await self._load_json(self.free_generations_file)
        user_key = str(user_id)
        today = datetime.now().strftime("%Y-%m-%d")
        if user_key not in data:
            data[user_key] = {"date": today, "count": 0, "bonus": 0}
        user_data = data[user_key]
        if user_data.get("date") != today:
            user_data["date"] = today
            user_data["count"] = 0
        old_count = max(0, int(user_data.get("count", 0)))
        user_data["count"] = old_count + 1
        await self._save_json(self.free_generations_file, data)
        logger.info("Free gen incremented user_id=%s date=%s count=%s", user_id, today, old_count + 1)

    async def consume_free_generation_once(
        self,
        user_id: int,
        *,
        task_id: str,
        sku_id: str = "",
        source: str = "delivery",
    ) -> Dict[str, Any]:
        if not task_id:
            return {"status": "missing_task_id"}
        from app.pricing.free_policy import get_free_daily_limit

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO storage_json (partner_id, filename, payload) VALUES ($1, $2, '{}'::jsonb) "
                    "ON CONFLICT DO NOTHING",
                    self.partner_id,
                    self.free_generations_file,
                )
                await conn.execute(
                    "INSERT INTO storage_json (partner_id, filename, payload) VALUES ($1, $2, '{}'::jsonb) "
                    "ON CONFLICT DO NOTHING",
                    self.partner_id,
                    self.free_deductions_file,
                )

                free_payload = await conn.fetchval(
                    "SELECT payload FROM storage_json WHERE partner_id=$1 AND filename=$2 FOR UPDATE",
                    self.partner_id,
                    self.free_generations_file,
                )
                deductions_payload = await conn.fetchval(
                    "SELECT payload FROM storage_json WHERE partner_id=$1 AND filename=$2 FOR UPDATE",
                    self.partner_id,
                    self.free_deductions_file,
                )
                free_data = self._coerce_payload(free_payload, filename=self.free_generations_file)
                deductions = self._coerce_payload(deductions_payload, filename=self.free_deductions_file)

                today = datetime.now().strftime("%Y-%m-%d")
                user_key = str(user_id)
                entry = free_data.get(user_key, {})
                if entry.get("date") != today:
                    entry = {"date": today, "count": 0, "bonus": 0}
                used_count = max(0, int(entry.get("count", 0)))
                limit = int(get_free_daily_limit())
                remaining = max(0, limit - used_count)

                if task_id in deductions:
                    return {
                        "status": "duplicate",
                        "used_today": used_count,
                        "remaining": remaining,
                        "limit_per_day": limit,
                    }

                if remaining <= 0:
                    return {
                        "status": "deny",
                        "used_today": used_count,
                        "remaining": 0,
                        "limit_per_day": limit,
                    }

                entry["count"] = used_count + 1
                free_data[user_key] = entry
                deductions[task_id] = {
                    "user_id": user_id,
                    "sku_id": sku_id,
                    "source": source,
                    "created_at": datetime.utcnow().isoformat(),
                }

                await conn.execute(
                    "UPDATE storage_json SET payload=$3::jsonb, updated_at=now() "
                    "WHERE partner_id=$1 AND filename=$2",
                    self.partner_id,
                    self.free_generations_file,
                    json.dumps(free_data) if free_data else "{}",
                )
                await conn.execute(
                    "UPDATE storage_json SET payload=$3::jsonb, updated_at=now() "
                    "WHERE partner_id=$1 AND filename=$2",
                    self.partner_id,
                    self.free_deductions_file,
                    json.dumps(deductions) if deductions else "{}",
                )
                remaining = max(0, limit - int(entry.get("count", 0)))
                return {
                    "status": "ok",
                    "used_today": int(entry.get("count", 0)),
                    "remaining": remaining,
                    "limit_per_day": limit,
                }

    async def get_hourly_free_usage(self, user_id: int) -> Dict[str, Any]:
        data = await self._load_json(self.hourly_free_usage_file)
        return data.get(str(user_id), {})

    async def set_hourly_free_usage(self, user_id: int, window_start_iso: str, used_count: int) -> None:
        data = await self._load_json(self.hourly_free_usage_file)
        data[str(user_id)] = {
            "window_start_iso": window_start_iso,
            "used_count": int(used_count),
        }
        await self._save_json(self.hourly_free_usage_file, data)

    async def get_referral_free_bank(self, user_id: int) -> int:
        data = await self._load_json(self.referral_free_bank_file)
        return int(data.get(str(user_id), 0))

    async def set_referral_free_bank(self, user_id: int, remaining_count: int) -> None:
        data = await self._load_json(self.referral_free_bank_file)
        data[str(user_id)] = int(max(0, remaining_count))
        await self._save_json(self.referral_free_bank_file, data)

    async def get_admin_limit(self, user_id: int) -> float:
        from app.config import get_settings

        settings = get_settings()
        if user_id == settings.admin_id:
            return float("inf")
        data = await self._load_json(self.admin_limits_file)
        admin_data = data.get(str(user_id), {})
        return float(admin_data.get("limit", 100.0))

    async def get_admin_spent(self, user_id: int) -> float:
        data = await self._load_json(self.admin_limits_file)
        admin_data = data.get(str(user_id), {})
        return float(admin_data.get("spent", 0.0))

    async def get_admin_remaining(self, user_id: int) -> float:
        limit = await self.get_admin_limit(user_id)
        if limit == float("inf"):
            return float("inf")
        spent = await self.get_admin_spent(user_id)
        return max(0.0, limit - spent)

    # ==================== GENERATION JOBS ====================

    async def add_generation_job(
        self,
        user_id: int,
        model_id: str,
        model_name: str,
        params: Dict[str, Any],
        price: float,
        task_id: Optional[str] = None,
        status: str = "pending",
        *,
        job_id: Optional[str] = None,
        request_id: Optional[str] = None,
        prompt: Optional[str] = None,
        prompt_hash: Optional[str] = None,
        result_url: Optional[str] = None,
        error_code: Optional[str] = None,
    ) -> str:
        import uuid

        job_id = job_id or task_id or str(uuid.uuid4())
        data = await self._load_json(self.jobs_file)
        job = {
            "job_id": job_id,
            "request_id": request_id,
            "user_id": user_id,
            "model_id": model_id,
            "model_name": model_name,
            "prompt": prompt,
            "prompt_hash": prompt_hash,
            "params": params,
            "price": price,
            "status": status,
            "task_id": task_id,
            "external_task_id": task_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "result_urls": [],
            "result_url": result_url,
            "error_message": None,
            "error_code": error_code,
        }
        data[job_id] = job
        await self._save_json(self.jobs_file, data)
        return job_id

    async def update_job_status(
        self,
        job_id: str,
        status: str,
        result_urls: Optional[List[str]] = None,
        error_message: Optional[str] = None,
        error_code: Optional[str] = None,
        result_url: Optional[str] = None,
    ) -> None:
        data = await self._load_json(self.jobs_file)
        if job_id not in data:
            raise ValueError(f"Job {job_id} not found")
        job = data[job_id]
        job["status"] = status
        job["updated_at"] = datetime.now().isoformat()
        if result_urls is not None:
            job["result_urls"] = result_urls
            if result_urls:
                job["result_url"] = result_urls[0]
        if error_message is not None:
            job["error_message"] = error_message
        if error_code is not None:
            job["error_code"] = error_code
        if result_url is not None:
            job["result_url"] = result_url
        await self._save_json(self.jobs_file, data)

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        data = await self._load_json(self.jobs_file)
        return data.get(job_id)

    async def list_jobs(
        self,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        data = await self._load_json(self.jobs_file)
        jobs = list(data.values())
        if user_id is not None:
            jobs = [j for j in jobs if j.get("user_id") == user_id]
        if status is not None:
            jobs = [j for j in jobs if j.get("status") == status]
        jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return jobs[:limit]

    async def add_generation_to_history(
        self,
        user_id: int,
        model_id: str,
        model_name: str,
        params: Dict[str, Any],
        result_urls: List[str],
        price: float,
        operation_id: Optional[str] = None,
    ) -> str:
        import uuid
        from app.services.history_service import append_event

        gen_id = operation_id or str(uuid.uuid4())
        data = await self._load_json(self.generations_history_file)
        user_key = str(user_id)
        if user_key not in data:
            data[user_key] = []
        generation = {
            "id": gen_id,
            "model_id": model_id,
            "model_name": model_name,
            "params": params,
            "result_urls": result_urls,
            "price": price,
            "timestamp": datetime.now().isoformat(),
        }
        data[user_key].append(generation)
        data[user_key] = data[user_key][-100:]
        await self._save_json(self.generations_history_file, data)
        await append_event(
            self,
            user_id=user_id,
            kind="generation",
            payload={
                "model_id": model_id,
                "model_name": model_name,
                "price": price,
                "result_urls": result_urls,
            },
            event_id=gen_id,
        )
        return gen_id

    async def get_user_generations_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        data = await self._load_json(self.generations_history_file)
        history = data.get(str(user_id), [])
        return history[-limit:]

    # ==================== PAYMENTS ====================

    async def add_payment(
        self,
        user_id: int,
        amount: float,
        payment_method: str,
        payment_id: Optional[str] = None,
        screenshot_file_id: Optional[str] = None,
        status: str = "pending",
    ) -> str:
        import uuid

        pay_id = payment_id or str(uuid.uuid4())
        data = await self._load_json(self.payments_file)
        payment = {
            "payment_id": pay_id,
            "user_id": user_id,
            "amount": amount,
            "payment_method": payment_method,
            "screenshot_file_id": screenshot_file_id,
            "status": status,
            "balance_charged": False,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "admin_id": None,
            "notes": None,
        }
        data[pay_id] = payment
        await self._save_json(self.payments_file, data)
        return pay_id

    async def mark_payment_status(
        self,
        payment_id: str,
        status: str,
        admin_id: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> None:
        data = await self._load_json(self.payments_file)
        if payment_id not in data:
            raise ValueError(f"Payment {payment_id} not found")
        payment = data[payment_id]
        success_statuses = {"approved", "completed"}
        credit_balance = status in success_statuses and not payment.get("balance_charged")
        if credit_balance:
            payment["balance_charged"] = True
        payment["status"] = status
        payment["updated_at"] = datetime.now().isoformat()
        if admin_id is not None:
            payment["admin_id"] = admin_id
        if notes is not None:
            payment["notes"] = notes
        if credit_balance:
            await self.add_user_balance(payment["user_id"], payment["amount"])
        await self._save_json(self.payments_file, data)

    async def get_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        data = await self._load_json(self.payments_file)
        return data.get(payment_id)

    async def list_payments(
        self,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        data = await self._load_json(self.payments_file)
        payments = list(data.values())
        if user_id is not None:
            payments = [p for p in payments if p.get("user_id") == user_id]
        if status is not None:
            payments = [p for p in payments if p.get("status") == status]
        payments.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return payments[:limit]

    # ==================== REFERRALS ====================

    async def set_referrer(self, user_id: int, referrer_id: int) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO referrals (partner_id, referred_user_id, referrer_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (partner_id, referred_user_id) DO NOTHING
                """,
                self.partner_id,
                int(user_id),
                int(referrer_id),
            )

    async def get_referrer(self, user_id: int) -> Optional[int]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT referrer_id FROM referrals WHERE partner_id=$1 AND referred_user_id=$2",
                self.partner_id,
                int(user_id),
            )
            if row:
                return int(row["referrer_id"])
        return None

    async def get_referrals(self, referrer_id: int) -> List[int]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT referred_user_id FROM referrals WHERE partner_id=$1 AND referrer_id=$2",
                self.partner_id,
                int(referrer_id),
            )
            return [int(row["referred_user_id"]) for row in rows]

    async def add_referral_bonus(self, referrer_id: int, bonus: float = 5) -> None:
        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            key = str(referrer_id)
            data[key] = float(data.get(key, 0.0)) + bonus
            return data

        await self.update_json_file(self.free_generations_file, updater)

    async def create_referral_record(
        self,
        *,
        referrer_id: int,
        referred_user_id: int,
        partner_id: str,
        ref_param: Optional[str],
        bonus_amount: int,
    ) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                INSERT INTO referrals (
                    partner_id,
                    referred_user_id,
                    referrer_id,
                    ref_param,
                    bonus_amount,
                    bonus_granted_at
                )
                VALUES ($1, $2, $3, $4, $5, now())
                ON CONFLICT (partner_id, referred_user_id) DO NOTHING
                """,
                partner_id,
                int(referred_user_id),
                int(referrer_id),
                ref_param,
                int(bonus_amount),
            )
            return result.startswith("INSERT")

    async def get_referral_stats(self, referrer_id: int, partner_id: str) -> Dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS invited,
                    COUNT(created_at) AS activated,
                    COUNT(bonus_granted_at) AS granted,
                    COALESCE(SUM(bonus_amount), 0) AS bonus_total
                FROM referrals
                WHERE partner_id=$1 AND referrer_id=$2
                """,
                partner_id,
                int(referrer_id),
            )
            if not row:
                return {"invited": 0, "activated": 0, "granted": 0, "bonus_total": 0}
            return {
                "invited": int(row["invited"] or 0),
                "activated": int(row["activated"] or 0),
                "granted": int(row["granted"] or 0),
                "bonus_total": int(row["bonus_total"] or 0),
            }

    async def list_recent_referrals(self, *, partner_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT referrer_id, referred_user_id, created_at, bonus_granted_at, bonus_amount
                FROM referrals
                WHERE partner_id=$1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                partner_id,
                int(limit),
            )
            return [
                {
                    "referrer_id": int(row["referrer_id"]),
                    "referred_user_id": int(row["referred_user_id"]),
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "bonus_granted_at": row["bonus_granted_at"].isoformat() if row["bonus_granted_at"] else None,
                    "bonus_amount": int(row["bonus_amount"] or 0),
                }
                for row in rows
            ]

    async def get_referral_admin_summary(self, *, partner_id: str, limit: int = 5) -> Dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            totals_row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS invited,
                    COUNT(bonus_granted_at) AS granted,
                    COALESCE(SUM(bonus_amount), 0) AS bonus_total
                FROM referrals
                WHERE partner_id=$1
                """,
                partner_id,
            )
            recent_rows = await conn.fetch(
                """
                SELECT referrer_id, referred_user_id, created_at, bonus_granted_at, bonus_amount
                FROM referrals
                WHERE partner_id=$1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                partner_id,
                int(limit),
            )
        totals = {
            "invited": int(totals_row["invited"] or 0) if totals_row else 0,
            "granted": int(totals_row["granted"] or 0) if totals_row else 0,
            "bonus_total": int(totals_row["bonus_total"] or 0) if totals_row else 0,
        }
        recent = [
            {
                "referrer_id": int(row["referrer_id"]),
                "referred_user_id": int(row["referred_user_id"]),
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "bonus_granted_at": row["bonus_granted_at"].isoformat() if row["bonus_granted_at"] else None,
                "bonus_amount": int(row["bonus_amount"] or 0),
            }
            for row in recent_rows
        ]
        return {"totals": totals, "recent": recent}

    # ==================== GENERIC JSON FILES ====================

    async def read_json_file(self, filename: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = await self._load_json(filename)
        if payload:
            return payload
        return default or {}

    async def write_json_file(self, filename: str, data: Dict[str, Any]) -> None:
        await self._save_json(filename, data)

    async def update_json_file(
        self,
        filename: str,
        update_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> Dict[str, Any]:
        pool = await self._get_pool()
        lock_key = self._advisory_lock_key_pair(filename)
        async with pool.acquire() as conn:
            async with conn.transaction():
                from app.utils.pg_advisory_lock import acquire_advisory_xact_lock, log_advisory_lock_key

                correlation_id = get_correlation_id() or "corr-na"
                log_advisory_lock_key(logger, lock_key, correlation_id=correlation_id, action="pg_advisory_xact_lock")
                lock_start = time.monotonic()
                try:
                    await acquire_advisory_xact_lock(conn, lock_key)
                except Exception as exc:
                    lock_duration_ms = int((time.monotonic() - lock_start) * 1000)
                    logger.error(
                        "PG_ADVISORY_XACT_LOCK_FAILED filename=%s duration_ms=%s correlation_id=%s error=%s",
                        filename,
                        lock_duration_ms,
                        correlation_id,
                        exc,
                        exc_info=True,
                    )
                    raise
                lock_duration_ms = int((time.monotonic() - lock_start) * 1000)
                logger.info(
                    "PG_ADVISORY_XACT_LOCK_ACQUIRED filename=%s duration_ms=%s correlation_id=%s",
                    filename,
                    lock_duration_ms,
                    correlation_id,
                )
                row = await conn.fetchrow(
                    "SELECT payload FROM storage_json WHERE partner_id=$1 AND filename=$2 FOR UPDATE",
                    self.partner_id,
                    filename,
                )
                current: Dict[str, Any] = {}
                if row:
                    payload = row[0]
                    if isinstance(payload, dict):
                        current = dict(payload)
                    elif isinstance(payload, str):
                        try:
                            parsed = json.loads(payload)
                        except json.JSONDecodeError:
                            parsed = None
                        if isinstance(parsed, dict):
                            current = parsed
                updated = update_fn(dict(current))
                await conn.execute(
                    """
                    INSERT INTO storage_json (partner_id, filename, payload)
                    VALUES ($1, $2, $3::jsonb)
                    ON CONFLICT (partner_id, filename)
                    DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()
                    """,
                    self.partner_id,
                    filename,
                    json.dumps(updated) if updated else "{}",
                )
                return updated

    # ==================== UTILITY ====================

    def test_connection(self) -> bool:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.ping())
        logger.warning("[STORAGE] test_connection called inside running loop; use await ping()")
        return True

    async def ping(self) -> bool:
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute("SELECT 1")
            return True
        except Exception as exc:
            logger.warning("[STORAGE] ping_failed partner_id=%s error=%s", self.partner_id, exc)
            return False

    async def close(self) -> None:
        pools = list(self._pools.values())
        self._pools.clear()
        self._schema_ready_loops.clear()
        self._file_locks.clear()
        for pool in pools:
            await pool.close()

    async def initialize(self) -> bool:
        """Initialize storage connection and ensure schema."""
        try:
            await self._get_pool()
            return await self.ping()
        except Exception as exc:
            logger.warning("[STORAGE] init_failed partner_id=%s error=%s", self.partner_id, exc)
            return False

    # ==================== MIGRATION HELPERS ====================

    async def has_completed_migration(self, key: str) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT 1 FROM migrations_meta WHERE key=$1", key)
            return row is not None

    async def mark_migration_done(self, key: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO migrations_meta (key, completed_at) VALUES ($1, now()) ON CONFLICT (key) DO NOTHING",
                key,
            )

    async def is_empty(self) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT count(*) AS c FROM storage_json WHERE partner_id=$1", self.partner_id)
            return not row or row[0] == 0

    async def migrate_from_github(self, github_storage: BaseStorage) -> None:
        migrate_key = "github_to_postgres"
        if await self.has_completed_migration(migrate_key):
            logger.info("[STORAGE] migration already completed")
            return
        files = [
            self.balances_file,
            self.languages_file,
            self.gift_claimed_file,
            self.free_generations_file,
            self.hourly_free_usage_file,
            self.referral_free_bank_file,
            self.admin_limits_file,
            self.generations_history_file,
            self.payments_file,
            self.referrals_file,
            self.jobs_file,
        ]
        migrated = []
        for fname in files:
            try:
                payload = await github_storage.read_json_file(fname, default={})
                await self._save_json(fname, payload or {})
                migrated.append(fname)
                logger.info("[STORAGE] migrated %s", fname)
            except Exception as exc:
                logger.warning("[STORAGE] migrate_failed file=%s error=%s", fname, exc)
        await self.mark_migration_done(migrate_key)
        logger.info("[STORAGE] migration_completed migrated_files=%s", ",".join(migrated) if migrated else "none")
