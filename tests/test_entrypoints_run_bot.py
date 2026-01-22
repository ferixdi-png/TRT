import os

from entrypoints import run_bot


def test_is_preflight_strict_default_true(monkeypatch):
    monkeypatch.delenv("BILLING_PREFLIGHT_STRICT", raising=False)
    assert run_bot.is_preflight_strict() is True


def test_is_preflight_strict_false(monkeypatch):
    monkeypatch.setenv("BILLING_PREFLIGHT_STRICT", "0")
    assert run_bot.is_preflight_strict() is False


def test_is_preflight_strict_true(monkeypatch):
    monkeypatch.setenv("BILLING_PREFLIGHT_STRICT", "yes")
    assert run_bot.is_preflight_strict() is True
