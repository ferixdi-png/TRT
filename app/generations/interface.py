"""
Единый интерфейс для генераций
Все генерации возвращают стандартизированный результат
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime


class GenerationStatus(Enum):
    """Статус генерации"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class GenerationResult:
    """Стандартизированный результат генерации"""
    status: GenerationStatus
    output: Optional[Any] = None  # Результат генерации (текст, изображение, и т.д.)
    meta: Dict[str, Any] = None  # Метаданные (model_id, params, и т.д.)
    cost: float = 0.0  # Стоимость в рублях
    timings: Dict[str, float] = None  # Временные метрики
    prompt_preview: str = ""  # Превью промпта
    error: Optional[str] = None  # Ошибка, если есть
    task_id: Optional[str] = None  # ID задачи в KIE API
    
    def __post_init__(self):
        if self.meta is None:
            self.meta = {}
        if self.timings is None:
            self.timings = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует в словарь"""
        return {
            "status": self.status.value,
            "output": self.output,
            "meta": self.meta,
            "cost": self.cost,
            "timings": self.timings,
            "prompt_preview": self.prompt_preview[:100] if self.prompt_preview else "",
            "error": self.error,
            "task_id": self.task_id
        }


class GenerationInterface:
    """Единый интерфейс для всех генераций"""
    
    @staticmethod
    def create_status_message(
        result: GenerationResult,
        user_lang: str = 'ru',
        progress: Optional[float] = None
    ) -> str:
        """Создаёт сообщение о статусе генерации для пользователя"""
        if user_lang == 'ru':
            if result.status == GenerationStatus.PENDING:
                return "⏳ Генерация поставлена в очередь..."
            elif result.status == GenerationStatus.PROCESSING:
                progress_text = f" ({int(progress * 100)}%)" if progress else ""
                return f"🔄 Генерация выполняется{progress_text}..."
            elif result.status == GenerationStatus.COMPLETED:
                return "✅ Генерация завершена!"
            elif result.status == GenerationStatus.FAILED:
                return f"❌ Ошибка: {result.error or 'Неизвестная ошибка'}"
            else:
                return "⏸️ Генерация отменена"
        else:
            if result.status == GenerationStatus.PENDING:
                return "⏳ Generation queued..."
            elif result.status == GenerationStatus.PROCESSING:
                progress_text = f" ({int(progress * 100)}%)" if progress else ""
                return f"🔄 Processing{progress_text}..."
            elif result.status == GenerationStatus.COMPLETED:
                return "✅ Generation completed!"
            elif result.status == GenerationStatus.FAILED:
                return f"❌ Error: {result.error or 'Unknown error'}"
            else:
                return "⏸️ Generation cancelled"
    
    @staticmethod
    def create_result_message(
        result: GenerationResult,
        user_lang: str = 'ru'
    ) -> str:
        """Создаёт итоговое сообщение с результатом"""
        if result.status != GenerationStatus.COMPLETED:
            return GenerationInterface.create_status_message(result, user_lang)
        
        if user_lang == 'ru':
            message = "✅ <b>Генерация завершена!</b>\n\n"
            if result.meta.get("model_name"):
                message += f"Модель: {result.meta['model_name']}\n"
            if result.cost > 0:
                message += f"Стоимость: {result.cost:.2f} ₽\n"
            if result.timings.get("total"):
                message += f"Время: {result.timings['total']:.1f} сек\n"
            message += "\n💡 <b>Что можно сделать дальше:</b>\n"
            message += "• Сгенерировать ещё раз\n"
            message += "• Попробовать другую модель\n"
            message += "• Изменить параметры"
        else:
            message = "✅ <b>Generation completed!</b>\n\n"
            if result.meta.get("model_name"):
                message += f"Model: {result.meta['model_name']}\n"
            if result.cost > 0:
                message += f"Cost: {result.cost:.2f} ₽\n"
            if result.timings.get("total"):
                message += f"Time: {result.timings['total']:.1f} sec\n"
            message += "\n💡 <b>What you can do next:</b>\n"
            message += "• Generate again\n"
            message += "• Try another model\n"
            message += "• Change parameters"
        
        return message

