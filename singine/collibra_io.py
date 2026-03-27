"""Compatibility shim for Collibra I/O workflows.

Canonical impl at collibra/singine-collibra/python/singine_collibra/io.py
"""
from __future__ import annotations

import os
import sys

_COLLIBRA_ROOT = os.environ.get(
    "COLLIBRA_DIR",
    os.path.expanduser("~/ws/git/github/sindoc/collibra"),
)
_CANONICAL_PYTHON = os.path.join(_COLLIBRA_ROOT, "singine-collibra", "python")

if _CANONICAL_PYTHON not in sys.path and os.path.isdir(_CANONICAL_PYTHON):
    sys.path.insert(0, _CANONICAL_PYTHON)

try:
    from singine_collibra.io import *  # noqa: F401, F403
except ImportError:
    pass
