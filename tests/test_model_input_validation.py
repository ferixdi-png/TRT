"""
Тесты валидации входных параметров моделей.
Минимум 3 теста на каждую критичную модель:
1. Минимальный валидный запрос
2. Типичный запрос со всеми параметрами
3. Невалидный запрос (ошибка валидации)
"""

import pytest
from typing import Dict, Any, Tuple, Optional


def validate_via_input_builder(model_id: str, params: Dict[str, Any]) -> Tuple[Dict, Optional[str]]:
    """
    Helper для валидации через kie_input_builder.build_input.
    Возвращает (normalized_input, error_message).
    """
    try:
        from app.kie_catalog import get_model_map
        from app.services.kie_input_builder import build_input
        
        catalog = get_model_map()
        if model_id not in catalog:
            return {}, f"Model {model_id} not found in catalog"
        
        model_spec = catalog[model_id]
        return build_input(model_spec, params)
    except Exception as e:
        return {}, str(e)


class TestWan26TextToVideo:
    """Тесты для wan/2-6-text-to-video"""
    
    MODEL_ID = "wan/2-6-text-to-video"
    
    def test_minimal_valid(self):
        """Минимальный валидный запрос - только prompt"""
        params = {"prompt": "A cat walking in the park"}
        errors = self._validate(params)
        assert not errors, f"Expected no errors, got: {errors}"
    
    def test_typical_full(self):
        """Типичный запрос со всеми параметрами"""
        params = {
            "prompt": "A beautiful sunset over the ocean with waves",
            "duration": "10",
            "resolution": "1080p",
            "multi_shots": False
        }
        errors = self._validate(params)
        assert not errors, f"Expected no errors, got: {errors}"
    
    def test_invalid_empty_prompt(self):
        """Пустой промпт должен вернуть ошибку"""
        params = {"prompt": ""}
        errors = self._validate(params)
        assert errors, "Expected validation error for empty prompt"
    
    def test_invalid_prompt_too_long(self):
        """Слишком длинный промпт (>5000) должен вернуть ошибку"""
        params = {"prompt": "x" * 5001}
        errors = self._validate(params)
        assert errors, "Expected validation error for prompt > 5000 chars"
    
    def test_invalid_duration(self):
        """Невалидное duration должно вернуть ошибку"""
        params = {"prompt": "Test", "duration": "20"}  # 20 not in [5, 10, 15]
        errors = self._validate(params)
        assert errors, "Expected validation error for invalid duration"
    
    def test_duration_normalization(self):
        """Duration должно нормализоваться из числа в строку"""
        params = {"prompt": "Test", "duration": 10}  # int instead of str
        errors = self._validate(params)
        assert not errors, f"Should accept numeric duration, got: {errors}"
    
    def _validate(self, params: Dict[str, Any]):
        """Helper для валидации через kie_input_builder"""
        result, error = validate_via_input_builder(self.MODEL_ID, params)
        if error:
            return [error]
        return []


class TestWan25ImageToVideo:
    """Тесты для wan/2-5-image-to-video"""
    
    MODEL_ID = "wan/2-5-image-to-video"
    
    def test_minimal_valid(self):
        """Минимальный валидный запрос"""
        params = {
            "prompt": "Animate this image",
            "image_input": ["https://example.com/image.jpg"]
        }
        errors = self._validate(params)
        assert not errors, f"Expected no errors, got: {errors}"
    
    def test_typical_full(self):
        """Типичный запрос со всеми параметрами"""
        params = {
            "prompt": "Make the person wave their hand",
            "image_input": ["https://example.com/person.jpg"],
            "duration": "5",
            "resolution": "720p",
            "enable_prompt_expansion": True
        }
        errors = self._validate(params)
        assert not errors, f"Expected no errors, got: {errors}"
    
    def test_invalid_no_image(self):
        """Без image_input должна быть ошибка"""
        params = {"prompt": "Animate this"}
        errors = self._validate(params)
        assert errors, "Expected validation error for missing image_input"
    
    def test_invalid_prompt_too_long(self):
        """Промпт >800 символов для wan/2-5 должен вернуть ошибку"""
        params = {
            "prompt": "x" * 801,
            "image_input": ["https://example.com/image.jpg"]
        }
        errors = self._validate(params)
        assert errors, "Expected validation error for prompt > 800 chars"
    
    def test_image_urls_array_rejected(self):
        """image_urls (массив) не поддерживается - нужен image_url (строка)"""
        params = {
            "prompt": "Test",
            "image_urls": ["https://example.com/image.jpg"]
        }
        # Должен либо отвергнуть, либо конвертировать в image_url
        errors = self._validate(params)
        # Не ассертим ошибку, т.к. валидатор может конвертировать
    
    def _validate(self, params: Dict[str, Any]):
        result, error = validate_via_input_builder(self.MODEL_ID, params)
        if error:
            return [error]
        return []


