import pytest

from app.kie.kie_client import KIEClient


@pytest.mark.asyncio
async def test_kie_client_requires_api_key():
    client = KIEClient(api_key=None, base_url="https://example.com")
    result = await client._request_json("GET", "/api/v1/models")
    assert result["ok"] is False
    assert "KIE_API_KEY" in result["error"]
