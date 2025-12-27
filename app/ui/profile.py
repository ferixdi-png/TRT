"""Backward-compat shim for wizard profile rendering.

Some flows import :func:`build_profile` from ``app.ui.profile``.
The implementation lives in ``app.ui.model_profile``.
This module keeps the import path stable.
"""

from .model_profile import build_profile

__all__ = ["build_profile"]
