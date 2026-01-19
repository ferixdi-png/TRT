"""
KIE Stub - симулятор KIE API для тестов
Переключение через env KIE_STUB=1
"""

import os
import asyncio
import logging
import uuid
import json
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.utils.logging_config import get_logger
from app.observability.trace import trace_event, url_summary
from app.observability.structured_logs import log_structured_event

logger = get_logger(__name__)


class KIEStub:
    """Симулятор KIE API для тестов"""
    
    def __init__(self):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._task_states = {}  # task_id -> state progression
    
    async def create_task(
        self,
        model_id: str,
        input_data: Dict[str, Any],
        callback_url: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Создать задачу (симуляция)
        
        Returns:
            {'ok': True, 'taskId': str}
        """
        task_id = str(uuid.uuid4())
        
        # Симулируем создание задачи
        self._tasks[task_id] = {
            'task_id': task_id,
            'model_id': model_id,
            'input_data': input_data,
            'callback_url': callback_url,
            'created_at': datetime.now().isoformat(),
            'state': 'pending'
        }
        
        # Запускаем симуляцию обработки (в фоне)
        asyncio.create_task(self._simulate_processing(task_id))

        logger.info(f"[STUB] Task created: {task_id} for model {model_id}")
        trace_event(
            "info",
            correlation_id or "corr-na-na",
            event="TRACE_OUT",
            stage="KIE_CREATE",
            action="KIE_CREATE",
            model_id=model_id,
            task_id=task_id,
            outcome="stub_created",
        )
        log_structured_event(
            correlation_id=correlation_id,
            action="KIE_CREATE",
            action_path="kie_stub.create_task",
            model_id=model_id,
            outcome="stub_created",
        )
        
        return {
            'ok': True,
            'taskId': task_id
        }
    
    async def _simulate_processing(self, task_id: str):
        """Симулировать обработку задачи"""
        # pending -> processing -> success
        await asyncio.sleep(1)  # pending

        if task_id in self._tasks:
            self._tasks[task_id]['state'] = 'processing'
            logger.debug(f"[STUB] Task {task_id} -> processing")
        
        await asyncio.sleep(2)  # processing

        if task_id in self._tasks:
            # Генерируем фиктивные URLs
            task = self._tasks[task_id]
            model_id = task['model_id']

            # Генерируем результат в зависимости от типа модели
            result_urls = []
            result_text = None
            model_id_lower = model_id.lower()
            if 'image' in model_id_lower or 'text-to-image' in model_id_lower:
                result_urls = [f"https://example.com/generated/image_{task_id}.png"]
            elif 'video' in model_id_lower or 'text-to-video' in model_id_lower:
                result_urls = [f"https://example.com/generated/video_{task_id}.mp4"]
            elif 'audio' in model_id_lower or 'voice' in model_id_lower or 'text-to-audio' in model_id_lower:
                result_urls = [f"https://example.com/generated/audio_{task_id}.mp3"]
            else:
                result_text = f"Stub result for task {task_id}"

            self._tasks[task_id]['state'] = 'success'
            self._tasks[task_id]['result_urls'] = result_urls
            result_payload = {
                "resultUrls": result_urls,
                "resultText": result_text,
                "resultObject": result_text,
            }
            self._tasks[task_id]['resultJson'] = json.dumps(result_payload)
            self._tasks[task_id]['resultText'] = result_text
            logger.debug(f"[STUB] Task {task_id} -> success")
    
    async def get_task_status(self, task_id: str, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Получить статус задачи (симуляция)
        
        Returns:
            {
                'ok': True,
                'state': str ('pending', 'processing', 'completed', 'failed'),
                'resultUrls': List[str] (если completed),
                'resultJson': str (если completed)
            }
        """
        if task_id not in self._tasks:
            return {
                'ok': False,
                'state': 'failed',
                'error': 'Task not found'
            }
        
        task = self._tasks[task_id]
        state = task.get('state', 'pending')
        
        result = {
            'ok': True,
            'state': state
        }
        
        if state == 'success':
            result['resultUrls'] = task.get('result_urls', [])
            result['resultJson'] = task.get('resultJson', '{}')
            if task.get("resultText"):
                result["resultText"] = task.get("resultText")
        elif state == 'failed':
            result['failCode'] = 'STUB_ERROR'
            result['failMsg'] = 'Simulated error'

        trace_event(
            "info",
            correlation_id or "corr-na-na",
            event="TRACE_IN",
            stage="KIE_POLL",
            action="KIE_POLL",
            task_id=task_id,
            state=state,
            result_url_summary=url_summary((result.get("resultUrls") or [None])[0]),
        )
        
        return result
    
    async def wait_for_task(
        self,
        task_id: str,
        timeout: int = 900,
        poll_interval: int = 3,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ждать завершения задачи (симуляция)"""
        start_time = asyncio.get_event_loop().time()
        attempt = 0
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                return {
                    'ok': False,
                    'state': 'timeout',
                    'error': f'Task timeout after {timeout}s'
                }
            attempt += 1
            status = await self.get_task_status(task_id, correlation_id=correlation_id)
            log_structured_event(
                correlation_id=correlation_id,
                action="KIE_POLL",
                action_path="kie_stub.wait_for_task",
                param={"attempt": attempt, "elapsed": round(elapsed, 3)},
                outcome=status.get("state"),
            )
            
            if not status.get('ok'):
                await asyncio.sleep(poll_interval)
                continue
            
            state = status.get('state', 'pending')
            
            if state in ('success', 'completed', 'failed'):
                return status
            
            await asyncio.sleep(poll_interval)


def get_kie_client_or_stub():
    """Получить KIE клиент или stub в зависимости от env"""
    allow_real = os.getenv("KIE_ALLOW_REAL", "0").lower() in ("1", "true", "yes")
    allow_real = allow_real or os.getenv("ALLOW_REAL_GENERATION", "0").lower() in ("1", "true", "yes")
    force_stub = os.getenv("KIE_STUB", "0").lower() in ("1", "true", "yes")
    has_api_key = bool(os.getenv("KIE_API_KEY"))

    if force_stub or not allow_real or not has_api_key:
        logger.info("[STUB] Using KIE stub (force_stub=%s allow_real=%s has_key=%s)", force_stub, allow_real, has_api_key)
        return KIEStub()

    from app.integrations.kie_client import KIEClient
    return KIEClient()
