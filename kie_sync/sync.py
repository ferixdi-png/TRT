"""
Sync mode: extract pricing and input schemas from KIE Market pages
and write to pricing/config.yaml and models/catalog.yaml
"""

import asyncio
import json
import logging
import yaml
from typing import Dict, List, Any, Optional
from pathlib import Path
from playwright.async_api import async_playwright, Page, Request, Response

from kie_sync.validator import validate_pricing_config, validate_catalog_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KIE_MARKET_URL = "https://kie.ai/market"
PRICING_CONFIG_PATH = Path("pricing/config.yaml")
CATALOG_CONFIG_PATH = Path("models/catalog.yaml")


def normalize_model_id(model_slug: str) -> str:
    """
    Normalize model slug to model ID format.
    
    Examples:
        "sora-2-text-to-video" -> "sora-2-text-to-video"
        "wan-2-6" -> "wan/2-6-text-to-video" (needs type detection)
    """
    # For now, return as-is. Will be enhanced based on actual page structure
    return model_slug


def normalize_field_type(field_data: Dict[str, Any]) -> str:
    """
    Normalize field type to unified format.
    
    Returns: 'string', 'enum', 'array_url', 'number', 'bool'
    """
    field_type = field_data.get('type', '').lower()
    
    # Check for enum
    if 'enum' in field_data or 'options' in field_data:
        return 'enum'
    
    # Check for array of URLs
    if field_type == 'array':
        item_type = field_data.get('items', {}).get('type', '').lower()
        if 'url' in field_data.get('description', '').lower() or item_type == 'string':
            return 'array_url'
        return 'array'
    
    # Check for boolean
    if field_type in ['boolean', 'bool']:
        return 'bool'
    
    # Check for number
    if field_type in ['number', 'integer', 'int', 'float']:
        return 'number'
    
    # Default to string
    return 'string'


