"""
Kie.ai documentation parser.

Extracts model information from HTML pages safely, without breaking on layout changes.
"""

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from app.kie_sync.config import (
    CACHE_DIR, DOCS_BASE_URL, API_BASE_URL,
    STANDARD_CREATE_ENDPOINT, STANDARD_RECORD_ENDPOINT,
    RATE_LIMIT_RPS, REQUEST_TIMEOUT, MAX_RETRIES
)

logging = None
try:
    import logging
    logger = logging.getLogger(__name__)
except:
    pass


class KieParser:
    """
    Parser for Kie.ai documentation pages.
    
    Extracts:
    - model_id (from JSON/cURL examples)
    - endpoints (standard or overrides)
    - input schema (fields, required, types, defaults, enums, constraints)
    - pricing (USD/credits)
    """
    
    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.last_request_time = 0.0
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def _rate_limit(self):
        """Rate limiting: 1 request per second."""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < 1.0 / RATE_LIMIT_RPS:
            time.sleep(1.0 / RATE_LIMIT_RPS - elapsed)
        self.last_request_time = time.time()
    
    def _get_cache_path(self, url: str) -> Path:
        """Get cache file path for URL."""
        # Create safe filename from URL
        parsed = urlparse(url)
        slug = parsed.path.strip("/").replace("/", "_")
        if not slug:
            slug = "index"
        return self.cache_dir / f"{slug}.html"
    
    def _get_checksum(self, content: str) -> str:
        """Calculate SHA256 checksum of content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    async def fetch_page(self, url: str, use_cache: bool = True) -> Tuple[str, str]:
        """
        Fetch HTML page with caching and rate limiting.
        
        Returns:
            (content, checksum)
        """
        cache_path = self._get_cache_path(url)
        checksum_path = cache_path.with_suffix('.checksum')
        
        # Check cache
        if use_cache and cache_path.exists() and checksum_path.exists():
            cached_checksum = checksum_path.read_text().strip()
            return cache_path.read_text(encoding='utf-8'), cached_checksum
        
        # Rate limit
        self._rate_limit()
        
        # Fetch with retries
        for attempt in range(MAX_RETRIES + 1):
            try:
                if not self.session:
                    raise RuntimeError("Session not initialized")
                
                async with self.session.get(url) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        checksum = self._get_checksum(content)
                        
                        # Save to cache
                        cache_path.write_text(content, encoding='utf-8')
                        checksum_path.write_text(checksum, encoding='utf-8')
                        
                        return content, checksum
                    else:
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(1.0)
                            continue
                        raise Exception(f"HTTP {resp.status}: {url}")
            except Exception as e:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(1.0)
                    continue
                raise
        
        raise Exception(f"Failed to fetch {url} after {MAX_RETRIES + 1} attempts")
    
    def extract_model_id(self, html: str, url: str) -> Optional[str]:
        """
        Extract model_id from HTML.
        
        Looks for:
        - JSON blocks with "model": "..."
        - cURL examples with "model": "..."
        """
        # Try JSON blocks first
        json_pattern = r'"model"\s*:\s*"([^"]+)"'
        matches = re.findall(json_pattern, html, re.IGNORECASE)
        if matches:
            # Use first match
            model_id = matches[0].strip()
            if model_id and "/" in model_id:  # Basic validation
                return model_id
        
        # Try cURL examples
        curl_pattern = r'curl[^}]*\{[^}]*"model"\s*:\s*"([^"]+)"'
        matches = re.findall(curl_pattern, html, re.IGNORECASE | re.DOTALL)
        if matches:
            model_id = matches[0].strip()
            if model_id and "/" in model_id:
                return model_id
        
        # Fallback: try to extract from URL
        # e.g., docs.kie.ai/market/seedream/seedream -> seedream/seedream
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split("/") if p]
        if len(path_parts) >= 2 and path_parts[0] == "market":
            return "/".join(path_parts[1:])
        
        return None
    
    def extract_endpoints(self, html: str) -> Dict[str, str]:
        """
        Extract endpoints from HTML.
        
        Returns:
            {"create": "...", "record": "..."} or empty dict if not found
        """
        endpoints = {}
        
        # Look for createTask endpoint
        create_pattern = r'(?:POST|post)\s+([^\s]+/createTask[^\s]*)'
        matches = re.findall(create_pattern, html, re.IGNORECASE)
        if matches:
            endpoint = matches[0].strip()
            if endpoint.startswith("http"):
                endpoints["create"] = endpoint
            elif endpoint.startswith("/"):
                endpoints["create"] = API_BASE_URL + endpoint
            else:
                endpoints["create"] = API_BASE_URL + "/" + endpoint
        else:
            # Use standard
            endpoints["create"] = API_BASE_URL + STANDARD_CREATE_ENDPOINT
        
        # Look for recordInfo endpoint
        record_pattern = r'(?:GET|get)\s+([^\s]+/recordInfo[^\s]*)'
        matches = re.findall(record_pattern, html, re.IGNORECASE)
        if matches:
            endpoint = matches[0].strip()
            if endpoint.startswith("http"):
                endpoints["record"] = endpoint
            elif endpoint.startswith("/"):
                endpoints["record"] = API_BASE_URL + endpoint
            else:
                endpoints["record"] = API_BASE_URL + "/" + endpoint
        else:
            # Use standard
            endpoints["record"] = API_BASE_URL + STANDARD_RECORD_ENDPOINT
        
        return endpoints
    
    def extract_input_schema(self, html: str) -> Dict[str, Any]:
        """
        Extract input schema from HTML.
        
        Looks for:
        - Tables with "Input Object Parameters" / "Request Parameters"
        - JSON examples in request body
        """
        soup = BeautifulSoup(html, 'html.parser')
        schema = {}
        
        # Try to find parameter tables
        tables = soup.find_all('table')
        for table in tables:
            headers = [th.get_text().strip().lower() for th in table.find_all(['th', 'td'])[:5]]
            if any(keyword in " ".join(headers) for keyword in ['parameter', 'field', 'input', 'name']):
                rows = table.find_all('tr')[1:]  # Skip header
                for row in rows:
                    cells = [td.get_text().strip() for td in row.find_all(['td', 'th'])]
                    if len(cells) >= 2:
                        field_name = cells[0]
                        if not field_name or field_name.lower() in ['parameter', 'field', 'name']:
                            continue
                        
                        field_spec = {
                            "type": "string",  # Default
                            "required": False,
                            "unknown": False
                        }
                        
                        # Try to extract type
                        if len(cells) > 1:
                            type_text = cells[1].lower()
                            if 'array' in type_text:
                                field_spec["type"] = "array"
                            elif 'number' in type_text or 'int' in type_text or 'float' in type_text:
                                field_spec["type"] = "number"
                            elif 'bool' in type_text or 'boolean' in type_text:
                                field_spec["type"] = "boolean"
                        
                        # Try to extract required flag
                        row_text = " ".join(cells).lower()
                        if 'required' in row_text or 'обязательно' in row_text:
                            field_spec["required"] = True
                        
                        # Try to extract default
                        default_match = re.search(r'default[:\s]+([^\s,;]+)', row_text, re.IGNORECASE)
                        if default_match:
                            default_val = default_match.group(1).strip().strip('"').strip("'")
                            field_spec["default"] = default_val
                        
                        # Try to extract enum/options
                        if 'enum' in row_text or 'options' in row_text or '|' in row_text:
                            # Look for enum values
                            enum_match = re.search(r'(?:enum|options|values?)[:\s]+([^;]+)', row_text, re.IGNORECASE)
                            if enum_match:
                                enum_text = enum_match.group(1)
                                enum_values = [v.strip().strip('"').strip("'") for v in enum_text.split(',') if v.strip()]
                                if enum_values:
                                    field_spec["enum"] = enum_values
                        
                        # Try to extract constraints
                        max_len_match = re.search(r'max[_\s]?length[:\s]+(\d+)', row_text, re.IGNORECASE)
                        if max_len_match:
                            field_spec["max_length"] = int(max_len_match.group(1))
                        
                        max_items_match = re.search(r'max[_\s]?items?[:\s]+(\d+)', row_text, re.IGNORECASE)
                        if max_items_match:
                            field_spec["max_items"] = int(max_items_match.group(1))
                        
                        schema[field_name] = field_spec
        
        # Also try to extract from JSON examples
        json_blocks = re.findall(r'\{[^{}]*"input"\s*:\s*\{[^}]+\}[^}]*\}', html, re.IGNORECASE | re.DOTALL)
        for json_block in json_blocks:
            try:
                # Try to parse as JSON
                data = json.loads(json_block)
                if "input" in data and isinstance(data["input"], dict):
                    for field_name, field_value in data["input"].items():
                        if field_name not in schema:
                            schema[field_name] = {
                                "type": type(field_value).__name__,
                                "required": False,
                                "unknown": False
                            }
                        # Infer type from value
                        if isinstance(field_value, list):
                            schema[field_name]["type"] = "array"
                        elif isinstance(field_value, (int, float)):
                            schema[field_name]["type"] = "number"
                        elif isinstance(field_value, bool):
                            schema[field_name]["type"] = "boolean"
            except:
                pass  # Skip invalid JSON
        
        return schema
    
    def extract_pricing(self, html: str) -> Dict[str, Any]:
        """
        Extract pricing information from HTML.
        
        Returns:
            {"usd": float, "credits": int} or empty dict
        """
        pricing = {}
        
        # Look for USD prices
        usd_pattern = r'\$?(\d+\.?\d*)\s*USD'
        usd_matches = re.findall(usd_pattern, html, re.IGNORECASE)
        if usd_matches:
            try:
                pricing["usd"] = float(usd_matches[0])
            except:
                pass
        
        # Look for credits
        credits_pattern = r'(\d+)\s*credits?'
        credits_matches = re.findall(credits_pattern, html, re.IGNORECASE)
        if credits_matches:
            try:
                pricing["credits"] = int(credits_matches[0])
            except:
                pass
        
        return pricing
    
    async def parse_page(self, url: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Parse a single Kie.ai documentation page.
        
        Returns:
            Model data dict or None if parsing failed
        """
        try:
            html, checksum = await self.fetch_page(url, use_cache=use_cache)
            
            model_id = self.extract_model_id(html, url)
            if not model_id:
                if logger:
                    logger.warning(f"Could not extract model_id from {url}")
                return None
            
            endpoints = self.extract_endpoints(html)
            input_schema = self.extract_input_schema(html)
            pricing = self.extract_pricing(html)
            
            return {
                "model_id": model_id,
                "docs_url": url,
                "endpoints": endpoints,
                "input_schema": input_schema,
                "pricing": pricing,
                "checksum": checksum,
                "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            if logger:
                logger.error(f"Failed to parse {url}: {e}", exc_info=True)
            return None
    
    async def discover_pages(self) -> List[str]:
        """
        Discover Kie.ai documentation pages.
        
        Uses docs.kie.ai/llms.txt as index.
        """
        pages = []
        
        try:
            # Fetch index
            index_url = "https://docs.kie.ai/llms.txt"
            html, _ = await self.fetch_page(index_url, use_cache=True)
            
            # Extract market/* URLs
            market_pattern = r'https?://docs\.kie\.ai/market/[^\s\)]+'
            matches = re.findall(market_pattern, html)
            pages.extend(matches)
            
            # Also try relative URLs
            relative_pattern = r'/market/[^\s\)]+'
            relative_matches = re.findall(relative_pattern, html)
            for rel_url in relative_matches:
                full_url = urljoin(DOCS_BASE_URL, rel_url)
                if full_url not in pages:
                    pages.append(full_url)
        
        except Exception as e:
            if logger:
                logger.error(f"Failed to discover pages: {e}", exc_info=True)
        
        return pages

