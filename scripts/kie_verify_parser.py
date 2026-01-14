#!/usr/bin/env python3
"""
KIE Verify Parser - безопасная сверка upstream Kie.ai docs с существующим реестром.

ПРАВИЛА:
- НЕ добавляет новые модели автоматически
- Только сравнивает существующие модели
- Новые модели записываются как "candidates" и требуют явной команды для добавления
- Цены: upstream_usd -> our_rub = round(upstream_usd * USD_TO_RUB * 2)
"""

import sys
import os
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import KIE config (единый источник для USD_TO_RUB)
from scripts.kie_config import get_usd_to_rub_rate, calculate_rub_price, KIEConfigError


@dataclass
class UpstreamModelInfo:
    """Информация о модели из upstream (Kie.ai docs)."""
    model_id: str
    input_schema: Dict[str, Any]  # name -> {required, type, default, options, constraints}
    upstream_usd_price: Optional[float] = None
    docs_url: Optional[str] = None
    fetched_at: Optional[str] = None


@dataclass
class ModelDiff:
    """Различия между upstream и локальным реестром."""
    model_id: str
    exists_locally: bool
    schema_changes: List[str]  # Список изменений в схеме
    price_changes: Optional[Dict[str, Any]] = None  # upstream_usd, our_current_rub, calculated_rub
    is_new_model: bool = False


def load_local_registry() -> Dict[str, Any]:
    """Загружает локальный реестр моделей."""
    # Ищем source of truth файл
    possible_paths = [
        project_root / "models" / "KIE_SOURCE_OF_TRUTH.json",
        project_root / "models" / "kie_models.json",
        project_root / "app" / "kie" / "models_registry.json",
    ]
    
    for path in possible_paths:
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    
    print("⚠️  Local registry not found, using empty dict")
    return {}


