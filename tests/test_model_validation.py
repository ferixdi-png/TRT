"""Тесты для валидатора моделей и flow."""

import pytest
from app.models.validator import ModelValidator, validate_models_for_ui
from app.flows.request_flow import RequestFlow, initialize_model_flow, get_next_parameter_prompt


@pytest.mark.asyncio
async def test_model_validator_all_valid():
    """Проверяем что все модели валидны."""
    validator = ModelValidator()
    result = validator.validate_all_models()
    
    assert 'error' not in result, f"Validation error: {result.get('error')}"
    assert result['total_models'] > 0, "No models found"
    assert len(result['invalid_models']) == 0, f"Invalid models found: {result['invalid_models']}"
    assert len(result['valid_models']) == result['total_models']


@pytest.mark.asyncio
async def test_validate_models_for_ui():
    """Проверяем быструю валидацию для UI."""
    valid_models, errors = validate_models_for_ui()
    
    assert len(errors) == 0, f"Validation errors: {errors}"
    assert len(valid_models) > 0, "No valid models for UI"
    
    # Проверяем что у всех моделей есть необходимые поля
    for model in valid_models:
        assert 'id' in model, f"Model missing id: {model}"
        assert 'model_type' in model, f"Model missing model_type: {model}"
        assert 'input' in model, f"Model missing input: {model}"
        assert 'pricing' in model, f"Model missing pricing: {model}"


def test_request_flow_initialization():
    """Тестируем инициализацию flow."""
    flow = RequestFlow()
    
    # Тестовая модель
    model_data = {
        'id': 'test-model',
        'model_type': 'text_to_image',
        'input': {
            'prompt': {
                'type': 'string',
                'required': True,
                'max': 1000
            },
            'aspect_ratio': {
                'type': 'enum',
                'required': True,
                'values': ['1:1', '4:3', '16:9']
            },
            'style': {
                'type': 'enum',
                'required': False,
                'values': ['realistic', 'anime'],
                'default': 'realistic'
            }
        }
    }
    
    flow_config = flow.initialize_flow(model_data)
    
    assert flow_config['model_id'] == 'test-model'
    assert flow_config['model_type'] == 'text_to_image'
    assert len(flow_config['required_params']) == 2
    assert len(flow_config['optional_params']) == 1
    assert flow_config['state'] == 'collecting'
    assert flow_config['current_index'] == 0


def test_request_flow_parameter_sequence():
    """Тестируем последовательность параметров."""
    model_data = {
        'id': 'test-model',
        'model_type': 'text_to_image',
        'input': {
            'prompt': {'type': 'string', 'required': True},
            'aspect_ratio': {'type': 'enum', 'required': True, 'values': ['1:1', '4:3']},
            'style': {'type': 'enum', 'required': False, 'values': ['realistic', 'anime']}
        }
    }
    
    flow_config = initialize_model_flow(model_data)
    flow = RequestFlow()
    
    # Первый параметр
    param1 = flow.get_next_parameter(flow_config)
    assert param1['name'] == 'prompt'
    assert param1['required'] == True
    
    # Переходим к следующему
    flow_config = flow.advance_to_next_parameter(flow_config)
    
    # Второй параметр
    param2 = flow.get_next_parameter(flow_config)
    assert param2['name'] == 'aspect_ratio'
    assert param2['required'] == True
    
    # Переходим к следующему
    flow_config = flow.advance_to_next_parameter(flow_config)
    
    # Третий параметр
    param3 = flow.get_next_parameter(flow_config)
    assert param3['name'] == 'style'
    assert param3['required'] == False
    
    # Переходим к следующему
    flow_config = flow.advance_to_next_parameter(flow_config)
    
    # Больше нет параметров
    param4 = flow.get_next_parameter(flow_config)
    assert param4 is None
    assert flow.is_complete(flow_config)


def test_request_flow_validation():
    """Тестируем валидацию параметров."""
    flow = RequestFlow()
    
    # String validation
    param = {'type': 'string', 'max': 10}
    is_valid, error = flow.validate_parameter_value(param, "test")
    assert is_valid == True
    assert error == ""
    
    is_valid, error = flow.validate_parameter_value(param, "too long text")
    assert is_valid == False
    assert "слишком длинный" in error
    
    # Enum validation
    param = {'type': 'enum', 'values': ['a', 'b', 'c']}
    is_valid, error = flow.validate_parameter_value(param, 'a')
    assert is_valid == True
    
    is_valid, error = flow.validate_parameter_value(param, 'd')
    assert is_valid == False
    assert "Выберите одно из" in error
    
    # Array validation
    param = {'type': 'array', 'max_items': 2}
    is_valid, error = flow.validate_parameter_value(param, ['a', 'b'])
    assert is_valid == True
    
    is_valid, error = flow.validate_parameter_value(param, ['a', 'b', 'c'])
    assert is_valid == False
    assert "Слишком много элементов" in error


def test_request_flow_defaults():
    """Тестируем применение значений по умолчанию."""
    flow = RequestFlow()
    
    flow_config = {
        'optional_params': [
            {'name': 'style', 'default': 'realistic'},
            {'name': 'quality', 'default': 'high'}
        ],
        'required_params': []
    }
    
    collected = {'prompt': 'test'}
    result = flow.apply_defaults(flow_config, collected)
    
    assert result['prompt'] == 'test'
    assert result['style'] == 'realistic'
    assert result['quality'] == 'high'


def test_request_flow_primary_input_detection():
    """Тестируем определение первичного ввода."""
    flow = RequestFlow()
    
    # Image-first model
    params = [
        {'name': 'image_input', 'type': 'array'},
        {'name': 'prompt', 'type': 'string'}
    ]
    primary = flow._determine_primary_input(params)
    assert primary['name'] == 'image_input'
    
    # Text-first model
    params = [
        {'name': 'prompt', 'type': 'string'},
        {'name': 'aspect_ratio', 'type': 'enum'}
    ]
    primary = flow._determine_primary_input(params)
    assert primary['name'] == 'prompt'
    
    # Video model - video_input не распознается как primary, вернется prompt
    params = [
        {'name': 'video_input', 'type': 'array'},
        {'name': 'prompt', 'type': 'string'}
    ]
    primary = flow._determine_primary_input(params)
    assert primary['name'] == 'prompt'  # video_input не в списке поддерживаемых


def test_parameter_prompt_formatting():
    """Тестируем форматирование запросов параметров."""
    flow = RequestFlow()
    
    # Required enum parameter
    param = {
        'name': 'aspect_ratio',
        'type': 'enum',
        'required': True,
        'values': ['1:1', '4:3', '16:9'],
        'description': 'Соотношение сторон изображения'
    }
    
    prompt = flow.format_parameter_prompt(param, user_lang='ru')
    assert 'Введите aspect_ratio' in prompt
    assert '(обязательно)' in prompt
    assert 'Соотношение сторон изображения' in prompt
    assert 'Варианты: 1:1, 4:3, 16:9' in prompt
    
    # Optional string parameter
    param = {
        'name': 'style',
        'type': 'string',
        'required': False,
        'max': 100,
        'description': 'Стиль изображения'
    }
    
    prompt = flow.format_parameter_prompt(param, user_lang='ru')
    assert 'Введите style' in prompt
    assert '(опционально)' in prompt
    assert 'Стиль изображения' in prompt
    assert 'Максимум символов: 100' in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
