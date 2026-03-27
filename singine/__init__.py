"""Singine - CLI, bridge, and notebook-facing helpers."""

from .personal_os import build_personal_os_manifest, write_personal_os_bundle
from .zip_neighborhood_demo import build_zip_neighborhood_demo, write_zip_neighborhood_demo_bundle

__version__ = "0.1.0"

__all__ = [
    "build_personal_os_manifest",
    "build_zip_neighborhood_demo",
    "write_personal_os_bundle",
    "write_zip_neighborhood_demo_bundle",
]
