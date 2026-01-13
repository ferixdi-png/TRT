"""
Fast-ack webhook update queue with background workers.

This module provides instant HTTP responses to Telegram webhook calls
while processing updates asynchronously in background workers.

Key features:
- Instant 200 OK response (< 200ms target)
- Bounded queue to prevent memory overflow
- Multiple concurrent workers for throughput
- Graceful degradation (drop updates when overloaded, but still ack)
- Metrics for monitoring
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class QueueMetrics:
    """Metrics for monitoring queue health."""
    total_received: int = 0
    total_processed: int = 0
    total_dropped: int = 0
    total_errors: int = 0
    total_held: int = 0  # Held in PASSIVE mode
    total_requeued: int = 0  # Put back to queue
    total_processed_degraded: int = 0  # Processed despite PASSIVE (degraded mode)
    workers_active: int = 0
    queue_depth_current: int = 0
    last_drop_time: Optional[float] = None


@dataclass
class UpdateQueueManager:
    """
    Manages async queue for Telegram updates with background workers.
    
    Architecture:
    - Webhook handler calls enqueue() and immediately returns 200 OK
    - N worker tasks read from queue and call dp.feed_update()
    - If queue full: drop update, log warning, but still ack HTTP 200
    - Metrics exposed for /health endpoint
    """
    
    max_size: int = 100  # Max queued updates before dropping
    num_workers: int = 3  # Concurrent worker tasks
    
    _queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue())
    _workers: list = field(default_factory=list)
    _metrics: QueueMetrics = field(default_factory=QueueMetrics)
    _running: bool = False
    _dp = None  # Dispatcher instance
    _bot = None  # Bot instance
    _active_state = None  # Active state for lock checking
    
    def configure(self, dp, bot, active_state=None):
        """Configure dispatcher, bot, and active state."""
        self._dp = dp
        self._bot = bot
        self._active_state = active_state
        logger.info("[QUEUE] Configured with dp=%s bot=%s", 
                   type(dp).__name__, type(bot).__name__)
    
    async def start(self):
        """Start background workers."""
        if self._running:
            logger.warning("[QUEUE] Already running")
            return
        
        if not self._dp or not self._bot:
            raise RuntimeError("Must call configure() before start()")
        
        self._running = True
        self._queue = asyncio.Queue(maxsize=self.max_size)
        
        # Spawn worker tasks
        for i in range(self.num_workers):
            worker = asyncio.create_task(
                self._worker_loop(worker_id=i),
                name=f"update_worker_{i}"
            )
            self._workers.append(worker)
        
        logger.info("[QUEUE] Started %d workers (queue_max=%d)", 
                   self.num_workers, self.max_size)
    
    async def stop(self):
        """Stop workers gracefully."""
        if not self._running:
            return
        
        self._running = False
        
        # Cancel all workers
        for worker in self._workers:
            worker.cancel()
        
        # Wait for cancellation
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        
        logger.info("[QUEUE] Stopped workers")
    
    def enqueue(self, update, update_id: int = 0) -> bool:
        """
        Enqueue update for background processing.
        
        Returns:
            True if enqueued, False if dropped (queue full)
        
        This method is synchronous and returns immediately.
        Webhook handler should always return 200 OK regardless.
        """
        self._metrics.total_received += 1
        
        # Wrap update with metadata for PASSIVE handling
        item = {
            "update": update,
            "update_id": update_id,
            "attempt": 0,
            "first_seen": time.time(),
        }
        
        try:
            # Try to put without blocking
            self._queue.put_nowait(item)
            self._metrics.queue_depth_current = self._queue.qsize()
            return True
        except asyncio.QueueFull:
            # Queue overloaded - drop update but log
            self._metrics.total_dropped += 1
            self._metrics.last_drop_time = time.time()
            logger.warning(
                "[QUEUE] DROPPED update_id=%s (queue full: %d/%d)",
                update_id, self._queue.qsize(), self.max_size
            )
            return False

    @staticmethod
    def _is_passive_allowed(update) -> bool:
        message = getattr(update, "message", None)
        if message:
            text = getattr(message, "text", None)
            if text and text.strip().lower().startswith("/start"):
                return True

        callback = getattr(update, "callback_query", None)
        if callback:
            data = getattr(callback, "data", None)
            if not data:
                return False
            if data == "main_menu":
                return True
            if data.startswith("menu:"):
                return True
            if data == "quick:menu":
                return True

        return False
    
    async def _worker_loop(self, worker_id: int):
        """Background worker that processes updates from queue."""
        import os
        import time
        
        logger.info("[WORKER_%d] Started", worker_id)
        
        last_passive_log = 0.0  # Rate-limit PASSIVE_WAIT logging
        active_enter_logged = False  # Track first ACTIVE enter
        
        while self._running:
            try:
                # Pull update from queue (with timeout to check active state regularly)
                item = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0
                )
                
                # Extract item metadata
                update = item["update"]
                update_id = item["update_id"]
                
                self._metrics.workers_active += 1
                self._metrics.queue_depth_current = self._queue.qsize()
                
                try:
                    force_active = os.getenv("SINGLETON_LOCK_FORCE_ACTIVE", "0") in ("1", "true", "True")
                    is_passive = self._active_state and not self._active_state.active and not force_active
                    if is_passive and not self._is_passive_allowed(update):
                        now = time.time()
                        if now - last_passive_log > 5.0:
                            logger.info(
                                "[WORKER_%d] ⏸️ PASSIVE_HOLD update_id=%s queue_depth=%d",
                                worker_id, update_id, self._queue.qsize()
                            )
                            last_passive_log = now
                        self._metrics.total_held += 1
                        item["attempt"] += 1
                        try:
                            self._queue.put_nowait(item)
                        except asyncio.QueueFull:
                            self._metrics.total_dropped += 1
                            logger.warning(
                                "[WORKER_%d] ⚠️ PASSIVE_DROP update_id=%s (queue full)",
                                worker_id, update_id
                            )
                        await asyncio.sleep(0.5)
                        continue

                    if is_passive:
                        self._metrics.total_processed_degraded += 1
                    # ACTIVE: Log first entry
                    if not active_enter_logged and not is_passive:
                        logger.info("[WORKER_%d] ✅ ACTIVE_ENTER active=True", worker_id)
                        active_enter_logged = True

                    logger.info("[WORKER_%d] 🎯 WORKER_PICK update_id=%s", worker_id, update_id)
                    
                    # 🔐 STEP 1: Check persistent dedup BEFORE processing (FAIL-OPEN)
                    if update_id:
                        from app.storage.factory import get_storage
                        storage = get_storage()
                        
                        try:
                            # Check if already processed using storage method
                            if await storage.is_update_processed(update_id):
                                logger.warning(
                                    "[WORKER_%d] ⏭️ DEDUP_SKIP update_id=%s (already processed)",
                                    worker_id, update_id
                                )
                                self._metrics.total_dropped += 1
                                # Skip processing - task_done() in finally
                                continue
                            
                            # Mark as processing
                            await storage.mark_update_processed(
                                update_id,
                                worker_id=f"worker_{worker_id}",
                                update_type="message" if getattr(update, "message", None) else "callback_query"
                            )
                            logger.debug("[WORKER_%d] ✅ DEDUP_OK update_id=%s marked as processing", worker_id, update_id)
                            
                        except Exception as e:
                            # FAIL-OPEN: Log and continue processing without dedup
                            # This prevents worker deadlock when DB is unavailable
                            logger.warning(
                                "[WORKER_%d] ⚠️ DEDUP_FAIL_OPEN update_id=%s: %s - continuing without dedup",
                                worker_id, update_id, str(e)
                            )
                    
                    # STEP 2: Process update (feed to dispatcher)
                    logger.info(
                        "[WORKER_%d] 🚀 DISPATCH_START update_id=%s",
                        worker_id, update_id
                    )
                    
                    force_degraded = os.getenv("SINGLETON_LOCK_FORCE_ACTIVE", "0") in ("1", "true", "True")
                    if force_degraded and self._active_state and not self._active_state.active:
                        self._metrics.total_processed_degraded += 1
                    elif not is_passive:
                        self._metrics.total_processed += 1
                    
                    start_time = time.monotonic()
                    await asyncio.wait_for(
                        self._dp.feed_update(self._bot, update),
                        timeout=30.0
                    )
                    elapsed = time.monotonic() - start_time
                    
                    logger.info(
                        "[WORKER_%d] ✅ DISPATCH_OK update_id=%s in %.2fs → DONE",
                        worker_id, update_id, elapsed
                    )
                
                except asyncio.TimeoutError:
                    logger.error(
                        "[WORKER_%d] Timeout processing update_id=%s",
                        worker_id, update_id
                    )
                    self._metrics.total_errors += 1
                
                except Exception as exc:
                    logger.exception(
                        "[WORKER_%d] Error processing update_id=%s: %s",
                        worker_id, update_id, exc
                    )
                    self._metrics.total_errors += 1
                
                finally:
                    self._metrics.workers_active -= 1
                    self._queue.task_done()
            
            except asyncio.TimeoutError:
                # No updates available, continue loop
                continue
            
            except asyncio.CancelledError:
                logger.info("[WORKER_%d] Cancelled", worker_id)
                break
            
            except Exception as exc:
                logger.exception("[WORKER_%d] Unexpected error: %s", worker_id, exc)
        
        logger.info("[WORKER_%d] Stopped", worker_id)
    
    def get_metrics(self) -> dict:
        """Get current metrics for /health endpoint."""
        return {
            "total_received": self._metrics.total_received,
            "total_processed": self._metrics.total_processed,
            "total_processed_degraded": self._metrics.total_processed_degraded,
            "total_held": self._metrics.total_held,
            "total_requeued": self._metrics.total_requeued,
            "total_dropped": self._metrics.total_dropped,
            "total_errors": self._metrics.total_errors,
            "workers_active": self._metrics.workers_active,
            "queue_depth": self._metrics.queue_depth_current,
            "queue_max": self.max_size,
            "drop_rate": (
                self._metrics.total_dropped / max(self._metrics.total_received, 1)
            ) * 100,
        }


# Global singleton
_queue_manager: Optional[UpdateQueueManager] = None


def get_queue_manager() -> UpdateQueueManager:
    """Get or create global queue manager."""
    global _queue_manager
    if _queue_manager is None:
        import os
        max_size = int(os.getenv("UPDATE_QUEUE_SIZE", "100"))
        num_workers = int(os.getenv("UPDATE_QUEUE_WORKERS", "3"))
        _queue_manager = UpdateQueueManager(max_size=max_size, num_workers=num_workers)
    return _queue_manager
