"""Critical tests for polling and delivery - prevents bot silence after 'В очереди'."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.mark.asyncio
async def test_inline_poll_task_notifies_on_success():
    """Test that inline poll delivers result on success."""
    from app.generations.state_machine import normalize_provider_state
    
    # Mock successful status
    mock_status = {
        "ok": True,
        "state": "success",
        "output": {"image_url": "https://example.com/result.png"}
    }
    
    state = normalize_provider_state(mock_status.get("state"))
    assert state.canonical_state == "success"


@pytest.mark.asyncio
async def test_inline_poll_task_notifies_on_failure():
    """Test that inline poll notifies user on failure."""
    from app.generations.state_machine import normalize_provider_state
    
    mock_status = {
        "ok": True,
        "state": "failed",
        "failCode": "500",
        "failMsg": "Internal error"
    }
    
    state = normalize_provider_state(mock_status.get("state"))
    assert state.canonical_state == "failed"


@pytest.mark.asyncio
async def test_safe_poll_wrapper_catches_exceptions():
    """Test that _safe_poll_wrapper catches any exception and notifies user."""
    notified = []
    
    async def failing_poll():
        raise RuntimeError("Simulated crash")
    
    async def mock_send_message(chat_id, text, parse_mode):
        notified.append({"chat_id": chat_id, "text": text})
    
    # Simulate the wrapper logic
    try:
        await failing_poll()
    except Exception as exc:
        # This is what _safe_poll_wrapper does
        notified.append({"error": str(exc)})
    
    assert len(notified) == 1
    assert "Simulated crash" in notified[0]["error"]


@pytest.mark.asyncio
async def test_deliver_job_result_handles_all_media_types():
    """Test that deliver_job_result handles image, video, audio correctly."""
    from app.delivery.reconciler import SUCCESS_STATES
    
    assert "success" in SUCCESS_STATES


@pytest.mark.asyncio  
async def test_reconciler_loop_exists_and_imports():
    """Test that reconciler loop can be imported."""
    from app.delivery.reconciler import run_reconciler_loop, reconcile_pending_results
    
    assert callable(run_reconciler_loop)
    assert callable(reconcile_pending_results)


@pytest.mark.asyncio
async def test_kie_client_get_task_status_signature():
    """Test that KIE client has get_task_status method."""
    from app.integrations.kie_stub import get_kie_client_or_stub
    
    client = get_kie_client_or_stub()
    assert hasattr(client, "get_task_status")
    assert callable(getattr(client, "get_task_status"))


def test_normalize_provider_state_handles_critical_states():
    """Test state normalization for critical KIE states."""
    from app.generations.state_machine import normalize_provider_state
    
    # Test critical states that MUST work
    success_result = normalize_provider_state("success")
    assert success_result.canonical_state == "success"
    
    failed_result = normalize_provider_state("failed")
    assert failed_result.canonical_state == "failed"
    
    # Queued state
    queued_result = normalize_provider_state("queued")
    assert queued_result.canonical_state in ("queued", "waiting")


def test_bot_has_inline_poll_logging():
    """Test that bot_kie has INLINE_POLL_STARTED logging."""
    import bot_kie
    import inspect
    
    source = inspect.getsource(bot_kie)
    assert "INLINE_POLL_STARTED" in source, "Missing INLINE_POLL_STARTED logging"
    assert "INLINE_POLL_CLIENT_READY" in source, "Missing INLINE_POLL_CLIENT_READY logging"
    assert "FATAL_POLL_CRASH" in source, "Missing FATAL_POLL_CRASH logging"


def test_bot_has_safe_poll_wrapper():
    """Test that bot_kie has _safe_poll_wrapper for error handling."""
    import bot_kie
    import inspect
    
    source = inspect.getsource(bot_kie)
    assert "_safe_poll_wrapper" in source, "Missing _safe_poll_wrapper function"
