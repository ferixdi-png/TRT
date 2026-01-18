import pytest

from app.kie.kie_client import KIEClient


def test_kie_client_sets_bearer_auth_header():
    client = KIEClient(api_key="test-key", base_url="https://example.com")
    headers = client._headers("corr-1")
    assert headers["Authorization"] == "Bearer test-key"
