"""Lens system for viewing Logseq entities through different metamodel perspectives.

This module provides abstraction layers (lenses) that transform Logseq entities
into various metamodel representations, primarily focused on Collibra.
"""

from .base import Lens, LensRegistry
from .collibra import CollibraLens, CollibraAsset, CollibraRelation
from .activity import ActivityLens, Activity, ActivityType

__all__ = [
    'Lens',
    'LensRegistry',
    'CollibraLens',
    'CollibraAsset',
    'CollibraRelation',
    'ActivityLens',
    'Activity',
    'ActivityType',
]
