"""
Model Validator - проверка валидности моделей согласно инвариантам проекта

Инварианты:
- Модель должна иметь цену/sku (из pricing YAML)
- Модель должна иметь тип (model_type)
- Модель должна иметь параметры ввода (input)
- Модель должна иметь маппинг в Kie.ai запрос
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class ModelValidator:
    """Валидатор моделей согласно инвариантам проекта."""
    
    def __init__(self):
        self.pricing_data = None
        self.models_data = None
        self.validation_errors = []
        self.valid_models = []
        self.invalid_models = []
        
    def load_pricing_data(self) -> bool:
        """Загружает данные о ценах из pricing YAML."""
        try:
            pricing_path = Path(__file__).parent.parent.parent / "data" / "kie_pricing_rub.yaml"
            if not pricing_path.exists():
                logger.error(f"Pricing file not found: {pricing_path}")
                return False
                
            import yaml
            with open(pricing_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                
            self.pricing_data = data.get('models', [])
            logger.info(f"Loaded pricing data for {len(self.pricing_data)} models")
            return True
        except Exception as e:
            logger.error(f"Failed to load pricing data: {e}")
            return False
    
    def load_models_data(self) -> bool:
        """Загружает данные моделей из models YAML."""
        try:
            from app.models.yaml_registry import load_yaml_models
            self.models_data = load_yaml_models()
            logger.info(f"Loaded models data for {len(self.models_data)} models")
            return True
        except Exception as e:
            logger.error(f"Failed to load models data: {e}")
            return False
    
    def validate_model(self, model_id: str, model_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Валидирует одну модель.
        
        Returns:
            (is_valid, error_messages)
        """
        errors = []
        
        # Проверка 1: model_type
        if 'model_type' not in model_data:
            errors.append("Missing model_type")
        elif not model_data['model_type']:
            errors.append("Empty model_type")
            
        # Проверка 2: input параметры
        if 'input' not in model_data:
            errors.append("Missing input section")
        elif not isinstance(model_data['input'], dict):
            errors.append("Invalid input section type")
        elif not model_data['input']:
            errors.append("Empty input section")
        else:
            # Проверяем что у input есть хотя бы один required параметр
            has_required = any(
                param_info.get('required', False) 
                for param_info in model_data['input'].values()
            )
            if not has_required:
                errors.append("No required parameters in input")
        
        # Проверка 3: цена/SKU
        if not self.pricing_data:
            errors.append("Pricing data not loaded")
        else:
            # Ищем модель в pricing
            pricing_found = False
            for pricing_model in self.pricing_data:
                if pricing_model.get('id') == model_id:
                    pricing_found = True
                    # Проверяем что есть SKU
                    skus = pricing_model.get('skus', [])
                    if not skus:
                        errors.append("No SKUs in pricing")
                    else:
                        # Проверяем что у SKU есть цена
                        for sku in skus:
                            if 'price_rub' not in sku:
                                errors.append(f"SKU missing price_rub: {sku}")
                    break
            
            if not pricing_found:
                errors.append("Model not found in pricing")
        
        # Проверка 4: маппинг в Kie.ai (проверяем что model_mode существует)
        if 'model_mode' not in model_data:
            errors.append("Missing model_mode (Kie.ai mapping)")
        
        return len(errors) == 0, errors
    
    def validate_all_models(self) -> Dict[str, Any]:
        """
        Валидирует все модели.
        
        Returns:
            {
                'total_models': int,
                'valid_models': List[str],
                'invalid_models': List[Dict],
                'validation_errors': List[str]
            }
        """
        if not self.load_pricing_data():
            return {'error': 'Failed to load pricing data'}
            
        if not self.load_models_data():
            return {'error': 'Failed to load models data'}
        
        self.valid_models = []
        self.invalid_models = []
        all_errors = []
        
        for model_id, model_data in self.models_data.items():
            is_valid, errors = self.validate_model(model_id, model_data)
            
            if is_valid:
                self.valid_models.append(model_id)
            else:
                self.invalid_models.append({
                    'model_id': model_id,
                    'errors': errors
                })
                all_errors.extend([f"{model_id}: {error}" for error in errors])
                
                # Логируем пропущенные модели
                logger.warning(f"MODEL_SKIPPED_INVALID: model_id={model_id}, errors={errors}")
        
        return {
            'total_models': len(self.models_data),
            'valid_models': self.valid_models,
            'invalid_models': self.invalid_models,
            'validation_errors': all_errors
        }
    
    def get_missing_fields_report(self) -> str:
        """Возвращает отчет о недостающих полях для каждой модели."""
        if not self.invalid_models:
            return "All models are valid! ✅"
        
        report = ["# Missing Fields Report\n"]
        report.append(f"Total invalid models: {len(self.invalid_models)}\n")
        
        for model_info in self.invalid_models:
            model_id = model_info['model_id']
            errors = model_info['errors']
            
            report.append(f"## {model_id}")
            for error in errors:
                report.append(f"- ❌ {error}")
            report.append("")
        
        return "\n".join(report)
    
    def get_valid_models_for_ui(self) -> List[Dict[str, Any]]:
        """
        Возвращает список валидных моделей для UI.
        
        Returns:
            List of model dicts with all required fields
        """
        if not self.valid_models or not self.models_data:
            return []
        
        valid_models_data = []
        for model_id in self.valid_models:
            if model_id in self.models_data:
                model_data = self.models_data[model_id].copy()
                model_data['id'] = model_id
                
                # Добавляем информацию о ценах
                if self.pricing_data:
                    for pricing_model in self.pricing_data:
                        if pricing_model.get('id') == model_id:
                            model_data['pricing'] = pricing_model
                            break
                
                valid_models_data.append(model_data)
        
        return valid_models_data


def validate_models_for_ui() -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Быстрая валидация моделей для UI.
    
    Returns:
        (valid_models, error_messages)
    """
    validator = ModelValidator()
    result = validator.validate_all_models()
    
    if 'error' in result:
        return [], [result['error']]
    
    error_messages = result['validation_errors']
    valid_models = validator.get_valid_models_for_ui()
    
    return valid_models, error_messages


if __name__ == "__main__":
    # Тестовый запуск
    validator = ModelValidator()
    result = validator.validate_all_models()
    
    print(f"Total models: {result['total_models']}")
    print(f"Valid models: {len(result['valid_models'])}")
    print(f"Invalid models: {len(result['invalid_models'])}")
    
    if result['invalid_models']:
        print("\n" + validator.get_missing_fields_report())
