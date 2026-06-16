"""
singine-mcp-silkpage-photo — MCP server that maps photo classification data
to silkpage XML (DocBook + SKOS sidebar) and manages layout.xml registration.

Transport: stdio — register with:
  claude mcp add singine-silkpage-photo --transport stdio -- \\
      python3 /path/to/io.lutino.mcp/mcp-silkpage-photo/src/server.py

Environment variables:
  SINGINE_SILKPAGE_ROOT  Path to silkpage repo www root.
                         Default: ~/ws/silkpage/main/silkpage/www/silkpage.markupware.com
  SINGINE_LAYOUT_XML     Path to layout.xml.
                         Default: <SILKPAGE_ROOT>/src/xml/en/layout.xml
  SINGINE_PHOTOS_XML_DIR Path to photo XML output directory.
                         Default: <SILKPAGE_ROOT>/src/xml/en/photos
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from string import Template
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="singine-silkpage-photo",
    instructions=(
        "Generate silkpage XML (DocBook + SKOS sidebar) from photo classification data "
        "and register pages in layout.xml."
    ),
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_SILKPAGE_ROOT = Path(os.environ.get(
    "SINGINE_SILKPAGE_ROOT",
    Path.home() / "ws/silkpage/main/silkpage/www/silkpage.markupware.com",
))
_LAYOUT_XML = Path(os.environ.get(
    "SINGINE_LAYOUT_XML",
    _SILKPAGE_ROOT / "src/xml/en/layout.xml",
))
_PHOTOS_XML_DIR = Path(os.environ.get(
    "SINGINE_PHOTOS_XML_DIR",
    _SILKPAGE_ROOT / "src/xml/en/photos",
))

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

_CATEGORY_LABELS = {
    "FamilyPhoto": "Family Photo",
    "FriendsPhoto": "Friends Photo",
    "ExSpousePresent": "Ex-Spouse Present",
    "SceneryOnly": "Scenery Only",
    "OccasionPhoto": "Occasion Photo",
    "UnclassifiedPhoto": "Unclassified",
}

_ACTION_LABELS = {
    "KeepPrimary": "Keep — Primary Archive",
    "ArchiveSeparate": "Archive — Separate",
    "ArchiveSecondary": "Archive — Secondary",
    "FlagForReview": "Flag for Manual Review",
}

_PHOTO_XML_TEMPLATE = """\
<?xml version='1.0' encoding='UTF-8'?>
<webpage xmlns:db="http://docbook.org/ns/docbook"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         xmlns:skos="http://www.w3.org/2004/02/skos/core#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         id="photo-${photo_id}">

  <config param="rcsdate" value="$$Date: ${taken} $$"/>

  <head>
    <title>${filename}</title>
    <summary>${description}</summary>
    <keywords>photo, ${occasion}, ${category_key}, ${action_key}</keywords>
  </head>

  <sidebar id="photo-${photo_id}-skos">
    <db:title>Classification Context</db:title>
    <skos:Concept rdf:about="urn:sindoc:photo:category:${category_key}">
      <skos:prefLabel xml:lang="en">${category_label}</skos:prefLabel>
      <skos:broader rdf:resource="urn:sindoc:photo:PhotoAsset"/>
      <skos:inScheme rdf:resource="urn:sindoc:scheme:photo-classification"/>
    </skos:Concept>
    <skos:Concept rdf:about="urn:sindoc:photo:action:${action_key}">
      <skos:prefLabel xml:lang="en">${action_label}</skos:prefLabel>
      <skos:inScheme rdf:resource="urn:sindoc:scheme:photo-classification"/>
    </skos:Concept>
  </sidebar>

  <db:section role="provenance">
    <db:title>Provenance</db:title>
    <db:informaltable><db:tgroup cols="2"><db:tbody>
      <db:row><db:entry>File</db:entry><db:entry>${filename}</db:entry></db:row>
      <db:row><db:entry>Taken</db:entry><db:entry>${taken}</db:entry></db:row>
      <db:row><db:entry>Source system</db:entry><db:entry>${source}</db:entry></db:row>
      <db:row><db:entry>SHA-256 (original)</db:entry><db:entry>${sha256}</db:entry></db:row>
    </db:tbody></db:tgroup></db:informaltable>
  </db:section>

  <db:section role="source-ids">
    <db:title>Source Identifiers</db:title>
    <db:para role="note">These identifiers are required to safely delete the original
    from each source system once the local copy is verified.</db:para>
    <db:informaltable><db:tgroup cols="3">
      <db:thead>
        <db:row>
          <db:entry>System</db:entry>
          <db:entry>Identifier</db:entry>
          <db:entry>Copy verified</db:entry>
        </db:row>
      </db:thead>
      <db:tbody>
