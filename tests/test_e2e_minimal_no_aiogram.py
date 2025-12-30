import os
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_generate_with_payment_minimal(monkeypatch):
    os.environ.setdefault("KIE_API_KEY", "test-key")

    from app.payments import integration

    # Force free-model path to avoid billing/database dependencies
    monkeypatch.setattr(integration, "is_free_model", lambda model_id: True)
    monkeypatch.setattr(integration, "get_charge_manager", lambda: SimpleNamespace(db_service=None))

    captured = {}

    async def fake_generate(self, model_id, user_inputs, progress_callback=None, timeout=300):
        captured["model_id"] = model_id
        captured["user_inputs"] = dict(user_inputs)
        return {"success": True, "result_urls": ["https://example.com/out.png"], "task_id": "stub-task"}

    monkeypatch.setattr(integration.KieGenerator, "generate", fake_generate)

    result = await integration.generate_with_payment(
        model_id="z-image",
        user_inputs={"prompt": "hi"},
        user_id=123,
        amount=0.0,
        reserve_balance=True,
    )

    assert result["success"] is True
    assert result.get("output_url") == "https://example.com/out.png"
    assert result.get("payment_status") == "free_tier"
    assert captured.get("model_id") == "z-image"
    assert captured.get("user_inputs", {}).get("prompt") == "hi"


class FakeMessage:
    def __init__(self) -> None:
        self.message_id = 1
        self.messages = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        text = "".join(str(arg) for arg in args if isinstance(arg, str))
        self.messages.append(text)
        return self

    async def edit_text(self, *args, **kwargs):
        text = "".join(str(arg) for arg in args if isinstance(arg, str))
        self.edits.append(text)
        return self


class FakeCallback:
    def __init__(self, message):
        self.message = message
        self.data = "confirm"
        self.from_user = SimpleNamespace(id=123)
        self.answered = False

    async def answer(self, *args, **kwargs):
        self.answered = True


class FakeState:
    def __init__(self, data):
        self._data = data
        self.state = None

    async def get_data(self):
        return self._data

    async def set_state(self, state):
        self.state = state

    async def clear(self):
        self._data = {}


@pytest.mark.asyncio
async def test_confirm_handler_e2e_smoke(monkeypatch):
    """Lightweight e2e: wizard confirmation -> generator -> success message."""

    from bot.handlers import flow

    model = {
        "model_id": "z-image",
        "display_name": "Z Image",
        "required_inputs": ["prompt"],
        "properties": {"prompt": {"type": "string"}},
    }

    monkeypatch.setattr(flow, "_get_models_list", lambda: [model])
    monkeypatch.setattr(flow, "calculate_kie_cost", lambda *args, **kwargs: 0.0)
    monkeypatch.setattr(flow, "calculate_user_price", lambda amount: amount)
    monkeypatch.setattr(flow, "idem_try_start", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr(flow, "acquire_job_lock", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr(flow, "release_job_lock", lambda *args, **kwargs: None)
    monkeypatch.setattr(flow, "idem_finish", lambda *args, **kwargs: None)

    class DummyChargeManager:
        async def get_user_balance(self, user_id):
            return 0.0

    monkeypatch.setattr(flow, "get_charge_manager", lambda: DummyChargeManager())

    async def fake_generate_with_payment(**kwargs):
        return {"success": True, "result_urls": ["https://example.com/out.png"], "task_id": "t1"}

    monkeypatch.setattr(flow, "generate_with_payment", fake_generate_with_payment)

    flow_ctx = {
        "model_id": "z-image",
        "required_fields": ["prompt"],
        "optional_fields": [],
        "properties": model["properties"],
        "collected": {"prompt": "котик"},
        "index": 0,
        "collecting_optional": False,
    }

    message = FakeMessage()
    callback = FakeCallback(message)
    state = FakeState({"flow_ctx": flow_ctx})

    await flow.confirm_cb(callback, state)

    assert any("https://example.com/out.png" in msg for msg in message.messages)
    assert callback.answered is True
