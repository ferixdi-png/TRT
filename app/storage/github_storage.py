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
import math
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable, Tuple

import aiohttp

from app.storage.base import BaseStorage
from app.config_env import resolve_storage_prefix

logger = logging.getLogger(__name__)

_request_cache: ContextVar[Optional[Dict[str, Tuple[Dict[str, Any], Optional[str]]]]] = ContextVar(
    "github_storage_request_cache",
    default=None,
)


class GitHubConflictError(RuntimeError):
    """Raised when GitHub Contents API returns a 409 conflict."""


@dataclass(frozen=True)
class GitHubConfig:
    storage_repo: str
    storage_branch: str
    code_repo: str
    code_branch: str
    token: str
    committer_name: str
    committer_email: str
    storage_prefix: str
    legacy_storage_prefix: Optional[str]
    bot_instance_id: str
    timeout_seconds: float
    max_parallel: int
    max_retries: int
    backoff_base: float


class GitHubStorage(BaseStorage):
    """JSON storage implementation backed by GitHub Contents API."""

    def __init__(self):
        self.config = self._load_config()
        self._semaphore = asyncio.Semaphore(self.config.max_parallel)
        self._implicit_dirs_logged = False
        self._sessions: Dict[int, aiohttp.ClientSession] = {}
        self._session_loops: Dict[int, asyncio.AbstractEventLoop] = {}
        self._sessions_lock = threading.Lock()
        self._stub_enabled = os.getenv("GITHUB_STORAGE_STUB", "0") in ("1", "true", "yes")
        self._stub_store: Dict[str, Tuple[Dict[str, Any], Optional[str]]] = {}
        self._storage_branch_checked = False
        self._storage_branch_lock = asyncio.Lock()
        self._legacy_prefix = self.config.legacy_storage_prefix
        self._legacy_warning_logged = False
        self._read_cache: Dict[str, "GitHubStorage._ReadCacheEntry"] = {}
        self._read_cache_ttl = float(os.getenv("GITHUB_READ_CACHE_TTL", "3"))
        self._read_inflight: Dict[int, Dict[str, asyncio.Future]] = {}
        self._read_inflight_lock = threading.Lock()
        self._write_locks_by_loop: Dict[int, Dict[str, asyncio.Lock]] = {}
        self._write_locks_lock = threading.Lock()

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

        logger.info(
            "[STORAGE] mode=github instance=%s prefix=%s repo=%s branch=%s parallel=%s retries=%s timeout=%ss",
            self.config.bot_instance_id,
            self.config.storage_prefix,
            self.config.storage_repo,
            self.config.storage_branch,
            self.config.max_parallel,
            self.config.max_retries,
            self.config.timeout_seconds,
        )

    def _load_config(self) -> GitHubConfig:
        code_repo = os.getenv("GITHUB_REPO", "").strip()
        code_branch = os.getenv("GITHUB_BRANCH", "main").strip()
        storage_branch = os.getenv("STORAGE_BRANCH", os.getenv("STORAGE_GITHUB_BRANCH", "storage")).strip()
        storage_repo = os.getenv("STORAGE_GITHUB_REPO", code_repo).strip()
        token = os.getenv("GITHUB_TOKEN", "").strip()
        committer_name = os.getenv("GITHUB_COMMITTER_NAME", "TRT Bot").strip()
        committer_email = os.getenv("GITHUB_COMMITTER_EMAIL", "bot@example.com").strip()
        raw_storage_prefix = os.getenv("STORAGE_PREFIX", "").strip()
        bot_instance_id = os.getenv("BOT_INSTANCE_ID", "").strip()
        prefix_resolution = resolve_storage_prefix(raw_storage_prefix, bot_instance_id)
        timeout_seconds = float(os.getenv("GITHUB_TIMEOUT_SECONDS", "20"))
        max_parallel = int(os.getenv("GITHUB_MAX_PARALLEL", "4"))
        max_retries = int(os.getenv("GITHUB_WRITE_RETRIES", "5"))
        backoff_base = float(os.getenv("GITHUB_BACKOFF_BASE", "0.5"))

        missing = []
        if not code_repo:
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
        if storage_repo == code_repo and storage_branch == code_branch:
            raise ValueError(
                "[STORAGE][GITHUB] storage_branch_must_differ_from_code_branch"
            )

        return GitHubConfig(
            storage_repo=storage_repo,
            storage_branch=storage_branch,
            code_repo=code_repo,
            code_branch=code_branch,
            token=token,
            committer_name=committer_name,
            committer_email=committer_email,
            storage_prefix=prefix_resolution.effective_prefix,
            legacy_storage_prefix=prefix_resolution.legacy_prefix,
            bot_instance_id=bot_instance_id,
            timeout_seconds=timeout_seconds,
            max_parallel=max_parallel,
            max_retries=max_retries,
            backoff_base=backoff_base,
        )

    @dataclass(frozen=True)
    class _ResponsePayload:
        status: int
        headers: Dict[str, str]
        text: str

    @dataclass(frozen=True)
    class _ReadCacheEntry:
        data: Dict[str, Any]
        sha: Optional[str]
        fetched_at: float

    def _loop_id(self, loop: asyncio.AbstractEventLoop) -> int:
        return id(loop)

    async def _close_session(self, reason: str = "close") -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is None:
            with self._sessions_lock:
                self._sessions.clear()
                self._session_loops.clear()
            logger.info("[GITHUB] session_detached=true reason=%s", reason)
            return

        loop_id = self._loop_id(loop)
        session = None
        with self._sessions_lock:
            session = self._sessions.pop(loop_id, None)
            self._session_loops.pop(loop_id, None)
        if session and not session.closed:
            await session.close()
            logger.info("[GITHUB] session_closed=true reason=%s loop_id=%s", reason, loop_id)

    async def _close_all_sessions(self, reason: str = "close") -> None:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        with self._sessions_lock:
            sessions = list(self._sessions.items())
            loops = dict(self._session_loops)
            self._sessions.clear()
            self._session_loops.clear()

        for loop_id, session in sessions:
            loop = loops.get(loop_id)
            if session.closed:
                continue
            if current_loop and loop is current_loop:
                await session.close()
                logger.info("[GITHUB] session_closed=true reason=%s loop_id=%s", reason, loop_id)
                continue
            if loop and loop.is_running() and not loop.is_closed():
                self._schedule_session_close(loop, session, reason)
                logger.info(
                    "[GITHUB] session_close_scheduled=true reason=%s loop_id=%s",
                    reason,
                    loop_id,
                )
                continue
            logger.info("[GITHUB] session_detached=true reason=%s loop_id=%s", reason, loop_id)

    def _schedule_session_close(
        self,
        loop: asyncio.AbstractEventLoop,
        session: aiohttp.ClientSession,
        reason: str,
    ) -> None:
        def _closer() -> None:
            async def _close() -> None:
                if not session.closed:
                    await session.close()
                    logger.info("[GITHUB] session_closed=true reason=%s loop_id=%s", reason, id(loop))

            asyncio.create_task(_close())

        try:
            loop.call_soon_threadsafe(_closer)
        except RuntimeError:
            logger.info("[GITHUB] session_detached=true reason=%s loop_id=%s", reason, id(loop))

    async def _get_session(self) -> aiohttp.ClientSession:
        loop = asyncio.get_running_loop()
        loop_id = self._loop_id(loop)
        session = None
        with self._sessions_lock:
            session = self._sessions.get(loop_id)
            if session and session.closed:
                self._sessions.pop(loop_id, None)
                self._session_loops.pop(loop_id, None)
                session = None
        if session is None:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            headers = {
                "Accept": "application/vnd.github+json",
                "Authorization": f"token {self.config.token}",
                "User-Agent": "TRT-GitHubStorage",
            }
            session = aiohttp.ClientSession(timeout=timeout, headers=headers)
            with self._sessions_lock:
                self._sessions[loop_id] = session
                self._session_loops[loop_id] = loop
            logger.info("GITHUB_SESSION_CREATED loop_id=%s", loop_id)
        return session

    async def _reset_session_for_loop(self, reason: str) -> None:
        loop = asyncio.get_running_loop()
        loop_id = self._loop_id(loop)
        session = None
        with self._sessions_lock:
            session = self._sessions.pop(loop_id, None)
            self._session_loops.pop(loop_id, None)
        if session and not session.closed:
            await session.close()
        logger.warning("GITHUB_SESSION_RESET reason=%s loop_id=%s", reason, loop_id)

    def _get_inflight_map(self, loop_id: int) -> Dict[str, asyncio.Future]:
        with self._read_inflight_lock:
            return self._read_inflight.setdefault(loop_id, {})

    def _get_write_lock(self, filename: str) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        loop_id = self._loop_id(loop)
        with self._write_locks_lock:
            loop_locks = self._write_locks_by_loop.setdefault(loop_id, {})
            lock = loop_locks.get(filename)
            if lock is None:
                lock = asyncio.Lock()
                loop_locks[filename] = lock
            return lock

    def _get_read_cache(self, filename: str) -> Optional["GitHubStorage._ReadCacheEntry"]:
        entry = self._read_cache.get(filename)
        if not entry:
            return None
        age = time.monotonic() - entry.fetched_at
        if age <= self._read_cache_ttl:
            return entry
        return None

    def _set_read_cache(self, filename: str, data: Dict[str, Any], sha: Optional[str]) -> None:
        self._read_cache[filename] = self._ReadCacheEntry(
            data=data,
            sha=sha,
            fetched_at=time.monotonic(),
        )

    async def _ensure_storage_branch_exists(self) -> None:
        if self._stub_enabled:
            return
        if self._storage_branch_checked:
            return
        async with self._storage_branch_lock:
            if self._storage_branch_checked:
                return
            storage_branch = self.config.storage_branch
            storage_repo = self.config.storage_repo
            code_branch = self.config.code_branch
            code_repo = self.config.code_repo
            if storage_branch == code_branch and storage_repo == code_repo:
                self._storage_branch_checked = True
                return
            ref_url = self._git_url(f"ref/heads/{storage_branch}")
            response = await self._request_with_retry(
                "GET",
                ref_url,
                op="branch_check",
                path=storage_branch,
                ok_statuses=(200, 404),
            )
            if response.status == 200:
                self._storage_branch_checked = True
                return
            base_branch = code_branch
            if storage_repo != code_repo:
                base_branch = await self._get_default_branch() or code_branch
            base_ref_url = self._git_url(f"ref/heads/{base_branch}")
            base_response = await self._request_with_retry(
                "GET",
                base_ref_url,
                op="branch_base",
                path=base_branch,
                ok_statuses=(200,),
            )
            base_payload = self._parse_json(base_response.text)
            base_sha = base_payload.get("object", {}).get("sha")
            if not base_sha:
                logger.error(
                    "[GITHUB] op=branch_base path=%s ok=false error=no_sha",
                    base_branch,
                )
                return
            create_url = self._git_url("refs")
            create_payload = {"ref": f"refs/heads/{storage_branch}", "sha": base_sha}
            create_response = await self._request_with_retry(
                "POST",
                create_url,
                op="branch_create",
                path=storage_branch,
                ok_statuses=(201, 422),
                json=create_payload,
            )
            if create_response.status == 201:
                logger.info("[GITHUB] branch_created=true branch=%s", storage_branch)
            self._storage_branch_checked = True

    async def _request_raw(self, method: str, url: str, **kwargs: Any) -> _ResponsePayload:
        async with self._semaphore:
            session = await self._get_session()
            response = await session.request(method, url, **kwargs)
            try:
                text = await response.text()
                return self._ResponsePayload(
                    status=response.status,
                    headers=dict(response.headers),
                    text=text,
                )
            finally:
                release = getattr(response, "release", None)
                if callable(release):
                    result = release()
                    if asyncio.iscoroutine(result):
                        await result

    def _storage_path(self, filename: str) -> str:
        safe_name = filename.strip("/").replace("..", "")
        return f"{self.config.storage_prefix}/{safe_name}"

    def _legacy_storage_path(self, filename: str) -> Optional[str]:
        if not self._legacy_prefix:
            return None
        safe_name = filename.strip("/").replace("..", "")
        return f"{self._legacy_prefix}/{safe_name}".strip("/")

    def _contents_url(self, path: str) -> str:
        return f"https://api.github.com/repos/{self.config.storage_repo}/contents/{path}"

    def _git_url(self, path: str) -> str:
        return f"https://api.github.com/repos/{self.config.storage_repo}/git/{path.lstrip('/')}"

    def _repo_url(self) -> str:
        return f"https://api.github.com/repos/{self.config.storage_repo}"

    async def _get_default_branch(self) -> Optional[str]:
        response = await self._request_with_retry(
            "GET",
            self._repo_url(),
            op="repo_info",
            path=self.config.storage_repo,
            ok_statuses=(200,),
        )
        payload = self._parse_json(response.text)
        return payload.get("default_branch")

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        op: str,
        path: str,
        ok_statuses: Tuple[int, ...],
        **kwargs: Any,
    ) -> _ResponsePayload:
        last_response: Optional[GitHubStorage._ResponsePayload] = None
        for attempt in range(1, self.config.max_retries + 1):
            start_ts = time.monotonic()
            try:
                response = await self._request_raw(method, url, **kwargs)
            except RuntimeError as exc:
                if self._should_reset_session(exc):
                    await self._reset_session_for_loop(reason=str(exc))
                    await self._backoff(attempt)
                    continue
                raise
            last_response = response
            status = response.status
            ok = status in ok_statuses
            latency_ms = int((time.monotonic() - start_ts) * 1000)
            logger.info(
                "[GITHUB] op=%s path=%s ok=%s status=%s attempt=%s latency_ms=%s",
                op,
                path,
                str(ok).lower(),
                status,
                attempt,
                latency_ms,
            )
            if ok:
                return response

            if self._should_retry(status, response.headers):
                await self._backoff(attempt, response.headers)
                continue

            return response

        if last_response is None:
            raise RuntimeError("GitHub request failed without response")
        return last_response

    def _should_reset_session(self, exc: RuntimeError) -> bool:
        message = str(exc).lower()
        return (
            "different loop" in message
            or "attached to a different loop" in message
            or "session is closed" in message
            or "event loop is closed" in message
        )

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

    async def _read_json(
        self,
        filename: str,
        *,
        force_refresh: bool = False,
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        await self._ensure_storage_branch_exists()
        cache = self._get_request_cache()
        if not force_refresh:
            cached = cache.get(filename)
            if cached is not None:
                logger.info(
                    "STORAGE_READ_OK path=%s source=request_cache",
                    self._storage_path(filename),
                )
                return cached
            read_cache = self._get_read_cache(filename)
            if read_cache is not None:
                logger.info(
                    "STORAGE_READ_OK path=%s source=read_cache",
                    self._storage_path(filename),
                )
                cache[filename] = (read_cache.data, read_cache.sha)
                return read_cache.data, read_cache.sha

        loop = asyncio.get_running_loop()
        loop_id = self._loop_id(loop)
        inflight = self._get_inflight_map(loop_id)
        future = inflight.get(filename)
        if future is not None:
            logger.info(
                "STORAGE_SINGLEFLIGHT_HIT path=%s loop_id=%s",
                self._storage_path(filename),
                loop_id,
            )
            data, sha = await future
            cache[filename] = (data, sha)
            return data, sha

        future = loop.create_future()
        inflight[filename] = future
        try:
            data, sha, status = await self._fetch_json_payload(filename)
            if status == 404:
                data, sha = await self._ensure_default_file(filename)

            cache[filename] = (data, sha)
            self._set_read_cache(filename, data, sha)
            future.set_result((data, sha))
            logger.info(
                "STORAGE_READ_OK path=%s source=origin status=%s",
                self._storage_path(filename),
                status,
            )
            return data, sha
        except Exception as exc:
            if not future.done():
                future.set_exception(exc)
            logger.warning(
                "STORAGE_READ_FAIL path=%s error_class=%s",
                self._storage_path(filename),
                exc.__class__.__name__,
            )
            raise
        finally:
            inflight.pop(filename, None)

    async def _write_json(self, filename: str, data: Dict[str, Any], sha: Optional[str]) -> Optional[str]:
        await self._ensure_storage_branch_exists()
        path = self._storage_path(filename)
        url = self._contents_url(path)
        payload_json = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        logger.info(
            "[GITHUB] write_attempt repo=%s branch=%s path=%s size_bytes=%s",
            self.config.storage_repo,
            self.config.storage_branch,
            path,
            len(payload_json.encode("utf-8")),
        )
        if self._stub_enabled:
            sha = f"stub-{int(time.time() * 1000)}"
            self._stub_store[path] = (data, sha)
            logger.info("[GITHUB] write_ok path=%s status=stub", path)
            return sha
        content = base64.b64encode(payload_json.encode("utf-8")).decode("utf-8")
        payload = {
            "message": f"storage update {path}",
            "content": content,
            "branch": self.config.storage_branch,
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
            logger.info(
                "[GITHUB] write_ok path=%s status=%s",
                path,
                response.status,
            )
            payload = self._parse_json(response.text)
            new_sha = payload.get("content", {}).get("sha") or payload.get("sha")
            self._set_read_cache(filename, data, new_sha or sha)
            return new_sha
        if response.status == 409:
            raise GitHubConflictError(f"GitHub write conflict for {path}")
        logger.error(
            "[GITHUB] op=write path=%s ok=false status=%s error_class=GitHubWriteError",
            path,
            response.status,
        )
        raise RuntimeError(f"GitHub write failed {response.status}: {response.text}")

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
        lock = self._get_write_lock(filename)
        async with lock:
            last_error: Optional[Exception] = None
            for attempt in range(1, self.config.max_retries + 1):
                data, sha = await self._read_json(filename, force_refresh=True)
                updated = update_fn(dict(data))
                merged = self._merge_json(data, updated)
                try:
                    new_sha = await self._write_json(filename, merged, sha)
                    self._set_request_cache(filename, merged, new_sha or sha)
                    self._set_read_cache(filename, merged, new_sha or sha)
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

    def _parse_json(self, payload: str) -> Dict[str, Any]:
        if not payload:
            return {}
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {}

    def _get_request_cache(self) -> Dict[str, Tuple[Dict[str, Any], Optional[str]]]:
        cache = _request_cache.get()
        if cache is None:
            cache = {}
            _request_cache.set(cache)
        return cache

    def _set_request_cache(self, filename: str, data: Dict[str, Any], sha: Optional[str]) -> None:
        cache = self._get_request_cache()
        cache[filename] = (data, sha)

    def _default_payload_for(self, filename: str) -> Dict[str, Any]:
        return {}

    async def _fetch_json_payload(self, filename: str) -> Tuple[Dict[str, Any], Optional[str], int]:
        path = self._storage_path(filename)
        if self._stub_enabled:
            payload = self._stub_store.get(path)
            if payload is None:
                legacy_path = self._legacy_storage_path(filename)
                if legacy_path:
                    legacy_payload = self._stub_store.get(legacy_path)
                    if legacy_payload is not None:
                        if not self._legacy_warning_logged:
                            logger.warning(
                                "[STORAGE] legacy_path_used=true path=%s new_path=%s",
                                legacy_path,
                                path,
                            )
                            self._legacy_warning_logged = True
                        data, sha = legacy_payload
                        return data, sha, 200
                return {}, None, 404
            data, sha = payload
            return data, sha, 200
        url = self._contents_url(path)
        response = await self._request_with_retry(
            "GET",
            url,
            op="read",
            path=path,
            ok_statuses=(200, 404),
            params={"ref": self.config.storage_branch},
        )
        if response.status == 404:
            legacy_path = self._legacy_storage_path(filename)
            if legacy_path:
                legacy_url = self._contents_url(legacy_path)
                legacy_response = await self._request_with_retry(
                    "GET",
                    legacy_url,
                    op="read",
                    path=legacy_path,
                    ok_statuses=(200, 404),
                    params={"ref": self.config.storage_branch},
                )
                if legacy_response.status == 200:
                    if not self._legacy_warning_logged:
                        logger.warning(
                            "[STORAGE] legacy_path_used=true path=%s new_path=%s",
                            legacy_path,
                            path,
                        )
                        self._legacy_warning_logged = True
                    payload = self._parse_json(legacy_response.text)
                    content = payload.get("content", "")
                    sha = payload.get("sha")
                    decoded = base64.b64decode(content).decode("utf-8") if content else "{}"
                    try:
                        data = json.loads(decoded) if decoded.strip() else {}
                    except json.JSONDecodeError:
                        logger.error("[GITHUB] read_invalid_json path=%s", legacy_path)
                        data = {}
                    return data, sha, 200
            return {}, None, 404
        if response.status != 200:
            logger.error(
                "[GITHUB] op=read path=%s ok=false status=%s error_class=GitHubReadError",
                path,
                response.status,
            )
            raise RuntimeError(f"GitHub read failed {response.status}: {response.text}")
        payload = self._parse_json(response.text)
        content = payload.get("content", "")
        sha = payload.get("sha")
        decoded = base64.b64decode(content).decode("utf-8") if content else "{}"
        try:
            data = json.loads(decoded) if decoded.strip() else {}
        except json.JSONDecodeError:
            logger.error("[GITHUB] read_invalid_json path=%s", path)
            data = {}
        return data, sha, 200

    async def _ensure_default_file(self, filename: str) -> Tuple[Dict[str, Any], Optional[str]]:
        default_data = self._default_payload_for(filename)
        path = self._storage_path(filename)
        try:
            new_sha = await self._write_json(filename, default_data, None)
            logger.info("[GITHUB] default_created=true path=%s", path)
            self._set_request_cache(filename, default_data, new_sha)
            self._set_read_cache(filename, default_data, new_sha)
            return default_data, new_sha
        except GitHubConflictError:
            logger.info("[GITHUB] default_create_conflict=true path=%s", path)
        data, sha, _ = await self._fetch_json_payload(filename)
        return data, sha

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

    async def close(self) -> None:
        """Close shared resources (aiohttp session)."""
        await self._close_all_sessions(reason="close")

    def test_connection(self) -> bool:
        """Sync connection test for GitHub storage."""
        async def _check() -> bool:
            if self._stub_enabled:
                return True
            path = self._storage_path(self.balances_file)
            url = self._contents_url(path)
            timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            headers = {
                "Accept": "application/vnd.github+json",
                "Authorization": f"token {self.config.token}",
                "User-Agent": "TRT-GitHubStorage",
            }
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url, params={"ref": self.config.storage_branch}) as response:
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
        return self._coerce_balance(data.get(str(user_id), 0.0))

    async def set_user_balance(self, user_id: int, amount: float) -> None:
        safe_amount = self._coerce_balance(amount)

        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            data[str(user_id)] = safe_amount
            return data

        await self._update_json(self.balances_file, updater)

    async def add_user_balance(self, user_id: int, amount: float) -> float:
        safe_amount = self._coerce_balance(amount)

        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            current = self._coerce_balance(data.get(str(user_id), 0.0))
            data[str(user_id)] = self._coerce_balance(current + safe_amount)
            return data

        data = await self._update_json(self.balances_file, updater)
        return self._coerce_balance(data.get(str(user_id), 0.0))

    async def subtract_user_balance(self, user_id: int, amount: float) -> bool:
        success = False
        safe_amount = self._coerce_balance(amount)

        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            nonlocal success
            current = self._coerce_balance(data.get(str(user_id), 0.0))
            if safe_amount <= 0:
                return data
            if current >= safe_amount:
                data[str(user_id)] = self._coerce_balance(current - safe_amount)
                success = True
            return data

        await self._update_json(self.balances_file, updater)
        return success

    @staticmethod
    def _coerce_balance(value: Any) -> float:
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return 0.0
        if not math.isfinite(amount) or amount < 0:
            return 0.0
        return amount

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
        from app.pricing.free_policy import get_free_daily_limit

        free_per_day = get_free_daily_limit()
        used = await self.get_user_free_generations_today(user_id)
        return max(0, free_per_day - used)

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

    async def get_hourly_free_usage(self, user_id: int) -> Dict[str, Any]:
        data, _ = await self._read_json(self.hourly_free_usage_file)
        return data.get(str(user_id), {})

    async def set_hourly_free_usage(self, user_id: int, window_start_iso: str, used_count: int) -> None:
        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            data[str(user_id)] = {
                "window_start_iso": window_start_iso,
                "used_count": int(used_count),
            }
            return data

        await self._update_json(self.hourly_free_usage_file, updater)

    async def get_referral_free_bank(self, user_id: int) -> int:
        data, _ = await self._read_json(self.referral_free_bank_file)
        return int(data.get(str(user_id), 0))

    async def set_referral_free_bank(self, user_id: int, remaining_count: int) -> None:
        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            data[str(user_id)] = int(max(0, remaining_count))
            return data

        await self._update_json(self.referral_free_bank_file, updater)

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
        from app.services.history_service import append_event

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
            event_id=history_id,
        )
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

    # ==================== GENERIC JSON FILES ====================

    async def read_json_file(self, filename: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data, _ = await self._read_json(filename)
        if data:
            return data
        return default or {}

    async def write_json_file(self, filename: str, data: Dict[str, Any]) -> None:
        lock = self._get_write_lock(filename)
        async with lock:
            last_error: Optional[Exception] = None
            for attempt in range(1, self.config.max_retries + 1):
                _, sha = await self._read_json(filename, force_refresh=True)
                try:
                    new_sha = await self._write_json(filename, data, sha)
                    self._set_request_cache(filename, data, new_sha or sha)
                    self._set_read_cache(filename, data, new_sha or sha)
                    if attempt > 1:
                        logger.info(
                            "[GITHUB] write_conflict resolved=true attempts=%s path=%s",
                            attempt,
                            self._storage_path(filename),
                        )
                    return
                except GitHubConflictError as exc:
                    last_error = exc
                    logger.warning(
                        "[GITHUB] write_retry attempt=%s path=%s reason=conflict",
                        attempt,
                        self._storage_path(filename),
                    )
                    await self._backoff(attempt)
            raise RuntimeError("Exceeded GitHub write retries") from last_error

    async def update_json_file(
        self,
        filename: str,
        update_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> Dict[str, Any]:
        return await self._update_json(filename, update_fn)
