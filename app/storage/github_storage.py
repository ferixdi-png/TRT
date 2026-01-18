"""
GitHub storage implementation - stores JSON data via GitHub Contents API.
Only storage/{BOT_INSTANCE_ID}/... paths are allowed.
"""

import asyncio
import base64
import json
import logging
import os
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable, Tuple

import aiohttp

from app.storage.base import BaseStorage

logger = logging.getLogger(__name__)


class GitHubConflictError(RuntimeError):
    """Raised when GitHub Contents API returns a 409 conflict."""


@dataclass(frozen=True)
class GitHubConfig:
    repo: str
    branch: str
    token: str
    committer_name: str
    committer_email: str
    storage_prefix: str
    bot_instance_id: str
    timeout_seconds: float
    max_parallel: int
    max_retries: int
    backoff_base: float


class GitHubStorage(BaseStorage):
    """JSON storage implementation backed by GitHub Contents API."""

    def __init__(self):
        self.config = self._load_config()
        self._sessions: Dict[int, aiohttp.ClientSession] = {}
        self._session_loops: Dict[int, asyncio.AbstractEventLoop] = {}
        self._semaphore = asyncio.Semaphore(self.config.max_parallel)
        self._implicit_dirs_logged = False

        self.balances_file = "user_balances.json"
        self.languages_file = "user_languages.json"
        self.gift_claimed_file = "gift_claimed.json"
        self.free_generations_file = "daily_free_generations.json"
        self.admin_limits_file = "admin_limits.json"
        self.generations_history_file = "generations_history.json"
        self.payments_file = "payments.json"
        self.referrals_file = "referrals.json"
        self.jobs_file = "generation_jobs.json"

        logger.info(
            "[STORAGE] mode=github instance=%s prefix=%s branch=%s parallel=%s retries=%s timeout=%ss",
            self.config.bot_instance_id,
            self.config.storage_prefix,
            self.config.branch,
            self.config.max_parallel,
            self.config.max_retries,
            self.config.timeout_seconds,
        )

    def _load_config(self) -> GitHubConfig:
        repo = os.getenv("GITHUB_REPO", "").strip()
        branch = os.getenv("GITHUB_BRANCH", "main").strip()
        token = os.getenv("GITHUB_TOKEN", "").strip()
        committer_name = os.getenv("GITHUB_COMMITTER_NAME", "TRT Bot").strip()
        committer_email = os.getenv("GITHUB_COMMITTER_EMAIL", "bot@example.com").strip()
        storage_prefix = os.getenv("STORAGE_PREFIX", "storage").strip().strip("/")
        bot_instance_id = os.getenv("BOT_INSTANCE_ID", "").strip()
        timeout_seconds = float(os.getenv("GITHUB_TIMEOUT_SECONDS", "20"))
        max_parallel = int(os.getenv("GITHUB_MAX_PARALLEL", "4"))
        max_retries = int(os.getenv("GITHUB_WRITE_RETRIES", "5"))
        backoff_base = float(os.getenv("GITHUB_BACKOFF_BASE", "0.5"))

        missing = []
        if not repo:
            missing.append("GITHUB_REPO")
        if not token:
            missing.append("GITHUB_TOKEN")
        if not bot_instance_id:
            missing.append("BOT_INSTANCE_ID")
        if missing:
            raise ValueError(
                "[STORAGE][GITHUB] missing_required_envs="
                + ",".join(missing)
                + " (BOT_INSTANCE_ID required per deploy)"
            )

        return GitHubConfig(
            repo=repo,
            branch=branch,
            token=token,
            committer_name=committer_name,
            committer_email=committer_email,
            storage_prefix=storage_prefix,
            bot_instance_id=bot_instance_id,
            timeout_seconds=timeout_seconds,
            max_parallel=max_parallel,
            max_retries=max_retries,
            backoff_base=backoff_base,
        )

    def _detach_session(self, loop_id: int, *, reason: str, new_loop_id: Optional[int] = None) -> None:
        session = self._sessions.pop(loop_id, None)
        self._session_loops.pop(loop_id, None)
        if session:
            logger.warning(
                "[GITHUB] session_detached reason=%s old_loop_id=%s new_loop_id=%s",
                reason,
                loop_id,
                new_loop_id,
            )

    async def _close_session_for_current_loop(self, reason: str) -> None:
        loop = asyncio.get_running_loop()
        loop_id = id(loop)
        session = self._sessions.pop(loop_id, None)
        self._session_loops.pop(loop_id, None)
        if not session:
            return
        try:
            await session.close()
            logger.info("[GITHUB] session_closed reason=%s loop_id=%s", reason, loop_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("[GITHUB] session_close_failed reason=%s error=%s", reason, exc)

    async def _get_session(self) -> aiohttp.ClientSession:
        loop = asyncio.get_running_loop()
        loop_id = id(loop)
        session = self._sessions.get(loop_id)
        stored_loop = self._session_loops.get(loop_id)

        if session and session.closed:
            self._detach_session(loop_id, reason="loop_closed", new_loop_id=loop_id)
            session = None
            stored_loop = None

        if session and stored_loop is not loop:
            self._detach_session(loop_id, reason="loop_mismatch", new_loop_id=loop_id)
            session = None

        if not session:
            for other_loop_id, other_loop in list(self._session_loops.items()):
                if other_loop_id != loop_id and other_loop.is_closed():
                    self._detach_session(
                        other_loop_id,
                        reason="loop_mismatch",
                        new_loop_id=loop_id,
                    )

        if session and not session.closed:
            return session

        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        session = aiohttp.ClientSession(
            timeout=timeout,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"token {self.config.token}",
                "User-Agent": "TRT-GitHubStorage",
            },
        )
        self._sessions[loop_id] = session
        self._session_loops[loop_id] = loop
        return session

    def _storage_path(self, filename: str) -> str:
        safe_name = filename.strip("/").replace("..", "")
        return f"{self.config.storage_prefix}/{self.config.bot_instance_id}/{safe_name}"

    def _contents_url(self, path: str) -> str:
        return f"https://api.github.com/repos/{self.config.repo}/contents/{path}"

    async def _request(self, method: str, url: str, **kwargs) -> aiohttp.ClientResponse:
        session = await self._get_session()
        async with self._semaphore:
            response = await session.request(method, url, **kwargs)
        return response

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        op: str,
        path: str,
        ok_statuses: Tuple[int, ...],
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        last_response: Optional[aiohttp.ClientResponse] = None
        for attempt in range(1, self.config.max_retries + 1):
            response = await self._request(method, url, **kwargs)
            last_response = response
            status = response.status
            ok = status in ok_statuses
            logger.info(
                "[GITHUB] op=%s path=%s ok=%s status=%s attempt=%s",
                op,
                path,
                str(ok).lower(),
                status,
                attempt,
            )
            if ok:
                return response

            if self._should_retry(status, response.headers):
                await response.release()
                await self._backoff(attempt, response.headers)
                continue

            return response

        if last_response is None:
            raise RuntimeError("GitHub request failed without response")
        return last_response

    def _should_retry(self, status: int, headers: aiohttp.typedefs.LooseHeaders) -> bool:
        retryable = status in {429, 500, 502, 503, 504}
        if status == 403 and headers.get("X-RateLimit-Remaining") == "0":
            return True
        return retryable

    def _retry_after_seconds(self, headers: aiohttp.typedefs.LooseHeaders) -> Optional[float]:
        retry_after = headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                return None
        reset_header = headers.get("X-RateLimit-Reset")
        if reset_header:
            try:
                reset_at = float(reset_header)
                delay = max(0.0, reset_at - time.time())
                return delay if delay > 0 else None
            except ValueError:
                return None
        return None

    async def _read_json(self, filename: str) -> Tuple[Dict[str, Any], Optional[str]]:
        path = self._storage_path(filename)
        url = self._contents_url(path)
        response = await self._request_with_retry(
            "GET",
            url,
            op="read",
            path=path,
            ok_statuses=(200, 404),
            params={"ref": self.config.branch},
        )
        if response.status == 404:
            await response.release()
            return {}, None
        if response.status != 200:
            payload = await response.text()
            await response.release()
            logger.error(
                "[GITHUB] op=read path=%s ok=false status=%s error_class=GitHubReadError",
                path,
                response.status,
            )
            raise RuntimeError(f"GitHub read failed {response.status}: {payload}")
        payload = await response.json()
        await response.release()
        content = payload.get("content", "")
        sha = payload.get("sha")
        decoded = base64.b64decode(content).decode("utf-8") if content else "{}"
        try:
            data = json.loads(decoded) if decoded.strip() else {}
        except json.JSONDecodeError:
            logger.error("[GITHUB] read_invalid_json path=%s", path)
            data = {}
        return data, sha

    async def _write_json(self, filename: str, data: Dict[str, Any], sha: Optional[str]) -> None:
        path = self._storage_path(filename)
        url = self._contents_url(path)
        payload_json = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        logger.info(
            "[GITHUB] write_attempt path=%s size_bytes=%s",
            path,
            len(payload_json.encode("utf-8")),
        )
        content = base64.b64encode(payload_json.encode("utf-8")).decode("utf-8")
        payload = {
            "message": f"storage update {path}",
            "content": content,
            "branch": self.config.branch,
            "committer": {
                "name": self.config.committer_name,
                "email": self.config.committer_email,
            },
        }
        if sha:
            payload["sha"] = sha
        if not self._implicit_dirs_logged:
            logger.info("[GITHUB] implicit_dirs=true path=%s", path)
            self._implicit_dirs_logged = True
        response = await self._request_with_retry(
            "PUT",
            url,
            op="write",
            path=path,
            ok_statuses=(200, 201, 409),
            json=payload,
        )
        if response.status in (200, 201):
            await response.release()
            logger.info(
                "[GITHUB] write_ok path=%s status=%s",
                path,
                response.status,
            )
            return
        if response.status == 409:
            await response.release()
            raise GitHubConflictError(f"GitHub write conflict for {path}")
        payload_text = await response.text()
        await response.release()
        logger.error(
            "[GITHUB] op=write path=%s ok=false status=%s error_class=GitHubWriteError",
            path,
            response.status,
        )
        raise RuntimeError(f"GitHub write failed {response.status}: {payload_text}")

    def _merge_json(self, base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base)
        for key, value in incoming.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._merge_json(merged[key], value)
            else:
                merged[key] = value
        return merged

    async def _update_json(
        self,
        filename: str,
        update_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> Dict[str, Any]:
        last_error: Optional[Exception] = None
        for attempt in range(1, self.config.max_retries + 1):
            data, sha = await self._read_json(filename)
            updated = update_fn(dict(data))
            merged = self._merge_json(data, updated)
            try:
                await self._write_json(filename, merged, sha)
                if attempt > 1:
                    logger.info(
                        "[GITHUB] write_conflict resolved=true attempts=%s path=%s",
                        attempt,
                        self._storage_path(filename),
                    )
                return merged
            except GitHubConflictError as exc:
                last_error = exc
                logger.warning(
                    "[GITHUB] write_retry attempt=%s path=%s reason=conflict",
                    attempt,
                    self._storage_path(filename),
                )
                await self._backoff(attempt)
        logger.error(
            "[GITHUB] write_conflict resolved=false attempts=%s path=%s",
            self.config.max_retries,
            self._storage_path(filename),
        )
        raise RuntimeError("Exceeded GitHub write retries") from last_error

    async def _backoff(self, attempt: int, headers: Optional[aiohttp.typedefs.LooseHeaders] = None) -> None:
        delay = (2 ** (attempt - 1)) * self.config.backoff_base
        retry_after = self._retry_after_seconds(headers or {})
        if retry_after is not None:
            delay = max(delay, retry_after)
        jitter = random.uniform(0, self.config.backoff_base)
        logger.info(
            "[GITHUB] write_backoff attempt=%s delay_s=%.2f",
            attempt,
            delay + jitter,
        )
        await asyncio.sleep(delay + jitter)

    async def initialize(self) -> bool:
        """Optional initialization hook for factory."""
        return True

    def test_connection(self) -> bool:
        """Sync connection test for GitHub storage."""
        async def _check() -> bool:
            path = self._storage_path(self.balances_file)
            url = self._contents_url(path)
            timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            headers = {
                "Accept": "application/vnd.github+json",
                "Authorization": f"token {self.config.token}",
                "User-Agent": "TRT-GitHubStorage",
            }
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url, params={"ref": self.config.branch}) as response:
                    if response.status not in (200, 404):
                        payload = await response.text()
                        raise RuntimeError(f"GitHub test_connection failed {response.status}: {payload}")
            return True

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            result: Dict[str, Optional[Exception]] = {"error": None}
            success = {"value": False}

            def runner() -> None:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    success["value"] = new_loop.run_until_complete(_check())
                except Exception as exc:  # pragma: no cover - defensive
                    result["error"] = exc
                finally:
                    new_loop.close()

            thread = threading.Thread(target=runner, daemon=True)
            thread.start()
            thread.join()
            if result["error"]:
                logger.warning(
                    "[GITHUB] test_connection_ok=false error_class=%s",
                    result["error"].__class__.__name__,
                )
                return False
            if success["value"]:
                logger.info("[GITHUB] test_connection_ok=true")
                return True
            logger.warning("[GITHUB] test_connection_ok=false")
            return False

        try:
            result_ok = asyncio.run(_check())
            if result_ok:
                logger.info("[GITHUB] test_connection_ok=true")
            else:
                logger.warning("[GITHUB] test_connection_ok=false")
            return result_ok
        except Exception as exc:
            logger.warning(
                "[GITHUB] test_connection_ok=false error_class=%s",
                exc.__class__.__name__,
            )
            return False

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
        data, _ = await self._read_json(self.balances_file)
        return float(data.get(str(user_id), 0.0))

    async def set_user_balance(self, user_id: int, amount: float) -> None:
        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            data[str(user_id)] = amount
            return data

        await self._update_json(self.balances_file, updater)

    async def add_user_balance(self, user_id: int, amount: float) -> float:
        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            current = float(data.get(str(user_id), 0.0))
            data[str(user_id)] = current + amount
            return data

        data = await self._update_json(self.balances_file, updater)
        return float(data.get(str(user_id), 0.0))

    async def subtract_user_balance(self, user_id: int, amount: float) -> bool:
        success = False

        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            nonlocal success
            current = float(data.get(str(user_id), 0.0))
            if current >= amount:
                data[str(user_id)] = current - amount
                success = True
            return data

        await self._update_json(self.balances_file, updater)
        return success

    async def get_user_language(self, user_id: int) -> str:
        data, _ = await self._read_json(self.languages_file)
        return data.get(str(user_id), "ru")

    async def set_user_language(self, user_id: int, language: str) -> None:
        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            data[str(user_id)] = language
            return data

        await self._update_json(self.languages_file, updater)

    async def has_claimed_gift(self, user_id: int) -> bool:
        data, _ = await self._read_json(self.gift_claimed_file)
        return data.get(str(user_id), False)

    async def set_gift_claimed(self, user_id: int) -> None:
        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            data[str(user_id)] = True
            return data

        await self._update_json(self.gift_claimed_file, updater)

    async def get_user_free_generations_today(self, user_id: int) -> int:
        data, _ = await self._read_json(self.free_generations_file)
        user_key = str(user_id)
        today = datetime.now().strftime("%Y-%m-%d")
        if user_key not in data:
            return 0
        user_data = data[user_key]
        if user_data.get("date") == today:
            return user_data.get("count", 0)
        return 0

    async def get_user_free_generations_remaining(self, user_id: int) -> int:
        from app.config import get_settings

        settings = get_settings()
        free_per_day = 5
        used = await self.get_user_free_generations_today(user_id)
        data, _ = await self._read_json(self.free_generations_file)
        user_key = str(user_id)
        bonus = data.get(user_key, {}).get("bonus", 0)
        total_available = free_per_day + bonus
        return max(0, total_available - used)

    async def increment_free_generations(self, user_id: int) -> None:
        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            user_key = str(user_id)
            today = datetime.now().strftime("%Y-%m-%d")
            if user_key not in data:
                data[user_key] = {"date": today, "count": 0, "bonus": 0}
            user_data = data[user_key]
            if user_data.get("date") != today:
                user_data["date"] = today
                user_data["count"] = 0
            user_data["count"] = user_data.get("count", 0) + 1
            return data

        await self._update_json(self.free_generations_file, updater)

    async def get_admin_limit(self, user_id: int) -> float:
        from app.config import get_settings

        settings = get_settings()
        if user_id == settings.admin_id:
            return float("inf")
        data, _ = await self._read_json(self.admin_limits_file)
        admin_data = data.get(str(user_id), {})
        return float(admin_data.get("limit", 100.0))

    async def get_admin_spent(self, user_id: int) -> float:
        data, _ = await self._read_json(self.admin_limits_file)
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
    ) -> str:
        from uuid import uuid4

        job_id = task_id or str(uuid4())

        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            data[job_id] = {
                "job_id": job_id,
                "user_id": user_id,
                "model_id": model_id,
                "model_name": model_name,
                "params": params,
                "price": price,
                "task_id": task_id,
                "status": status,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            return data

        await self._update_json(self.jobs_file, updater)
        return job_id

    async def update_job_status(
        self,
        job_id: str,
        status: str,
        result_urls: Optional[List[str]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            job = data.get(job_id)
            if not job:
                return data
            job["status"] = status
            job["updated_at"] = datetime.now().isoformat()
            if result_urls is not None:
                job["result_urls"] = result_urls
            if error_message:
                job["error_message"] = error_message
            data[job_id] = job
            return data

        await self._update_json(self.jobs_file, updater)

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        data, _ = await self._read_json(self.jobs_file)
        return data.get(job_id)

    async def list_jobs(
        self,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        data, _ = await self._read_json(self.jobs_file)
        jobs = list(data.values())
        if user_id is not None:
            jobs = [job for job in jobs if job.get("user_id") == user_id]
        if status:
            jobs = [job for job in jobs if job.get("status") == status]
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
        from uuid import uuid4

        history_id = operation_id or str(uuid4())

        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            user_history = data.get(str(user_id), [])
            user_history.append(
                {
                    "operation_id": history_id,
                    "model_id": model_id,
                    "model_name": model_name,
                    "params": params,
                    "result_urls": result_urls,
                    "price": price,
                    "created_at": datetime.now().isoformat(),
                }
            )
            data[str(user_id)] = user_history[-100:]
            return data

        await self._update_json(self.generations_history_file, updater)
        return history_id

    async def get_user_generations_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        data, _ = await self._read_json(self.generations_history_file)
        history = data.get(str(user_id), [])
        return history[-limit:][::-1]

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
        from uuid import uuid4

        pay_id = payment_id or str(uuid4())

        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            data[pay_id] = {
                "payment_id": pay_id,
                "user_id": user_id,
                "amount": amount,
                "payment_method": payment_method,
                "screenshot_file_id": screenshot_file_id,
                "status": status,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            return data

        await self._update_json(self.payments_file, updater)
        return pay_id

    async def mark_payment_status(
        self,
        payment_id: str,
        status: str,
        admin_id: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> None:
        prior_status = None
        payment_user_id = None
        payment_amount = None

        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            nonlocal prior_status, payment_user_id, payment_amount
            if payment_id not in data:
                raise ValueError(f"Payment {payment_id} not found")
            payment = data[payment_id]
            prior_status = payment.get("status")
            payment_user_id = payment.get("user_id")
            payment_amount = payment.get("amount")
            payment["status"] = status
            payment["updated_at"] = datetime.now().isoformat()
            if admin_id is not None:
                payment["admin_id"] = admin_id
            if notes:
                payment["notes"] = notes
            data[payment_id] = payment
            return data

        await self._update_json(self.payments_file, updater)
        if status == "approved" and prior_status != "approved":
            if payment_user_id is not None and payment_amount is not None:
                await self.add_user_balance(int(payment_user_id), float(payment_amount))

    async def get_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        data, _ = await self._read_json(self.payments_file)
        return data.get(payment_id)

    async def list_payments(
        self,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        data, _ = await self._read_json(self.payments_file)
        payments = list(data.values())
        if user_id is not None:
            payments = [p for p in payments if p.get("user_id") == user_id]
        if status:
            payments = [p for p in payments if p.get("status") == status]
        payments.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return payments[:limit]

    # ==================== REFERRALS ====================

    async def set_referrer(self, user_id: int, referrer_id: int) -> None:
        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            data[str(user_id)] = referrer_id
            return data

        await self._update_json(self.referrals_file, updater)

    async def get_referrer(self, user_id: int) -> Optional[int]:
        data, _ = await self._read_json(self.referrals_file)
        referrer = data.get(str(user_id))
        return int(referrer) if referrer is not None else None

    async def get_referrals(self, referrer_id: int) -> List[int]:
        data, _ = await self._read_json(self.referrals_file)
        return [int(uid) for uid, ref in data.items() if int(ref) == referrer_id]

    async def add_referral_bonus(self, referrer_id: int, bonus: float) -> None:
        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            key = str(referrer_id)
            data[key] = float(data.get(key, 0.0)) + bonus
            return data

        await self._update_json(self.referrals_file, updater)

    async def get_referral_bonus(self, referrer_id: int) -> float:
        data, _ = await self._read_json(self.referrals_file)
        return float(data.get(str(referrer_id), 0.0))

    async def close(self) -> None:
        await self._close_session_for_current_loop("close")