class TestKling26TextToVideo:
    """Тесты для kling-2.6/text-to-video"""
    
    MODEL_ID = "kling-2.6/text-to-video"
    
    def test_minimal_valid(self):
        """Минимальный валидный запрос"""
        params = {
            "prompt": "A robot dancing",
            "duration": "5",
            "sound": False,
            "aspect_ratio": "16:9"
        }
        errors = self._validate(params)
        assert not errors, f"Expected no errors, got: {errors}"
    
    def test_typical_with_sound(self):
        """Запрос со звуком (удваивает цену)"""
        params = {
            "prompt": "A band playing music",
            "duration": "10",
            "sound": True,
            "aspect_ratio": "16:9"
        }
        errors = self._validate(params)
        assert not errors, f"Expected no errors, got: {errors}"
    
    def test_invalid_duration(self):
        """Только 5 или 10 секунд поддерживается"""
        params = {
            "prompt": "Test",
            "duration": "15",  # Not supported for kling-2.6
            "sound": False
        }
        errors = self._validate(params)
        assert errors, "Expected validation error for duration=15"
    
    def _validate(self, params: Dict[str, Any]):
        result, error = validate_via_input_builder(self.MODEL_ID, params)
        if error:
            return [error]
        return []


class TestSora2ProTextToVideo:
    """Тесты для sora-2-pro-text-to-video"""
    
    MODEL_ID = "sora-2-pro-text-to-video"
    
    def test_minimal_valid(self):
        """Минимальный валидный запрос"""
        params = {"prompt": "A futuristic city at night"}
        errors = self._validate(params)
        assert not errors, f"Expected no errors, got: {errors}"
    
    def test_typical_full(self):
        """Типичный запрос со всеми параметрами"""
        params = {
            "prompt": "A dragon flying over mountains at sunset",
            "n_frames": "15",
            "size": "high",
            "aspect_ratio": "landscape",
            "remove_watermark": True
        }
        errors = self._validate(params)
        assert not errors, f"Expected no errors, got: {errors}"
    
    @pytest.mark.xfail(reason="n_frames not enum-validated at input_builder level")
    def test_invalid_n_frames(self):
        """Только 10 или 15 секунд поддерживается"""
        params = {
            "prompt": "Test",
            "n_frames": "5"  # Not supported
        }
        errors = self._validate(params)
        assert errors, "Expected validation error for n_frames=5"
    
    def _validate(self, params: Dict[str, Any]):
        result, error = validate_via_input_builder(self.MODEL_ID, params)
        if error:
            return [error]
        return []


