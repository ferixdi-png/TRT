#!/usr/bin/env python3
"""
Полный краулер всего сайта KIE AI.
Парсит ВСЕ страницы, ВСЕ ссылки, ВСЕ буквы, ВСЮ документацию.
"""

import os
import sys
import json
import asyncio
import logging
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urlunparse
from dotenv import load_dotenv

try:
    from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Response
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

# Домены для парсинга
ALLOWED_DOMAINS = [
    'kie.ai',
    'www.kie.ai',
    'docs.kie.ai',
    'api.kie.ai'
]

# Базовые URL
KIE_BASE_URL = "https://kie.ai"
KIE_DOCS_URL = "https://docs.kie.ai"

# Пути для сохранения
OUTPUT_DIR = root_dir / "data" / "kie_full_site"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Поддиректории
HTML_DIR = OUTPUT_DIR / "html"
TEXT_DIR = OUTPUT_DIR / "text"
JSON_DIR = OUTPUT_DIR / "json"
IMAGES_DIR = OUTPUT_DIR / "images"
LINKS_DIR = OUTPUT_DIR / "links"

for dir_path in [HTML_DIR, TEXT_DIR, JSON_DIR, IMAGES_DIR, LINKS_DIR]:
    dir_path.mkdir(exist_ok=True)


# Статистика
STATS = {
    'total_pages': 0,
    'parsed_pages': 0,
    'failed_pages': 0,
    'total_links': 0,
    'unique_links': 0,
    'start_time': None,
    'end_time': None
}


