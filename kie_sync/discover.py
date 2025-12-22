"""
Discover mode: find and analyze JSON endpoints and data structures from KIE Market
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
from playwright.async_api import async_playwright, Page, Request, Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KIE_MARKET_URL = "https://kie.ai/market"


def setup_network_interception(page: Page) -> List[Dict[str, Any]]:
    """
    Setup network request/response interception.
    
    Returns:
        List that will be populated with captured data
    """
    captured_data = []
    
    async def handle_request(request: Request):
        """Handle request interception"""
        if request.resource_type in ['xhr', 'fetch']:
            logger.debug(f"Request: {request.method} {request.url}")
    
    async def handle_response(response: Response):
        """Handle response interception"""
        try:
            if response.request.resource_type in ['xhr', 'fetch']:
                content_type = response.headers.get('content-type', '').lower()
                if 'application/json' in content_type:
                    try:
                        json_data = await response.json()
                        captured_data.append({
                            'url': response.url,
                            'method': response.request.method,
                            'status': response.status,
                            'data': json_data
                        })
                        logger.info(f"Captured JSON: {response.url} (status {response.status})")
                    except Exception as e:
                        logger.debug(f"Failed to parse JSON from {response.url}: {e}")
        except Exception as e:
            logger.debug(f"Error handling response: {e}")
    
    page.on('request', handle_request)
    page.on('response', handle_response)
    
    return captured_data


async def discover_model_page(model_slug: str, captured_data: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Discover JSON data structures for a specific model page.
    
    Args:
        model_slug: Model identifier/slug (e.g., "sora-2-text-to-video")
        captured_data: List to append captured requests/responses
    
    Returns:
        Dictionary with discovered model data structure or None
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        # Start intercepting
        captured_data_ref = setup_network_interception(page)
        
        # Navigate to model page
        model_url = f"{KIE_MARKET_URL}/{model_slug}" if model_slug else KIE_MARKET_URL
        logger.info(f"Navigating to: {model_url}")
        
        try:
            await page.goto(model_url, wait_until='networkidle', timeout=30000)
            
            # Wait a bit for any lazy-loaded data
            await asyncio.sleep(2)
            
            # Try to find API/data button and click if exists
            try:
                # Look for "API" tab or button
                api_button = await page.query_selector('button:has-text("API"), a:has-text("API"), [data-tab="api"]')
                if api_button:
                    await api_button.click()
                    await asyncio.sleep(1)
            except Exception as e:
                logger.debug(f"Could not click API tab: {e}")
            
            # Get page content to analyze
            page_content = await page.content()
            
            # Look for JSON data in script tags
            script_tags = await page.query_selector_all('script[type="application/json"], script#__NEXT_DATA__')
            for script in script_tags:
                try:
                    script_content = await script.text_content()
                    if script_content:
                        try:
                            json_data = json.loads(script_content)
                            captured_data.append({
                                'url': model_url,
                                'type': 'script_tag',
                                'data': json_data
                            })
                            logger.info(f"Found JSON in script tag on {model_url}")
                        except json.JSONDecodeError:
                            pass
                except Exception as e:
                    logger.debug(f"Error reading script tag: {e}")
            
        except Exception as e:
            logger.error(f"Error navigating to {model_url}: {e}")
        finally:
            await browser.close()
    
    return captured_data_ref if 'captured_data_ref' in locals() else []


async def discover_market_page() -> Dict[str, Any]:
    """
    Discover the market main page structure and extract model list.
    
    Returns:
        Dictionary with discovered market structure
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        captured_data = setup_network_interception(page)
        
        logger.info(f"Navigating to: {KIE_MARKET_URL}")
        
        try:
            await page.goto(KIE_MARKET_URL, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(2)
            
            # Look for model links or API endpoints
            # Try to find links to individual models
            model_links = await page.query_selector_all('a[href*="/market/"], [data-model-id], [data-model-slug]')
            
            models = []
            for link in model_links:
                try:
                    href = await link.get_attribute('href')
                    text = await link.text_content()
                    model_id = await link.get_attribute('data-model-id') or await link.get_attribute('data-model-slug')
                    models.append({
                        'href': href,
                        'text': text.strip() if text else None,
                        'model_id': model_id
                    })
                except Exception as e:
                    logger.debug(f"Error extracting model link: {e}")
            
            # Look for JSON in script tags
            script_tags = await page.query_selector_all('script[type="application/json"], script#__NEXT_DATA__')
            for script in script_tags:
                try:
                    script_content = await script.text_content()
                    if script_content:
                        try:
                            json_data = json.loads(script_content)
                            captured_data.append({
                                'url': KIE_MARKET_URL,
                                'type': 'script_tag',
                                'data': json_data
                            })
                        except json.JSONDecodeError:
                            pass
                except Exception as e:
                    logger.debug(f"Error reading script tag: {e}")
            
        except Exception as e:
            logger.error(f"Error navigating to {KIE_MARKET_URL}: {e}")
        finally:
            await browser.close()
    
    return {
        'captured_data': captured_data,
        'models': models if 'models' in locals() else []
    }


async def analyze_json_structure(data: Any, path: str = '') -> Dict[str, Any]:
    """
    Analyze JSON structure to find pricing and schema information.
    
    Args:
        data: JSON data to analyze
        path: Current path in JSON structure
    
    Returns:
        Dictionary with analysis results
    """
    analysis = {
        'has_pricing': False,
        'has_schema': False,
        'pricing_paths': [],
        'schema_paths': [],
        'structure_sample': {}
    }
    
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            
            # Check for pricing indicators
            if any(keyword in key.lower() for keyword in ['price', 'pricing', 'cost', 'credit', 'usd', 'cost']):
                analysis['has_pricing'] = True
                analysis['pricing_paths'].append(current_path)
            
            # Check for schema indicators
            if any(keyword in key.lower() for keyword in ['schema', 'input', 'param', 'field', 'required', 'enum', 'type']):
                analysis['has_schema'] = True
                analysis['schema_paths'].append(current_path)
            
            # Recursively analyze nested structures
            nested = analyze_json_structure(value, current_path)
            if nested['has_pricing']:
                analysis['has_pricing'] = True
                analysis['pricing_paths'].extend(nested['pricing_paths'])
            if nested['has_schema']:
                analysis['has_schema'] = True
                analysis['schema_paths'].extend(nested['schema_paths'])
            
            # Store sample structure (limit depth)
            if len(path.split('.')) < 3:
                if isinstance(value, (dict, list)):
                    analysis['structure_sample'][key] = type(value).__name__
                else:
                    analysis['structure_sample'][key] = str(value)[:50]
    
    elif isinstance(data, list) and data:
        # Analyze first item if it's a list
        nested = analyze_json_structure(data[0], f"{path}[0]")
        if nested['has_pricing']:
            analysis['has_pricing'] = True
            analysis['pricing_paths'].extend(nested['pricing_paths'])
        if nested['has_schema']:
            analysis['has_schema'] = True
            analysis['schema_paths'].extend(nested['schema_paths'])
    
    return analysis


async def main():
    """Main discover function"""
    logger.info("=== KIE Market Discover Mode ===")
    
    # Discover main market page
    logger.info("\n1. Discovering market main page...")
    market_data = await discover_market_page()
    
    print(f"\n=== Market Page Discovery ===")
    print(f"Captured {len(market_data['captured_data'])} JSON endpoints/data structures")
    print(f"Found {len(market_data['models'])} model links")
    
    # Analyze captured data
    print(f"\n=== JSON Structure Analysis ===")
    for i, item in enumerate(market_data['captured_data']):
        print(f"\n--- Endpoint/Data {i+1} ---")
        print(f"URL/Type: {item.get('url', item.get('type', 'unknown'))}")
        if 'method' in item:
            print(f"Method: {item['method']}")
        if 'status' in item:
            print(f"Status: {item['status']}")
        
        analysis = analyze_json_structure(item.get('data', {}))
        print(f"Has Pricing: {analysis['has_pricing']}")
        print(f"Has Schema: {analysis['has_schema']}")
        if analysis['pricing_paths']:
            print(f"Pricing Paths: {analysis['pricing_paths'][:5]}")
        if analysis['schema_paths']:
            print(f"Schema Paths: {analysis['schema_paths'][:5]}")
        
        # Show sample structure (first level)
        if analysis['structure_sample']:
            print(f"Sample Structure: {list(analysis['structure_sample'].keys())[:10]}")
    
    # Show model links
    if market_data['models']:
        print(f"\n=== Model Links Found ===")
        for model in market_data['models'][:10]:
            print(f"  - {model.get('text', 'N/A')}: {model.get('href', model.get('model_id', 'N/A'))}")
    
    # Save discovery results
    output_file = Path("kie_sync/discover_results.json")
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(market_data, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n=== Discovery Results Saved ===")
    print(f"File: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
