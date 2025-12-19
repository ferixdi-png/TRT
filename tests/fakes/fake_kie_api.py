"""
Fake KIE API для тестов
НИКОГДА не делает реальных HTTP запросов
"""

import asyncio
import time
from typing import Dict, Any, Optional
from enum import Enum


class TaskState(Enum):
    """Состояния задачи"""
    WAITING = "waiting"
    QUEUING = "queuing"
    GENERATING = "generating"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class FakeKieAPI:
    """
    Fake KIE API для тестирования
    Поддерживает сценарии: SUCCESS, FAIL, TIMEOUT
    """
    
    def __init__(self):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._task_counter = 0
        self._fail_mode = False  # Режим принудительного фейла
        self._timeout_mode = False  # Режим таймаута
    
    def set_fail_mode(self, enabled: bool = True):
        """Включает/выключает режим принудительного фейла"""
        self._fail_mode = enabled
    
    def set_timeout_mode(self, enabled: bool = True):
        """Включает/выключает режим таймаута"""
        self._timeout_mode = enabled
    
    async def create_task(
        self,
        model_id: str,
        input_data: Dict[str, Any],
        callback_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Создаёт fake задачу
        
        Returns:
            {
                "ok": bool,
                "taskId": str,
                "status": str
            }
        """
        await asyncio.sleep(0.1)  # Имитация задержки сети
        
        if self._fail_mode:
            return {
                "ok": False,
                "error": "Fake API: Forced failure mode",
                "status": 500
            }
        
        self._task_counter += 1
        task_id = f"fake_task_{self._task_counter}"
        
        # Определяем состояние в зависимости от режима
        if self._timeout_mode:
            state = TaskState.WAITING
        else:
            state = TaskState.WAITING
        
        self._tasks[task_id] = {
            "taskId": task_id,
            "model_id": model_id,
            "input": input_data,
            "state": state.value,
            "created_at": time.time(),
            "callback_url": callback_url,
        }
        
        return {
            "ok": True,
            "taskId": task_id,
            "status": "created"
        }
    
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Получает статус fake задачи
        
        Returns:
            {
                "ok": bool,
                "state": str,
                "resultJson": Optional[str],
                "error": Optional[str]
            }
        """
        await asyncio.sleep(0.05)  # Имитация задержки сети
        
        if task_id not in self._tasks:
            return {
                "ok": False,
                "error": f"Task {task_id} not found",
                "state": "error"
            }
        
        task = self._tasks[task_id]
        elapsed = time.time() - task["created_at"]
        
        # Логика изменения состояния
        if self._timeout_mode:
            # В режиме таймаута всегда waiting
            return {
                "ok": True,
                "state": TaskState.WAITING.value,
                "resultJson": None,
                "error": None
            }
        
        if self._fail_mode:
            # В режиме фейла переходим в failed
            task["state"] = TaskState.FAILED.value
            return {
                "ok": False,
                "state": TaskState.FAILED.value,
                "resultJson": None,
                "error": "Fake API: Forced failure"
            }
        
        # Нормальная логика: waiting -> queuing -> generating -> success
        if elapsed < 0.5:
            task["state"] = TaskState.WAITING.value
        elif elapsed < 1.0:
            task["state"] = TaskState.QUEUING.value
        elif elapsed < 2.0:
            task["state"] = TaskState.GENERATING.value
        else:
            # Генерируем fake результат
            task["state"] = TaskState.SUCCESS.value
            task["result"] = {
                "urls": [f"https://fake-cdn.example.com/result_{task_id}.jpg"],
                "model": task["model_id"]
            }
        
        result_json = None
        if task["state"] == TaskState.SUCCESS.value and "result" in task:
            import json
            result_json = json.dumps(task["result"])
        
        return {
            "ok": task["state"] != TaskState.FAILED.value,
            "state": task["state"],
            "resultJson": result_json,
            "error": None if task["state"] != TaskState.FAILED.value else "Fake error"
        }
    
    def reset(self):
        """Сбрасывает состояние fake API"""
        self._tasks.clear()
        self._task_counter = 0
        self._fail_mode = False
        self._timeout_mode = False


# Глобальный экземпляр для тестов
_fake_api = None


def get_fake_kie_api() -> FakeKieAPI:
    """Получает глобальный экземпляр fake API"""
    global _fake_api
    if _fake_api is None:
        _fake_api = FakeKieAPI()
    return _fake_api
