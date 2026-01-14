"""Fallback pytest_asyncio shim for environments without the dependency.

This repository historically carried a tiny subset of ``pytest-asyncio`` so
tests can run even when the real dependency isn't installed.

One more wrinkle: in some environments, pytest discovers a ``pytest11``
entrypoint that imports ``pytest_asyncio.plugin``. If we only provide a
single-file module (``pytest_asyncio.py``), that import fails because Python
doesn't consider it a *package*.

To keep everything self-contained, this shim:
  - makes itself look like a package (sets ``__path__``), and
  - registers an in-memory submodule ``pytest_asyncio.plugin`` in ``sys.modules``.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
import types
from typing import Any, Callable

import pytest

# ---------------------------------------------------------------------------
# Make this module behave like a package so ``import pytest_asyncio.plugin``
# works in environments where pytest tries to load that plugin.
# ---------------------------------------------------------------------------

# If __path__ exists, importlib treats the module as a package.
__path__ = []  # type: ignore[var-annotated]


def fixture(*f_args, **f_kwargs):
    def decorator(func: Callable[..., Any]):
        if inspect.isasyncgenfunction(func):
            @pytest.fixture(*f_args, **f_kwargs)
            def wrapper(*args, **kwargs):
                async def runner():
                    async for value in func(*args, **kwargs):
                        return value
                    return None

                value = asyncio.run(runner())
                try:
                    yield value
                finally:
                    asyncio.run(func(*args, **kwargs).aclose())

            return wrapper

        if inspect.iscoroutinefunction(func):
            @pytest.fixture(*f_args, **f_kwargs)
            def wrapper(*args, **kwargs):
                return asyncio.run(func(*args, **kwargs))

            return wrapper

        return pytest.fixture(*f_args, **f_kwargs)(func)

    return decorator


def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: mark test to run in asyncio loop")


def pytest_pyfunc_call(pyfuncitem):
    test_func = pyfuncitem.obj
    if inspect.iscoroutinefunction(test_func):
        asyncio.run(test_func(**pyfuncitem.funcargs))
        return True
    return None


# ---------------------------------------------------------------------------
# Provide ``pytest_asyncio.plugin`` compatibility.
# ---------------------------------------------------------------------------

_plugin = types.ModuleType("pytest_asyncio.plugin")
_plugin.fixture = fixture  # type: ignore[attr-defined]
_plugin.pytest_configure = pytest_configure  # type: ignore[attr-defined]
_plugin.pytest_pyfunc_call = pytest_pyfunc_call  # type: ignore[attr-defined]
sys.modules.setdefault("pytest_asyncio.plugin", _plugin)

