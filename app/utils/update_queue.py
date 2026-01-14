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
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

import aiohttp

logger = logging.getLogger(__name__)


async def _send_passive_ack(
    update: Any,
    update_id: int,
    worker_id: int
) -> tuple[bool, Optional[str]]:
    """
    Send user feedback for PASSIVE mode update using direct Telegram API.
    
    This function uses direct HTTP calls to Telegram API (not aiogram) to ensure
    user always gets feedback even if aiogram dispatcher is broken.
    
    Args:
        update: Telegram Update object (dict or aiogram Update)
        update_id: Update ID for logging
        worker_id: Worker ID for logging
        
    Returns:
        (success: bool, cid: Optional[str])
    """
    # Generate CID
    cid = f"cid_{uuid.uuid4().hex[:12]}"
    
    # Get bot token
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
    if not bot_token:
        logger.error("[WORKER_%d] ❌ PASSIVE_ACK_FAIL: TELEGRAM_BOT_TOKEN not set", worker_id)
        return False, cid
    
    # Parse update (support both dict and aiogram Update)
    update_dict = None
    if isinstance(update, dict):
        update_dict = update
    elif hasattr(update, '__dict__'):
        # Try to convert aiogram Update to dict-like access
        update_dict = update
    else:
        logger.warning("[WORKER_%d] ⚠️ PASSIVE_UNKNOWN_UPDATE type=%s update_id=%s", 
                      worker_id, type(update).__name__, update_id)
        return False, cid
    
    # Extract callback_query or message
    callback_query = None
    message = None
    
    if isinstance(update_dict, dict):
        callback_query = update_dict.get('callback_query')
        message = update_dict.get('message')
    else:
        # aiogram Update object
        callback_query = getattr(update_dict, 'callback_query', None)
        message = getattr(update_dict, 'message', None)
    
    # Prepare message text
    passive_msg = "⏸️ Сервис перезапускается… попробуйте через 10–20 секунд"
    
    # Send response based on update type
    try:
        timeout = aiohttp.ClientTimeout(total=3.0)  # Short timeout
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if callback_query:
                # Extract callback_query_id
                if isinstance(callback_query, dict):
                    callback_query_id = callback_query.get('id')
                    callback_data = callback_query.get('data', '')
                else:
                    callback_query_id = getattr(callback_query, 'id', None)
                    callback_data = getattr(callback_query, 'data', '') or ''
                
                if not callback_query_id:
                    logger.warning("[WORKER_%d] ⚠️ PASSIVE_UNKNOWN_UPDATE: callback_query without id", worker_id)
                    return False, cid
                
                # Call answerCallbackQuery
                url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
                payload = {
                    "callback_query_id": str(callback_query_id),
                    "text": passive_msg,
                    "show_alert": False
                }
                
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        logger.info(
                            "[WORKER_%d] ✅ PASSIVE_ACK_SENT type=callback_query update_id=%s cid=%s data=%s",
                            worker_id, update_id, cid, callback_data[:50]
                        )
                        return True, cid
                    else:
                        error_text = await resp.text()
                        logger.warning(
                            "[WORKER_%d] ❌ PASSIVE_ACK_FAIL type=callback_query update_id=%s status=%d error=%s",
                            worker_id, update_id, resp.status, error_text[:200]
                        )
                        return False, cid
            
            elif message:
                # Extract chat_id
                if isinstance(message, dict):
                    chat_id = message.get('chat', {}).get('id')
                    message_text = message.get('text', '')
                else:
                    chat = getattr(message, 'chat', None)
                    chat_id = getattr(chat, 'id', None) if chat else None
                    message_text = getattr(message, 'text', '') or ''
                
                if not chat_id:
                    logger.warning("[WORKER_%d] ⚠️ PASSIVE_UNKNOWN_UPDATE: message without chat.id", worker_id)
                    return False, cid
                
                # Call sendMessage
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": passive_msg,
                    "disable_web_page_preview": True
                }
                
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        logger.info(
                            "[WORKER_%d] ✅ PASSIVE_ACK_SENT type=message update_id=%s cid=%s text=%s",
                            worker_id, update_id, cid, message_text[:50] if message_text else "(no text)"
                        )
                        return True, cid
                    else:
                        error_text = await resp.text()
                        logger.warning(
                            "[WORKER_%d] ❌ PASSIVE_ACK_FAIL type=message update_id=%s status=%d error=%s",
                            worker_id, update_id, resp.status, error_text[:200]
                        )
                        return False, cid
            else:
                logger.warning(
                    "[WORKER_%d] ⚠️ PASSIVE_UNKNOWN_UPDATE: update_id=%s (no callback_query or message)",
                    worker_id, update_id
                )
                return False, cid
                
    except asyncio.TimeoutError:
        logger.warning(
            "[WORKER_%d] ❌ PASSIVE_ACK_FAIL: timeout update_id=%s cid=%s",
            worker_id, update_id, cid
        )
        return False, cid
    except Exception as e:
        logger.warning(
            "[WORKER_%d] ❌ PASSIVE_ACK_FAIL: exception update_id=%s cid=%s error=%s",
            worker_id, update_id, cid, str(e)
        )
        return False, cid


