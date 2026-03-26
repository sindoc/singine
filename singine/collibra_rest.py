"""Compatibility shim for Collibra REST helpers.

The canonical implementation lives in the sibling collibra repository under:

  collibra/singine-collibra/python/singine_collibra/rest.py

This shim preserves existing imports while moving the implementation boundary to
the collibra repo.
"""

from __future__ import annotations

from .collibra_idgen import _ensure_singine_collibra

if not _ensure_singine_collibra():
    raise ImportError("singine_collibra package not available via COLLIBRA_DIR")

from singine_collibra.rest import *  # noqa: F401,F403
