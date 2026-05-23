#!/usr/bin/env python3
"""
generate_atom.py — Generate an Atom feed from committee-results.json.

Produces output/latest/ATOM (no file extension — Nginx serves with correct
Content-Type).  The feed is addressable at:

  https://singine.uk/latest/ATOM

URN scheme mirrors sinedge/persona-governance-updates.atom.xml:
  urn:singine:cleanup:disk:<item-id>
  urn:singine:cleanup:gov:<rule-id>
  urn:singine:cleanup:session:<iso-date>

Usage:
  python3 generate_atom.py [--in report/committee-results.json]
                           [--out output/latest/ATOM]
                           [--base-url https://singine.uk]

singine invocation:
  singine runtime exec-external python3 cleanup/generate_atom.py
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from xml.dom import minidom

SCRIPT_DIR = Path(__file__).resolve().parent
REPORT_DIR = SCRIPT_DIR / "report"
OUTPUT_DIR = SCRIPT_DIR / "output"

ATOM_NS  = "http://www.w3.org/2005/Atom"
DC_NS    = "http://purl.org/dc/elements/1.1/"
SINGINE_NS = "urn:singine:ns:"

ET.register_namespace("",      ATOM_NS)
ET.register_namespace("dc",    DC_NS)
ET.register_namespace("si",    SINGINE_NS)


# ── XML helpers ───────────────────────────────────────────────────────────────

def atom(tag: str) -> str:
    return f"{{{ATOM_NS}}}{tag}"

def dc(tag: str) -> str:
    return f"{{{DC_NS}}}{tag}"

def sub(parent: ET.Element, tag: str, text: str | None = None,
        **attrs: str) -> ET.Element:
    el = ET.SubElement(parent, tag, attrib=attrs)
    if text is not None:
        el.text = text
    return el

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def pretty(tree: ET.Element) -> str:
    raw = ET.tostring(tree, encoding="unicode", xml_declaration=False)
    dom = minidom.parseString(f'<?xml version="1.0" encoding="UTF-8"?>{raw}')
    lines = dom.toprettyxml(indent="  ", encoding=None).splitlines()
    # minidom adds a duplicate declaration; strip it
    if lines and lines[0].startswith("<?xml"):
        lines = lines[1:]
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + "\n".join(lines) + "\n"


# ── Entry builders ─────────────────────────────────────────────────────────────

def disk_entry(item: dict, base_url: str, updated: str) -> ET.Element:
    entry = ET.Element(atom("entry"))
    urn   = f"urn:singine:cleanup:disk:{item['id']}"
    sub(entry, atom("id"),       urn)
    sub(entry, atom("title"),    f"[{item['risk'].upper()}] {item['label']}")
    sub(entry, atom("updated"),  updated)
    sub(entry, atom("link"),     rel="alternate",
        href=f"{base_url}/cleanup.html#{item['id']}")
    sub(entry, atom("link"),     rel="related",
        href=f"{base_url}/latest/ATOM")
    sub(entry, atom("category"), term=item["category"])
    sub(entry, atom("category"), term=item["risk"])
    # dc:identifier = path
    sub(entry, dc("identifier"), item.get("path", ""))
    content_text = (
        f"Size: {item.get('size_human','?')}  |  "
        f"Risk: {item['risk']}  |  "
        f"Path: {item.get('path','?')}\n\n"
        f"singine command:\n{item.get('singine_cmd','')}\n\n"
        f"Shell:\n{item.get('shell_cmd','')}\n\n"
        f"{item.get('notes','')}"
    ).strip()
    sub(entry, atom("content"), content_text, type="text")
    return entry


def gov_entry(rule: dict, base_url: str, updated: str) -> ET.Element:
    entry = ET.Element(atom("entry"))
    urn   = f"urn:singine:cleanup:gov:{rule['id'].lower()}"
    sub(entry, atom("id"),      urn)
    sub(entry, atom("title"),   f"{rule['id']} — {rule['title']}")
    sub(entry, atom("updated"), updated)
    sub(entry, atom("link"),    rel="alternate",
        href=f"{base_url}/cleanup.html#governance")
    sub(entry, atom("category"), term="governance")
    sub(entry, atom("category"), term=rule["id"].lower())
    content_text = (
        f"Applies: {rule.get('applies','')}\n\n"
        f"Rule: {rule.get('rule','')}"
    )
    sub(entry, atom("content"), content_text, type="text")
    return entry


def session_entry(payload: dict, base_url: str, updated: str,
                  total: str, n_items: int, db_state: str) -> ET.Element:
    entry = ET.Element(atom("entry"))
    ts    = payload.get("generated_at", updated)[:10]
    urn   = f"urn:singine:cleanup:session:{ts}"
    sub(entry, atom("id"),      urn)
    sub(entry, atom("title"),
        f"Cleanup scan {ts} — {total} reclaimable, governance: {db_state}")
    sub(entry, atom("updated"), updated)
    sub(entry, atom("link"),    rel="alternate",
        href=f"{base_url}/cleanup.html")
    sub(entry, atom("link"),    rel="enclosure",
        href=f"{base_url}/api/report",
        type="application/json",
        title="committee-results.json")
    sub(entry, atom("category"), term="session")
    content_text = (
        f"Total reclaimable: {total}\n"
        f"Items: {n_items}\n"
        f"Governance DB: {db_state}\n"
        f"Generator: cleanup/collect.py + cleanup/generate_atom.py\n\n"
        f"To regenerate:\n"
        f"  singine runtime exec-external python3 cleanup/collect.py\n"
        f"  singine runtime exec-external python3 cleanup/generate_atom.py"
    )
    sub(entry, atom("content"), content_text, type="text")
    return entry


# ── Feed builder ──────────────────────────────────────────────────────────────

def build_feed(payload: dict, base_url: str) -> ET.Element:
    disk = payload["result_sets"]["disk"]
    gov  = payload["result_sets"]["governance"]
    updated = now_iso()

    feed = ET.Element(atom("feed"))
    sub(feed, atom("id"),     f"{base_url}/latest/ATOM")
    sub(feed, atom("title"),  "singine latest — disk cleanup + governance")
    sub(feed, atom("updated"), updated)
    sub(feed, atom("author")).append(
        _text_el(atom("name"), "singine cleanup pipeline"))
    sub(feed, atom("link"), rel="self",
        href=f"{base_url}/latest/ATOM",
        type="application/atom+xml")
    sub(feed, atom("link"), rel="alternate",
        href=f"{base_url}/cleanup.html",
        type="text/html")
    sub(feed, atom("link"), rel="related",
        href=f"{base_url}/api/report",
        type="application/json",
        title="committee-results.json")
    sub(feed, dc("language"),  "en")
    sub(feed, dc("publisher"), "singine.uk")
    sub(feed, dc("rights"),    "lutino.io")

    # Session summary entry (first = newest)
    total    = disk.get("total_reclaimable_human", "?")
    n_items  = len([i for i in disk.get("items", []) if i.get("size_bytes", -1) > 0])
    db_state = gov.get("db_state", "unknown")
    feed.append(session_entry(payload, base_url, updated, total, n_items, db_state))

    # Disk entries (safe items first, then review)
    items = sorted(
        [i for i in disk.get("items", []) if i.get("size_bytes", -1) > 0],
        key=lambda x: (0 if x["risk"] == "safe" else 1, -x.get("size_bytes", 0))
    )
    for item in items:
        feed.append(disk_entry(item, base_url, updated))

    # Governance rule entries
    for rule in gov.get("rules", []):
        feed.append(gov_entry(rule, base_url, updated))

    return feed


def _text_el(tag: str, text: str) -> ET.Element:
    el = ET.Element(tag)
    el.text = text
    return el


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in",       dest="infile",
                        default=str(REPORT_DIR / "committee-results.json"))
    parser.add_argument("--out",      dest="outfile",
                        default=str(OUTPUT_DIR / "latest" / "ATOM"))
    parser.add_argument("--base-url", default="https://singine.uk")
    args = parser.parse_args()

    inpath  = Path(args.infile)
    outpath = Path(args.outfile)

    if not inpath.exists():
        print(f"ERROR: {inpath} not found. Run collect.py first.", file=sys.stderr)
        sys.exit(1)

    payload  = json.loads(inpath.read_text(encoding="utf-8"))
    feed     = build_feed(payload, args.base_url)
    feed_xml = pretty(feed)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    outpath.write_text(feed_xml, encoding="utf-8")

    n_entries = feed_xml.count("<entry>")
    print(f"written: {outpath}", file=sys.stderr)
    print(json.dumps({
        "ok":       True,
        "feed":     str(outpath),
        "url":      f"{args.base_url}/latest/ATOM",
        "entries":  n_entries,
        "bytes":    len(feed_xml),
    }))


if __name__ == "__main__":
    main()
