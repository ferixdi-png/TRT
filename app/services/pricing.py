"""
Pricing Service - работа с ценами, топ-5 моделями и бесплатным доступом

Инварианты:
- Бесплатные генерации разрешены ТОЛЬКО через FAST TOOLS
- Только top-5 самых дешёвых SKU доступны бесплатно
- Детерминированный выбор топ-5
- Стабильные и тестируемые лимиты
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class TopModel:
    """Информация о модели в топ-5."""
    model_id: str
    model_name: str
    model_emoji: str
    sku_id: str
    price_rub: float
    unit: str
    params: Dict[str, Any]


class PricingService:
    """Сервис для работы с ценами и бесплатным доступом."""
    
    def __init__(self):
        self._top_models_cache: Optional[List[TopModel]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_seconds = 300  # 5 минут кэш
        
    def get_top_5_models(self) -> List[TopModel]:
        """
        Возвращает топ-5 самых дешёвых моделей.
        Детерминированный выбор по базовой цене.
        
        Returns:
            List[TopModel] - топ-5 моделей
        """
        # Проверяем кэш
        now = datetime.now()
        if (self._top_models_cache and 
            self._cache_timestamp and 
            (now - self._cache_timestamp).total_seconds() < self._cache_ttl_seconds):
            return self._top_models_cache
        
        # Загружаем данные
        models_data = self._load_all_models_with_pricing()
        
        # Фильтруем и сортируем
        valid_models = []
        for model_data in models_data:
            # Берем только самые дешёвые SKU для каждой модели
            cheapest_sku = self._get_cheapest_sku(model_data)
            if cheapest_sku:
                top_model = TopModel(
                    model_id=model_data['id'],
                    model_name=model_data.get('name', model_data['id']),
                    model_emoji=model_data.get('emoji', '🤖'),
                    sku_id=cheapest_sku['sku_id'],
                    price_rub=cheapest_sku['price_rub'],
                    unit=cheapest_sku.get('unit', 'generation'),
                    params=cheapest_sku.get('params', {})
                )
                valid_models.append(top_model)
        
        # Сортируем по цене (возрастание) и берем топ-5
        valid_models.sort(key=lambda x: x.price_rub)
        top_5 = valid_models[:5]
        
        # Кэшируем результат
        self._top_models_cache = top_5
        self._cache_timestamp = now
        
        logger.info(f"Top-5 models calculated: {[m.model_id for m in top_5]}")
        return top_5
    
    def _load_all_models_with_pricing(self) -> List[Dict[str, Any]]:
        """Загружает все модели с данными о ценах."""
        try:
            # Загружаем модели из реестра
            from app.models.yaml_registry import load_yaml_models
            yaml_models = load_yaml_models()
            
            # Загружаем цены
            pricing_data = self._load_pricing_data()
            
            # Объединяем данные
            models_with_pricing = []
            for model_id, model_data in yaml_models.items():
                # Ищем модель в прайсинге
                pricing_info = None
                for pricing_model in pricing_data:
                    if pricing_model.get('id') == model_id:
                        pricing_info = pricing_model
                        break
                
                if pricing_info:
                    combined_data = model_data.copy()
                    combined_data['id'] = model_id
                    combined_data['pricing'] = pricing_info
                    models_with_pricing.append(combined_data)
            
            logger.info(f"Loaded {len(models_with_pricing)} models with pricing data")
            return models_with_pricing
            
        except Exception as e:
            logger.error(f"Failed to load models with pricing: {e}")
            return []
    
    def _load_pricing_data(self) -> List[Dict[str, Any]]:
        """Загружает данные о ценах."""
        try:
            import yaml
            from pathlib import Path
            
            pricing_path = Path(__file__).parent.parent.parent / "data" / "kie_pricing_rub.yaml"
            with open(pricing_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            return data.get('models', [])
        except Exception as e:
            logger.error(f"Failed to load pricing data: {e}")
            return []
    
    def _get_cheapest_sku(self, model_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Возвращает самый дешёвый SKU для модели."""
        pricing_info = model_data.get('pricing', {})
        skus = pricing_info.get('skus', [])
        
        if not skus:
            return None
        
        # Ищем самый дешёвый SKU
        cheapest = None
        cheapest_price = float('inf')
        
        for sku in skus:
            price = sku.get('price_rub', 0)
            if price < cheapest_price:
                cheapest_price = price
                cheapest = sku.copy()
                # Добавляем sku_id для идентификации
                cheapest['sku_id'] = f"{model_data['id']}::{self._format_params(sku.get('params', {}))}"
        
        return cheapest
    
    def _format_params(self, params: Dict[str, Any]) -> str:
        """Форматирует параметры для SKU ID."""
        if not params:
            return "default"
        
        parts = []
        for key, value in sorted(params.items()):
            parts.append(f"{key}={value}")
        
        return "::".join(parts)
    
    def is_model_in_top_5(self, model_id: str) -> bool:
        """
        Проверяет, входит ли модель в топ-5.
        
        Args:
            model_id: ID модели
            
        Returns:
            True если модель в топ-5
        """
        top_models = self.get_top_5_models()
        return any(model.model_id == model_id for model in top_models)
    
    def is_free_generation_allowed(self, model_id: str, source: str) -> bool:
        """
        Проверяет разрешен ли бесплатный доступ.
        
        Args:
            model_id: ID модели
            source: источник запроса (например, 'fast_tools')
            
        Returns:
            True если бесплатный доступ разрешен
        """
        # Бесплатный доступ только через FAST TOOLS
        if source != 'fast_tools':
            return False
        
        # Только для топ-5 моделей
        return self.is_model_in_top_5(model_id)
    
    def get_free_models_for_ui(self, user_lang: str = 'ru') -> Tuple[List[TopModel], str]:
        """
        Возвращает модели для бесплатного доступа в UI.
        
        Args:
            user_lang: язык пользователя
            
        Returns:
            (models, error_message)
        """
        try:
            top_models = self.get_top_5_models()
            
            if not top_models:
                return [], "Бесплатные модели временно недоступны" if user_lang == 'ru' else "Free models temporarily unavailable"
            
            return top_models, ""
            
        except Exception as e:
            logger.error(f"Error getting free models: {e}")
            return [], "Ошибка загрузки моделей" if user_lang == 'ru' else "Error loading models"
    
    def clear_cache(self):
        """Очищает кэш топ-5 моделей."""
        self._top_models_cache = None
        self._cache_timestamp = None
        logger.info("Top-5 models cache cleared")


# Глобальный экземпляр сервиса
_pricing_service: Optional[PricingService] = None


def get_pricing_service() -> PricingService:
    """Возвращает глобальный экземпляр PricingService."""
    global _pricing_service
    if _pricing_service is None:
        _pricing_service = PricingService()
    return _pricing_service


def is_free_generation_allowed(model_id: str, source: str) -> bool:
    """
    Удобная функция для проверки бесплатного доступа.
    
    Args:
        model_id: ID модели
        source: источник запроса
        
    Returns:
        True если бесплатный доступ разрешен
    """
    service = get_pricing_service()
    return service.is_free_generation_allowed(model_id, source)


def get_top_5_models() -> List[TopModel]:
    """
    Удобная функция для получения топ-5 моделей.
    
    Returns:
        Список топ-5 моделей
    """
    service = get_pricing_service()
    return service.get_top_5_models()
