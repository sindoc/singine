"""Compatibility shim for Collibra I/O workflows.

The canonical implementation lives in the sibling collibra repository under:

  collibra/singine-collibra/python/singine_collibra/io.py

This shim keeps the existing singine import path stable while delegating the
actual implementation to the Collibra repo.
"""

from __future__ import annotations

from .collibra_idgen import _ensure_singine_collibra

if not _ensure_singine_collibra():
    raise ImportError("singine_collibra package not available via COLLIBRA_DIR")

from singine_collibra.io import *  # noqa: F401,F403
