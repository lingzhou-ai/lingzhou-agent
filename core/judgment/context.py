"""Compatibility facade for judgment context helpers.

This module keeps legacy import paths stable while implementation lives in
core/judgment/context_helpers.py.
"""

from __future__ import annotations

from . import context_helpers as _helpers

__all__ = list(getattr(_helpers, "__all__", ()))

for _name in __all__:
    globals()[_name] = getattr(_helpers, _name)

if "_name" in locals():
    del _name

del _helpers