def parse_kie_docs_html(html_content: str, model_id: str) -> Optional[UpstreamModelInfo]:
    """
    Парсит HTML страницу Kie.ai docs для извлечения информации о модели.
    
    Ищет:
    - model_id из JSON примеров: "model": "..."
    - input schema из таблиц "Input Object Parameters" или JSON body
    - цены из таблиц или JSON примеров
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("⚠️  BeautifulSoup not available, skipping HTML parsing")
        return None
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Извлекаем model_id из JSON примеров
    found_model_id = None
    json_blocks = soup.find_all(['code', 'pre'], string=re.compile(r'"model"\s*:\s*"([^"]+)"'))
    for block in json_blocks:
        match = re.search(r'"model"\s*:\s*"([^"]+)"', block.get_text())
        if match:
            found_model_id = match.group(1)
            break
    
    if not found_model_id:
        # Fallback: используем переданный model_id
        found_model_id = model_id
    
    # Извлекаем input schema из таблиц
    input_schema = {}
    
    # Ищем таблицы с параметрами
    tables = soup.find_all('table')
    for table in tables:
        headers = [th.get_text().strip().lower() for th in table.find_all('th')]
        if 'parameter' in headers or 'field' in headers or 'name' in headers:
            rows = table.find_all('tr')[1:]  # Пропускаем заголовок
            for row in rows:
                cells = [td.get_text().strip() for td in row.find_all(['td', 'th'])]
                if len(cells) >= 2:
                    field_name = cells[0]
                    field_info = {
                        "required": "required" in " ".join(cells).lower(),
                        "type": cells[1] if len(cells) > 1 else "string",
                        "default": None,
                        "options": [],
                    }
                    input_schema[field_name] = field_info
    
    # Извлекаем цены (если есть)
    upstream_usd_price = None
    price_patterns = [
        r'\$(\d+\.?\d*)\s*(?:USD|usd)',
        r'(\d+\.?\d*)\s*(?:USD|usd)',
        r'price[:\s]+(\d+\.?\d*)',
    ]
    text = soup.get_text()
    for pattern in price_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                upstream_usd_price = float(match.group(1))
                break
            except ValueError:
                continue
    
    return UpstreamModelInfo(
        model_id=found_model_id,
        input_schema=input_schema,
        upstream_usd_price=upstream_usd_price,
        docs_url=None,  # Будет заполнено при вызове
        fetched_at=datetime.now().isoformat()
    )


def compare_with_local(
    upstream_info: UpstreamModelInfo,
    local_registry: Dict[str, Any],
    verify_only: bool = True
) -> Optional[ModelDiff]:
    """
    Сравнивает upstream информацию с локальным реестром.
    
    Args:
        upstream_info: Информация о модели из upstream
        local_registry: Локальный реестр моделей
        verify_only: Если True, только сверяет существующие модели, новые помечает как candidates
    
    Returns:
        ModelDiff если модель существует локально или verify_only=False, None если новая модель и verify_only=True
    """
    model_id = upstream_info.model_id
    
    # Ищем модель в локальном реестре
    local_model = None
    if "models" in local_registry:
        for model in local_registry["models"]:
            if model.get("model_id") == model_id:
                local_model = model
                break
    
    exists_locally = local_model is not None
    
    # В режиме verify-only пропускаем новые модели (они будут помечены как candidates отдельно)
    if verify_only and not exists_locally:
        return None  # Новая модель, не сравниваем
    
    schema_changes = []
    price_changes = None
    
    if exists_locally:
        # Сравниваем схему
        local_schema = local_model.get("input_schema", {})
        for field_name, upstream_field in upstream_info.input_schema.items():
            local_field = local_schema.get(field_name)
            if not local_field:
                schema_changes.append(f"New field in upstream: {field_name}")
            else:
                # Сравниваем required
                if upstream_field.get("required") != local_field.get("required"):
                    schema_changes.append(
                        f"Field {field_name}: required changed from {local_field.get('required')} to {upstream_field.get('required')}"
                    )
        
        # Сравниваем цены
        if upstream_info.upstream_usd_price:
            try:
                # Используем единый источник конфигурации (запрещает тихие дефолты)
                calculated_rub = calculate_rub_price(upstream_info.upstream_usd_price, markup_multiplier=2.0)
                local_price = local_model.get("pricing", {}).get("rub_per_gen")
                if local_price and local_price != calculated_rub:
                    price_changes = {
                        "upstream_usd": upstream_info.upstream_usd_price,
                        "our_current_rub": local_price,
                        "calculated_rub": calculated_rub,
                        "difference": calculated_rub - local_price
                    }
            except KIEConfigError as e:
                # Не молчим - выводим ошибку, но продолжаем работу
                print(f"⚠️  Price calculation skipped: {e}")
                schema_changes.append(f"Price calculation failed: USD_TO_RUB not configured")
    else:
        # Новая модель (только если verify_only=False)
        schema_changes.append("NEW MODEL - not in local registry")
    
    return ModelDiff(
        model_id=model_id,
        exists_locally=exists_locally,
        schema_changes=schema_changes,
        price_changes=price_changes,
        is_new_model=not exists_locally
    )


def fetch_kie_docs_page(url: str) -> Optional[str]:
    """Загружает HTML страницу Kie.ai docs."""
    try:
        import requests
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            return resp.text
        return None
    except Exception as e:
        print(f"⚠️  Failed to fetch {url}: {e}")
        return None


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Verify KIE models against upstream docs")
    parser.add_argument("--model-id", help="Specific model ID to check")
    parser.add_argument("--docs-url", help="URL to Kie.ai docs page")
    parser.add_argument("--html-file", help="Local HTML file instead of URL")
    parser.add_argument("--verify-only", action="store_true", 
                       help="Verify-only mode: only check existing models, mark new ones as candidates")
    parser.add_argument("--allow-new", action="store_true",
                       help="Allow processing new models (default: verify-only mode)")
    
    args = parser.parse_args()
    
    print("="*60)
    print("  KIE VERIFY PARSER")
    print("="*60)
    
    # Загружаем локальный реестр
    local_registry = load_local_registry()
    print(f"✅ Loaded local registry ({len(local_registry.get('models', []))} models)")
    
    # Определяем режим: verify_only по умолчанию, если не указан --allow-new
    verify_only_mode = not args.allow_new
    
    if args.verify_only and not args.docs_url and not args.html_file:
        print("ℹ️  Verify-only mode: no upstream fetch (use --docs-url or --html-file to fetch)")
        print("   Loading existing candidates...")
        
        # Показываем существующие candidates
        artifacts_dir = project_root / "artifacts"
        candidates_file = artifacts_dir / "kie_model_candidates.json"
        if candidates_file.exists():
            with open(candidates_file, 'r', encoding='utf-8') as f:
                candidates = json.load(f)
            print(f"   Found {len(candidates)} candidate models:")
            for c in candidates:
                print(f"     - {c.get('model_id')} (added: {c.get('added_at', 'unknown')})")
        else:
            print("   No candidates found")
        return 0
    
    # Если указан HTML файл, используем его
    html_content = None
    if args.html_file:
        with open(args.html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
    elif args.docs_url:
        print(f"📥 Fetching {args.docs_url}...")
        html_content = fetch_kie_docs_page(args.docs_url)
    
    if not html_content:
        print("❌ No HTML content available")
        return 1
    
    # Парсим
    model_id = args.model_id or "unknown"
    upstream_info = parse_kie_docs_html(html_content, model_id)
    
    if not upstream_info:
        print("❌ Failed to parse upstream info")
        return 1
    
    print(f"✅ Parsed upstream info for {upstream_info.model_id}")
    
    # Сравниваем (verify_only_mode по умолчанию - только существующие модели)
    diff = compare_with_local(upstream_info, local_registry, verify_only=verify_only_mode)
    
    # Если verify_only_mode и модель новая - помечаем как candidate
    if verify_only_mode and diff is None:
        # Новая модель - добавляем в candidates
        artifacts_dir = project_root / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        
        candidates_file = artifacts_dir / "kie_model_candidates.json"
        candidates = []
        if candidates_file.exists():
            with open(candidates_file, 'r', encoding='utf-8') as f:
                candidates = json.load(f)
        
        # Проверяем, нет ли уже такой модели в candidates
        if not any(c.get("model_id") == upstream_info.model_id for c in candidates):
            candidate = {
                "model_id": upstream_info.model_id,
                "upstream_info": asdict(upstream_info),
                "added_at": datetime.now().isoformat(),
                "status": "candidate",
                "note": "New model from upstream, requires manual review"
            }
            candidates.append(candidate)
            
            with open(candidates_file, 'w', encoding='utf-8') as f:
                json.dump(candidates, f, indent=2, ensure_ascii=False)
            
            print(f"\n✅ New model marked as CANDIDATE: {upstream_info.model_id}")
            print(f"💾 Candidates saved to {candidates_file}")
            return 0
    
    if diff is None:
        print("⚠️  Model not found locally and verify_only mode enabled (skipped, marked as candidate)")
        return 0
    
    # Выводим diff для существующих моделей
    print("\n" + "="*60)
    print("  DIFF REPORT")
    print("="*60)
    print(f"Model ID: {diff.model_id}")
    print(f"Exists locally: {diff.exists_locally}")
    print(f"Is new model: {diff.is_new_model}")
    
    if diff.schema_changes:
        print("\nSchema changes:")
        for change in diff.schema_changes:
            print(f"  - {change}")
    
    if diff.price_changes:
        print("\nPrice changes:")
        print(f"  Upstream USD: ${diff.price_changes['upstream_usd']}")
        print(f"  Our current RUB: ₽{diff.price_changes['our_current_rub']}")
        print(f"  Calculated RUB: ₽{diff.price_changes['calculated_rub']}")
        print(f"  Difference: ₽{diff.price_changes['difference']}")
    
    # Сохраняем snapshot
    artifacts_dir = project_root / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    
    snapshot = {
        "fetched_at": datetime.now().isoformat(),
        "model_id": upstream_info.model_id,
        "upstream_info": asdict(upstream_info),
        "diff": asdict(diff),
        "verify_only": verify_only_mode
    }
    
    snapshot_file = artifacts_dir / f"kie_upstream_snapshot_{upstream_info.model_id.replace('/', '_')}.json"
    with open(snapshot_file, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Snapshot saved to {snapshot_file}")
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

