#!/usr/bin/env python3
"""
Полный парсинг документации и инструкций KIE AI.
Собирает все знания, инструкции и документацию по всем моделям с сайта KIE AI.
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from dotenv import load_dotenv

try:
    from playwright.async_api import async_playwright, Page, Browser, BrowserContext
except ImportError:
    print("❌ playwright не установлен. Установите: pip install playwright")
    print("   Затем: playwright install chromium")
    sys.exit(1)

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# URLs для парсинга
KIE_BASE_URL = "https://kie.ai"
KIE_LOGIN_URL = "https://kie.ai/login"
KIE_DOCS_URL = "https://docs.kie.ai"
KIE_MARKET_URL = "https://kie.ai/market"
KIE_DOCS_MARKET_URL = "https://docs.kie.ai/market"

# Пути для сохранения
OUTPUT_DIR = root_dir / "data" / "kie_documentation"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STATE_PATH = root_dir / ".cache" / "kie_storage_state.json"
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


class KIEDocumentationParser:
    """Парсер документации KIE AI."""
    
    def __init__(self, email: Optional[str] = None, password: Optional[str] = None, headless: bool = True, interactive: bool = False):
        self.email = email or os.getenv("KIE_EMAIL")
        self.password = password or os.getenv("KIE_PASSWORD")
        self.headless = headless
        self.interactive = interactive
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_authenticated = False
        
    async def __aenter__(self):
        """Async context manager entry."""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(
            headless=self.headless,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.browser:
            await self.browser.close()
    
    async def login(self) -> bool:
        """Авторизация на сайте KIE AI."""
        if not self.email or not self.password:
            logger.warning("⚠️ KIE_EMAIL или KIE_PASSWORD не установлены")
            logger.info("💡 Установите переменные окружения или передайте email/password")
            return False
        
        try:
            # Загружаем сохранённое состояние, если есть
            if STATE_PATH.exists():
                logger.info(f"📂 Загрузка сохранённого состояния из {STATE_PATH}")
                storage_state = json.loads(STATE_PATH.read_text(encoding='utf-8'))
                self.context = await self.browser.new_context(storage_state=storage_state)
            else:
                self.context = await self.browser.new_context()
            
            self.page = await self.context.new_page()
            
            # Переходим на страницу логина
            logger.info(f"🔐 Переход на страницу логина: {KIE_LOGIN_URL}")
            await self.page.goto(KIE_LOGIN_URL, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(2)
            
            # Ищем поля для ввода
            try:
                # Пробуем разные селекторы для email
                email_selectors = [
                    'input[type="email"]',
                    'input[name="email"]',
                    'input[id*="email"]',
                    'input[placeholder*="email" i]',
                    'input[placeholder*="почта" i]'
                ]
                
                email_input = None
                for selector in email_selectors:
                    try:
                        email_input = await self.page.query_selector(selector)
                        if email_input:
                            break
                    except:
                        continue
                
                if not email_input:
                    logger.error("❌ Не удалось найти поле для email")
                    return False
                
                # Пробуем разные селекторы для password
                password_selectors = [
                    'input[type="password"]',
                    'input[name="password"]',
                    'input[id*="password"]'
                ]
                
                password_input = None
                for selector in password_selectors:
                    try:
                        password_input = await self.page.query_selector(selector)
                        if password_input:
                            break
                    except:
                        continue
                
                if not password_input:
                    logger.error("❌ Не удалось найти поле для password")
                    return False
                
                # Заполняем поля
                logger.info("📝 Заполнение формы логина...")
                await email_input.fill(self.email)
                await asyncio.sleep(0.5)
                await password_input.fill(self.password)
                await asyncio.sleep(0.5)
                
                # Ищем кнопку входа
                submit_selectors = [
                    'button[type="submit"]',
                    'button:has-text("Sign in")',
                    'button:has-text("Login")',
                    'button:has-text("Войти")',
                    'button:has-text("Вход")',
                    'form button',
                    'input[type="submit"]'
                ]
                
                submit_button = None
                for selector in submit_selectors:
                    try:
                        submit_button = await self.page.query_selector(selector)
                        if submit_button:
                            break
                    except:
                        continue
                
                if submit_button:
                    await submit_button.click()
                else:
                    # Пробуем нажать Enter
                    await self.page.keyboard.press("Enter")
                
                # Ждём перехода или подтверждения
                await asyncio.sleep(3)
                
                # Проверяем, требуется ли подтверждение через Google/YouTube
                current_url = self.page.url
                page_text = await self.page.text_content('body') or ''
                
                # Проверяем признаки необходимости подтверждения
                needs_verification = any([
                    'google' in current_url.lower(),
                    'accounts.google.com' in current_url.lower(),
                    'youtube' in current_url.lower(),
                    'verification' in page_text.lower(),
                    'подтверждение' in page_text.lower(),
                    'код' in page_text.lower() and 'подтвержд' in page_text.lower(),
                    'code' in page_text.lower() and 'verify' in page_text.lower()
                ])
                
                if needs_verification:
                    logger.info("🔐 Требуется подтверждение через Google/YouTube")
                    
                    if self.interactive or not self.headless:
                        logger.info("💡 Ожидание ручного подтверждения...")
                        logger.info("   Пожалуйста, выполните подтверждение в открытом браузере")
                        logger.info("   После успешного подтверждения нажмите Enter здесь...")
                        
                        # Ждём, пока пользователь подтвердит
                        try:
                            # Периодически проверяем, завершилось ли подтверждение
                            max_wait_time = 300  # 5 минут максимум
                            check_interval = 2  # Проверяем каждые 2 секунды
                            waited = 0
                            
                            while waited < max_wait_time:
                                await asyncio.sleep(check_interval)
                                waited += check_interval
                                
                                current_url = self.page.url
                                page_text = await self.page.text_content('body') or ''
                                
                                # Проверяем, завершилось ли подтверждение
                                if "login" not in current_url.lower() and "google" not in current_url.lower():
                                    if "kie.ai" in current_url.lower() or "market" in current_url.lower():
                                        logger.info("✅ Подтверждение завершено!")
                                        break
                                
                                # Показываем прогресс каждые 30 секунд
                                if waited % 30 == 0:
                                    logger.info(f"   Ожидание... ({waited}/{max_wait_time} сек)")
                            
                            # Финальная проверка
                            await asyncio.sleep(2)
                            current_url = self.page.url
                            
                        except KeyboardInterrupt:
                            logger.warning("⚠️ Прервано пользователем")
                            return False
                    else:
                        logger.warning("⚠️ Требуется интерактивное подтверждение")
                        logger.info("💡 Запустите скрипт с --interactive или --headless=false")
                        logger.info("   python scripts/parse_kie_documentation.py --interactive")
                        return False
                
                # Проверяем, успешна ли авторизация
                current_url = self.page.url
                if "login" not in current_url.lower() and "google" not in current_url.lower():
                    if "kie.ai" in current_url.lower() or "market" in current_url.lower() or "docs" in current_url.lower():
                        logger.info("✅ Авторизация успешна!")
                        self.is_authenticated = True
                        
                        # Сохраняем состояние
                        storage_state = await self.context.storage_state()
                        STATE_PATH.write_text(
                            json.dumps(storage_state, indent=2),
                            encoding='utf-8'
                        )
                        logger.info(f"💾 Состояние сохранено в {STATE_PATH}")
                        return True
                
                # Если всё ещё на странице логина
                if "login" in current_url.lower():
                    logger.warning("⚠️ Похоже, авторизация не удалась. Проверьте логин и пароль.")
                    if self.interactive or not self.headless:
                        logger.info("💡 Попробуйте авторизоваться вручную в открытом браузере")
                        input("   Нажмите Enter после успешной авторизации...")
                        # Проверяем снова
                        current_url = self.page.url
                        if "login" not in current_url.lower():
                            self.is_authenticated = True
                            storage_state = await self.context.storage_state()
                            STATE_PATH.write_text(
                                json.dumps(storage_state, indent=2),
                                encoding='utf-8'
                            )
                            return True
                    return False
                
                # Неизвестное состояние
                logger.warning(f"⚠️ Неизвестное состояние авторизации. URL: {current_url}")
                return False
                    
            except Exception as e:
                logger.error(f"❌ Ошибка при авторизации: {e}", exc_info=True)
                return False
                
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при авторизации: {e}", exc_info=True)
            return False
    
    async def parse_docs_homepage(self) -> Dict[str, Any]:
        """Парсит главную страницу документации."""
        logger.info("📚 Парсинг главной страницы документации...")
        
        try:
            await self.page.goto(KIE_DOCS_URL, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)
            
            # Получаем HTML содержимое
            html_content = await self.page.content()
            
            # Извлекаем текст
            text_content = await self.page.text_content('body')
            
            # Ищем все ссылки на модели
            links = await self.page.query_selector_all('a[href*="/market"], a[href*="/models"]')
            model_links = []
            for link in links:
                href = await link.get_attribute('href')
                text = await link.text_content()
                if href:
                    model_links.append({
                        'url': href if href.startswith('http') else f"{KIE_DOCS_URL}{href}",
                        'text': text.strip() if text else ''
                    })
            
            return {
                'url': KIE_DOCS_URL,
                'html': html_content,
                'text': text_content,
                'model_links': model_links,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка при парсинге главной страницы: {e}", exc_info=True)
            return {}
    
    async def parse_docs_market(self) -> Dict[str, Any]:
        """Парсит страницу Market Documentation."""
        logger.info("📚 Парсинг Market Documentation...")
        
        try:
            await self.page.goto(KIE_DOCS_MARKET_URL, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)
            
            # Получаем содержимое
            html_content = await self.page.content()
            text_content = await self.page.text_content('body')
            
            # Ищем все модели по категориям
            categories = {}
            
            # Пробуем найти категории (Image, Video, Audio)
            category_selectors = [
                'h2:has-text("Image")',
                'h2:has-text("Video")',
                'h2:has-text("Audio")',
                '[data-category]',
                '.category'
            ]
            
            # Ищем все ссылки на модели
            model_links = await self.page.query_selector_all('a[href*="/market/"]')
            models = []
            
            for link in model_links:
                href = await link.get_attribute('href')
                text = await link.text_content()
                if href and text:
                    models.append({
                        'url': href if href.startswith('http') else f"{KIE_DOCS_URL}{href}",
                        'name': text.strip(),
                        'slug': href.split('/')[-1] if '/' in href else ''
                    })
            
            return {
                'url': KIE_DOCS_MARKET_URL,
                'html': html_content,
                'text': text_content,
                'models': models,
                'categories': categories,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка при парсинге Market: {e}", exc_info=True)
            return {}
    
    async def parse_model_documentation(self, model_slug: str) -> Dict[str, Any]:
        """Парсит документацию конкретной модели."""
        model_url = f"{KIE_DOCS_URL}/market/{model_slug}"
        logger.info(f"📖 Парсинг документации модели: {model_slug}")
        
        try:
            await self.page.goto(model_url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)
            
            # Получаем содержимое
            html_content = await self.page.content()
            text_content = await self.page.text_content('body')
            
            # Извлекаем структурированные данные
            model_data = {
                'slug': model_slug,
                'url': model_url,
                'html': html_content,
                'text': text_content,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            # Пробуем найти JSON данные в script тегах
            script_tags = await self.page.query_selector_all('script[type="application/json"], script#__NEXT_DATA__')
            for script in script_tags:
                try:
                    script_content = await script.text_content()
                    if script_content:
                        try:
                            json_data = json.loads(script_content)
                            model_data['json_data'] = json_data
                            break
                        except json.JSONDecodeError:
                            pass
                except:
                    pass
            
            # Извлекаем секции документации
            sections = {}
            
            # Quickstart
            quickstart = await self.page.query_selector('[id*="quickstart" i], [class*="quickstart" i]')
            if quickstart:
                sections['quickstart'] = await quickstart.text_content()
            
            # API Reference
            api_ref = await self.page.query_selector('[id*="api" i], [class*="api-reference" i]')
            if api_ref:
                sections['api_reference'] = await api_ref.text_content()
            
            # Code Samples
            code_samples = await self.page.query_selector_all('pre code, .code-sample')
            if code_samples:
                sections['code_samples'] = []
                for code in code_samples:
                    code_text = await code.text_content()
                    if code_text:
                        sections['code_samples'].append(code_text)
            
            # Parameters
            params_section = await self.page.query_selector('[id*="parameter" i], [class*="parameter" i]')
            if params_section:
                sections['parameters'] = await params_section.text_content()
            
            model_data['sections'] = sections
            
            return model_data
            
        except Exception as e:
            logger.error(f"❌ Ошибка при парсинге модели {model_slug}: {e}", exc_info=True)
            return {'slug': model_slug, 'error': str(e)}
    
    async def parse_all_models_from_api(self) -> List[Dict[str, Any]]:
        """Получает список всех моделей из API."""
        logger.info("📡 Получение списка моделей из API...")
        
        try:
            from kie_client import get_client
            
            client = get_client()
            models = await client.list_models()
            
            if models:
                logger.info(f"✅ Получено {len(models)} моделей из API")
                return models
            else:
                logger.warning("⚠️ API не вернул модели")
                return []
                
        except Exception as e:
            logger.error(f"❌ Ошибка при получении моделей из API: {e}", exc_info=True)
            return []
    
    async def parse_all_documentation(self) -> Dict[str, Any]:
        """Парсит всю документацию."""
        logger.info("🚀 Начало полного парсинга документации KIE AI...")
        
        all_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'docs_homepage': {},
            'docs_market': {},
            'models': {},
            'api_models': []
        }
        
        # 1. Парсим главную страницу документации
        all_data['docs_homepage'] = await self.parse_docs_homepage()
        
        # 2. Парсим Market Documentation
        all_data['docs_market'] = await self.parse_docs_market()
        
        # 3. Получаем список моделей из API
        api_models = await self.parse_all_models_from_api()
        all_data['api_models'] = api_models
        
        # 4. Парсим документацию для каждой модели
        model_slugs = set()
        
        # Из Market страницы
        if 'models' in all_data['docs_market']:
            for model in all_data['docs_market']['models']:
                if model.get('slug'):
                    model_slugs.add(model['slug'])
        
        # Из API моделей
        for api_model in api_models:
            model_id = api_model.get('id') or api_model.get('model_id') or ''
            if model_id:
                # Пробуем преобразовать model_id в slug
                slug = model_id.replace('/', '-').lower()
                model_slugs.add(slug)
        
        # Парсим каждую модель
        logger.info(f"📚 Парсинг документации для {len(model_slugs)} моделей...")
        for i, slug in enumerate(sorted(model_slugs), 1):
            logger.info(f"  [{i}/{len(model_slugs)}] {slug}")
            model_docs = await self.parse_model_documentation(slug)
            if model_docs:
                all_data['models'][slug] = model_docs
            await asyncio.sleep(1)  # Небольшая задержка между запросами
        
        return all_data


async def main():
    """Основная функция."""
    import argparse
    
    parser_args = argparse.ArgumentParser(description='Парсер документации KIE AI')
    parser_args.add_argument('--interactive', '-i', action='store_true',
                            help='Интерактивный режим (для подтверждения через Google/YouTube)')
    parser_args.add_argument('--headless', action='store_true', default=None,
                            help='Запуск в headless режиме (по умолчанию: True)')
    parser_args.add_argument('--no-headless', action='store_true',
                            help='Запуск с видимым браузером (для отладки)')
    
    args = parser_args.parse_args()
    
    # Определяем режим headless
    headless = True
    if args.no_headless:
        headless = False
    elif args.headless is not None:
        headless = args.headless
    
    # Интерактивный режим автоматически включает видимый браузер
    interactive = args.interactive
    if interactive:
        headless = False
    
    logger.info("🚀 Запуск парсера документации KIE AI...")
    if interactive:
        logger.info("🔧 Интерактивный режим включен (для подтверждения через Google/YouTube)")
    if not headless:
        logger.info("👁️  Браузер будет видимым")
    
    # Получаем логин и пароль
    email = os.getenv("KIE_EMAIL")
    password = os.getenv("KIE_PASSWORD")
    
    if not email or not password:
        logger.warning("⚠️ KIE_EMAIL или KIE_PASSWORD не установлены в переменных окружения")
        logger.info("💡 Установите переменные окружения:")
        logger.info("   export KIE_EMAIL=your_email@example.com")
        logger.info("   export KIE_PASSWORD=your_password")
        logger.info("")
        logger.info("Или создайте .env файл с этими переменными")
        
        # Пробуем запросить интерактивно
        try:
            email = input("Введите email KIE AI (или нажмите Enter для пропуска): ").strip()
            if email:
                password = input("Введите пароль KIE AI: ").strip()
        except KeyboardInterrupt:
            logger.info("\n❌ Прервано пользователем")
            return 1
    
    async with KIEDocumentationParser(email=email, password=password, headless=headless, interactive=interactive) as parser:
        # Авторизация
        if email and password:
            logger.info("🔐 Попытка авторизации...")
            success = await parser.login()
            if not success:
                logger.warning("⚠️ Авторизация не удалась, продолжаем без неё...")
        else:
            logger.info("ℹ️ Пропуск авторизации (нет логина/пароля)")
        
        # Парсим всю документацию
        all_documentation = await parser.parse_all_documentation()
        
        # Сохраняем результаты
        logger.info("💾 Сохранение результатов...")
        
        # Сохраняем полный дамп
        full_dump_file = OUTPUT_DIR / f"full_documentation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(full_dump_file, 'w', encoding='utf-8') as f:
            json.dump(all_documentation, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ Полный дамп сохранён: {full_dump_file}")
        
        # Сохраняем структурированные данные
        structured_file = OUTPUT_DIR / "documentation_structured.json"
        structured_data = {
            'timestamp': all_documentation['timestamp'],
            'total_models': len(all_documentation['models']),
            'models': {}
        }
        
        for slug, model_data in all_documentation['models'].items():
            structured_data['models'][slug] = {
                'slug': slug,
                'url': model_data.get('url', ''),
                'sections': model_data.get('sections', {}),
                'has_code_samples': bool(model_data.get('sections', {}).get('code_samples')),
                'has_api_reference': bool(model_data.get('sections', {}).get('api_reference')),
                'has_quickstart': bool(model_data.get('sections', {}).get('quickstart'))
            }
        
        with open(structured_file, 'w', encoding='utf-8') as f:
            json.dump(structured_data, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ Структурированные данные сохранены: {structured_file}")
        
        # Сохраняем текстовые версии для каждой модели
        text_dir = OUTPUT_DIR / "models_text"
        text_dir.mkdir(exist_ok=True)
        
        for slug, model_data in all_documentation['models'].items():
            text_file = text_dir / f"{slug}.txt"
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(f"Model: {slug}\n")
                f.write(f"URL: {model_data.get('url', '')}\n")
                f.write("=" * 80 + "\n\n")
                
                if 'sections' in model_data:
                    for section_name, section_content in model_data['sections'].items():
                        f.write(f"\n## {section_name.upper()}\n")
                        f.write("=" * 80 + "\n")
                        if isinstance(section_content, list):
                            for item in section_content:
                                f.write(f"{item}\n\n")
                        else:
                            f.write(f"{section_content}\n\n")
                
                f.write("\n" + "=" * 80 + "\n")
                f.write("FULL TEXT CONTENT:\n")
                f.write("=" * 80 + "\n")
                f.write(model_data.get('text', ''))
        
        logger.info(f"✅ Текстовые версии сохранены в {text_dir}")
        
        # Выводим статистику
        print("\n" + "=" * 80)
        print("📊 СТАТИСТИКА ПАРСИНГА")
        print("=" * 80)
        print(f"Всего моделей обработано: {len(all_documentation['models'])}")
        print(f"Моделей из API: {len(all_documentation['api_models'])}")
        print(f"Моделей с Quickstart: {sum(1 for m in all_documentation['models'].values() if m.get('sections', {}).get('quickstart'))}")
        print(f"Моделей с API Reference: {sum(1 for m in all_documentation['models'].values() if m.get('sections', {}).get('api_reference'))}")
        print(f"Моделей с Code Samples: {sum(1 for m in all_documentation['models'].values() if m.get('sections', {}).get('code_samples'))}")
        print(f"\nФайлы сохранены в: {OUTPUT_DIR}")
        print("=" * 80)
        
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

