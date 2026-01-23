import pytest

from app.storage.hybrid_storage import HybridStorage
from app.storage.json_storage import JsonStorage


class DummyPrimaryStorage:
    def __init__(self):
        self.write_calls = 0

    async def read_json_file(self, filename: str, default=None):
        return default or {}

    async def write_json_file(self, filename: str, data):
        self.write_calls += 1

    async def get_user_language(self, user_id: int) -> str:
        return "ru"

    async def set_user_language(self, user_id: int, language: str) -> None:
        return None

    async def has_claimed_gift(self, user_id: int) -> bool:
        return False

    async def set_gift_claimed(self, user_id: int) -> None:
        return None

    async def get_user_balance(self, user_id: int) -> float:
        return 0.0

    async def set_user_balance(self, user_id: int, amount: float) -> None:
        return None

    async def add_user_balance(self, user_id: int, amount: float) -> float:
        return amount

    async def subtract_user_balance(self, user_id: int, amount: float) -> bool:
        return True

    async def get_user_free_generations_today(self, user_id: int) -> int:
        return 0

    async def get_user_free_generations_remaining(self, user_id: int) -> int:
        return 0

    async def increment_free_generations(self, user_id: int) -> None:
        return None

    async def get_hourly_free_usage(self, user_id: int):
        return {}

    async def set_hourly_free_usage(self, user_id: int, window_start_iso: str, used_count: int) -> None:
        return None

    async def get_referral_free_bank(self, user_id: int) -> int:
        return 0

    async def set_referral_free_bank(self, user_id: int, remaining_count: int) -> None:
        return None

    async def get_admin_limit(self, user_id: int) -> float:
        return 0.0

    async def get_admin_spent(self, user_id: int) -> float:
        return 0.0

    async def get_admin_remaining(self, user_id: int) -> float:
        return 0.0

    async def add_generation_job(self, *args, **kwargs):
        return "job"

    async def update_job_status(self, *args, **kwargs):
        return None

    async def get_job(self, job_id: str):
        return None

    async def list_jobs(self, *args, **kwargs):
        return []

    async def add_generation_to_history(self, *args, **kwargs):
        return "gen"

    async def get_user_generations_history(self, *args, **kwargs):
        return []

    def test_connection(self) -> bool:
        return True

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_storage_no_git_commits(tmp_path):
    runtime_storage = JsonStorage(str(tmp_path), bot_instance_id="test-instance")
    primary_storage = DummyPrimaryStorage()
    hybrid = HybridStorage(
        primary_storage,
        runtime_storage,
        runtime_files={
            "user_balances.json",
            "daily_free_generations.json",
            "admin_limits.json",
            "hourly_free_usage.json",
            "referral_free_bank.json",
        },
    )

    await hybrid.write_json_file("user_balances.json", {"1": 10})

    assert primary_storage.write_calls == 0
