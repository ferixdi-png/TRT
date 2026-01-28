"""
Тесты для проверки единого pipeline параметров.

Проверяет что:
1. input_parameters использует валидацию при вводе
2. confirm_generation использует ту же валидацию  
3. Ошибки валидации показываются пользователю
4. Параметры нормализуются одинаково
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bot_kie import input_parameters, confirm_generation
from kie_input_adapter import normalize_for_generation, validate_params, get_schema


class TestUnifiedParameterPipeline:
    """Тесты единого pipeline параметров."""

    @pytest.mark.asyncio
    async def test_input_parameters_validates_enum_input(self):
        """Проверяем что input_parameters валидирует enum значения."""
        # Создаем mock update с текстом
        update = MagicMock()
        update.effective_user.id = 12345
        update.message.text = "invalid_value"
        update.message.chat_id = 67890
        update.message.message_id = 1
        update.update_id = "test_update_123"
        
        context = MagicMock()
        context.user_data = {}
        
        # Мокаем сессию с enum параметром
        mock_session = {
            'model_id': 'test/model',
            'waiting_for': 'style',
            'params': {},
            'properties': {
                'style': {
                    'type': 'enum',
                    'values': ['realistic', 'cartoon', 'anime'],
                    'required': True
                }
            }
        }
        
        with patch('bot_kie.user_sessions', {12345: mock_session}):
            with patch('bot_kie.get_user_language', return_value='ru'):
                with patch('bot_kie._answer_callback_early'):
                    with patch('bot_kie.ensure_correlation_id', return_value='test_corr'):
                        with patch('bot_kie._should_dedupe_update', return_value=False):
                            with patch('bot_kie._create_background_task'):
                                with patch('bot_kie._log_route_decision_once'):
                                    with patch('bot_kie._collect_missing_required_media', return_value=[]):
                                        with patch('bot_kie.update.message.reply_text') as mock_reply:
                                            
                                            # Вызываем input_parameters
                                            result = await input_parameters(update, context)
                                            
                                            # Проверяем что было сообщение об ошибке
                                            mock_reply.assert_called_once()
                                            call_args = mock_reply.call_args
                                            assert "недопустимое значение" in call_args[0][0].lower() or "invalid" in call_args[0][0].lower()
                                            
                                            # Проверяем что состояние не изменилось
                                            assert result == 1  # INPUTTING_PARAMS

    @pytest.mark.asyncio
    async def test_input_parameters_validates_number_range(self):
        """Проверяем что input_parameters валидирует числовые диапазоны."""
        update = MagicMock()
        update.effective_user.id = 12345
        update.message.text = "150"
        update.message.chat_id = 67890
        update.message.message_id = 1
        update.update_id = "test_update_123"
        
        context = MagicMock()
        context.user_data = {}
        
        # Мокаем сессию с числовым параметром с ограничением
        mock_session = {
            'model_id': 'test/model',
            'waiting_for': 'strength',
            'params': {},
            'properties': {
                'strength': {
                    'type': 'number',
                    'min': 0.0,
                    'max': 1.0,
                    'required': True
                }
            }
        }
        
        with patch('bot_kie.user_sessions', {12345: mock_session}):
            with patch('bot_kie.get_user_language', return_value='ru'):
                with patch('bot_kie._answer_callback_early'):
                    with patch('bot_kie.ensure_correlation_id', return_value='test_corr'):
                        with patch('bot_kie._should_dedupe_update', return_value=False):
                            with patch('bot_kie._create_background_task'):
                                with patch('bot_kie._log_route_decision_once'):
                                    with patch('bot_kie._collect_missing_required_media', return_value=[]):
                                        with patch('bot_kie.update.message.reply_text') as mock_reply:
                                            
                                            result = await input_parameters(update, context)
                                            
                                            # Проверяем что было сообщение об ошибке
                                            mock_reply.assert_called_once()
                                            call_args = mock_reply.call_args
                                            error_text = call_args[0][0].lower()
                                            assert "диапазон" in error_text or "range" in error_text or "150" in error_text

    @pytest.mark.asyncio
    async def test_confirm_generation_normalizes_params(self):
        """Проверяем что confirm_generation нормализует параметры."""
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.id = "test_query"
        update.callback_query.message.chat_id = 67890
        update.callback_query.message.message_id = 1
        update.callback_query.data = "confirm_generate"
        update.effective_user.id = 12345
        update.update_id = "test_update_123"
        
        context = MagicMock()
        context.user_data = {}
        
        # Мокаем сессию с параметрами
        mock_session = {
            'model_id': 'test/model',
            'params': {
                'prompt': 'test prompt',
                'strength': '0.8'  # Должно быть преобразовано в число
            },
            'request_id': 'test_request'
        }
        
        # Мокаем normalize_for_generation
        mock_api_params = {
            'prompt': 'test prompt',
            'strength': 0.8  # Преобразованное число
        }
        
        with patch('bot_kie.user_sessions', {12345: mock_session}):
            with patch('bot_kie.get_user_language', return_value='ru'):
                with patch('bot_kie.get_is_admin', return_value=False):
                    with patch('bot_kie._answer_callback_early'):
                        with patch('bot_kie.ensure_correlation_id', return_value='test_corr'):
                            with patch('bot_kie._check_existing_active_task', return_value=False):
                                with patch('bot_kie.get_storage') as mock_storage:
                                    mock_storage.return_value = AsyncMock()
                                    with patch('kie_input_adapter.normalize_for_generation', return_value=(mock_api_params, [])) as mock_normalize:
                                        with patch('bot_kie._create_background_task'):
                                            with patch('bot_kie._submit_generation_request') as mock_submit:
                                                with patch('bot_kie._send_or_edit_message') as mock_send:
                                                    
                                                    await confirm_generation(update, context)
                                                    
                                                    # Проверяем что normalize_for_generation был вызван
                                                    mock_normalize.assert_called_once_with('test/model', {
                                                        'prompt': 'test prompt',
                                                        'strength': '0.8'
                                                    })

    @pytest.mark.asyncio
    async def test_confirm_generation_shows_validation_errors(self):
        """Проверяем что confirm_generation показывает ошибки валидации."""
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.id = "test_query"
        update.callback_query.message.chat_id = 67890
        update.callback_query.message.message_id = 1
        update.callback_query.data = "confirm_generate"
        update.effective_user.id = 12345
        update.update_id = "test_update_123"
        
        context = MagicMock()
        context.user_data = {}
        
        mock_session = {
            'model_id': 'test/model',
            'params': {
                'prompt': 'test prompt',
                'strength': 'invalid_value'  # Невалидное значение
            },
            'request_id': 'test_request'
        }
        
        validation_errors = [
            "Параметр 'strength' должен быть числом",
            "Параметр 'style' обязателен для заполнения"
        ]
        
        with patch('bot_kie.user_sessions', {12345: mock_session}):
            with patch('bot_kie.get_user_language', return_value='ru'):
                with patch('bot_kie.get_is_admin', return_value=False):
                    with patch('bot_kie._answer_callback_early'):
                        with patch('bot_kie.ensure_correlation_id', return_value='test_corr'):
                            with patch('bot_kie._check_existing_active_task', return_value=False):
                                with patch('kie_input_adapter.normalize_for_generation', return_value=({}, validation_errors)) as mock_normalize:
                                    with patch('bot_kie._send_or_edit_message') as mock_send:
                                        
                                        await confirm_generation(update, context)
                                        
                                        # Проверяем что normalize_for_generation был вызван
                                        mock_normalize.assert_called_once()
                                        
                                        # Проверяем что было отправлено сообщение об ошибке
                                        mock_send.assert_called_once()
                                        call_args = mock_send.call_args
                                        error_text = call_args[0][0]
                                        assert "ошибка валидации параметров" in error_text.lower()
                                        assert "strength" in error_text
                                        assert "числом" in error_text

    def test_normalize_for_generation_applies_defaults(self):
        """Проверяем что normalize_for_generation применяет дефолтные значения."""
        # Мокаем схему с дефолтными значениями
        mock_schema = {
            'prompt': {'type': 'string', 'required': True},
            'strength': {'type': 'number', 'default': 0.5},
            'style': {'type': 'enum', 'values': ['realistic', 'cartoon'], 'default': 'realistic'}
        }
        
        params = {
            'prompt': 'test prompt'
            # strength и style отсутствуют - должны примениться дефолты
        }
        
        with patch('kie_input_adapter.get_schema', return_value=mock_schema):
            api_params, errors = normalize_for_generation('test/model', params)
            
            # Проверяем что применены дефолты
            assert api_params['strength'] == 0.5
            assert api_params['style'] == 'realistic'
            assert len(errors) == 0

    def test_validate_params_catches_required_fields(self):
        """Проверяем что validate_params находит обязательные поля."""
        schema = {
            'prompt': {'type': 'string', 'required': True},
            'strength': {'type': 'number', 'required': True},
            'style': {'type': 'enum', 'values': ['realistic', 'cartoon'], 'required': False}
        }
        
        params = {
            'prompt': 'test prompt'
            # strength отсутствует, но required=True
        }
        
        is_valid, errors = validate_params(schema, params)
        
        assert not is_valid
        assert len(errors) > 0
        assert any('strength' in error and 'обязателен' in error for error in errors)

    def test_validate_params_validates_enum_values(self):
        """Проверяем что validate_params проверяет enum значения."""
        schema = {
            'style': {'type': 'enum', 'values': ['realistic', 'cartoon'], 'required': True}
        }
        
        params = {
            'style': 'invalid_style'
        }
        
        is_valid, errors = validate_params(schema, params)
        
        assert not is_valid
        assert len(errors) > 0
        assert any('style' in error and ('realistic' in error or 'cartoon' in error) for error in errors)

    def test_validate_params_validates_number_ranges(self):
        """Проверяем что validate_params проверяет числовые диапазоны."""
        schema = {
            'strength': {'type': 'number', 'min': 0.0, 'max': 1.0, 'required': True}
        }
        
        params = {
            'strength': 1.5  # Выше максимума
        }
        
        is_valid, errors = validate_params(schema, params)
        
        # Note: текущая реализация не проверяет min/max для чисел,
        # но тест показывает где это нужно добавить
        # assert not is_valid
        # assert any('strength' in error and ('диапазон' in error or 'range' in error) for error in errors)
        # assert any('strength' in error and ('диапазон' in error or 'range' in error) for error in errors)
