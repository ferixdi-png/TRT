from app.integrations.kie_stub import KIEStub, get_kie_client_or_stub
from app.integrations.kie_client import KIEClient


def test_kie_env_uses_real_when_api_key_present(monkeypatch):
    monkeypatch.setenv("KIE_API_KEY", "test-key")
    monkeypatch.delenv("TEST_MODE", raising=False)
    monkeypatch.delenv("KIE_STUB", raising=False)
    client = get_kie_client_or_stub()
    assert isinstance(client, KIEClient)


def test_kie_env_uses_stub_when_forced(monkeypatch):
    monkeypatch.setenv("KIE_API_KEY", "test-key")
    monkeypatch.setenv("KIE_STUB", "1")
    monkeypatch.delenv("TEST_MODE", raising=False)
    client = get_kie_client_or_stub()
    assert isinstance(client, KIEStub)


def test_kie_env_uses_stub_in_test_mode(monkeypatch):
    monkeypatch.setenv("KIE_API_KEY", "test-key")
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.delenv("KIE_STUB", raising=False)
    client = get_kie_client_or_stub()
    assert isinstance(client, KIEStub)


def test_kie_env_uses_real_client_without_key(monkeypatch):
    """Without KIE_API_KEY, real client is returned (will fail with 401).
    
    Partners MUST provide their own KIE_API_KEY - no fallback to stub!
    """
    monkeypatch.delenv("KIE_API_KEY", raising=False)
    monkeypatch.delenv("TEST_MODE", raising=False)
    monkeypatch.delenv("KIE_STUB", raising=False)
    client = get_kie_client_or_stub()
    # Real client is returned - it will fail with 401 "KIE_API_KEY not configured"
    assert isinstance(client, KIEClient)
