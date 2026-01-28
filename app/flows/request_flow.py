"""
Request Flow/Builder - единый пайплайн ввода параметров

Инварианты:
- Единый state machine для всех моделей
- Последовательный сбор обязательных параметров
- Опциональные параметры с дефолтами
- Поддержка media/text/enum параметров
- UX: кнопки опций + "назад/меню"
"""

import logging
from typing import Dict, Any, List, Optional, Tuple, Union
from enum import Enum
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class ParameterType(Enum):
    """Типы параметров."""
    STRING = "string"
    ENUM = "enum"
    ARRAY = "array"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    FLOAT = "float"


class MediaKind(Enum):
    """Типы медиа."""
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"


class FlowState(Enum):
    """Состояния flow."""
    COLLECTING = "collecting"
    VALIDATING = "validating"
    CONFIRMING = "confirming"
    COMPLETE = "complete"
    ERROR = "error"


class RequestFlow:
    """Единый flow для сбора параметров модели."""
    
    def __init__(self):
        self.current_state = FlowState.COLLECTING
        self.current_param_index = 0
        self.collected_params = {}
        self.param_history = []
        
    def initialize_flow(self, model_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Инициализирует flow для модели.
        
        Args:
            model_data: Данные модели из реестра
            
        Returns:
            Dict с параметрами flow
        """
        input_params = model_data.get('input', {})
        
        # Определяем порядок параметров
        required_params = []
        optional_params = []
        
        for param_name, param_info in input_params.items():
            param_data = {
                'name': param_name,
                'type': param_info.get('type', 'string'),
                'required': param_info.get('required', False),
                'default': param_info.get('default'),
                'max': param_info.get('max'),
                'values': param_info.get('values', []),
                'item_type': param_info.get('item_type'),
                'description': param_info.get('description', ''),
            }
            
            if param_data['required']:
                required_params.append(param_data)
            else:
                optional_params.append(param_data)
        
        # Определяем первичный ввод (image/video/text)
        primary_input = self._determine_primary_input(required_params + optional_params)
        
        flow_config = {
            'model_id': model_data.get('id'),
            'model_type': model_data.get('model_type'),
            'primary_input': primary_input,
            'required_params': required_params,
            'optional_params': optional_params,
            'all_params': required_params + optional_params,
            'current_index': 0,
            'state': FlowState.COLLECTING.value,
        }
        
        logger.info(f"Flow initialized for model {model_data.get('id')}: "
                   f"{len(required_params)} required, {len(optional_params)} optional")
        
        return flow_config
    
    def _determine_primary_input(self, params: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Определяет первичный параметр ввода (image/video/text).
        
        Args:
            params: Список всех параметров
            
        Returns:
            Primary param or None
        """
        # Ищем image/video параметры
        for param in params:
            param_name = param['name'].lower()
            param_type = param['type']
            
            # Image input
            if param_name in ['image_input', 'image_urls', 'image'] or param_type == 'array':
                if param_name in ['image_input', 'image_urls', 'image'] or \
                   param.get('item_type') == 'string':
                    return param
            
            # Video input
            elif param_name in ['video_input', 'video'] and param_type == 'array':
                return param
            
            # Audio input
            elif param_name in ['audio_input', 'audio'] and param_type == 'array':
                return param
        
        # Если нет media, primary это prompt/text
        for param in params:
            if param['name'] in ['prompt', 'text'] and param['type'] == 'string':
                return param
        
        return None
    
    def get_next_parameter(self, flow_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Возвращает следующий параметр для сбора.
        
        Args:
            flow_config: Текущая конфигурация flow
            
        Returns:
            Next parameter or None if complete
        """
        all_params = flow_config['all_params']
        current_index = flow_config['current_index']
        
        if current_index >= len(all_params):
            return None
        
        return all_params[current_index]
    
    def advance_to_next_parameter(self, flow_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Переходит к следующему параметру.
        
        Args:
            flow_config: Текущая конфигурация flow
            
        Returns:
            Updated flow_config
        """
        flow_config['current_index'] += 1
        
        # Проверяем завершенность
        if flow_config['current_index'] >= len(flow_config['all_params']):
            flow_config['state'] = FlowState.COMPLETE.value
        
        return flow_config
    
    def validate_parameter_value(self, param: Dict[str, Any], value: Any) -> Tuple[bool, str]:
        """
        Валидирует значение параметра.
        
        Args:
            param: Информация о параметре
            value: Значение для валидации
            
        Returns:
            (is_valid, error_message)
        """
        param_type = param['type']
        
        # String validation
        if param_type == 'string':
            if not isinstance(value, str):
                return False, "Значение должно быть текстом"
            
            max_length = param.get('max')
            if max_length and len(value) > max_length:
                return False, f"Текст слишком длинный (максимум {max_length} символов)"
        
        # Enum validation
        elif param_type == 'enum':
            valid_values = param.get('values', [])
            if value not in valid_values:
                return False, f"Выберите одно из: {', '.join(valid_values)}"
        
        # Array validation
        elif param_type == 'array':
            if not isinstance(value, list):
                return False, "Значение должно быть списком"
            
            max_items = param.get('max_items')
            if max_items and len(value) > max_items:
                return False, f"Слишком много элементов (максимум {max_items})"
        
        # Boolean validation
        elif param_type == 'boolean':
            if not isinstance(value, bool):
                return False, "Значение должно быть да/нет"
        
        # Number validation
        elif param_type in ['integer', 'float']:
            try:
                num_value = float(value) if param_type == 'float' else int(value)
                # TODO: добавить проверку min/max если нужно
            except (ValueError, TypeError):
                return False, "Значение должно быть числом"
        
        return True, ""
    
    def apply_defaults(self, flow_config: Dict[str, Any], collected: Dict[str, Any]) -> Dict[str, Any]:
        """
        Применяет значения по умолчанию для опциональных параметров.
        
        Args:
            flow_config: Конфигурация flow
            collected: Собранные параметры
            
        Returns:
            Parameters with defaults applied
        """
        result = collected.copy()
        
        for param in flow_config['optional_params']:
            param_name = param['name']
            if param_name not in result and 'default' in param:
                result[param_name] = param['default']
                logger.info(f"Applied default for {param_name}: {param['default']}")
        
        return result
    
    def is_complete(self, flow_config: Dict[str, Any]) -> bool:
        """Проверяет завершен ли сбор параметров."""
        return flow_config['state'] == FlowState.COMPLETE.value
    
    def get_progress_text(self, flow_config: Dict[str, Any], user_lang: str = 'ru') -> str:
        """
        Возвращает текст о прогрессе сбора параметров.
        
        Args:
            flow_config: Конфигурация flow
            user_lang: Язык пользователя
            
        Returns:
            Progress text
        """
        total = len(flow_config['all_params'])
        current = flow_config['current_index']
        
        if user_lang == 'ru':
            return f"Шаг {current + 1} из {total}"
        else:
            return f"Step {current + 1} of {total}"
    
    def format_parameter_prompt(self, param: Dict[str, Any], user_lang: str = 'ru') -> str:
        """
        Формирует текст запроса параметра.
        
        Args:
            param: Информация о параметре
            user_lang: Язык пользователя
            
        Returns:
            Formatted prompt text
        """
        param_name = param['name']
        param_type = param['type']
        required = param['required']
        description = param.get('description', '')
        
        if user_lang == 'ru':
            prompt = f"Введите {param_name}"
            if required:
                prompt += " (обязательно)"
            else:
                prompt += " (опционально)"
            
            if description:
                prompt += f"\n\n{description}"
            
            # Добавляем подсказки для разных типов
            if param_type == 'enum':
                values = param.get('values', [])
                prompt += f"\n\nВарианты: {', '.join(values)}"
            
            elif param_type == 'string':
                max_len = param.get('max')
                if max_len:
                    prompt += f"\n\nМаксимум символов: {max_len}"
            
            elif param_type == 'array':
                max_items = param.get('max_items')
                if max_items:
                    prompt += f"\n\nМаксимум элементов: {max_items}"
        else:
            # English version
            prompt = f"Enter {param_name}"
            if required:
                prompt += " (required)"
            else:
                prompt += " (optional)"
            
            if description:
                prompt += f"\n\n{description}"
            
            if param_type == 'enum':
                values = param.get('values', [])
                prompt += f"\n\nOptions: {', '.join(values)}"
        
        return prompt


# Глобальные функции для интеграции с существующим кодом

def create_request_flow() -> RequestFlow:
    """Создает новый экземпляр RequestFlow."""
    return RequestFlow()


def initialize_model_flow(model_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Инициализирует flow для модели.
    
    Args:
        model_data: Данные модели из реестра
        
    Returns:
        Flow configuration
    """
    flow = create_request_flow()
    return flow.initialize_flow(model_data)


def get_next_parameter_prompt(flow_config: Dict[str, Any], user_lang: str = 'ru') -> Optional[str]:
    """
    Возвращает текст для следующего параметра.
    
    Args:
        flow_config: Конфигурация flow
        user_lang: Язык пользователя
        
    Returns:
        Prompt text or None if complete
    """
    flow = create_request_flow()
    
    param = flow.get_next_parameter(flow_config)
    if not param:
        return None
    
    return flow.format_parameter_prompt(param, user_lang)


def advance_flow(flow_config: Dict[str, Any]) -> Dict[str, Any]:
    """
        Продвигает flow к следующему параметру.
        
        Args:
        flow_config: Текущая конфигурация flow
            
        Returns:
        Updated flow_config
        """
    flow = create_request_flow()
    return flow.advance_to_next_parameter(flow_config)
