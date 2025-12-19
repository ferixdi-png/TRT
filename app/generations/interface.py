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
                return (
                    "⏳ <b>Генерация поставлена в очередь</b>\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "✅ <b>Ваш запрос принят!</b>\n\n"
                    "💡 <b>Что происходит:</b>\n"
                    "• Ваш запрос добавлен в очередь обработки\n"
                    "• Нейросеть начнет работу в ближайшее время\n"
                    "• Обычно ожидание занимает несколько секунд\n\n"
                    "⏰ <b>Пожалуйста, подождите...</b>\n\n"
                    "💡 <b>Что будет дальше:</b>\n"
                    "• Вы получите уведомление, когда генерация начнется\n"
                    "• Затем будет показан прогресс выполнения\n"
                    "• Результат появится автоматически по готовности\n\n"
                    "✨ Не закрывайте бота, процесс идет!"
                )
            elif result.status == GenerationStatus.PROCESSING:
                progress_text = f"\n\n📊 <b>Прогресс:</b> {int(progress * 100)}%" if progress else ""
                return (
                    f"🔄 <b>Генерация выполняется</b>{progress_text}\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "✅ <b>Генерация началась!</b>\n\n"
                    "💡 <b>Что происходит:</b>\n"
                    "• Нейросеть анализирует ваш запрос\n"
                    "• Идет процесс создания контента\n"
                    "• Обычно это занимает 10-60 секунд\n\n"
                    "⏰ <b>Пожалуйста, подождите...</b>\n\n"
                    "💡 <b>Что будет дальше:</b>\n"
                    "• Результат появится автоматически по готовности\n"
                    "• Вы сможете сохранить или поделиться им\n"
                    "• Можете создать новую генерацию\n\n"
                    "✨ Не закрывайте бота, процесс идет!"
                )
            elif result.status == GenerationStatus.COMPLETED:
                return (
                    "🎉 <b>Генерация завершена!</b> 🎉\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "✅ <b>Ваш контент готов!</b>\n\n"
                    "💡 Результат будет показан ниже.\n"
                    "Наслаждайтесь! ✨"
                )
            elif result.status == GenerationStatus.FAILED:
                error_msg = result.error or 'Произошла ошибка при обработке запроса.'
                return (
                    f"❌ <b>Генерация не удалась</b>\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"💡 <b>Что произошло:</b>\n{error_msg}\n\n"
                    "🔧 <b>Что можно сделать:</b>\n"
                    "• Проверьте параметры запроса\n"
                    "• Попробуйте еще раз через несколько секунд\n"
                    "• Выберите другую модель, если проблема повторяется\n"
                    "• Вернитесь в главное меню и начните заново\n\n"
                    "💡 <b>Совет:</b> Если ошибка повторяется, попробуйте упростить запрос."
                )
            else:
                return (
                    "⏸️ <b>Генерация отменена</b>\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "💡 Генерация была отменена.\n\n"
                    "🔄 Вы можете начать новую генерацию из главного меню."
                )
        else:
            if result.status == GenerationStatus.PENDING:
                return (
                    "⏳ <b>Generation queued</b>\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "✅ <b>Your request has been accepted!</b>\n\n"
                    "💡 <b>What's happening:</b>\n"
                    "• Your request has been added to the processing queue\n"
                    "• The AI will start working soon\n"
                    "• Usually the wait takes a few seconds\n\n"
                    "⏰ <b>Please wait...</b>\n\n"
                    "You'll receive a notification when generation starts!"
                )
            elif result.status == GenerationStatus.PROCESSING:
                progress_text = f"\n\n📊 <b>Progress:</b> {int(progress * 100)}%" if progress else ""
                return (
                    f"🔄 <b>Processing</b>{progress_text}\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "💡 <b>What's happening:</b>\n"
                    "• The AI is analyzing your request\n"
                    "• Content is being created\n"
                    "• Usually this takes 10-60 seconds\n\n"
                    "⏰ <b>Please wait...</b>\n\n"
                    "You'll receive a notification when the result is ready!"
                )
            elif result.status == GenerationStatus.COMPLETED:
                return (
                    "🎉 <b>Generation completed!</b> 🎉\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "✅ <b>Your content is ready!</b>\n\n"
                    "💡 The result will be shown below.\n"
                    "Enjoy! ✨"
                )
            elif result.status == GenerationStatus.FAILED:
                error_msg = result.error or 'An error occurred while processing your request.'
                return (
                    f"❌ <b>Generation failed</b>\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"💡 <b>What happened:</b>\n{error_msg}\n\n"
                    "🔧 <b>What you can do:</b>\n"
                    "• Check your request parameters\n"
                    "• Try again in a few seconds\n"
                    "• Select a different model if the problem persists\n"
                    "• Return to the main menu and start over\n\n"
                    "💡 <b>Tip:</b> If the error repeats, try simplifying your request."
                )
            else:
                return (
                    "⏸️ <b>Generation cancelled</b>\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "💡 Generation was cancelled.\n\n"
                    "🔄 You can start a new generation from the main menu."
                )
    
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