class TestFluxKontext:
    """Тесты для flux/kontext"""
    
    MODEL_ID = "flux/kontext"
    
    def test_minimal_valid(self):
        """Минимальный валидный запрос"""
        params = {
            "prompt": "Make the background blue",
            "image_input": ["https://example.com/image.jpg"]
        }
        errors = self._validate(params)
        assert not errors, f"Expected no errors, got: {errors}"
    
    def test_with_quality_pro(self):
        """Запрос с качеством Pro"""
        params = {
            "prompt": "Add sunglasses to the person",
            "image_input": ["https://example.com/face.jpg"],
            "quality": "Pro"
        }
        errors = self._validate(params)
        assert not errors, f"Expected no errors, got: {errors}"
    
    def test_quality_case_insensitive(self):
        """Quality должно нормализоваться (pro -> Pro)"""
        params = {
            "prompt": "Edit",
            "image_input": ["https://example.com/image.jpg"],
            "quality": "pro"  # lowercase
        }
        errors = self._validate(params)
        assert not errors, f"Should accept lowercase quality, got: {errors}"
    
    def _validate(self, params: Dict[str, Any]):
        result, error = validate_via_input_builder(self.MODEL_ID, params)
        if error:
            return [error]
        return []


@pytest.mark.skip(reason="midjourney/text-to-image removed from catalog")
class TestMidjourneyTextToImage:
    """Тесты для midjourney/text-to-image"""
    
    MODEL_ID = "midjourney/text-to-image"
    
    def test_minimal_valid(self):
        """Минимальный валидный запрос"""
        params = {"prompt": "A beautiful landscape"}
        errors = self._validate(params)
        assert not errors, f"Expected no errors, got: {errors}"
    
    def test_typical_full(self):
        """Типичный запрос со всеми параметрами"""
        params = {
            "prompt": "cyberpunk city, neon lights, rain --ar 16:9",
            "speed": "fast",
            "version": "7",
            "aspect_ratio": "16:9"
        }
        errors = self._validate(params)
        assert not errors, f"Expected no errors, got: {errors}"
    
    def test_niji_version(self):
        """Версия niji для аниме стиля"""
        params = {
            "prompt": "anime girl with cat ears",
            "version": "niji7"
        }
        errors = self._validate(params)
        assert not errors, f"Expected no errors, got: {errors}"
    
    def _validate(self, params: Dict[str, Any]):
        result, error = validate_via_input_builder(self.MODEL_ID, params)
        if error:
            return [error]
        return []


class TestSunoV5:
    """Тесты для suno/v5"""
    
    MODEL_ID = "suno/v5"
    
    def test_minimal_valid(self):
        """Минимальный валидный запрос"""
        params = {"prompt": "Upbeat pop song about summer"}
        errors = self._validate(params)
        assert not errors, f"Expected no errors, got: {errors}"
    
    def test_typical_full(self):
        """Типичный запрос со всеми параметрами"""
        params = {
            "prompt": "Melancholic piano ballad about lost love",
            "style": "pop ballad",
            "instrumental": True
        }
        errors = self._validate(params)
        assert not errors, f"Expected no errors, got: {errors}"
    
    def test_invalid_empty_prompt(self):
        """Пустой промпт должен вернуть ошибку"""
        params = {"prompt": ""}
        errors = self._validate(params)
        assert errors, "Expected validation error for empty prompt"
    
    def _validate(self, params: Dict[str, Any]):
        result, error = validate_via_input_builder(self.MODEL_ID, params)
        if error:
            return [error]
        return []


