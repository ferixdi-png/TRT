"""GitHub-backed storage for balances and purchases."""
from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class GitHubStorage:
    def __init__(self) -> None:
        self.repo = os.getenv("GITHUB_REPO", "")
        self.token = os.getenv("GITHUB_TOKEN", "")
        self.branch = os.getenv("GITHUB_BRANCH", "main")
        prefix = os.getenv("STORAGE_PREFIX", "storage")
        self.path = f"{prefix}/users.json"
        self.committer_name = os.getenv("GITHUB_COMMITTER_NAME", "TRT Storage Bot")
        self.committer_email = os.getenv("GITHUB_COMMITTER_EMAIL", "trt-storage-bot@users.noreply.github.com")
        if not self.repo or not self.token:
            raise RuntimeError("GITHUB_REPO and GITHUB_TOKEN are required for GitHubStorage")

    async def _request(self, method: str, url: str, payload: dict | None = None) -> dict:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers, json=payload) as resp:
                data = await resp.json()
                if resp.status >= 400:
                    raise RuntimeError(f"GitHub API error {resp.status}: {data}")
                return data

    async def _get_file(self) -> tuple[dict, str | None]:
        url = f"https://api.github.com/repos/{self.repo}/contents/{self.path}"
        params = f"?ref={self.branch}"
        try:
            data = await self._request("GET", url + params)
            content = base64.b64decode(data.get("content", "")).decode("utf-8")
            payload = json.loads(content) if content else {"users": {}}
            return payload, data.get("sha")
        except RuntimeError as exc:
            if "404" in str(exc):
                return {"users": {}}, None
            raise

    async def _save_file(self, payload: dict, sha: str | None) -> None:
        url = f"https://api.github.com/repos/{self.repo}/contents/{self.path}"
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        body = {
            "message": f"update storage {datetime.now(timezone.utc).isoformat()}",
            "content": base64.b64encode(content).decode("utf-8"),
            "branch": self.branch,
            "committer": {
                "name": self.committer_name,
                "email": self.committer_email,
            },
        }
        if sha:
            body["sha"] = sha
        await self._request("PUT", url, body)

    async def _update_user(self, user_id: int, updater) -> dict:
        payload, sha = await self._get_file()
        users = payload.setdefault("users", {})
        record = users.setdefault(str(user_id), {"balance": 0, "purchases": [], "history": []})
        updater(record)
        await self._save_file(payload, sha)
        return record

    async def get_user(self, user_id: int) -> dict:
        payload, _ = await self._get_file()
        return payload.setdefault("users", {}).setdefault(str(user_id), {"balance": 0, "purchases": [], "history": []})

    async def get_user_balance(self, user_id: int) -> int:
        record = await self.get_user(user_id)
        return int(record.get("balance", 0))

    async def set_user_balance(self, user_id: int, balance: int) -> None:
        await self._update_user(user_id, lambda rec: rec.__setitem__("balance", int(balance)))

    async def add_purchase(self, user_id: int, item: dict) -> None:
        await self._update_user(user_id, lambda rec: rec.setdefault("purchases", []).append(item))

    async def add_history(self, user_id: int, entry: dict) -> None:
        await self._update_user(user_id, lambda rec: rec.setdefault("history", []).append(entry))
