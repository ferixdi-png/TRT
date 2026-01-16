#!/usr/bin/env python3
"""
Проверка соответствия параметров моделей в боте реальным параметрам Kie.ai API
Сравнивает:
1. models/kie_models.yaml (локальный реестр)
2. models/kie_models_source_of_truth.json (source of truth)
3. API /v1/market/list (если доступно)
"""

import sys
import json
import os
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from collections import defaultdict

# Добавляем корневую директорию
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    print("⚠️ PyYAML not installed. Install with: pip install PyYAML")

# Цвета для вывода
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_success(msg):
    print(f"{Colors.GREEN}[OK] {msg}{Colors.RESET}")

def print_warning(msg):
    print(f"{Colors.YELLOW}[WARN] {msg}{Colors.RESET}")

def print_error(msg):
    print(f"{Colors.RED}[ERROR] {msg}{Colors.RESET}")

def print_info(msg):
    print(f"{Colors.BLUE}[INFO] {msg}{Colors.RESET}")

def print_header(msg):
    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{msg}{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}\n")


class ModelParameterChecker:
    def __init__(self):
        self.root_dir = Path(__file__).parent.parent
        self.yaml_file = self.root_dir / "models" / "kie_models.yaml"
        self.source_of_truth_file = self.root_dir / "models" / "kie_models_source_of_truth.json"
        self.issues = defaultdict(list)
        self.stats = {
            'total_models': 0,
            'checked_models': 0,
            'issues_found': 0,
            'missing_params': 0,
            'mismatched_params': 0,
            'missing_models': 0
        }
    
    def load_yaml_models(self) -> Dict[str, Any]:
        """Загружает модели из YAML"""
        if not YAML_AVAILABLE:
            return {}
        
        if not self.yaml_file.exists():
            print_warning(f"YAML file not found: {self.yaml_file}")
            return {}
        
        try:
            with open(self.yaml_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                return data.get('models', {})
        except Exception as e:
            print_error(f"Failed to load YAML: {e}")
            return {}
    
    def load_source_of_truth(self) -> Dict[str, Any]:
        """Загружает source of truth JSON"""
        if not self.source_of_truth_file.exists():
            print_warning(f"Source of truth file not found: {self.source_of_truth_file}")
            return {}
        
        try:
            with open(self.source_of_truth_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print_error(f"Failed to load source of truth: {e}")
            return {}
    
    async def load_api_models(self) -> List[Dict[str, Any]]:
        """Загружает модели из API (если доступно)"""
        api_key = os.getenv('KIE_API_KEY')
        if not api_key:
            print_info("KIE_API_KEY not set, skipping API check")
            return []
        
        try:
            from app.integrations.kie_client import get_kie_client
            client = get_kie_client()
            models = await client.list_models()
            await client.close()
            return models if models else []
        except Exception as e:
            print_warning(f"Failed to load from API: {e}")
            return []
    
    def normalize_model_id(self, model_id: str) -> str:
        """Нормализует ID модели для сравнения"""
        return model_id.lower().strip().replace('_', '-').replace(' ', '-')
    
    def extract_params_from_yaml(self, model_data: Dict[str, Any]) -> Dict[str, Any]:
        """Извлекает параметры из YAML модели"""
        params = {}
        
        # input_params из YAML
        input_params = model_data.get('input_params', {})
        if isinstance(input_params, dict):
            # Нормализуем структуру: если это словарь с вложенными словарями (type, required, etc)
            for key, value in input_params.items():
                if isinstance(value, dict):
                    # Извлекаем тип и другие свойства
                    param_type = value.get('type', 'string')
                    params[key] = {
                        'type': param_type,
                        'required': value.get('required', False),
                        'default': value.get('default'),
                        'values': value.get('values'),  # для enum
                        'min': value.get('min'),
                        'max': value.get('max')
                    }
                else:
                    params[key] = value
        
        # Также проверяем другие поля
        if 'model_type' in model_data:
            params['_model_type'] = model_data['model_type']
        
        return params
    
    def extract_params_from_source_of_truth(self, model_id: str, sot_data: Dict[str, Any]) -> Dict[str, Any]:
        """Извлекает параметры из source of truth"""
        params = {}
        
        # Ищем модель в source of truth
        models = sot_data.get('models', {})
        if model_id in models:
            model_info = models[model_id]
            # Извлекаем input из source of truth (структура: input -> param_name -> type/required/etc)
            input_data = model_info.get('input', {})
            if isinstance(input_data, dict):
                for key, value in input_data.items():
                    if isinstance(value, dict):
                        params[key] = {
                            'type': value.get('type', 'string'),
                            'required': value.get('required', False),
                            'default': value.get('default'),
                            'values': value.get('values'),
                            'min': value.get('min'),
                            'max': value.get('max')
                        }
                    else:
                        params[key] = value
            # Также проверяем endpoint
            if 'endpoint' in model_info:
                params['_endpoint'] = model_info['endpoint']
        
        return params
    
    def extract_params_from_api(self, model_id: str, api_models: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Извлекает параметры из API ответа"""
        params = {}
        
        # Ищем модель в API ответе
        for model in api_models:
            api_model_id = model.get('id') or model.get('model_id') or model.get('name', '')
            if self.normalize_model_id(api_model_id) == self.normalize_model_id(model_id):
                # Извлекаем параметры из API
                if 'input' in model:
                    params = model['input'].copy() if isinstance(model['input'], dict) else {}
                elif 'params' in model:
                    params = model['params'].copy() if isinstance(model['params'], dict) else {}
                break
        
        return params
    
    def compare_params(self, yaml_params: Dict[str, Any], sot_params: Dict[str, Any], 
                      api_params: Dict[str, Any], model_id: str) -> List[str]:
        """Сравнивает параметры и возвращает список проблем"""
        issues = []
        
        # Собираем все уникальные параметры
        all_params = set()
        all_params.update(yaml_params.keys())
        all_params.update(sot_params.keys())
        all_params.update(api_params.keys())
        
        # Убираем служебные параметры
        all_params = {p for p in all_params if not p.startswith('_')}
        
        # Проверяем каждый параметр
        for param in all_params:
            yaml_val = yaml_params.get(param)
            sot_val = sot_params.get(param)
            api_val = api_params.get(param) if api_params else None
            
            # Если параметр есть в YAML, но нет в source of truth
            if yaml_val is not None and sot_val is None:
                issues.append(f"Parameter '{param}' exists in YAML but missing in source_of_truth")
            
            # Если параметр есть в source of truth, но нет в YAML
            if sot_val is not None and yaml_val is None:
                issues.append(f"Parameter '{param}' exists in source_of_truth but missing in YAML")
            
            # Если параметр есть в API, но нет в YAML
            if api_val is not None and yaml_val is None:
                issues.append(f"Parameter '{param}' exists in API but missing in YAML")
            
            # Детальная проверка структуры параметра
            if yaml_val is not None and sot_val is not None:
                # Если оба - словари с метаданными
                if isinstance(yaml_val, dict) and isinstance(sot_val, dict):
                    yaml_type = yaml_val.get('type', 'unknown')
                    sot_type = sot_val.get('type', 'unknown')
                    if yaml_type != sot_type:
                        issues.append(f"Parameter '{param}' type mismatch: YAML={yaml_type}, SOT={sot_type}")
                    
                    yaml_required = yaml_val.get('required', False)
                    sot_required = sot_val.get('required', False)
                    if yaml_required != sot_required:
                        issues.append(f"Parameter '{param}' required mismatch: YAML={yaml_required}, SOT={sot_required}")
                    
                    # Проверяем enum values
                    yaml_values = yaml_val.get('values')
                    sot_values = sot_val.get('values')
                    if yaml_values and sot_values:
                        yaml_set = set(yaml_values) if isinstance(yaml_values, list) else set()
                        sot_set = set(sot_values) if isinstance(sot_values, list) else set()
                        if yaml_set != sot_set:
                            missing_in_yaml = sot_set - yaml_set
                            missing_in_sot = yaml_set - sot_set
                            if missing_in_yaml:
                                issues.append(f"Parameter '{param}' missing enum values in YAML: {missing_in_yaml}")
                            if missing_in_sot:
                                issues.append(f"Parameter '{param}' missing enum values in SOT: {missing_in_sot}")
                # Простая проверка типов для примитивных значений
                elif type(yaml_val) != type(sot_val):
                    issues.append(f"Parameter '{param}' type mismatch: YAML={type(yaml_val).__name__}, SOT={type(sot_val).__name__}")
        
        return issues
    
    async def check_all_models(self):
        """Проверяет все модели"""
        print_header("ЗАГРУЗКА ДАННЫХ")
        
        # Загружаем данные
        yaml_models = self.load_yaml_models()
        sot_data = self.load_source_of_truth()
        api_models = await self.load_api_models()
        
        print_info(f"YAML models: {len(yaml_models)}")
        print_info(f"Source of truth models: {len(sot_data.get('models', {}))}")
        print_info(f"API models: {len(api_models)}")
        
        self.stats['total_models'] = len(yaml_models)
        
        print_header("ПРОВЕРКА ПАРАМЕТРОВ")
        
        # Проверяем каждую модель из YAML
        for model_id, model_data in yaml_models.items():
            self.stats['checked_models'] += 1
            
            # Извлекаем параметры
            yaml_params = self.extract_params_from_yaml(model_data)
            sot_params = self.extract_params_from_source_of_truth(model_id, sot_data)
            api_params = self.extract_params_from_api(model_id, api_models) if api_models else {}
            
            # Сравниваем
            issues = self.compare_params(yaml_params, sot_params, api_params, model_id)
            
            if issues:
                self.stats['issues_found'] += len(issues)
                self.issues[model_id] = issues
                print_warning(f"Model '{model_id}': {len(issues)} issues")
                for issue in issues:
                    print(f"  - {issue}")
            else:
                print_success(f"Model '{model_id}': OK")
        
        # Проверяем модели из source of truth, которых нет в YAML
        sot_models = sot_data.get('models', {})
        yaml_model_ids = set(yaml_models.keys())
        sot_model_ids = set(sot_models.keys())
        
        missing_in_yaml = sot_model_ids - yaml_model_ids
        if missing_in_yaml:
            self.stats['missing_models'] = len(missing_in_yaml)
            print_warning(f"Models in source_of_truth but not in YAML: {len(missing_in_yaml)}")
            for model_id in list(missing_in_yaml)[:10]:  # Показываем первые 10
                print(f"  - {model_id}")
    
    def print_report(self):
        """Выводит финальный отчет"""
        print_header("ФИНАЛЬНЫЙ ОТЧЕТ")
        
        print(f"Всего моделей: {self.stats['total_models']}")
        print(f"Проверено моделей: {self.stats['checked_models']}")
        print(f"Найдено проблем: {self.stats['issues_found']}")
        print(f"Моделей с проблемами: {len(self.issues)}")
        print(f"Моделей отсутствующих в YAML: {self.stats['missing_models']}")
        
        if self.issues:
            print_header("ДЕТАЛИ ПРОБЛЕМ")
            for model_id, issues in list(self.issues.items())[:20]:  # Первые 20
                print(f"\n{Colors.BOLD}Model: {model_id}{Colors.RESET}")
                for issue in issues[:5]:  # Первые 5 проблем
                    print(f"  - {issue}")
        else:
            print_success("Все параметры соответствуют!")
        
        # Рекомендации
        if self.issues:
            print_header("РЕКОМЕНДАЦИИ")
            print("1. Проверьте несоответствия параметров между YAML и source_of_truth")
            print("2. Обновите YAML файл с параметрами из API (если доступно)")
            print("3. Убедитесь, что все обязательные параметры присутствуют")
            print("4. Проверьте типы параметров (string, int, float, bool, array)")


async def main():
    """Главная функция"""
    checker = ModelParameterChecker()
    await checker.check_all_models()
    checker.print_report()
    
    # Возвращаем код выхода
    return 0 if not checker.issues else 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

