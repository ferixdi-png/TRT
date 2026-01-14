#!/usr/bin/env python3
"""
Orphan Callback Reconciliation Monitor

Reconciles orphan callbacks (callbacks that arrived before job creation):
1. Polls orphan_callbacks table every 60s
2. Attempts to match orphan with existing job
3. Updates job if found
4. Marks orphan as processed

Designed as background task for main_render.py or standalone cron job.

Usage:
    # As background task (in main_render.py startup):
    asyncio.create_task(run_orphan_reconciliation_loop(storage, bot))
    
    # As standalone script:
    python3 tools/orphan_reconciliation.py
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


async def reconcile_orphans(storage, bot=None, limit: int = 100) -> dict:
    """
    Reconcile unprocessed orphan callbacks.
    
    Returns:
        {
            'processed': int,
            'matched': int,
            'errors': int
        }
    """
    stats = {'processed': 0, 'matched': 0, 'errors': 0}
    
    # Get unprocessed orphans
    orphans = await storage._get_unprocessed_orphans(limit=limit)
    
    if not orphans:
        logger.debug("[ORPHAN_RECONCILE] No orphans to process")
        return stats
    
    logger.info(f"[ORPHAN_RECONCILE] Processing {len(orphans)} orphan callbacks")
    
    for orphan in orphans:
        task_id = orphan['task_id']
        payload = orphan.get('payload', {})
        
        # Parse payload if string
        if isinstance(payload, str):
            import json
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        
        try:
            # Try to find job by task_id (job might have been created after callback)
            job = await storage.find_job_by_task_id(task_id)
            
            if job:
                # MATCH FOUND - update job with orphan data
                logger.info(f"[ORPHAN_RECONCILE] ✅ Match found for {task_id}")
                
                state = payload.get('state') or payload.get('status', 'unknown')
                result_urls = payload.get('result_urls') or payload.get('resultUrls', [])
                error_text = payload.get('error_text') or payload.get('failMsg')
                
                from app.storage.status import normalize_job_status
                normalized_status = normalize_job_status(state)
                
                # Update job
                job_id = job.get('job_id') or job.get('id') or task_id
                await storage.update_job_status(
                    job_id,
                    normalized_status,
                    result_urls=result_urls or None,
                    error_message=error_text
                )
                
                # Try to deliver to Telegram if bot available
                if bot and normalized_status == 'done' and result_urls:
                    user_id = job.get('user_id')
                    chat_id = job.get('chat_id') or user_id
                    
                    if chat_id:
                        try:
                            # Send result (simplified - use bot.send_message)
                            text = f"✅ Генерация готова (из orphan reconciliation)\\n{result_urls[0]}"
                            await bot.send_message(chat_id, text)
                            logger.info(f"[ORPHAN_RECONCILE] 📨 Delivered to chat_id={chat_id}")
                        except Exception as e:
                            logger.warning(f"[ORPHAN_RECONCILE] Failed to deliver: {e}")
                
                # Mark orphan as processed (success)
                await storage._mark_orphan_processed(task_id, error=None)
                stats['matched'] += 1
            else:
                # NO MATCH - check if orphan is too old (>1 hour = give up)
                received_at = orphan.get('received_at')
                if isinstance(received_at, str):
                    try:
                        from dateutil import parser
                        received_at = parser.parse(received_at)
                    except Exception:
                        received_at = None
                
                if received_at and datetime.now() - received_at > timedelta(hours=1):
                    # Too old - mark as processed with error
                    await storage._mark_orphan_processed(
                        task_id,
                        error="No matching job found after 1 hour"
                    )
                    logger.warning(f"[ORPHAN_RECONCILE] ⚠️ Orphan {task_id} expired (>1h old)")
                else:
                    # Still waiting - leave unprocessed
                    logger.debug(f"[ORPHAN_RECONCILE] ⏳ Orphan {task_id} still waiting for job")
            
            stats['processed'] += 1
        
        except Exception as e:
            logger.exception(f"[ORPHAN_RECONCILE] ❌ Error processing {task_id}: {e}")
            stats['errors'] += 1
            
            # Mark as processed with error (prevent infinite retry)
            try:
                await storage._mark_orphan_processed(task_id, error=str(e))
            except Exception:
                pass
    
    if stats['matched'] > 0:
        logger.info(
            f"[ORPHAN_RECONCILE] ✅ Reconciled {stats['matched']}/{stats['processed']} orphans "
            f"(errors={stats['errors']})"
        )
    
    return stats


async def run_orphan_reconciliation_loop(storage, bot=None, interval: int = 60):
    """
    Background task: reconcile orphans every `interval` seconds.
    
    Args:
        storage: Storage instance
        bot: Telegram Bot instance (optional, for delivery)
        interval: Seconds between reconciliation runs (default 60)
    """
    logger.info(f"[ORPHAN_RECONCILE] Started background loop (interval={interval}s)")
    
    while True:
        try:
            stats = await reconcile_orphans(storage, bot, limit=100)
            
            if stats['processed'] > 0:
                logger.info(
                    f"[ORPHAN_RECONCILE] Cycle complete: "
                    f"processed={stats['processed']} matched={stats['matched']} errors={stats['errors']}"
                )
        except Exception as e:
            logger.exception(f"[ORPHAN_RECONCILE] Loop error: {e}")
        
        await asyncio.sleep(interval)


# Standalone execution
if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
    
    async def main():
        from app.storage import get_storage
        storage = get_storage()
        
        logger.info("Running orphan reconciliation (one-shot)")
        stats = await reconcile_orphans(storage, bot=None, limit=100)
        
        logger.info(f"Results: {stats}")
        return 0 if stats['errors'] == 0 else 1
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
