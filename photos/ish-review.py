#!/usr/bin/env python3
"""
singine photo review — iSH / Alpine Linux compatible deletion review tool.

Reads singine silkpage XML photo records (synced from Mac via rsync/SFTP)
and displays a classification summary, deletion queue, and safe-delete instructions.

Requirements (Alpine Linux / iSH):
  apk add python3 openssh-client rsync
  # lxml is optional; falls back to stdlib xml.etree.ElementTree

Usage:
  # 1. Sync photo XML records from Mac to iPad
  python3 ish-review.py sync --mac-host 192.168.1.x --mac-user sina

  # 2. Show full summary
  python3 ish-review.py status

  # 3. Show deletion queue (verified copies only)
  python3 ish-review.py queue

  # 4. Show all ex-spouse flagged photos
  python3 ish-review.py flagged

  # 5. SSH to Mac and run deletion (iCloud removes from iPad automatically)
  python3 ish-review.py delete-icloud --mac-host 192.168.1.x --uuid UUID1 UUID2

  # 6. Show Google Photos deletion manifest (manual web deletion needed)
  python3 ish-review.py google-manifest
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PHOTOS_XML_DIR = Path(os.environ.get(
    "SINGINE_PHOTOS_XML_DIR",
    Path.home() / "singine-photos",
))
DELETION_MANIFEST_CSV = Path(os.environ.get(
    "SINGINE_GOOGLE_DELETION_CSV",
    Path.home() / ".singine" / "google-photos-deletion-manifest.csv",
))
ICLOUD_DELETION_MANIFEST = Path(os.environ.get(
    "SINGINE_DELETION_MANIFEST",
    Path.home() / ".singine" / "deletion-manifest.json",
))

# Namespace map for DocBook + SKOS XML
NS = {
    "db": "http://docbook.org/ns/docbook",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
}

# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------

def _text(elem: ET.Element | None, default: str = "—") -> str:
    if elem is None:
        return default
    return (elem.text or "").strip() or default


def _find_entry(table: ET.Element | None, label: str) -> str:
    """Find a table row by first entry label, return second entry value."""
    if table is None:
        return "—"
    for row in table.findall(".//db:row", NS):
        entries = row.findall("db:entry", NS)
        if len(entries) >= 2 and _text(entries[0]) == label:
            return _text(entries[1])
    return "—"


def _parse_photo_xml(xml_path: Path) -> dict:
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Provenance section
        prov = root.find(".//db:section[@role='provenance']", NS)
        prov_table = prov.find(".//db:informaltable", NS) if prov else None

        # Source IDs section
        src_section = root.find(".//db:section[@role='source-ids']", NS)
        src_table = src_section.find(".//db:informaltable", NS) if src_section else None
        copy_path_el = src_section.find(".//db:para[@role='copy-location']/db:filename", NS) if src_section else None
        copy_sha_el = src_section.find(".//db:para[@role='copy-sha256']", NS) if src_section else None

        # Source rows
        source_ids = []
        if src_table:
            for row in src_table.findall(".//db:row", NS):
                entries = row.findall("db:entry", NS)
                if len(entries) >= 3:
                    source_ids.append({
                        "system": _text(entries[0]),
                        "id": _text(entries[1]),
                        "verified": _text(entries[2]),
                    })

        # Decision section
        dec = root.find(".//db:section[@role='decision']", NS)
        dec_table = dec.find(".//db:informaltable", NS) if dec else None

        # SKOS sidebar
        action_key = "—"
        for concept in root.findall(".//skos:Concept", NS):
            about = concept.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about", "")
            if "action:" in about:
                action_key = about.split("action:")[-1]

        return {
            "photo_id": root.get("id", xml_path.stem),
            "filename": _find_entry(prov_table, "File"),
            "taken": _find_entry(prov_table, "Taken"),
            "source": _find_entry(prov_table, "Source system"),
            "sha256_original": _find_entry(prov_table, "SHA-256 (original)"),
            "source_ids": source_ids,
            "copy_path": _text(copy_path_el),
            "copy_sha256": _text(copy_sha_el),
            "category": _find_entry(dec_table, "Category"),
            "action": _find_entry(dec_table, "Action"),
            "action_key": action_key,
            "reason": _find_entry(dec_table, "Reason"),
            "xml_path": str(xml_path),
        }
    except ET.ParseError as e:
        return {"photo_id": xml_path.stem, "error": str(e), "xml_path": str(xml_path)}


def _load_all_photos() -> list[dict]:
    if not PHOTOS_XML_DIR.exists():
        print(f"Photos XML directory not found: {PHOTOS_XML_DIR}")
        print("Run: python3 ish-review.py sync --mac-host <ip>")
        return []
    photos = []
    for f in sorted(PHOTOS_XML_DIR.glob("*.xml")):
        photos.append(_parse_photo_xml(f))
    return photos

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_sync(args):
    """Rsync photo XML records from the Mac to this device."""
    mac_host = args.mac_host
    mac_user = args.mac_user or os.environ.get("USER", "sina")
    mac_photos_dir = args.mac_dir or (
        f"{mac_user}@{mac_host}:ws/silkpage/main/silkpage/www/"
        "silkpage.markupware.com/src/xml/en/photos/"
    )

    PHOTOS_XML_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Syncing photo XML from {mac_host}…")
    result = subprocess.run(
        ["rsync", "-avz", "--progress", mac_photos_dir, str(PHOTOS_XML_DIR) + "/"],
        capture_output=False,
    )
    if result.returncode == 0:
        count = len(list(PHOTOS_XML_DIR.glob("*.xml")))
        print(f"\nSync complete — {count} photo records available.")
    else:
        print("Sync failed. Check SSH access to the Mac.")
        sys.exit(1)


def cmd_status(args):
    """Show a summary of all classified photos."""
    photos = _load_all_photos()
    if not photos:
        return

    by_action: dict[str, list] = {}
    for p in photos:
        if "error" in p:
            by_action.setdefault("parse-error", []).append(p)
            continue
        by_action.setdefault(p.get("action_key", "Unknown"), []).append(p)

    print(f"\n{'─' * 50}")
    print(f"  SINGINE PHOTO ARCHIVE — {len(photos)} records")
    print(f"{'─' * 50}\n")

    order = ["KeepPrimary", "ArchiveSeparate", "ArchiveSecondary", "FlagForReview", "Unknown", "parse-error"]
    labels = {
        "KeepPrimary":      "✓  Keep — Primary Archive",
        "ArchiveSeparate":  "⚠  Archive — Separate (ex-spouse)",
        "ArchiveSecondary": "↓  Archive — Secondary (cold)",
        "FlagForReview":    "?  Flag for Review",
        "Unknown":          "   Unknown",
        "parse-error":      "✗  Parse Error",
    }

    for key in order:
        group = by_action.get(key, [])
        if not group:
            continue
        label = labels.get(key, key)
        print(f"  {label}: {len(group)}")

    print()

    # Deletion readiness
    verified = [p for p in photos if any(s.get("verified") == "yes" for s in p.get("source_ids", []))]
    print(f"  Copies verified for safe deletion: {len(verified)}")
    print(f"  Awaiting verification:             {len(photos) - len(verified)}\n")


def cmd_queue(args):
    """Show photos ready for deletion from cloud (copy verified)."""
    photos = _load_all_photos()
    queue = [p for p in photos if any(s.get("verified") == "yes" for s in p.get("source_ids", []))]

    if not queue:
        print("\nNo photos verified for deletion yet.")
        print("Run the full pipeline on the Mac first:\n  singine photo classify-batch <dir>")
        return

    print(f"\n{'─' * 50}")
    print(f"  DELETION QUEUE — {len(queue)} photos ready")
    print(f"{'─' * 50}\n")

    by_system: dict[str, list] = {}
    for p in queue:
        for s in p.get("source_ids", []):
            if s.get("verified") == "yes":
                by_system.setdefault(s["system"], []).append({**p, "_source": s})

    for system, items in sorted(by_system.items()):
        print(f"  {system.upper()} ({len(items)} photos):")
        for item in items[:10]:
            sid = item["_source"]["id"]
            print(f"    {item['filename']}  [{sid[:12]}…]  {item['action']}")
        if len(items) > 10:
            print(f"    … and {len(items) - 10} more")
        print()

    print("  To delete from iCloud (also removes from iPhone/iPad):")
    print("    On Mac: singine photo delete-icloud --uuid <uuid1> <uuid2> …")
    print("    Or SSH: python3 ish-review.py delete-icloud --mac-host <ip> --uuid …\n")


def cmd_flagged(args):
    """Show photos flagged for separate archive (ex-spouse present)."""
    photos = _load_all_photos()
    flagged = [p for p in photos if p.get("action_key") == "ArchiveSeparate"]

    if not flagged:
        print("\nNo photos flagged for separate archive.")
        return

    print(f"\n{'─' * 50}")
    print(f"  SEPARATE ARCHIVE — {len(flagged)} photos")
    print(f"{'─' * 50}\n")
    print("  These will be moved to a private folder, separate from the")
    print("  main archive. They remain accessible but not in day-to-day view.\n")

    for p in flagged:
        icloud_ids = [s["id"] for s in p.get("source_ids", []) if s.get("system") == "icloud-photos"]
        gp_ids = [s["id"] for s in p.get("source_ids", []) if s.get("system") == "google-photos"]
        print(f"  {p['filename']}")
        print(f"    Taken:   {p.get('taken', '—')}")
        print(f"    Reason:  {p.get('reason', '—')}")
        if icloud_ids:
            print(f"    iCloud:  {icloud_ids[0][:24]}…")
        if gp_ids:
            print(f"    Google:  {gp_ids[0][:24]}…")
        print()


def cmd_delete_icloud(args):
    """SSH to Mac and delete photos from iCloud (removes from all devices)."""
    if not args.uuid:
        print("No UUIDs provided. Use --uuid UUID1 UUID2 …")
        sys.exit(1)

    mac_host = args.mac_host
    mac_user = args.mac_user or os.environ.get("USER", "sina")
    uuid_args = " ".join(f"--uuid {u}" for u in args.uuid)

    print(f"\n⚠  About to delete {len(args.uuid)} photos from iCloud via {mac_host}")
    print("   This removes them from iPhone and iPad too.\n")
    confirm = input("Type 'yes' to proceed: ").strip().lower()
    if confirm != "yes":
        print("Aborted.")
        return

    remote_cmd = (
        f"python3 ~/ws/singine/main/singine/io.lutino.mcp/mcp-icloud-photos/src/server.py "
        f"--delete {uuid_args}"
    )
    # Actually invoke via singine CLI on the Mac
    singine_cmd = f"singine photo delete-icloud {uuid_args}"

    print(f"\nSSH → {mac_user}@{mac_host}: {singine_cmd}")
    result = subprocess.run(
        ["ssh", f"{mac_user}@{mac_host}", singine_cmd],
        capture_output=False,
    )
    if result.returncode == 0:
        print("\nDeletion complete — iCloud will sync removal to all devices.")
    else:
        print("\nCommand failed. Check SSH connection and that singine is installed on the Mac.")


def cmd_google_manifest(args):
    """Show the Google Photos deletion manifest for manual web deletion."""
    if not DELETION_MANIFEST_CSV.exists():
        print(f"\nNo Google Photos deletion manifest found at {DELETION_MANIFEST_CSV}")
        print("Generate it on the Mac:")
        print("  singine-google-photos/generate_deletion_manifest --ids ID1 ID2 …")
        return

    print(f"\n{'─' * 50}")
    print("  GOOGLE PHOTOS DELETION MANIFEST")
    print(f"{'─' * 50}\n")
    print("  Open each URL in a browser to delete manually at photos.google.com\n")

    with open(DELETION_MANIFEST_CSV, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader, 1):
            status = row.get("status", "")
            if status in ("deleted",):
                continue
            print(f"  {i}. {row.get('filename', '—')}")
            print(f"     Date:  {row.get('date_created', '—')}")
            print(f"     URL:   {row.get('product_url', '—')}")
            print()

    print(f"  Full manifest: {DELETION_MANIFEST_CSV}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="ish-review",
        description="singine photo review — iSH/Alpine compatible",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # sync
    p_sync = sub.add_parser("sync", help="Rsync photo XML from Mac")
    p_sync.add_argument("--mac-host", required=True, help="Mac IP or hostname")
    p_sync.add_argument("--mac-user", default="", help="Mac username")
    p_sync.add_argument("--mac-dir", default="", help="Override remote photos XML path")

    # status
    sub.add_parser("status", help="Summary of all classified photos")

    # queue
    sub.add_parser("queue", help="Photos ready for deletion (copy verified)")

    # flagged
    sub.add_parser("flagged", help="Photos flagged for separate archive")

    # delete-icloud
    p_del = sub.add_parser("delete-icloud", help="SSH to Mac and delete from iCloud")
    p_del.add_argument("--mac-host", required=True, help="Mac IP or hostname")
    p_del.add_argument("--mac-user", default="", help="Mac username")
    p_del.add_argument("--uuid", nargs="+", required=True, help="iCloud UUIDs to delete")

    # google-manifest
    sub.add_parser("google-manifest", help="Show Google Photos deletion manifest")

    args = parser.parse_args()
    commands = {
        "sync": cmd_sync,
        "status": cmd_status,
        "queue": cmd_queue,
        "flagged": cmd_flagged,
        "delete-icloud": cmd_delete_icloud,
        "google-manifest": cmd_google_manifest,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