def _is_allowed_in_passive(update) -> bool:
    """
    Проверяет, разрешен ли update в PASSIVE режиме.
    
    Разрешены:
    - /start команда
    - main_menu, back_to_menu callback
    - help, menu:* callback
    
    Запрещены:
    - Генерации (gen:*, flow:*, generate:*)
    - Платежи (pay:*, payment:*, topup:*)
    - Редактирование параметров (param:*, edit:*)
    - Любые другие опасные действия
    """
    # Команда /start всегда разрешена
    if hasattr(update, 'message') and update.message:
        msg = update.message
        if msg.text and msg.text.startswith('/start'):
            return True
    
    # Проверяем callback_query
    if hasattr(update, 'callback_query') and update.callback_query:
        data = update.callback_query.data or ""
        
        # Разрешенные префиксы/значения
        allowed = [
            'main_menu',
            'back_to_menu',
            'help',
            'menu:',
        ]
        
        for pattern in allowed:
            if data == pattern or data.startswith(pattern):
                return True
    
    # По умолчанию запрещаем
    return False


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
    
    def get_bot(self):
        """Get configured bot instance."""
        return self._bot
    
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
                
                # 🔒 PASSIVE CHECK: Reject forbidden updates immediately with user feedback
                if self._active_state and not self._active_state.active:
                    if not _is_allowed_in_passive(update):
                        # Запрещенный update в PASSIVE режиме - отвечаем пользователю через прямой API
                        callback_data = None
                        if hasattr(update, 'callback_query') and update.callback_query:
                            callback_data = getattr(update.callback_query, 'data', None) or ''
                        elif isinstance(update, dict) and update.get('callback_query'):
                            callback_data = update['callback_query'].get('data', '')
                        
                        logger.info(
                            "[WORKER_%d] ⏸️ PASSIVE_REJECT %s data=%s",
                            worker_id,
                            "callback_query" if callback_data else "message",
                            callback_data[:50] if callback_data else "(no data)"
                        )
                        
                        # Send passive ack using direct Telegram API
                        ack_success, cid = await _send_passive_ack(update, update_id, worker_id)
                        
                        if not ack_success:
                            logger.warning(
                                "[WORKER_%d] ⚠️ PASSIVE_ACK_FAIL update_id=%s cid=%s",
                                worker_id, update_id, cid
                            )
                        
                        self._metrics.total_held += 1
                        
                        # Помечаем как обработанный (не оставляем в очереди)
                        self._queue.task_done()
                        continue  # Переходим к следующему update
                    else:
                        # Разрешенный update (menu/start) - обрабатываем
                        logger.info(
                            "[WORKER_%d] ✅ PASSIVE_MENU_OK processing allowed update",
                            worker_id
                        )
                
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

                    # Don't count PASSIVE-allowed updates as "degraded" - they're normal
                    # (degraded only applies to forced ACTIVE mode processing without lock)
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
