import importlib

import pytest


def test_legacy_singleton_lock_module_removed():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.singleton_lock")
