"""Fallback pytest_asyncio shim for environments without the dependency."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable

import pytest


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