${source_id_rows}
      </db:tbody>
    </db:tgroup></db:informaltable>
    <db:para role="copy-location">Local copy: <db:filename>${copy_path}</db:filename></db:para>
    <db:para role="copy-sha256">Copy SHA-256: ${copy_sha256}</db:para>
  </db:section>

  <db:section role="faces">
    <db:title>Recognized Faces</db:title>
    <db:itemizedlist>
${faces_items}
    </db:itemizedlist>
  </db:section>

  <db:section role="scene">
    <db:title>Scene Analysis</db:title>
    <db:informaltable><db:tgroup cols="2"><db:tbody>
      <db:row><db:entry>Occasion</db:entry><db:entry>${occasion}</db:entry></db:row>
      <db:row><db:entry>Setting</db:entry><db:entry>${setting}</db:entry></db:row>
      <db:row><db:entry>Sentiment</db:entry><db:entry>${sentiment}</db:entry></db:row>
      <db:row><db:entry>People</db:entry><db:entry>${people_count}</db:entry></db:row>
    </db:tbody></db:tgroup></db:informaltable>
    <db:para>${description}</db:para>
  </db:section>

  <db:section role="decision">
    <db:title>Archival Decision</db:title>
    <db:informaltable><db:tgroup cols="2"><db:tbody>
      <db:row><db:entry>Category</db:entry><db:entry>${category_label}</db:entry></db:row>
      <db:row><db:entry>Action</db:entry><db:entry>${action_label}</db:entry></db:row>
      <db:row><db:entry>Reason</db:entry><db:entry>${reason}</db:entry></db:row>
    </db:tbody></db:tgroup></db:informaltable>
  </db:section>

</webpage>
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_id(filename: str) -> str:
    stem = Path(filename).stem
    return re.sub(r"[^a-z0-9_-]", "_", stem.lower())[:64]


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return "unavailable"


def _faces_to_xml_items(faces: list[dict]) -> str:
    lines = []
    for f in faces:
        name = f.get("name", "unknown")
        conf = f.get("confidence", 0.0)
        lines.append(
            f'      <db:listitem><db:para>'
            f'<db:emphasis role="person">{name}</db:emphasis>'
            f' (confidence: {conf:.0%})'
            f'</db:para></db:listitem>'
        )
    return "\n".join(lines) if lines else '      <db:listitem><db:para>No faces detected.</db:para></db:listitem>'


def _source_id_rows(source_info: list[dict]) -> str:
    """Render <db:row> entries for the source-ids table."""
    if not source_info:
        return '        <db:row><db:entry>unknown</db:entry><db:entry>—</db:entry><db:entry>—</db:entry></db:row>'
    rows = []
    for s in source_info:
        system = s.get("system", "unknown")
        sid = s.get("id", "—")
        verified = "yes" if s.get("copy_verified") else "pending"
        rows.append(
            f'        <db:row>'
            f'<db:entry>{system}</db:entry>'
            f'<db:entry>{sid}</db:entry>'
            f'<db:entry>{verified}</db:entry>'
            f'</db:row>'
        )
    return "\n".join(rows)


