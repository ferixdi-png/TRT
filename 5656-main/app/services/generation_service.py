"""
Generation service - работа с генерациями через единый API
Polling без блокировки event loop
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.utils.logging_config import get_logger
from app.integrations.kie_stub import get_kie_client_or_stub
from app.storage import get_storage

logger = get_logger(__name__)


class GenerationService:
    """Сервис для работы с генерациями"""
    
    def __init__(self):
        self.kie_client = get_kie_client_or_stub()
        self.storage = get_storage()
        self._polling_tasks: Dict[str, asyncio.Task] = {}
    
    async def create_generation(
        self,
        user_id: int,
        model_id: str,
        model_name: str,
        params: Dict[str, Any],
        price: float
    ) -> str:
        """
        Создать генерацию
        
        Returns:
            job_id: str - ID задачи
        """
        # Создаем задачу в KIE
        result = await self.kie_client.create_task(model_id, params)
        
        if not result.get('ok'):
            error = result.get('error', 'Unknown error')
            logger.error(f"[GEN] Failed to create task: {error}")
            raise RuntimeError(f"Failed to create generation task: {error}")
        
        task_id = result.get('taskId')
        if not task_id:
            raise RuntimeError("No taskId in KIE response")
        
        # Сохраняем job в storage
        # Используем task_id как job_id для простоты
        job_id = await self.storage.add_generation_job(
            user_id=user_id,
            model_id=model_id,
            model_name=model_name,
            params=params,
            price=price,
            task_id=task_id,  # external_task_id будет сохранен как task_id
            status="pending"
        )
        
        logger.info(f"[GEN] Generation created: job_id={job_id}, task_id={task_id}, user_id={user_id}")
        
        return job_id
    
    async def start_polling(
        self,
        job_id: str,
        on_progress: Optional[callable] = None,
        on_complete: Optional[callable] = None,
        on_error: Optional[callable] = None
    ) -> None:
        """
        Начать polling задачи (без блокировки event loop)
        
        Args:
            job_id: ID задачи
            on_progress: Callback для обновления прогресса (state, message)
            on_complete: Callback при завершении (result_urls)
            on_error: Callback при ошибке (error_message)
        """
        if job_id in self._polling_tasks:
            logger.warning(f"[GEN] Polling already started for job {job_id}")
            return
        
        async def _poll_task():
            """Polling задача в фоне"""
            try:
                job = await self.storage.get_job(job_id)
                if not job:
                    logger.error(f"[GEN] Job {job_id} not found")
                    if on_error:
                        await on_error("Job not found")
                    return
                
                # Получаем external_task_id (от KIE API)
                task_id = job.get('external_task_id') or job.get('task_id')
                if not task_id:
                    logger.error(f"[GEN] No task_id in job {job_id}, job={job}")
                    if on_error:
                        await on_error("No task_id")
                    return
                
                # Polling с обновлением статуса
                timeout = 900  # 15 минут
                poll_interval = 3  # 3 секунды
                start_time = asyncio.get_event_loop().time()
                
                while True:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed > timeout:
                        await self.storage.update_job_status(job_id, "timeout")
                        if on_error:
                            await on_error("Timeout")
                        break
                    
                    # Получаем статус от KIE
                    status = await self.kie_client.get_task_status(task_id)
                    
                    if not status.get('ok'):
                        # Ошибка получения статуса - продолжаем polling
                        await asyncio.sleep(poll_interval)
                        continue
                    
                    state = status.get('state', 'pending')
                    
                    # Обновляем статус в storage
                    await self.storage.update_job_status(
                        job_id,
                        state,
                        result_urls=status.get('resultUrls', []),
                        error_message=status.get('failMsg')
                    )
                    
                    # Вызываем callback прогресса
                    if on_progress:
                        progress_messages = {
                            'pending': 'В очереди',
                            'processing': 'В работе',
                            'completed': 'Готово',
                            'failed': 'Ошибка'
                        }
                        message = progress_messages.get(state, state)
                        await on_progress(state, message)
                    
                    if state == 'completed':
                        result_urls = status.get('resultUrls', [])
                        if on_complete:
                            await on_complete(result_urls)
                        break
                    
                    if state == 'failed':
                        error_msg = status.get('failMsg', 'Unknown error')
                        if on_error:
                            await on_error(error_msg)
                        break
                    
                    # pending или processing - продолжаем polling
                    await asyncio.sleep(poll_interval)
            
            except Exception as e:
                logger.error(f"[GEN] Polling error for job {job_id}: {e}", exc_info=True)
                await self.storage.update_job_status(job_id, "failed", error_message=str(e))
                if on_error:
                    await on_error(str(e))
            finally:
                # Удаляем задачу из списка
                self._polling_tasks.pop(job_id, None)
        
        # Запускаем polling в фоне
        task = asyncio.create_task(_poll_task())
        self._polling_tasks[job_id] = task
    
    async def wait_for_generation(
        self,
        job_id: str,
        timeout: int = 900
    ) -> Dict[str, Any]:
        """
        Ждать завершения генерации (блокирующий вариант)
        
        Returns:
            {
                'ok': bool,
                'result_urls': List[str] (если ok),
                'error': str (если не ok)
            }
        """
        job = await self.storage.get_job(job_id)
        if not job:
            return {
                'ok': False,
                'error': 'Job not found'
            }
        
        # Получаем external_task_id (от KIE API)
        task_id = job.get('external_task_id') or job.get('task_id')
        if not task_id:
            return {
                'ok': False,
                'error': 'No task_id'
            }
        
        # Используем wait_for_task из клиента
        result = await self.kie_client.wait_for_task(task_id, timeout=timeout)
        
        if result.get('state') == 'completed':
            result_urls = result.get('resultUrls', [])
            await self.storage.update_job_status(job_id, 'completed', result_urls=result_urls)
            return {
                'ok': True,
                'result_urls': result_urls
            }
        else:
            error = result.get('error') or result.get('failMsg', 'Unknown error')
            await self.storage.update_job_status(job_id, 'failed', error_message=error)
            return {
                'ok': False,
                'error': error
            }
    
    async def cancel_generation(self, job_id: str) -> bool:
        """Отменить генерацию"""
        try:
            await self.storage.update_job_status(job_id, "cancelled")
            
            # Отменяем polling задачу если есть
            if job_id in self._polling_tasks:
                task = self._polling_tasks[job_id]
                task.cancel()
                self._polling_tasks.pop(job_id, None)
            
            return True
        except Exception as e:
            logger.error(f"[GEN] Failed to cancel job {job_id}: {e}")
            return False


def get_generation_service() -> GenerationService:
    """Получить generation service (singleton)"""
    # TODO: можно добавить singleton если нужно
    return GenerationService()
