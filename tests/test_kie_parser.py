"""
Unit tests for Kie parser.

Tests parsing of HTML fixtures without network calls.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.kie_sync.parser import KieParser

# Fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "kie_pages"


@pytest.fixture
def parser():
    """Create parser instance."""
    return KieParser(cache_dir=FIXTURES_DIR)


@pytest.mark.asyncio
async def test_extract_model_id_from_json(parser):
    """Test extracting model_id from JSON block."""
    html = '''
    <html>
    <body>
    <pre>
    {
      "model": "nano-banana-pro",
      "input": {
        "prompt": "test"
      }
    }
    </pre>
    </body>
    </html>
    '''
    
    model_id = parser.extract_model_id(html, "https://docs.kie.ai/market/nano-banana-pro")
    assert model_id == "nano-banana-pro"


@pytest.mark.asyncio
async def test_extract_model_id_from_curl(parser):
    """Test extracting model_id from cURL example."""
    html = '''
    <html>
    <body>
    <pre>
    curl --request POST \\
      --url https://api.kie.ai/api/v1/jobs/createTask \\
      --data '{
        "model": "flux-2/pro-image-to-image",
        "input": {"prompt": "test"}
      }'
    </pre>
    </body>
    </html>
    '''
    
    model_id = parser.extract_model_id(html, "https://docs.kie.ai/market/flux-2/pro-image-to-image")
    assert model_id == "flux-2/pro-image-to-image"


@pytest.mark.asyncio
async def test_extract_model_id_from_url(parser):
    """Test extracting model_id from URL as fallback."""
    url = "https://docs.kie.ai/market/seedream/seedream"
    html = "<html><body>No model ID in content</body></html>"
    
    model_id = parser.extract_model_id(html, url)
    assert model_id == "seedream/seedream"


@pytest.mark.asyncio
async def test_extract_endpoints(parser):
    """Test extracting endpoints from HTML."""
    html = '''
    <html>
    <body>
    <p>POST https://api.kie.ai/api/v1/jobs/createTask</p>
    <p>GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=...</p>
    </body>
    </html>
    '''
    
    endpoints = parser.extract_endpoints(html)
    assert "create" in endpoints
    assert "record" in endpoints
    assert "createTask" in endpoints["create"]
    assert "recordInfo" in endpoints["record"]


@pytest.mark.asyncio
async def test_extract_input_schema_from_table(parser):
    """Test extracting input schema from parameter table."""
    html = '''
    <html>
    <body>
    <table>
    <tr><th>Parameter</th><th>Type</th><th>Required</th><th>Default</th></tr>
    <tr><td>prompt</td><td>string</td><td>Yes</td><td>-</td></tr>
    <tr><td>resolution</td><td>enum</td><td>No</td><td>1K</td></tr>
    <tr><td>aspect_ratio</td><td>enum</td><td>No</td><td>1:1</td></tr>
    </table>
    </body>
    </html>
    '''
    
    schema = parser.extract_input_schema(html)
    assert "prompt" in schema
    assert schema["prompt"]["required"] is True
    assert "resolution" in schema
    assert schema["resolution"].get("default") == "1K"


@pytest.mark.asyncio
async def test_extract_pricing_usd(parser):
    """Test extracting USD pricing."""
    html = '''
    <html>
    <body>
    <p>Price: $0.0175 USD per generation</p>
    <p>Credits: 3.5 credits</p>
    </body>
    </html>
    '''
    
    pricing = parser.extract_pricing(html)
    assert pricing.get("usd") == 0.0175
    assert pricing.get("credits") == 3


@pytest.mark.asyncio
async def test_parse_page_with_fixture(parser):
    """Test parsing a real fixture page."""
    # Create a simple fixture
    fixture_path = FIXTURES_DIR / "nano-banana-pro.html"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    
    fixture_html = '''
    <html>
    <head><title>Nano Banana Pro</title></head>
    <body>
    <h1>Nano Banana Pro</h1>
    <pre>
    {
      "model": "nano-banana-pro",
      "input": {
        "prompt": "A beautiful landscape",
        "resolution": "1K",
        "aspect_ratio": "1:1"
      }
    }
    </pre>
    <table>
    <tr><th>Parameter</th><th>Type</th><th>Required</th></tr>
    <tr><td>prompt</td><td>string</td><td>Yes</td></tr>
    <tr><td>resolution</td><td>enum</td><td>No</td></tr>
    </table>
    <p>Price: $0.018 USD</p>
    </body>
    </html>
    '''
    
    fixture_path.write_text(fixture_html, encoding='utf-8')
    
    # Parse
    url = "https://docs.kie.ai/market/nano-banana-pro"
    data = await parser.parse_page(url, use_cache=True)
    
    assert data is not None
    assert data["model_id"] == "nano-banana-pro"
    assert "prompt" in data["input_schema"]
    assert data["pricing"].get("usd") == 0.018


@pytest.mark.asyncio
async def test_discover_pages(parser):
    """Test discovering pages from index."""
    # Mock index page
    index_html = '''
    <html>
    <body>
    <a href="/market/nano-banana-pro">Nano Banana Pro</a>
    <a href="/market/flux-2/pro-image-to-image">Flux 2 Pro</a>
    <a href="https://docs.kie.ai/market/bytedance/v1-pro-fast-image-to-video">ByteDance V1 Pro</a>
    </body>
    </html>
    '''
    
    with patch.object(parser, 'fetch_page', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = (index_html, "test_checksum")
        
        pages = await parser.discover_pages()
        
        assert len(pages) > 0
        assert any("nano-banana-pro" in p for p in pages)
        assert any("flux-2" in p for p in pages)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

