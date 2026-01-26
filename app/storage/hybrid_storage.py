"""
Hybrid storage: GitHub storage for static data, local runtime storage for balances/quotas.
"""
from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable

from app.storage.base import BaseStorage

logger = logging.getLogger(__name__)


class HybridStorage(BaseStorage):
    """Delegate runtime-sensitive data to runtime storage, everything else to primary storage."""

    def __init__(
        self,
        primary: BaseStorage,
        runtime: BaseStorage,
        runtime_files: Optional[set[str]] = None,
    ) -> None:
        self._primary = primary
        self._runtime = runtime
        self._runtime_files = runtime_files or set()
        self._primary_cache: Dict[str, HybridStorage._CacheEntry] = {}
        self._primary_cache_version = 0
        self._fallback_ttl = float(os.getenv("HYBRID_STORAGE_FALLBACK_TTL", "300"))
        self._balance_write_through = os.getenv("HYBRID_BALANCE_WRITE_THROUGH", "1") in ("1", "true", "yes")
        self._runtime_write_through = os.getenv("HYBRID_RUNTIME_WRITE_THROUGH", "1") in ("1", "true", "yes")

    async def _write_balance_primary(self, user_id: int, amount: float) -> None:
        if not self._balance_write_through:
            return
        try:
            await self._primary.set_user_balance(user_id, amount)
        except Exception as exc:
            logger.warning(
                "[STORAGE] balance_write_through_failed user_id=%s error=%s",
                user_id,
                exc,
            )

    async def _write_runtime_primary(self, filename: str, data: Dict[str, Any]) -> None:
        if not self._runtime_write_through:
            return
        try:
            await self._primary.write_json_file(filename, data)
            self._primary_cache_version += 1
            self._primary_cache[filename] = self._CacheEntry(
                data=data,
                updated_at=time.monotonic(),
                version=self._primary_cache_version,
            )
        except Exception as exc:
            logger.warning(
                "[STORAGE] runtime_write_through_failed path=%s error=%s",
                filename,
                exc,
            )

    async def _sync_runtime_file(self, filename: str) -> None:
        if not self._runtime_write_through:
            return
        payload = await self._runtime.read_json_file(filename, default={})
        await self._write_runtime_primary(filename, payload)

    @dataclass(frozen=True)
    class _CacheEntry:
        data: Dict[str, Any]
        updated_at: float
        version: int

    def _is_runtime_file(self, filename: str) -> bool:
        basename = os.path.basename(filename)
        return basename in self._runtime_files

    async def get_user(self, user_id: int, upsert: bool = True) -> Dict[str, Any]:
        balance = await self.get_user_balance(user_id)
        language = await self.get_user_language(user_id)
        gift_claimed = await self.has_claimed_gift(user_id)
        referrer_id = None
        if hasattr(self._primary, "get_referrer"):
            referrer_id = await self._primary.get_referrer(user_id)  # type: ignore[attr-defined]

        return {
            "user_id": user_id,
            "balance": balance,
            "language": language,
            "gift_claimed": gift_claimed,
            "referrer_id": referrer_id,
        }

    async def get_user_balance(self, user_id: int) -> float:
        return await self._runtime.get_user_balance(user_id)

    async def set_user_balance(self, user_id: int, amount: float) -> None:
        await self._runtime.set_user_balance(user_id, amount)
        await self._write_balance_primary(user_id, amount)

    async def add_user_balance(self, user_id: int, amount: float) -> float:
        new_balance = await self._runtime.add_user_balance(user_id, amount)
        await self._write_balance_primary(user_id, new_balance)
        return new_balance

    async def subtract_user_balance(self, user_id: int, amount: float) -> bool:
        success = await self._runtime.subtract_user_balance(user_id, amount)
        if success:
            new_balance = await self._runtime.get_user_balance(user_id)
            await self._write_balance_primary(user_id, new_balance)
        return success

    async def get_user_language(self, user_id: int) -> str:
        return await self._primary.get_user_language(user_id)

    async def set_user_language(self, user_id: int, language: str) -> None:
        await self._primary.set_user_language(user_id, language)

    async def has_claimed_gift(self, user_id: int) -> bool:
        return await self._primary.has_claimed_gift(user_id)

    async def set_gift_claimed(self, user_id: int) -> None:
        await self._primary.set_gift_claimed(user_id)

    async def get_user_free_generations_today(self, user_id: int) -> int:
        return await self._runtime.get_user_free_generations_today(user_id)

    async def get_user_free_generations_remaining(self, user_id: int) -> int:
        return await self._runtime.get_user_free_generations_remaining(user_id)

    async def increment_free_generations(self, user_id: int) -> None:
        await self._runtime.increment_free_generations(user_id)
        await self._sync_runtime_file("daily_free_generations.json")

    async def get_hourly_free_usage(self, user_id: int) -> Dict[str, Any]:
        return await self._runtime.get_hourly_free_usage(user_id)

    async def set_hourly_free_usage(self, user_id: int, window_start_iso: str, used_count: int) -> None:
        await self._runtime.set_hourly_free_usage(user_id, window_start_iso, used_count)
        await self._sync_runtime_file("hourly_free_usage.json")

    async def get_referral_free_bank(self, user_id: int) -> int:
        return await self._runtime.get_referral_free_bank(user_id)

    async def set_referral_free_bank(self, user_id: int, remaining_count: int) -> None:
        await self._runtime.set_referral_free_bank(user_id, remaining_count)
        await self._sync_runtime_file("referral_free_bank.json")

    async def get_admin_limit(self, user_id: int) -> float:
        return await self._runtime.get_admin_limit(user_id)

    async def get_admin_spent(self, user_id: int) -> float:
        return await self._runtime.get_admin_spent(user_id)

    async def get_admin_remaining(self, user_id: int) -> float:
        return await self._runtime.get_admin_remaining(user_id)

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
        correlation_id: Optional[str] = None,
        prompt: Optional[str] = None,
        prompt_hash: Optional[str] = None,
        sku_id: Optional[str] = None,
        is_free: bool = False,
        is_admin_user: bool = False,
        chat_id: Optional[int] = None,
        message_id: Optional[int] = None,
        result_url: Optional[str] = None,
        error_code: Optional[str] = None,
    ) -> str:
        return await self._primary.add_generation_job(
            user_id,
            model_id,
            model_name,
            params,
            price,
            task_id=task_id,
            status=status,
            job_id=job_id,
            request_id=request_id,
            correlation_id=correlation_id,
            prompt=prompt,
            prompt_hash=prompt_hash,
            sku_id=sku_id,
            is_free=is_free,
            is_admin_user=is_admin_user,
            chat_id=chat_id,
            message_id=message_id,
            result_url=result_url,
            error_code=error_code,
        )

    async def update_job_status(
        self,
        job_id: str,
        status: str,
        result_urls: Optional[List[str]] = None,
        error_message: Optional[str] = None,
        error_code: Optional[str] = None,
        result_url: Optional[str] = None,
    ) -> None:
        await self._primary.update_job_status(
            job_id,
            status,
            result_urls=result_urls,
            error_message=error_message,
            error_code=error_code,
            result_url=result_url,
        )

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return await self._primary.get_job(job_id)

    async def list_jobs(
        self,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return await self._primary.list_jobs(user_id=user_id, status=status, limit=limit)

    async def list_jobs_by_status(
        self,
        statuses: List[str],
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return await self._primary.list_jobs_by_status(statuses=statuses, limit=limit)

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
        return await self._primary.add_generation_to_history(
            user_id,
            model_id,
            model_name,
            params,
            result_urls,
            price,
            operation_id=operation_id,
        )

    async def get_user_generations_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        return await self._primary.get_user_generations_history(user_id, limit=limit)

    async def add_payment(
        self,
        user_id: int,
        amount: float,
        payment_method: str,
        payment_id: Optional[str] = None,
        screenshot_file_id: Optional[str] = None,
        status: str = "pending",
    ) -> str:
        return await self._primary.add_payment(
            user_id,
            amount,
            payment_method,
            payment_id=payment_id,
            screenshot_file_id=screenshot_file_id,
            status=status,
        )

    async def mark_payment_status(
        self,
        payment_id: str,
        status: str,
        admin_id: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> None:
        await self._primary.mark_payment_status(payment_id, status, admin_id=admin_id, notes=notes)

    async def get_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        return await self._primary.get_payment(payment_id)

    async def list_payments(
        self,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return await self._primary.list_payments(user_id=user_id, status=status, limit=limit)

    async def set_referrer(self, user_id: int, referrer_id: int) -> None:
        await self._primary.set_referrer(user_id, referrer_id)

    async def get_referrer(self, user_id: int) -> Optional[int]:
        return await self._primary.get_referrer(user_id)

    async def get_referrals(self, referrer_id: int) -> List[int]:
        return await self._primary.get_referrals(referrer_id)

    async def add_referral_bonus(self, referrer_id: int, bonus_generations: int = 5) -> None:
        await self._primary.add_referral_bonus(referrer_id, bonus_generations)

    async def read_json_file(self, filename: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self._is_runtime_file(filename):
            return await self._runtime.read_json_file(filename, default)
        try:
            data = await self._primary.read_json_file(filename, default)
            if data:
                self._primary_cache_version += 1
                self._primary_cache[filename] = self._CacheEntry(
                    data=data,
                    updated_at=time.monotonic(),
                    version=self._primary_cache_version,
                )
            return data
        except Exception as exc:
            entry = self._primary_cache.get(filename)
            if entry is not None:
                age_sec = time.monotonic() - entry.updated_at
                logger.warning(
                    "STORAGE_FALLBACK_USED path=%s age_sec=%.2f version=%s ttl_sec=%.0f",
                    filename,
                    age_sec,
                    entry.version,
                    self._fallback_ttl,
                )
                return entry.data
            logger.warning(
                "[STORAGE] read_failed path=%s error_class=%s",
                filename,
                exc.__class__.__name__,
            )
            return default or {}

    async def write_json_file(self, filename: str, data: Dict[str, Any]) -> None:
        if self._is_runtime_file(filename):
            await self._runtime.write_json_file(filename, data)
            await self._write_runtime_primary(filename, data)
        else:
            await self._primary.write_json_file(filename, data)
            self._primary_cache_version += 1
            self._primary_cache[filename] = self._CacheEntry(
                data=data,
                updated_at=time.monotonic(),
                version=self._primary_cache_version,
            )

    async def update_json_file(
        self,
        filename: str,
        update_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
        lock_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self._is_runtime_file(filename):
            updated = await self._runtime.update_json_file(filename, update_fn, lock_mode=lock_mode)
            if updated:
                await self._write_runtime_primary(filename, updated)
            return updated
        updated = await self._primary.update_json_file(filename, update_fn, lock_mode=lock_mode)
        if updated:
            self._primary_cache_version += 1
            self._primary_cache[filename] = self._CacheEntry(
                data=updated,
                updated_at=time.monotonic(),
                version=self._primary_cache_version,
            )
        return updated

    def test_connection(self) -> bool:
        return self._primary.test_connection()

    async def close(self) -> None:
        await self._primary.close()
        await self._runtime.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._primary, name)
