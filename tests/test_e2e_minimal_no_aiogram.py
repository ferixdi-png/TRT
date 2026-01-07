import asyncio
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

    async def fake_generate(self, model_id, user_inputs, progress_callback=None, timeout=300, task_id_callback=None):
        captured["model_id"] = model_id
        captured["user_inputs"] = dict(user_inputs)
        if task_id_callback:
            if asyncio.iscoroutinefunction(task_id_callback):
                await task_id_callback("stub-task")
            else:
                maybe_coro = task_id_callback("stub-task")
                if asyncio.iscoroutine(maybe_coro):
                    await maybe_coro
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


@pytest.mark.asyncio
async def test_confirm_requires_media_input(monkeypatch):
    from bot.handlers import flow

    model = {
        "model_id": "media-model",
        "display_name": "Media Model",
        "input_schema": {
            "type": "object",
            "required": ["image_url"],
            "properties": {"image_url": {"type": "string", "format": "uri"}},
        },
    }

    monkeypatch.setattr(flow, "_get_models_list", lambda: [model])
async def test_confirm_handler_e2e_google_imagen4(monkeypatch):
    """Mini e2e for google/imagen4 to keep free-tier confirm path covered."""

    from bot.handlers import flow

    model = {
        "model_id": "google/imagen4",
        "display_name": "Imagen 4",
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
        return {"success": True, "result_urls": ["https://example.com/out2.png"], "task_id": "t2"}

    monkeypatch.setattr(flow, "generate_with_payment", fake_generate_with_payment)

    flow_ctx = {
        "model_id": "google/imagen4",
        "required_fields": ["prompt"],
        "optional_fields": [],
        "properties": model["properties"],
        "collected": {"prompt": "реалистичное фото"},
        "index": 0,
        "collecting_optional": False,
    }

    message = FakeMessage()
    callback = FakeCallback(message)
    state = FakeState({"flow_ctx": flow_ctx})

    await flow.confirm_cb(callback, state)

    assert any("https://example.com/out2.png" in msg for msg in message.messages)
    assert callback.answered is True


@pytest.mark.asyncio
async def test_confirm_handler_e2e_recraft(monkeypatch):
    """Mini e2e for recraft/remove-background confirm path (free tier)."""

    from bot.handlers import flow

    model = {
        "model_id": "recraft/remove-background",
        "display_name": "Remove BG",
        "required_inputs": ["image"],
        "properties": {"image": {"type": "string"}},
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
        return {"success": True, "result_urls": ["https://example.com/out3.png"], "task_id": "t3"}

    monkeypatch.setattr(flow, "generate_with_payment", fake_generate_with_payment)

    flow_ctx = {
        "model_id": "recraft/remove-background",
        "required_fields": ["image"],
        "optional_fields": [],
        "properties": model["properties"],
        "collected": {"image": "https://example.com/in.png"},
        "index": 0,
        "collecting_optional": False,
    }

    message = FakeMessage()
    callback = FakeCallback(message)
    state = FakeState({"flow_ctx": flow_ctx})

    await flow.confirm_cb(callback, state)

    assert any("https://example.com/out3.png" in msg for msg in message.messages)
    assert callback.answered is True


@pytest.mark.asyncio
async def test_confirm_handler_e2e_google_imagen4_fast(monkeypatch):
    """Mini e2e for google/imagen4-fast confirm path (free tier)."""

    from bot.handlers import flow

    model = {
        "model_id": "google/imagen4-fast",
        "display_name": "Imagen 4 Fast",
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
        return {"success": True, "result_urls": ["https://example.com/out4.png"], "task_id": "t4"}

    monkeypatch.setattr(flow, "generate_with_payment", fake_generate_with_payment)

    flow_ctx = {
        "model_id": "google/imagen4-fast",
        "required_fields": ["prompt"],
        "optional_fields": [],
        "properties": model["properties"],
        "collected": {"prompt": "быстрый стиль"},
        "index": 0,
        "collecting_optional": False,
    }

    message = FakeMessage()
    callback = FakeCallback(message)
    state = FakeState({"flow_ctx": flow_ctx})

    await flow.confirm_cb(callback, state)

    assert any("https://example.com/out4.png" in msg for msg in message.messages)
    assert callback.answered is True


@pytest.mark.asyncio
async def test_confirm_handler_defaults_to_production_mode_when_env_missing(monkeypatch):
    """Ensure TEST_MODE default is False so paid flows do not skip billing."""

    from bot.handlers import flow

    # Clear TEST_MODE to use default
    monkeypatch.delenv("TEST_MODE", raising=False)

    model = {
        "model_id": "paid-model",  # simulate paid model
        "display_name": "Paid Model",
        "required_inputs": ["prompt"],
        "properties": {"prompt": {"type": "string"}},
        "pricing": {"rub_per_gen": 5.0},
    }

    monkeypatch.setattr(flow, "_get_models_list", lambda: [model])
    monkeypatch.setattr(flow, "calculate_kie_cost", lambda *_, **__: 5.0)
    monkeypatch.setattr(flow, "calculate_user_price", lambda amount: amount)
    monkeypatch.setattr(flow, "idem_try_start", lambda *_, **__: (True, None))
    monkeypatch.setattr(flow, "acquire_job_lock", lambda *_, **__: (True, None))
    monkeypatch.setattr(flow, "release_job_lock", lambda *_, **__: None)

    class DummyChargeManager:
        async def get_user_balance(self, user_id):
            return 10.0

    monkeypatch.setattr(flow, "get_charge_manager", lambda: DummyChargeManager())

    payment_args = {}

    async def fake_generate_with_payment(**kwargs):
        payment_args.update(kwargs)
        assert kwargs["amount"] > 0  # should respect paid flow when TEST_MODE is unset
        return {"success": True, "result_urls": ["https://example.com/paid.png"], "task_id": "t-paid"}

    monkeypatch.setattr(flow, "generate_with_payment", fake_generate_with_payment)

    flow_ctx = {
        "model_id": "paid-model",
        "required_fields": ["prompt"],
        "optional_fields": [],
        "properties": model["properties"],
        "collected": {"prompt": "оплачиваемая генерация"},
        "index": 0,
        "collecting_optional": False,
    }

    message = FakeMessage()
    callback = FakeCallback(message)
    state = FakeState({"flow_ctx": flow_ctx})

    await flow.confirm_cb(callback, state)

    assert payment_args.get("amount") == 5.0
    assert any("https://example.com/paid.png" in msg for msg in message.messages)
    assert callback.answered is True
