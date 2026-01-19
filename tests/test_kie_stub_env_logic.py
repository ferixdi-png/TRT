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


def test_kie_env_uses_stub_without_key(monkeypatch):
    monkeypatch.delenv("KIE_API_KEY", raising=False)
    monkeypatch.delenv("TEST_MODE", raising=False)
    monkeypatch.delenv("KIE_STUB", raising=False)
    client = get_kie_client_or_stub()
    assert isinstance(client, KIEStub)