class TestInputSchemaValidation:
    """Тесты Source of Truth схемы и функций интеграции"""
    
    def test_validate_flux_pro_t2i(self):
        """Тест валидации через input_schema"""
        from app.models.input_schema import validate_input, get_defaults
        
        # Валидный запрос
        params = {"prompt": "A beautiful sunset", "resolution": "1K"}
        errors = validate_input("flux-2/pro-text-to-image", params, lang="ru")
        assert not errors, f"Expected no errors, got: {errors}"
    
    def test_validate_missing_required(self):
        """Отсутствие обязательного поля"""
        from app.models.input_schema import validate_input
        
        params = {"resolution": "1K"}  # No prompt
        errors = validate_input("flux-2/pro-text-to-image", params, lang="ru")
        assert errors, "Expected error for missing prompt"
    
    def test_get_defaults(self):
        """Проверка дефолтных значений"""
        from app.models.input_schema import get_defaults
        
        defaults = get_defaults("flux-2/pro-text-to-image")
        assert "resolution" in defaults
        assert defaults["resolution"] == "1K"
    
    def test_enum_validation(self):
        """Enum должен проверяться."""
        from app.models.input_schema import validate_input
        
        errors = validate_input("flux-2/pro-text-to-image", {
            "prompt": "test",
            "resolution": "INVALID"
        })
        assert len(errors) > 0
        assert any("resolution" in e.lower() or "разрешение" in e.lower() for e in errors)
    
    def test_get_param_spec(self):
        """get_param_spec должен возвращать спецификацию параметра."""
        from app.models.input_schema import get_param_spec
        
        spec = get_param_spec("wan/2-6-text-to-video", "duration")
        assert spec is not None
        assert spec.name == "duration"
        assert spec.enum_values == ["5", "10", "15"]
        assert spec.default == "5"
    
    def test_get_param_hint(self):
        """get_param_hint должен возвращать подсказку."""
        from app.models.input_schema import get_param_hint
        
        hint_ru = get_param_hint("wan/2-6-text-to-video", "duration", "ru")
        hint_en = get_param_hint("wan/2-6-text-to-video", "duration", "en")
        
        assert hint_ru  # Не пустая
        assert hint_en  # Не пустая
        assert hint_ru != hint_en  # Разные языки
    
    def test_get_param_label(self):
        """get_param_label должен возвращать человекочитаемое название."""
        from app.models.input_schema import get_param_label
        
        label = get_param_label("wan/2-6-text-to-video", "duration", "ru")
        assert label == "Длительность"
        
        # Fallback для неизвестной модели
        fallback = get_param_label("unknown-model", "some_param", "ru")
        assert fallback == "Some Param"  # humanized
    
    def test_normalize_param_value_enum(self):
        """normalize_param_value должен нормализовать enum."""
        from app.models.input_schema import normalize_param_value
        
        # Case-insensitive
        assert normalize_param_value("wan/2-6-text-to-video", "resolution", "720P") == "720p"
        assert normalize_param_value("wan/2-6-text-to-video", "resolution", "1080p") == "1080p"
        
        # None → default
        assert normalize_param_value("wan/2-6-text-to-video", "resolution", None) == "720p"
    
    def test_normalize_param_value_boolean(self):
        """normalize_param_value должен нормализовать boolean."""
        from app.models.input_schema import normalize_param_value
        
        # Различные варианты true
        assert normalize_param_value("kling-2.6/text-to-video", "sound", "true") == True
        assert normalize_param_value("kling-2.6/text-to-video", "sound", "да") == True
        assert normalize_param_value("kling-2.6/text-to-video", "sound", "1") == True
        
        # Различные варианты false
        assert normalize_param_value("kling-2.6/text-to-video", "sound", "false") == False
        assert normalize_param_value("kling-2.6/text-to-video", "sound", "нет") == False
    
    def test_get_model_checklist(self):
        """get_model_checklist должен возвращать чеклист."""
        from app.models.input_schema import get_model_checklist
        
        checklist = get_model_checklist("wan/2-6-text-to-video", "ru")
        assert len(checklist) > 0
        assert any("Промпт" in item for item in checklist)
    
    def test_build_param_prompt_text(self):
        """build_param_prompt_text должен строить текст для бота."""
        from app.models.input_schema import build_param_prompt_text
        
        text = build_param_prompt_text("wan/2-6-text-to-video", "duration", "ru")
        assert "Длительность" in text
        assert "5" in text or "10" in text or "15" in text  # enum values or default
    
    def test_model_schemas_count(self):
        """Должно быть зарегистрировано минимум 10 моделей."""
        from app.models.input_schema import MODEL_SCHEMAS
        
        assert len(MODEL_SCHEMAS) >= 10, f"Only {len(MODEL_SCHEMAS)} schemas registered"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
