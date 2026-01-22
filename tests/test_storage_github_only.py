from app.config import Settings


def test_storage_mode_is_db_only(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_ONLY_STORAGE", "true")
    settings = Settings()
    assert settings.get_storage_mode() == "db"
    assert settings.github_only_storage is True


def test_persist_history_uses_github_storage(monkeypatch):
    import bot_kie

    class DummyStorage:
        def __init__(self):
            self.read_calls = 0
            self.write_calls = 0

        async def read_json_file(self, filename: str, default=None):
            self.read_calls += 1
            return default or {}

        async def write_json_file(self, filename: str, data):
            self.write_calls += 1
            return None

        def test_connection(self):
            return True

    dummy_storage = DummyStorage()

    monkeypatch.setattr("app.storage.factory.get_storage", lambda: dummy_storage)
    monkeypatch.setattr(bot_kie, "create_operation", None)

    generation_id = bot_kie.save_generation_to_history(
        user_id=123,
        model_id="model-id",
        model_name="Model Name",
        params={"prompt": "hello"},
        result_urls=["https://example.com/result.png"],
        task_id="task-1",
        price=0.0,
        is_free=True,
    )

    assert generation_id is not None
    assert dummy_storage.read_calls >= 1
    assert dummy_storage.write_calls >= 1
