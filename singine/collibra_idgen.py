"""Singine CLI glue for ``singine collibra id/contract/server`` subcommands.

Dynamically imports the ``singine_collibra`` package from the collibra
repository (default: ~/ws/git/github/sindoc/collibra or $COLLIBRA_DIR).
The preferred layout is:

  collibra/singine-collibra/python/singine_collibra/

The legacy top-level ``collibra/singine_collibra/`` path is still accepted as a
fallback during migration.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _collibra_root() -> Path:
    return Path(
        os.environ.get(
            "COLLIBRA_DIR",
            str(Path.home() / "ws/git/github/sindoc/collibra"),
        )
    )


def _candidate_python_roots() -> list[str]:
    root = _collibra_root()
    return [
        str(root / "singine-collibra" / "python"),
        str(root),
    ]


def _ensure_singine_collibra() -> bool:
    """Add candidate Collibra Python roots to sys.path so singine_collibra imports."""
    for candidate in reversed(_candidate_python_roots()):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
    try:
        import singine_collibra  # noqa: F401
        return True
    except ImportError:
        return False


def _not_found(component: str) -> int:
    root = _collibra_root()
    print(
        f"[singine collibra] ERROR: singine_collibra package not found.\n"
        f"  Expected: {root}/singine-collibra/python/singine_collibra/\n"
        f"  Fallback: {root}/singine_collibra/\n"
        f"  Set COLLIBRA_DIR to the collibra repo root or clone it there."
    )
    return 1


# Re-export add_collibra_subcommands for use in build_parser()
def add_collibra_subcommands(collibra_sub: argparse._SubParsersAction) -> bool:
    """Dynamically load and register id/contract/server subcommands.

    Returns True if the singine_collibra package was found and loaded,
    False otherwise (commands will not be registered).
    """
    if not _ensure_singine_collibra():
        return False
    from singine_collibra.command import add_collibra_subcommands as _add
    _add(collibra_sub)
    return True
