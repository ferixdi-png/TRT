"""
Minimal harness to verify ACTIVE/PASSIVE state machine works correctly.
Tests that lock acquisition → active_state.active=True → workers process queue.
"""
import asyncio
import pytest
from unittest.mock import Mock, AsyncMock
from app.locking.active_state import ActiveState
from app.utils.update_queue import UpdateQueueManager


class FakeLockController:
    """Simulates lock controller with delayed acquisition."""
    
    def __init__(self, active_state: ActiveState, acquire_delay: float = 0.5):
        self.active_state = active_state
        self.acquire_delay = acquire_delay
        self._acquired = False
    
    async def simulate_lock_acquisition(self):
        """Simulate delayed lock acquisition (like real PostgreSQL advisory lock)."""
        await asyncio.sleep(self.acquire_delay)
        self._acquired = True
        # This is what lock_controller._set_state() should do
        self.active_state.set(True, reason="lock_acquired")
    
    def should_process_updates(self) -> bool:
        return self._acquired


@pytest.mark.asyncio
async def test_state_machine_activates_workers():
    """
    Test: Workers wait in PASSIVE, then lock acquired → ACTIVE → workers start processing.
    """
    # Setup
    active_state = ActiveState(active=False)
    lock_controller = FakeLockController(active_state, acquire_delay=0.2)
    
    # Create queue manager
    queue_manager = UpdateQueueManager(max_size=10, num_workers=2)
    
    # Mock dispatcher and bot
    mock_dp = AsyncMock()
    mock_dp.feed_update = AsyncMock()
    mock_bot = Mock()
    
    queue_manager.configure(mock_dp, mock_bot, active_state)
    
    # Start workers (they should wait in PASSIVE)
    await queue_manager.start()
    
    # Enqueue a fake update BEFORE lock acquired
    fake_update = Mock()
    fake_update.update_id = 12345
    queue_manager.enqueue(fake_update, update_id=12345)
    
    # Verify queue has item but workers haven't processed yet (PASSIVE)
    await asyncio.sleep(0.1)
    assert queue_manager._queue.qsize() > 0, "Update should be in queue"
    assert mock_dp.feed_update.call_count == 0, "Workers should not process in PASSIVE"
    
    # Simulate lock acquisition (sets active_state.active=True)
    await lock_controller.simulate_lock_acquisition()
    
    # Wait for workers to pick up update
    await asyncio.sleep(0.3)
    
    # Verify active state changed
    assert active_state.active == True, "active_state should be True after lock acquired"
    
    # Verify worker processed the update
    assert mock_dp.feed_update.call_count >= 1, "Worker should have processed update in ACTIVE"
    
    # Cleanup
    await queue_manager.stop()


@pytest.mark.asyncio
async def test_state_machine_wait_active_unblocks():
    """
    Test: active_state.wait_active() unblocks when set(True) is called.
    """
    active_state = ActiveState(active=False)
    
    # Task that waits for ACTIVE
    wait_task = asyncio.create_task(active_state.wait_active())
    
    # Should not be done yet
    await asyncio.sleep(0.05)
    assert not wait_task.done(), "wait_active() should block when False"
    
    # Activate
    active_state.set(True, reason="test")
    
    # Should unblock immediately
    result = await asyncio.wait_for(wait_task, timeout=0.5)
    assert result == True, "wait_active() should return True"


@pytest.mark.asyncio
async def test_state_machine_passive_to_active_to_passive():
    """
    Test: PASSIVE → ACTIVE → PASSIVE transitions work correctly.
    """
    active_state = ActiveState(active=False)
    
    # Start PASSIVE
    assert active_state.active == False
    
    # Transition to ACTIVE
    active_state.set(True, reason="lock_acquired")
    assert active_state.active == True
    
    # wait_active() should return immediately
    result = await asyncio.wait_for(active_state.wait_active(), timeout=0.1)
    assert result == True
    
    # Transition back to PASSIVE
    active_state.set(False, reason="lock_lost")
    assert active_state.active == False
    
    # wait_active() should block again
    wait_task = asyncio.create_task(active_state.wait_active())
    await asyncio.sleep(0.05)
    assert not wait_task.done(), "wait_active() should block after PASSIVE"
    
    wait_task.cancel()


if __name__ == "__main__":
    # Run tests directly
    asyncio.run(test_state_machine_activates_workers())
    asyncio.run(test_state_machine_wait_active_unblocks())
    asyncio.run(test_state_machine_passive_to_active_to_passive())
    print("✅ All state machine verification tests passed!")