def _render_xml(classification: dict[str, Any]) -> str:
    image_path = classification.get("image", "")
    filename = Path(image_path).name if image_path else "unknown.jpg"
    photo_id = _safe_id(filename)

    faces = classification.get("faces", [])
    scene = classification.get("scene", {})
    decision = classification.get("decision", {})

    category_key = decision.get("category", "UnclassifiedPhoto")
    action_key = decision.get("action", "FlagForReview")

    taken = classification.get("taken") or datetime.now(timezone.utc).isoformat()
    source = classification.get("source", "unknown")
    sha256 = _sha256(image_path) if image_path and Path(image_path).exists() else "unavailable"

    # source_info: list of {system, id, copy_verified} from iCloud/Google/local
    source_info: list[dict] = classification.get("source_info", [])
    if not source_info and source != "unknown":
        # Build a minimal entry from the flat source field
        source_info = [{"system": source, "id": classification.get("source_id", "—"), "copy_verified": False}]

    copy_path = classification.get("copy_path", "—")
    copy_sha256 = classification.get("copy_sha256", "—")

    values = {
        "photo_id": photo_id,
        "filename": filename,
        "taken": taken,
        "source": source,
        "sha256": sha256,
        "source_id_rows": _source_id_rows(source_info),
        "copy_path": copy_path,
        "copy_sha256": copy_sha256,
        "faces_items": _faces_to_xml_items(faces),
        "occasion": scene.get("occasion", "unknown"),
        "setting": scene.get("setting", "unknown"),
        "sentiment": scene.get("sentiment", "neutral"),
        "people_count": str(scene.get("people_count", 0)),
        "description": scene.get("description", ""),
        "category_key": category_key,
        "category_label": _CATEGORY_LABELS.get(category_key, category_key),
        "action_key": action_key,
        "action_label": _ACTION_LABELS.get(action_key, action_key),
        "reason": decision.get("reason", ""),
    }

    return Template(_PHOTO_XML_TEMPLATE).safe_substitute(values)


def _write_xml_file(xml_content: str, photo_id: str) -> Path:
    _PHOTOS_XML_DIR.mkdir(parents=True, exist_ok=True)
    out = _PHOTOS_XML_DIR / f"{photo_id}.xml"
    out.write_text(xml_content, encoding="utf-8")
    return out