class FullSiteCrawler:
    """Полный краулер сайта KIE AI."""
    
    def __init__(self, headless: bool = True, max_depth: int = 10):
        self.headless = headless
        self.max_depth = max_depth
        
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
        # Очередь для парсинга
        self.url_queue: List[Dict[str, Any]] = []
        self.visited_urls: Set[str] = set()
        self.url_index: Dict[str, Dict[str, Any]] = {}
        self.all_links: Set[str] = set()
        
        # Начальные URL для парсинга
        self.start_urls = [
            "https://kie.ai",
            "https://kie.ai/market",
            "https://docs.kie.ai",
            "https://docs.kie.ai/market",
        ]
    
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
    
    def is_allowed_url(self, url: str) -> bool:
        """Проверяет, разрешён ли URL для парсинга."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Проверяем домен
            if not any(allowed in domain for allowed in ALLOWED_DOMAINS):
                return False
            
            # Исключаем некоторые типы файлов
            excluded_extensions = ['.pdf', '.zip', '.exe', '.dmg', '.jpg', '.jpeg', '.png', '.gif', '.svg']
            path = parsed.path.lower()
            if any(path.endswith(ext) for ext in excluded_extensions):
                return False
            
            # Исключаем некоторые пути
            excluded_paths = ['/api/', '/_next/', '/static/', '/assets/']
            if any(excluded in path for excluded in excluded_paths):
                return False
            
            return True
        except:
            return False
    
    def normalize_url(self, url: str, base_url: str = None) -> str:
        """Нормализует URL."""
        try:
            # Если относительный URL, делаем абсолютным
            if not url.startswith('http'):
                if base_url:
                    url = urljoin(base_url, url)
                else:
                    return None
            
            parsed = urlparse(url)
            # Убираем фрагменты и параметры для нормализации
            normalized = urlunparse((
                parsed.scheme,
                parsed.netloc.lower(),
                parsed.path.rstrip('/'),
                '',
                '',
                ''
            ))
            
            return normalized
        except:
            return None
    
    def get_url_hash(self, url: str) -> str:
        """Получает хеш URL для использования в имени файла."""
        return hashlib.md5(url.encode()).hexdigest()
    
    
    async def extract_all_links(self, page: Page, current_url: str) -> List[str]:
        """Извлекает все ссылки со страницы."""
        links = []
        
        try:
            # Получаем все ссылки
            link_elements = await page.query_selector_all('a[href]')
            
            for link in link_elements:
                try:
                    href = await link.get_attribute('href')
                    if not href:
                        continue
                    
                    # Нормализуем URL
                    normalized = self.normalize_url(href, current_url)
                    if normalized and self.is_allowed_url(normalized):
                        links.append(normalized)
                        self.all_links.add(normalized)
                except:
                    continue
            
            # Также ищем ссылки в JavaScript (data-атрибуты, onclick и т.д.)
            try:
                js_links = await page.evaluate("""
                    () => {
                        const links = [];
                        // Ищем в data-атрибутах
                        document.querySelectorAll('[data-href], [data-url], [data-link]').forEach(el => {
                            const href = el.getAttribute('data-href') || el.getAttribute('data-url') || el.getAttribute('data-link');
                            if (href) links.push(href);
                        });
                        return links;
                    }
                """)
                
                for href in js_links:
                    normalized = self.normalize_url(href, current_url)
                    if normalized and self.is_allowed_url(normalized):
                        links.append(normalized)
                        self.all_links.add(normalized)
            except:
                pass
            
            return list(set(links))
        except Exception as e:
            logger.debug(f"Ошибка при извлечении ссылок: {e}")
            return []
    
    async def parse_page(self, url: str, depth: int = 0) -> Dict[str, Any]:
        """Парсит одну страницу."""
        if depth > self.max_depth:
            return None
        
        if url in self.visited_urls:
            return self.url_index.get(url)
        
        normalized_url = self.normalize_url(url)
        if not normalized_url:
            return None
        
        if normalized_url in self.visited_urls:
            return self.url_index.get(normalized_url)
        
        self.visited_urls.add(normalized_url)
        STATS['total_pages'] += 1
        
        logger.info(f"📄 [{depth}] Парсинг: {normalized_url}")
        
        try:
            # Создаём новую страницу для каждого запроса
            page = await self.context.new_page()
            
            # Перехватываем JSON ответы
            json_responses = []
            
            async def handle_response(response: Response):
                try:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'application/json' in content_type:
                        try:
                            json_data = await response.json()
                            json_responses.append({
                                'url': response.url,
                                'data': json_data
                            })
                        except:
                            pass
                except:
                    pass
            
            page.on('response', handle_response)
            
            # Загружаем страницу
            await page.goto(normalized_url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(2)
            
            # Скроллим страницу для загрузки динамического контента
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            
            # Получаем содержимое
            html_content = await page.content()
            text_content = await page.text_content('body') or ''
            
            # Извлекаем все ссылки
            links = await self.extract_all_links(page, normalized_url)
            
            # Сохраняем данные
            url_hash = self.get_url_hash(normalized_url)
            
            page_data = {
                'url': normalized_url,
                'depth': depth,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'title': await page.title(),
                'html_length': len(html_content),
                'text_length': len(text_content),
                'links_count': len(links),
                'links': links,
                'json_responses_count': len(json_responses)
            }
            
            # Сохраняем HTML
            html_file = HTML_DIR / f"{url_hash}.html"
            html_file.write_text(html_content, encoding='utf-8')
            page_data['html_file'] = str(html_file.relative_to(OUTPUT_DIR))
            
            # Сохраняем текст
            text_file = TEXT_DIR / f"{url_hash}.txt"
            text_file.write_text(text_content, encoding='utf-8')
            page_data['text_file'] = str(text_file.relative_to(OUTPUT_DIR))
            
            # Сохраняем JSON ответы
            if json_responses:
                json_file = JSON_DIR / f"{url_hash}.json"
                json_file.write_text(
                    json.dumps(json_responses, ensure_ascii=False, indent=2),
                    encoding='utf-8'
                )
                page_data['json_file'] = str(json_file.relative_to(OUTPUT_DIR))
            
            # Сохраняем ссылки
            links_file = LINKS_DIR / f"{url_hash}_links.json"
            links_file.write_text(
                json.dumps(links, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            
            self.url_index[normalized_url] = page_data
            STATS['parsed_pages'] += 1
            
            # Добавляем новые ссылки в очередь
            for link in links:
                if link not in self.visited_urls and self.is_allowed_url(link):
                    self.url_queue.append({
                        'url': link,
                        'depth': depth + 1
                    })
            
            await page.close()
            
            return page_data
            
        except Exception as e:
            logger.error(f"❌ Ошибка при парсинге {normalized_url}: {e}")
            STATS['failed_pages'] += 1
            
            error_data = {
                'url': normalized_url,
                'depth': depth,
                'error': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            self.url_index[normalized_url] = error_data
            return error_data
    
    async def crawl_all(self):
        """Запускает полный краулинг всего сайта."""
        STATS['start_time'] = datetime.now(timezone.utc).isoformat()
        logger.info("🚀 Начало полного краулинга сайта KIE AI...")
        logger.info("ℹ️  Авторизация не требуется - парсим публичный контент")
        
        # Инициализируем контекст браузера
        self.context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        # Добавляем начальные URL в очередь
        for url in self.start_urls:
            self.url_queue.append({
                'url': url,
                'depth': 0
            })
        
        # Загружаем сохранённый прогресс, если есть
        progress_file = OUTPUT_DIR / "crawl_progress.json"
        if progress_file.exists():
            try:
                progress_data = json.loads(progress_file.read_text(encoding='utf-8'))
                self.visited_urls = set(progress_data.get('visited_urls', []))
                self.url_index = progress_data.get('url_index', {})
                self.all_links = set(progress_data.get('all_links', []))
                logger.info(f"📂 Загружен сохранённый прогресс: {len(self.visited_urls)} страниц уже спарсено")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось загрузить прогресс: {e}")
        
        # Парсим все страницы из очереди
        processed_count = 0
        while self.url_queue:
            item = self.url_queue.pop(0)
            url = item['url']
            depth = item['depth']
            
            # Пропускаем, если уже посетили
            normalized = self.normalize_url(url)
            if normalized and normalized in self.visited_urls:
                continue
            
            # Парсим страницу
            await self.parse_page(url, depth)
            processed_count += 1
            
            # Сохраняем прогресс каждые 10 страниц
            if processed_count % 10 == 0:
                try:
                    progress_data = {
                        'visited_urls': list(self.visited_urls),
                        'url_index': self.url_index,
                        'all_links': list(self.all_links),
                        'queue_size': len(self.url_queue),
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }
                    progress_file.write_text(
                        json.dumps(progress_data, ensure_ascii=False, indent=2),
                        encoding='utf-8'
                    )
                except Exception as e:
                    logger.debug(f"Не удалось сохранить прогресс: {e}")
            
            # Небольшая задержка между запросами
            await asyncio.sleep(1)
            
            # Показываем прогресс
            if STATS['parsed_pages'] % 10 == 0:
                logger.info(f"📊 Прогресс: {STATS['parsed_pages']} страниц, {len(self.url_queue)} в очереди, {len(self.all_links)} уникальных ссылок")
        
        STATS['end_time'] = datetime.now(timezone.utc).isoformat()
        STATS['unique_links'] = len(self.all_links)
        STATS['total_links'] = len(self.all_links)
        
        # Удаляем файл прогресса после успешного завершения
        progress_file = OUTPUT_DIR / "crawl_progress.json"
        if progress_file.exists():
            try:
                progress_file.unlink()
            except:
                pass
        
        # Сохраняем индекс
        index_file = OUTPUT_DIR / "site_index.json"
        index_data = {
            'stats': STATS,
            'url_index': self.url_index,
            'all_links': sorted(list(self.all_links)),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        index_file.write_text(
            json.dumps(index_data, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        
        logger.info(f"✅ Краулинг завершён!")
        logger.info(f"📊 Статистика:")
        logger.info(f"   Всего страниц: {STATS['total_pages']}")
        logger.info(f"   Успешно спарсено: {STATS['parsed_pages']}")
        logger.info(f"   Ошибок: {STATS['failed_pages']}")
        logger.info(f"   Уникальных ссылок: {STATS['unique_links']}")
        logger.info(f"📁 Данные сохранены в: {OUTPUT_DIR}")


async def main():
    """Основная функция."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Полный краулер сайта KIE AI (без авторизации)')
    parser.add_argument('--no-headless', action='store_true',
                        help='Запуск с видимым браузером')
    parser.add_argument('--max-depth', type=int, default=10,
                        help='Максимальная глубина рекурсии (по умолчанию: 10)')
    
    args = parser.parse_args()
    
    headless = not args.no_headless
    
    logger.info("🚀 Запуск полного краулера сайта KIE AI")
    logger.info("ℹ️  Авторизация не требуется - парсим публичный контент")
    
    async with FullSiteCrawler(
        headless=headless,
        max_depth=args.max_depth
    ) as crawler:
        await crawler.crawl_all()
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