def normalize_field_schema(field_name: str, field_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize field schema to unified format.
    
    Returns normalized schema dict.
    """
    normalized = {
        'type': normalize_field_type(field_data),
        'required': field_data.get('required', False),
        'description': field_data.get('description', '')
    }
    
    # Add type-specific attributes
    if normalized['type'] == 'string':
        if 'maxLength' in field_data:
            normalized['max_length'] = field_data['maxLength']
        elif 'max_length' in field_data:
            normalized['max_length'] = field_data['max_length']
        if 'minLength' in field_data:
            normalized['min_length'] = field_data['minLength']
        elif 'min_length' in field_data:
            normalized['min_length'] = field_data['min_length']
    
    elif normalized['type'] == 'enum':
        enum_values = field_data.get('enum') or field_data.get('options', [])
        normalized['enum'] = [str(v) for v in enum_values]
    
    elif normalized['type'] == 'number':
        if 'minimum' in field_data:
            normalized['min'] = field_data['minimum']
        if 'maximum' in field_data:
            normalized['max'] = field_data['maximum']
        if 'default' in field_data:
            normalized['default'] = field_data['default']
    
    elif normalized['type'] == 'array_url':
        if 'minItems' in field_data:
            normalized['min_items'] = field_data['minItems']
        elif 'min_items' in field_data:
            normalized['min_items'] = field_data['min_items']
        if 'maxItems' in field_data:
            normalized['max_items'] = field_data['maxItems']
        elif 'max_items' in field_data:
            normalized['max_items'] = field_data['max_items']
    
    # Add default if present
    if 'default' in field_data and normalized['type'] != 'number':
        normalized['default'] = field_data['default']
    
    return normalized


def extract_pricing_from_page_data(page_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract pricing information from page JSON data.
    
    Returns pricing config dict or None.
    """
    # This will be implemented based on actual JSON structure discovered
    # For now, return placeholder structure
    return None


def extract_schema_from_page_data(page_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract input schema from page JSON data.
    
    Returns normalized schema dict or None.
    """
    # This will be implemented based on actual JSON structure discovered
    # For now, return placeholder structure
    return None


async def sync_model_page(model_slug: str, dry_run: bool = False) -> Dict[str, Any]:
    """
    Sync pricing and schema for a specific model page.
    
    Args:
        model_slug: Model slug (e.g., "sora-2-text-to-video")
        dry_run: If True, don't write files, just return what would change
    
    Returns:
        Dictionary with extracted data
    """
    model_url = f"{KIE_MARKET_URL}/{model_slug}"
    logger.info(f"Syncing model: {model_slug} from {model_url}")
    
    page_data = None
    pricing_data = None
    schema_data = None
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        try:
            await page.goto(model_url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(2)
            
            # Try to click API tab if exists
            try:
                api_button = await page.query_selector('button:has-text("API"), a:has-text("API"), [data-tab="api"]')
                if api_button:
                    await api_button.click()
                    await asyncio.sleep(1)
            except Exception as e:
                logger.debug(f"Could not click API tab: {e}")
            
            # Look for JSON in script tags
            script_tags = await page.query_selector_all('script[type="application/json"], script#__NEXT_DATA__')
            for script in script_tags:
                try:
                    script_content = await script.text_content()
                    if script_content:
                        try:
                            json_data = json.loads(script_content)
                            page_data = json_data
                            logger.info(f"Found JSON data for {model_slug}")
                            break
                        except json.JSONDecodeError:
                            pass
                except Exception as e:
                    logger.debug(f"Error reading script tag: {e}")
            
            # If no JSON found, try to extract from page content
            if not page_data:
                # Try to find pricing information in page text
                page_text = await page.text_content('body')
                logger.warning(f"No JSON data found for {model_slug}, will need manual extraction")
            
        except Exception as e:
            logger.error(f"Error syncing {model_slug}: {e}")
        finally:
            await browser.close()
    
    # Extract pricing and schema
    if page_data:
        pricing_data = extract_pricing_from_page_data(page_data)
        schema_data = extract_schema_from_page_data(page_data)
    
    return {
        'model_slug': model_slug,
        'pricing': pricing_data,
        'schema': schema_data,
        'page_data': page_data
    }


async def sync_all_models(dry_run: bool = False, model_filter: Optional[str] = None) -> Dict[str, Any]:
    """
    Sync all models from KIE Market.
    
    Args:
        dry_run: If True, show what would change without writing files
        model_filter: If provided, sync only this model
    
    Returns:
        Dictionary with sync results
    """
    # Load existing configs
    existing_pricing = {}
    existing_catalog = {}
    
    if PRICING_CONFIG_PATH.exists():
        with open(PRICING_CONFIG_PATH, 'r', encoding='utf-8') as f:
            existing_pricing = yaml.safe_load(f) or {}
    
    if CATALOG_CONFIG_PATH.exists():
        with open(CATALOG_CONFIG_PATH, 'r', encoding='utf-8') as f:
            existing_catalog = yaml.safe_load(f) or {}
    
    # Get model list (for now, use models from kie_models.py)
    from kie_models import KIE_MODELS
    
    models_to_sync = []
    if model_filter:
        models_to_sync = [m for m in KIE_MODELS if model_filter in m['id']]
    else:
        models_to_sync = KIE_MODELS
    
    logger.info(f"Syncing {len(models_to_sync)} models (dry_run={dry_run})")
    
    results = {
        'synced': [],
        'failed': [],
        'changes': {
            'pricing': {},
            'catalog': {}
        }
    }
    
    for model in models_to_sync[:5]:  # Limit to 5 for testing
        model_id = model['id']
        # Convert model ID to slug (simple conversion for now)
        model_slug = model_id.replace('/', '-')
        
        try:
            result = await sync_model_page(model_slug, dry_run)
            results['synced'].append(model_id)
            
            if result['pricing']:
                results['changes']['pricing'][model_id] = result['pricing']
            if result['schema']:
                results['changes']['catalog'][model_id] = result['schema']
                
        except Exception as e:
            logger.error(f"Failed to sync {model_id}: {e}")
            results['failed'].append({'model_id': model_id, 'error': str(e)})
    
    return results


async def main(dry_run: bool = False, model_filter: Optional[str] = None):
    """Main sync function"""
    logger.info(f"=== KIE Market Sync Mode (dry_run={dry_run}) ===")
    
    results = await sync_all_models(dry_run=dry_run, model_filter=model_filter)
    
    print(f"\n=== Sync Results ===")
    print(f"Synced: {len(results['synced'])} models")
    print(f"Failed: {len(results['failed'])} models")
    print(f"Pricing changes: {len(results['changes']['pricing'])} models")
    print(f"Catalog changes: {len(results['changes']['catalog'])} models")
    
    if dry_run:
        print("\n=== DRY RUN - No files modified ===")
        if results['changes']['pricing']:
            print("\nPricing changes that would be made:")
            for model_id, pricing in results['changes']['pricing'].items():
                print(f"  {model_id}: {pricing}")
        if results['changes']['catalog']:
            print("\nCatalog changes that would be made:")
            for model_id, schema in results['changes']['catalog'].items():
                print(f"  {model_id}: {len(schema.get('input_schema', {}))} fields")
    else:
        # TODO: Write to files
        print("\n=== Files would be updated here ===")
    
    if results['failed']:
        print("\n=== Failed Models ===")
        for failure in results['failed']:
            print(f"  {failure['model_id']}: {failure['error']}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--model', help='Sync specific model only')
    args = parser.parse_args()
    
    asyncio.run(main(dry_run=args.dry_run, model_filter=args.model))