def _register_in_layout(page_id: str, page_filename: str) -> bool:
    """Append a <notoc> entry for this photo page to layout.xml."""
    if not _LAYOUT_XML.exists():
        return False

    content = _LAYOUT_XML.read_text(encoding="utf-8")
    entry = f'<notoc page="photos/{page_filename}" dir="photos/{page_id}" filename="index.html"/>'

    # Idempotent — skip if already registered
    if f'photos/{page_filename}' in content:
        return True

    # Insert before closing </layout>
    content = content.replace("</layout>", f"{entry}\n</layout>")
    _LAYOUT_XML.write_text(content, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def photo_to_silkpage_xml(classification: dict) -> dict:
    """Generate a silkpage XML webpage from a photo classification result.

    Accepts the output of mcp-photo/classify_photo directly.
    Writes the XML file to the photos/ directory in the silkpage source tree.

    Args:
        classification: The dict returned by singine-photo/classify_photo, optionally
                        enriched with source metadata from mcp-icloud-photos or
                        mcp-google-photos. Keys:
                          image (str)      — absolute path to the photo
                          faces (list)     — from classify_photo
                          scene (dict)     — from classify_photo
                          decision (dict)  — from classify_photo
                          taken (str)      — ISO 8601 timestamp (optional)
                          source (str)     — "icloud-photos"|"google-photos"|"local"
                          source_id (str)  — UUID or Google media item ID (optional)
                          source_info (list) — [{system, id, copy_verified}] (optional,
                                              one entry per source system — use when
                                              photo exists in multiple clouds)
                          copy_path (str)  — verified local copy path (optional)
                          copy_sha256 (str) — SHA-256 of local copy (optional)

    Returns:
        {ok, xml_path, photo_id, xml_content}
    """
    try:
        xml_content = _render_xml(classification)
        image_path = classification.get("image", "")
        filename = Path(image_path).name if image_path else "unknown.jpg"
        photo_id = _safe_id(filename)
        out_path = _write_xml_file(xml_content, photo_id)
        return {
            "ok": True,
            "photo_id": photo_id,
            "xml_path": str(out_path),
            "xml_content": xml_content,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def register_in_layout(xml_path: str, page_id: str = "") -> dict:
    """Register a photo XML page in layout.xml as a <notoc> entry.

    Args:
        xml_path: Absolute path to the .xml file (as returned by photo_to_silkpage_xml).
        page_id:  Optional override for the page id. Derived from filename if omitted.

    Returns:
        {ok, registered, layout_xml}
    """
    p = Path(xml_path)
    if not p.exists():
        return {"ok": False, "error": f"xml_path not found: {xml_path}"}

    effective_id = page_id or _safe_id(p.stem)
    registered = _register_in_layout(effective_id, p.name)
    return {
        "ok": registered,
        "registered": registered,
        "page_id": effective_id,
        "layout_xml": str(_LAYOUT_XML),
    }


@mcp.tool()
def batch_to_silkpage(classifications: list[dict]) -> dict:
    """Convert multiple photo classification results to silkpage XML in one call.

    Generates one XML file per photo and registers each in layout.xml.

    Args:
        classifications: List of dicts from singine-photo/classify_photo.

    Returns summary with total, succeeded, failed counts and per-photo results.
    """
    results = []
    succeeded = 0
    failed = 0

    for cls in classifications:
        xml_result = photo_to_silkpage_xml(cls)
        if xml_result.get("ok"):
            reg_result = register_in_layout(xml_result["xml_path"])
            xml_result["registered"] = reg_result.get("registered", False)
            succeeded += 1
        else:
            failed += 1
        # Don't bloat the batch response with full XML content
        xml_result.pop("xml_content", None)
        results.append(xml_result)

    return {
        "ok": True,
        "total": len(classifications),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }


@mcp.tool()
def list_photo_pages() -> dict:
    """List all photo XML pages currently in the silkpage photos/ directory.

    Returns file names, photo IDs, and file sizes.
    """
    if not _PHOTOS_XML_DIR.exists():
        return {"ok": True, "pages": [], "photos_dir": str(_PHOTOS_XML_DIR)}

    pages = []
    for f in sorted(_PHOTOS_XML_DIR.glob("*.xml")):
        pages.append({
            "photo_id": f.stem,
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "path": str(f),
        })

    return {"ok": True, "count": len(pages), "pages": pages, "photos_dir": str(_PHOTOS_XML_DIR)}


_LIBRARY_XML_TEMPLATE = """\
<?xml version='1.0' encoding='UTF-8'?>
<webpage xmlns:db="http://docbook.org/ns/docbook"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         id="google-library">

  <config param="rcsdate" value="$$Date: ${generated_at} $$"/>

  <head>
    <title>${title}</title>
    <summary>Google Photos library overview: ${album_count} albums, ${photo_count} recent photos fetched</summary>
    <keywords>google-photos, library, overview</keywords>
  </head>

  <db:section role="albums">
    <db:title>Albums (${album_count})</db:title>
    <db:informaltable><db:tgroup cols="2">
      <db:thead>
        <db:row><db:entry>Title</db:entry><db:entry>Photos</db:entry></db:row>
      </db:thead>
      <db:tbody>
${album_rows}
      </db:tbody>
    </db:tgroup></db:informaltable>
  </db:section>

  <db:section role="recent-photos">
    <db:title>Recent Photos (${shown_count} shown)</db:title>
    <db:informaltable><db:tgroup cols="4">
      <db:thead>
        <db:row>
          <db:entry>Filename</db:entry>
          <db:entry>Date</db:entry>
          <db:entry>Camera</db:entry>
          <db:entry>Dimensions</db:entry>
        </db:row>
      </db:thead>
      <db:tbody>
${photo_rows}
      </db:tbody>
    </db:tgroup></db:informaltable>
  </db:section>

</webpage>
"""


def _album_rows_xml(albums: list[dict]) -> str:
    rows = []
    for a in albums:
        title = (a.get("title") or "(untitled)").replace("&", "&amp;").replace("<", "&lt;")
        count = str(a.get("photo_count", 0))
        rows.append(f"        <db:row><db:entry>{title}</db:entry><db:entry>{count}</db:entry></db:row>")
    return "\n".join(rows) if rows else "        <db:row><db:entry>No albums</db:entry><db:entry>0</db:entry></db:row>"


def _photo_rows_xml(photos: list[dict]) -> str:
    rows = []
    for p in photos:
        fn = (p.get("filename") or "").replace("&", "&amp;").replace("<", "&lt;")
        dt = (p.get("date_created") or "")[:10]
        make = (p.get("camera_make") or "").replace("&", "&amp;")
        model = (p.get("camera_model") or "").replace("&", "&amp;")
        cam = f"{make} {model}".strip() or "—"
        w = p.get("width") or ""
        h = p.get("height") or ""
        dims = f"{w}×{h}" if w and h else "—"
        rows.append(
            f"        <db:row>"
            f"<db:entry>{fn}</db:entry>"
            f"<db:entry>{dt}</db:entry>"
            f"<db:entry>{cam}</db:entry>"
            f"<db:entry>{dims}</db:entry>"
            f"</db:row>"
        )
    return "\n".join(rows) if rows else "        <db:row><db:entry colspan='4'>No photos</db:entry></db:row>"


@mcp.tool()
def google_library_to_silkpage(
    albums: list,
    photos: list,
    title: str = "Google Photos Library",
) -> dict:
    """Generate a silkpage XML overview page from Google Photos library data.

    Writes photos/google-library.xml with an albums table and recent-photos table.
    Automatically registers the page in layout.xml.

    Args:
        albums: List of album dicts from list_albums()["albums"].
        photos: List of photo dicts from search_photos()["photos"].
        title:  Page title (default: "Google Photos Library").

    Returns:
        {ok, xml_path, registered}
    """
    try:
        generated_at = datetime.now(timezone.utc).isoformat()
        values = {
            "title": title,
            "generated_at": generated_at,
            "album_count": str(len(albums)),
            "photo_count": str(len(photos)),
            "shown_count": str(len(photos)),
            "album_rows": _album_rows_xml(albums),
            "photo_rows": _photo_rows_xml(photos),
        }
        xml_content = Template(_LIBRARY_XML_TEMPLATE).safe_substitute(values)
        _PHOTOS_XML_DIR.mkdir(parents=True, exist_ok=True)
        out_path = _PHOTOS_XML_DIR / "google-library.xml"
        out_path.write_text(xml_content, encoding="utf-8")
        registered = _register_in_layout("google-library", "google-library.xml")
        return {
            "ok": True,
            "xml_path": str(out_path),
            "registered": registered,
            "album_count": len(albums),
            "photo_count": len(photos),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def silkpage_config() -> dict:
    """Return current silkpage path configuration for this MCP server."""
    return {
        "ok": True,
        "silkpage_root": str(_SILKPAGE_ROOT),
        "layout_xml": str(_LAYOUT_XML),
        "photos_xml_dir": str(_PHOTOS_XML_DIR),
        "layout_exists": _LAYOUT_XML.exists(),
        "photos_dir_exists": _PHOTOS_XML_DIR.exists(),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
