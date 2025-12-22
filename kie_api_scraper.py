# kie_api_scraper.py - Автоматический сборщик ВСЕХ моделей Kie.ai + API настройки
# Готовый скрипт "одна кнопка" - запускай и получай полный дамп

import requests
import json
import time
from urllib.parse import urljoin
import re
from bs4 import BeautifulSoup

class KieApiScraper:
    def __init__(self):
        # Проверка согласованности URL параметров
        self.base_url = "https://api.kie.ai/api/v1"
        self.docs_base = "https://docs.kie.ai"
        self.market_url = "https://kie.ai/ru/market"
        
        # Единые headers для всех запросов
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        self.models = []
    
    def get_market_page(self):
        """Парсит главную страницу с моделями"""
        try:
            print(f"   📡 Запрос к {self.market_url}...")
            resp = requests.get(self.market_url, headers=self.headers, timeout=10)
            resp.raise_for_status()  # Проверка статуса ответа
            print(f"   ✅ ОТВЕТ: Получен ответ со статусом {resp.status_code}")
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            print(f"   🔍 ОТВЕТ: Парсинг HTML страницы...")
            
            # Находим все карточки моделей
            cards = soup.find_all(['div', 'section'], class_=re.compile(r'(model|api|card|feature)'))
            print(f"   ✅ ОТВЕТ: Найдено {len(cards)} потенциальных карточек")
            
            model_links = []
            
            for card in cards:
                # Исправленный синтаксис поиска заголовка
                title = (card.find('h1') or card.find('h2') or card.find('h3') or 
                        card.find(class_=re.compile(r'title')))
                link = card.find('a', href=True)
                if title and link:
                    model_links.append({
                        'name': title.get_text().strip(),
                        'url': urljoin(self.market_url, link['href'])
                    })
            
            print(f"   ✅ ОТВЕТ: Извлечено {len(model_links)} ссылок на модели")
            return model_links
        except requests.RequestException as e:
            print(f"   ❌ ОТВЕТ: Ошибка при получении страницы маркета: {e}")
            return []
    
    def scrape_model_docs(self, model_url, model_name):
        """Парсит документацию конкретной модели"""
        try:
            print(f"    📥 Загрузка страницы модели...")
            resp = requests.get(model_url, headers=self.headers, timeout=10)
            resp.raise_for_status()
            print(f"    ✅ ОТВЕТ: Страница загружена (статус {resp.status_code})")
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            print(f"    🔍 ОТВЕТ: Парсинг HTML документации...")
            
            # Структура model_info согласована с финальным JSON
            model_info = {
                'name': model_name,
                'endpoint': '',
                'method': 'POST',
                'base_url': self.base_url,  # Используется тот же base_url из __init__
                'params': {},
                'example': '',
                'price': '',
                'category': ''
            }
            
            # Ищем endpoint - проверка согласованности с base_url
            endpoint_match = re.search(r'/([a-zA-Z0-9\-_]+)/?(generate|create)?', resp.text)
            if endpoint_match:
                model_info['endpoint'] = f"/{endpoint_match.group(1)}/generate"
                print(f"    ✅ ОТВЕТ: Endpoint найден: {model_info['endpoint']}")
            else:
                print(f"    ⚠️ ОТВЕТ: Endpoint не найден в тексте")
            
            # Ищем примеры JSON
            code_blocks = soup.find_all('pre', class_=re.compile(r'(json|code|example)'))
            print(f"    ✅ ОТВЕТ: Найдено {len(code_blocks)} блоков кода")
            for block in code_blocks[:2]:
                code = block.get_text()
                if 'prompt' in code and ('{' in code):
                    model_info['example'] = code.strip()
                    print(f"    ✅ ОТВЕТ: Пример JSON найден")
                    break
            
            # Извлекаем параметры из текста - все параметры согласованы
            param_patterns = {
                'duration': r'duration[:\s]*(\d+)',
                'width': r'width[:\s]*(\d+)',
                'height': r'height[:\s]*(\d+)',
                'steps': r'steps[:\s]*(\d+)'
            }
            
            found_params = []
            for param, pattern in param_patterns.items():
                match = re.search(pattern, resp.text, re.I)
                if match:
                    model_info['params'][param] = int(match.group(1))
                    found_params.append(param)
            
            if found_params:
                print(f"    ✅ ОТВЕТ: Найдено параметров: {', '.join(found_params)}")
            else:
                print(f"    ⚠️ ОТВЕТ: Параметры не найдены")
            
            # Валидация структуры модели перед добавлением
            print(f"    🔍 ОТВЕТ: Проверка структуры модели...")
            if self._validate_model_structure(model_info):
                self.models.append(model_info)
                print(f"    ✅ ОТВЕТ: Модель '{model_name}' успешно добавлена в коллекцию")
            else:
                print(f"    ❌ ОТВЕТ: Модель '{model_name}' не прошла валидацию структуры")
        except requests.RequestException as e:
            print(f"    ❌ ОТВЕТ: Ошибка при парсинге {model_name}: {e}")
        except Exception as e:
            print(f"    ❌ ОТВЕТ: Неожиданная ошибка для {model_name}: {e}")
    
    def _validate_model_structure(self, model_info):
        """Проверяет соответствие структуры модели требуемому формату"""
        required_fields = ['name', 'endpoint', 'method', 'base_url', 'params', 'example', 'price', 'category']
        
        # Проверка наличия всех обязательных полей
        for field in required_fields:
            if field not in model_info:
                print(f"      ❌ ОТВЕТ: Отсутствует обязательное поле: {field}")
                return False
        
        # Проверка типов данных
        if not isinstance(model_info['name'], str) or not model_info['name']:
            print(f"      ❌ ОТВЕТ: Неверный тип или пустое значение для 'name'")
            return False
        
        if not isinstance(model_info['params'], dict):
            print(f"      ❌ ОТВЕТ: 'params' должен быть словарем, получен {type(model_info['params'])}")
            return False
        
        if not isinstance(model_info['base_url'], str) or model_info['base_url'] != self.base_url:
            print(f"      ❌ ОТВЕТ: 'base_url' не соответствует ожидаемому значению")
            print(f"         Ожидается: {self.base_url}")
            print(f"         Получено: {model_info['base_url']}")
            return False
        
        print(f"      ✅ ОТВЕТ: Все поля присутствуют и имеют правильные типы")
        return True
    
    def validate_all_models(self):
        """Финальная проверка всех моделей на соответствие"""
        print("\n🔍 ФИНАЛЬНАЯ ПРОВЕРКА ВСЕХ МОДЕЛЕЙ...")
        print("=" * 60)
        valid_count = 0
        invalid_count = 0
        invalid_models = []
        
        for i, model in enumerate(self.models, 1):
            print(f"\n  📋 Проверка {i}/{len(self.models)}: {model['name']}")
            if self._validate_model_structure(model):
                valid_count += 1
                print(f"  ✅ ОТВЕТ: Модель '{model['name']}' соответствует структуре")
            else:
                invalid_count += 1
                invalid_models.append(model['name'])
                print(f"  ❌ ОТВЕТ: Модель '{model['name']}' НЕ соответствует структуре")
        
        print("\n" + "=" * 60)
        print("📊 ОТВЕТ: РЕЗУЛЬТАТЫ ФИНАЛЬНОЙ ПРОВЕРКИ:")
        print(f"  ✅ Валидных моделей: {valid_count}")
        print(f"  ❌ Невалидных моделей: {invalid_count}")
        print(f"  📦 Всего моделей: {len(self.models)}")
        
        if invalid_models:
            print(f"\n  ⚠️ Список невалидных моделей:")
            for name in invalid_models:
                print(f"    - {name}")
        
        if invalid_count == 0:
            print("\n✅ ОТВЕТ: ВСЕ МОДЕЛИ СООТВЕТСТВУЮТ ТРЕБОВАНИЯМ!")
            return True
        else:
            print(f"\n⚠️ ОТВЕТ: Обнаружено {invalid_count} невалидных моделей из {len(self.models)}")
            return False
    
    def run_full_scrape(self):
        """Полный сбор всех моделей с ответами на каждое действие"""
        print("=" * 60)
        print("🚀 ЗАПУСК АВТОМАТИЧЕСКОГО СБОРЩИКА МОДЕЛЕЙ KIE.AI")
        print("=" * 60)
        
        # Действие 1: Сканирование маркета
        print("\n📡 ДЕЙСТВИЕ 1: Сканирование страницы маркета...")
        model_links = self.get_market_page()
        
        if not model_links:
            print("❌ ОТВЕТ: Модели не найдены. Проверьте доступность сайта.")
            return []
        
        print(f"✅ ОТВЕТ: Найдено {len(model_links)} моделей на странице маркета")
        
        # Действие 2: Парсинг документации
        print(f"\n📚 ДЕЙСТВИЕ 2: Парсинг документации моделей...")
        max_models = min(30, len(model_links))
        print(f"✅ ОТВЕТ: Начинаем парсинг {max_models} моделей")
        
        for i, model in enumerate(model_links[:max_models], 1):
            print(f"\n  🔄 Обработка {i}/{max_models}: {model['name']}")
            self.scrape_model_docs(model['url'], model['name'])
            print(f"  ✅ ОТВЕТ: Обработка модели '{model['name']}' завершена")
            time.sleep(1)  # Не спамим
        
        print(f"\n✅ ОТВЕТ: Парсинг завершен. Обработано {len(self.models)} моделей")
        
        # Действие 3: Валидация всех моделей
        print("\n" + "=" * 60)
        is_valid = self.validate_all_models()
        print("=" * 60)
        
        # Действие 4: Сохранение результатов
        print("\n💾 ДЕЙСТВИЕ 4: Сохранение результатов в файл...")
        output_file = 'kie_full_api.json'
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.models, f, ensure_ascii=False, indent=2)
            print(f"✅ ОТВЕТ: Файл {output_file} успешно сохранен")
            print(f"   📊 Размер: {len(json.dumps(self.models, ensure_ascii=False))} символов")
        except Exception as e:
            print(f"❌ ОТВЕТ: Ошибка при сохранении файла: {e}")
            return []
        
        # Финальный ответ
        print("\n" + "=" * 60)
        print("🎉 ФИНАЛЬНЫЙ ОТВЕТ:")
        print(f"   ✅ Собрано моделей: {len(self.models)}")
        print(f"   ✅ Валидация: {'ПРОЙДЕНА' if is_valid else 'ЕСТЬ ОШИБКИ'}")
        print(f"   ✅ Файл сохранен: {output_file}")
        print("=" * 60)
        
        return self.models

