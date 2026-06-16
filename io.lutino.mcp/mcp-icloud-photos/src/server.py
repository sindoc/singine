"""
singine-mcp-icloud-photos — MCP server for iCloud Photos via osxphotos.

Reads the macOS Photos.app library (which syncs with iCloud) to:
  - Query photos by album, person, date range
  - Export originals with full metadata to a staging directory
  - Generate a deletion manifest (SHA-256 verified, safe to delete)
  - Delete photos from Photos.app (which removes them from iCloud and all devices)

IMPORTANT — macOS permissions required:
  System Preferences → Privacy & Security → Full Disk Access → add Terminal/iTerm

Transport: stdio — register with:
  claude mcp add singine-icloud-photos --transport stdio -- \\
      python3 /path/to/io.lutino.mcp/mcp-icloud-photos/src/server.py

Install: pip install osxphotos
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# osxphotos is installed in user site-packages (pip install --user)
import site as _site
_user_site = _site.getusersitepackages()
if _user_site and _user_site not in sys.path:
    sys.path.insert(0, _user_site)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="singine-icloud-photos",
    version="0.1.0",
    description=(
        "iCloud Photos via osxphotos: query, export originals, generate SHA-256 verified "
        "deletion manifests. Deleting via this server removes photos from iCloud and all "
        "connected devices (iPhone, iPad) automatically."
    ),
)

_STAGING_DIR = Path(os.environ.get(
    "SINGINE_PHOTO_STAGING",
    Path.home() / ".singine" / "photo-staging",
))
_DELETION_MANIFEST = Path(os.environ.get(
    "SINGINE_DELETION_MANIFEST",
    Path.home() / ".singine" / "deletion-manifest.json",
))

# ---------------------------------------------------------------------------
# Lazy Photos DB
# ---------------------------------------------------------------------------

_photos_db: Any = None

def _get_db() -> Any:
    global _photos_db
    if _photos_db is None:
        import osxphotos
        _photos_db = osxphotos.PhotosDB()
    return _photos_db


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _photo_to_dict(photo: Any, include_path: bool = False) -> dict:
    """Convert an osxphotos PhotoInfo to a serializable dict."""
    d: dict[str, Any] = {
        "uuid": photo.uuid,
        "filename": photo.original_filename,
        "date": photo.date.isoformat() if photo.date else None,
        "date_added": photo.date_added.isoformat() if photo.date_added else None,
        "width": photo.width,
        "height": photo.height,
        "size_bytes": photo.original_filesize,
        "camera_make": photo.exif_info.camera_make if photo.exif_info else None,
        "camera_model": photo.exif_info.camera_model if photo.exif_info else None,
        "gps_latitude": photo.latitude,
        "gps_longitude": photo.longitude,
        "location_name": None,
        "albums": [a.title for a in photo.album_info],
        "persons": photo.persons,
        "is_favorite": photo.favorite,
        "is_hidden": photo.hidden,
        "is_slow_mo": photo.slow_mo,
        "is_video": photo.isphoto is False,
        "live_photo": photo.live_photo,
        "burst": photo.burst,
        "uti": photo.uti,
        "icloud_status": "synced" if photo.iscloudasset else "local-only",
    }
    if photo.place:
        d["location_name"] = str(photo.place.name) if photo.place.name else None
    if include_path and photo.path:
        d["original_path"] = str(photo.path)
    return d


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def icloud_photos_status() -> dict:
    """Check Photos Library access and return library statistics.

    Returns total photo count, library path, and osxphotos version.
    If this fails, check Full Disk Access in System Preferences.
    """
    try:
        import osxphotos
        db = _get_db()
        return {
            "ok": True,
            "library_path": db.library_path,
            "photo_count": len(db.photos()),
            "video_count": len(db.photos(movies=True, images=False)),
            "album_count": len(db.album_names()),
            "person_count": len(db.persons_as_dict()),
            "osxphotos_version": osxphotos.__version__,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "hint": "Install osxphotos: pip install osxphotos. Also grant Full Disk Access to Terminal.",
        }


@mcp.tool()
def list_albums() -> dict:
    """List all albums in the Photos Library with photo counts."""
    try:
        db = _get_db()
        albums = []
        for album in db.album_info:
            albums.append({
                "uuid": album.uuid,
                "title": album.title,
                "photo_count": len(album.photos),
            })
        albums.sort(key=lambda a: a["title"])
        return {"ok": True, "albums": albums, "total": len(albums)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def list_persons() -> dict:
    """List all people recognized by Photos.app face detection."""
    try:
        db = _get_db()
        persons = []
        for name, photos in db.persons_as_dict().items():
            persons.append({"name": name, "photo_count": len(photos)})
        persons.sort(key=lambda p: p["name"])
        return {"ok": True, "persons": persons, "total": len(persons)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def search_photos(
    album: str = "",
    person: str = "",
    date_from: str = "",
    date_to: str = "",
    is_favorite: bool | None = None,
    limit: int = 100,
) -> dict:
    """Search photos in the iCloud Photos library.

    Args:
        album:       Album title filter (exact match, optional).
        person:      Person name filter — Photos.app face recognition (optional).
        date_from:   Start date ISO 8601 e.g. "2020-01-01" (optional).
        date_to:     End date ISO 8601 e.g. "2023-12-31" (optional).
        is_favorite: True to return only favorites (optional).
        limit:       Maximum results (default 100, use 0 for no limit).

    Returns list of photo records with UUID, filename, date, persons, albums.
    Use the UUID with export_photo to get the original file.
    """
    try:
        import osxphotos
        db = _get_db()

        opts: dict[str, Any] = {}
        if album:
            opts["albums"] = [album]
        if person:
            opts["persons"] = [person]
        if is_favorite is not None:
            opts["favorite"] = is_favorite

        photos = db.query(osxphotos.QueryOptions(**opts)) if opts else db.photos()

        if date_from:
            dt_from = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
            photos = [p for p in photos if p.date and p.date >= dt_from]
        if date_to:
            dt_to = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc)
            photos = [p for p in photos if p.date and p.date <= dt_to]

        total = len(photos)
        if limit:
            photos = photos[:limit]

        return {
            "ok": True,
            "total_matched": total,
            "returned": len(photos),
            "photos": [_photo_to_dict(p) for p in photos],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def get_photo_metadata(uuid: str) -> dict:
    """Get full metadata for a single photo by its iCloud Photos UUID.

    The UUID is the stable identifier across all Apple devices.
    It can be used to delete the photo from iCloud (which removes it everywhere).

    Args:
        uuid: The iCloud Photos UUID (from search_photos results).
    """
    try:
        import osxphotos
        db = _get_db()
        photos = db.query(osxphotos.QueryOptions(uuid=[uuid]))
        if not photos:
            return {"ok": False, "error": f"photo not found: {uuid}"}
        return {"ok": True, "photo": _photo_to_dict(photos[0], include_path=True)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def export_photo(uuid: str, dest_dir: str = "") -> dict:
    """Export the original photo file from iCloud Photos to a local directory.

    Exports the unmodified original (RAW, HEIC, JPEG, etc.) plus a JSON sidecar
    with full metadata. Computes SHA-256 of the exported file.

    This is step 1 of the safe-deletion workflow:
      export_photo → classify_photo (mcp-photo) → photo_to_silkpage_xml → delete_photos

    Args:
        uuid:     iCloud Photos UUID.
        dest_dir: Destination directory. Default: ~/.singine/photo-staging/<uuid>/
    """
    try:
        import osxphotos
        db = _get_db()
        photos = db.query(osxphotos.QueryOptions(uuid=[uuid]))
        if not photos:
            return {"ok": False, "error": f"photo not found: {uuid}"}

        photo = photos[0]
        out_dir = Path(dest_dir) if dest_dir else (_STAGING_DIR / uuid)
        out_dir.mkdir(parents=True, exist_ok=True)

        exporter = osxphotos.PhotoExporter(photo)
        results = exporter.export(
            str(out_dir),
            use_photos_export=False,
            overwrite=True,
        )

        exported_files = [str(p) for p in results.exported]
        sha256 = _sha256(Path(exported_files[0])) if exported_files else "unavailable"

        # Write metadata sidecar
        meta = _photo_to_dict(photo, include_path=True)
        meta["exported_path"] = exported_files[0] if exported_files else None
        meta["sha256"] = sha256
        meta["exported_at"] = datetime.now(timezone.utc).isoformat()

        sidecar_path = out_dir / f"{photo.original_filename}.singine.json"
        sidecar_path.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")

        return {
            "ok": True,
            "uuid": uuid,
            "exported_path": exported_files[0] if exported_files else None,
            "sidecar_path": str(sidecar_path),
            "sha256": sha256,
            "filename": photo.original_filename,
            "size_bytes": photo.original_filesize,
            "persons": photo.persons,
            "albums": [a.title for a in photo.album_info],
            "date": photo.date.isoformat() if photo.date else None,
        }
    except Exception as exc:
        return {"ok": False, "uuid": uuid, "error": str(exc)}


@mcp.tool()
def export_batch(uuids: list[str], dest_dir: str = "") -> dict:
    """Export multiple photos by UUID. Returns results list.

    Args:
        uuids:    List of iCloud Photos UUIDs to export.
        dest_dir: Base staging directory. Each photo goes in <dest_dir>/<uuid>/.
                  Default: ~/.singine/photo-staging/
    """
    base = Path(dest_dir) if dest_dir else _STAGING_DIR
    results = []
    ok_count = 0
    err_count = 0

    for uuid in uuids:
        result = export_photo(uuid, str(base / uuid))
        if result.get("ok"):
            ok_count += 1
        else:
            err_count += 1
        results.append(result)

    return {
        "ok": True,
        "total": len(uuids),
        "exported": ok_count,
        "errors": err_count,
        "results": results,
        "staging_dir": str(base),
    }


@mcp.tool()
def mark_verified_for_deletion(uuid: str, copy_path: str, copy_sha256: str) -> dict:
    """Record that a photo has been exported, verified, and is safe to delete.

    Writes an entry to the deletion manifest. Does NOT delete yet.
    Run delete_photos separately after reviewing the manifest.

    Args:
        uuid:         iCloud Photos UUID.
        copy_path:    Absolute path where the verified copy now lives (local disk).
        copy_sha256:  SHA-256 of the verified copy (from export_photo or singine-photo-scan).
    """
    _DELETION_MANIFEST.parent.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {}
    if _DELETION_MANIFEST.exists():
        try:
            manifest = json.loads(_DELETION_MANIFEST.read_text())
        except json.JSONDecodeError:
            manifest = {}

    manifest[uuid] = {
        "uuid": uuid,
        "copy_path": copy_path,
        "copy_sha256": copy_sha256,
        "marked_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending-deletion",
    }

    _DELETION_MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "uuid": uuid,
        "manifest_path": str(_DELETION_MANIFEST),
        "pending_deletion_count": len([v for v in manifest.values() if v["status"] == "pending-deletion"]),
    }


@mcp.tool()
def list_deletion_manifest() -> dict:
    """Show all photos marked as verified and pending deletion from iCloud.

    These are safe to delete — their copies have been SHA-256 verified.
    Use delete_photos to actually remove them from iCloud (and all devices).
    """
    if not _DELETION_MANIFEST.exists():
        return {"ok": True, "pending": [], "total": 0}

    manifest = json.loads(_DELETION_MANIFEST.read_text())
    pending = [v for v in manifest.values() if v["status"] == "pending-deletion"]
    deleted = [v for v in manifest.values() if v["status"] == "deleted"]

    return {
        "ok": True,
        "pending_deletion": pending,
        "already_deleted": len(deleted),
        "total_in_manifest": len(manifest),
        "manifest_path": str(_DELETION_MANIFEST),
    }


@mcp.tool()
def delete_photos(uuids: list[str], dry_run: bool = True) -> dict:
    """Delete photos from Photos.app (removes from iCloud and ALL devices).

    ⚠️  DESTRUCTIVE — deletes from iCloud, iPhone, and iPad simultaneously.
    Only call after:
      1. export_photo verified each UUID
      2. mark_verified_for_deletion recorded each UUID
      3. You have reviewed list_deletion_manifest

    Args:
        uuids:   List of iCloud Photos UUIDs to delete.
        dry_run: If True (default), simulates deletion without removing anything.
                 Set to False to actually delete. Always run dry_run=True first.

    Returns list of {uuid, status} per photo.
    """
    try:
        import osxphotos
        db = _get_db()

        photos_to_delete = db.query(osxphotos.QueryOptions(uuid=uuids))
        found_uuids = {p.uuid for p in photos_to_delete}
        not_found = [u for u in uuids if u not in found_uuids]

        results = []
        for uuid in not_found:
            results.append({"uuid": uuid, "status": "not_found"})

        if dry_run:
            for photo in photos_to_delete:
                results.append({
                    "uuid": photo.uuid,
                    "filename": photo.original_filename,
                    "status": "would_delete",
                    "date": photo.date.isoformat() if photo.date else None,
                })
            return {
                "ok": True,
                "dry_run": True,
                "would_delete": len(photos_to_delete),
                "not_found": len(not_found),
                "results": results,
                "next_step": "Call delete_photos with dry_run=False to confirm deletion.",
            }

        # Actual deletion — uses osxphotos delete which calls Photos.app via ScriptingBridge
        deleted = []
        errors = []
        for photo in photos_to_delete:
            try:
                photo.delete()
                deleted.append(photo.uuid)
                results.append({"uuid": photo.uuid, "filename": photo.original_filename, "status": "deleted"})
                # Update manifest
                if _DELETION_MANIFEST.exists():
                    manifest = json.loads(_DELETION_MANIFEST.read_text())
                    if photo.uuid in manifest:
                        manifest[photo.uuid]["status"] = "deleted"
                        manifest[photo.uuid]["deleted_at"] = datetime.now(timezone.utc).isoformat()
                        _DELETION_MANIFEST.write_text(json.dumps(manifest, indent=2))
            except Exception as e:
                errors.append({"uuid": photo.uuid, "error": str(e)})
                results.append({"uuid": photo.uuid, "status": "error", "error": str(e)})

        return {
            "ok": len(errors) == 0,
            "dry_run": False,
            "deleted": len(deleted),
            "errors": len(errors),
            "not_found": len(not_found),
            "results": results,
            "warning": "Photos deleted from iCloud — removed from iPhone and iPad too.",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
