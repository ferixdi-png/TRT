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
        
        try:
            # Try to put without blocking
            self._queue.put_nowait((update, update_id))
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
    
    async def _worker_loop(self, worker_id: int):
        """Background worker that processes updates from queue."""
        logger.info("[WORKER_%d] Started", worker_id)
        
        while self._running:
            try:
                # Wait for update from queue
                update, update_id = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0
                )
                
                self._metrics.workers_active += 1
                self._metrics.queue_depth_current = self._queue.qsize()
                
                try:
                    # Check if we should process (ACTIVE mode only)
                    if self._active_state and not self._active_state.active:
                        logger.debug(
                            "[WORKER_%d] Skipping update_id=%s (PASSIVE mode)",
                            worker_id, update_id
                        )
                        continue
                    
                    # Process update
                    start_time = time.monotonic()
                    
                    await asyncio.wait_for(
                        self._dp.feed_update(self._bot, update),
                        timeout=30.0
                    )
                    
                    elapsed = time.monotonic() - start_time
                    self._metrics.total_processed += 1
                    
                    if elapsed > 5.0:
                        logger.warning(
                            "[WORKER_%d] Slow update_id=%s took %.2fs",
                            worker_id, update_id, elapsed
                        )
                    else:
                        logger.debug(
                            "[WORKER_%d] Processed update_id=%s in %.2fs",
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