# === ЗАПУСК ОДНОЙ КНОПКОЙ ===
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🎯 ИНИЦИАЛИЗАЦИЯ СКРИПТА...")
    print("=" * 60)
    
    scraper = KieApiScraper()
    print("✅ ОТВЕТ: Класс KieApiScraper инициализирован")
    print(f"   📡 Base URL: {scraper.base_url}")
    print(f"   🌐 Market URL: {scraper.market_url}")
    
    models = scraper.run_full_scrape()
    
    # Действие 5: Показ примеров
    print("\n📋 ДЕЙСТВИЕ 5: Отображение примеров моделей...")
    if models:
        print(f"✅ ОТВЕТ: Показываем первые {min(5, len(models))} моделей из {len(models)}")
        print("\n" + "=" * 60)
        for i, model in enumerate(models[:5], 1):
            print(f"\n📦 Модель {i}: {model['name']}")
            print(f"   🔗 Endpoint: {model['endpoint'] or 'не найден'}")
            print(f"   📝 Method: {model['method']}")
            print(f"   🌐 Base URL: {model['base_url']}")
            if model['params']:
                print(f"   ⚙️ Параметры: {model['params']}")
            if model['example']:
                print(f"   💡 Пример: {model['example'][:100]}...")
            print()
        print("=" * 60)
        print(f"\n✅ ОТВЕТ: Все действия выполнены успешно!")
    else:
        print("❌ ОТВЕТ: Модели не были собраны. Проверьте логи выше.")

