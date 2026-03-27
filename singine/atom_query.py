"""Atom XML query requests and responses for Singine bridge lookups."""

from __future__ import annotations

import json
import subprocess
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .cortex_bridge import BridgeDB, classify_realm
from .server_surface import query_bridge


ATOM_NS = "http://www.w3.org/2005/Atom"
SINGINE_NS = "http://singine.io/ontology#"
XML_NS = "http://www.w3.org/XML/1998/namespace"

ET.register_namespace("", ATOM_NS)
ET.register_namespace("singine", SINGINE_NS)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atom_tag(local: str) -> str:
    return f"{{{ATOM_NS}}}{local}"


def singine_tag(local: str) -> str:
    return f"{{{SINGINE_NS}}}{local}"


def _indent_xml(element: ET.Element, level: int = 0) -> None:
    indent = "\n" + level * "  "
    if len(element):
        if not element.text or not element.text.strip():
            element.text = indent + "  "
        for child in element:
            _indent_xml(child, level + 1)
        if not element[-1].tail or not element[-1].tail.strip():
            element[-1].tail = indent
    if level and (not element.tail or not element.tail.strip()):
        element.tail = indent


def write_xml(path: Path, root: ET.Element) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _indent_xml(root)
    tree = ET.ElementTree(root)
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return path


def _request_payload(limit: int, realms: Sequence[str], query_mode: str, api_base_url: Optional[str]) -> Dict[str, Any]:
    return {
        "query_name": "latest-changes-across-realms",
        "query_mode": query_mode,
        "limit": limit,
        "realms": list(realms),
        "api_base_url": api_base_url,
    }


def build_request_feed(*, limit: int, realms: Sequence[str], query_mode: str, api_base_url: Optional[str]) -> ET.Element:
    feed = ET.Element(atom_tag("feed"))
    ET.SubElement(feed, atom_tag("id")).text = f"urn:singine:query-request:{uuid.uuid4()}"
    ET.SubElement(feed, atom_tag("title")).text = "Singine latest changes across realms request"
    ET.SubElement(feed, atom_tag("updated")).text = utc_now()
    author = ET.SubElement(feed, atom_tag("author"))
    ET.SubElement(author, atom_tag("name")).text = "singine"
    for realm in realms:
        ET.SubElement(feed, atom_tag("category"), {"term": realm, "label": "realm"})
    entry = ET.SubElement(feed, atom_tag("entry"))
    ET.SubElement(entry, atom_tag("id")).text = f"urn:singine:query-request-entry:{uuid.uuid4()}"
    ET.SubElement(entry, atom_tag("title")).text = "query:latest-changes-across-realms"
    ET.SubElement(entry, atom_tag("updated")).text = utc_now()
    content = ET.SubElement(entry, atom_tag("content"), {"type": "application/json"})
    content.text = json.dumps(_request_payload(limit, realms, query_mode, api_base_url), sort_keys=True)
    return feed


def parse_request_feed(path: Path) -> Dict[str, Any]:
    tree = ET.parse(path)
    root = tree.getroot()
    content = root.find(f".//{atom_tag('content')}")
    if content is None or not (content.text or "").strip():
        raise ValueError(f"request feed has no JSON content: {path}")
    payload = json.loads(content.text)
    payload["request_path"] = str(path)
    return payload


def build_latest_changes_graphql(limit: int, realm: str) -> str:
    return (
        "{ latestChanges("
        f'limit:{limit}, realm:"{realm}"'
        ") { iri label entity_type path mtime source_name source_kind source_root_path snippet } }"
    )


def _run_emacsclient_summary(path: Path, emacsclient_bin: str) -> Optional[str]:
    elisp = (
        "(with-current-buffer (find-file-noselect "
        + json.dumps(str(path))
        + ") "
        + "(goto-char (point-min)) "
        + "(let ((line (buffer-substring-no-properties "
        + "(line-beginning-position) (line-end-position)))) "
        + "(princ line)))"
    )
    try:
        completed = subprocess.run(
            [emacsclient_bin, "-a", "", "-e", elisp],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip().strip('"') or None


def enrich_filesystem_rows(rows: List[Dict[str, Any]], emacsclient_bin: Optional[str]) -> List[Dict[str, Any]]:
    if not emacsclient_bin:
        return rows
    enriched: List[Dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        path_text = copy.get("path")
        if path_text:
            summary = _run_emacsclient_summary(Path(path_text), emacsclient_bin)
            if summary:
                copy["filesystem_reader"] = "emacsclient"
                copy["filesystem_summary"] = summary
        enriched.append(copy)
    return enriched


def query_latest_changes_local(
    *,
    db_path: Path,
    limit: int,
    realms: Sequence[str],
    emacsclient_bin: Optional[str],
) -> Dict[str, List[Dict[str, Any]]]:
    db = BridgeDB(db_path)
    try:
        db.setup()
        results: Dict[str, List[Dict[str, Any]]] = {}
        for realm in realms:
            rows = db.latest_changes(limit=limit, realm=realm)
            if realm == "filesystem":
                rows = enrich_filesystem_rows(rows, emacsclient_bin)
            results[realm] = rows
        return results
    finally:
        db.close()


def query_latest_changes_api(
    *,
    api_base_url: str,
    limit: int,
    realms: Sequence[str],
    timeout: int,
    emacsclient_bin: Optional[str],
) -> Dict[str, List[Dict[str, Any]]]:
    results: Dict[str, List[Dict[str, Any]]] = {}
    for realm in realms:
        payload = query_bridge(
            api_base_url,
            action="graphql",
            query=build_latest_changes_graphql(limit, realm),
            limit=limit,
            timeout=timeout,
        )
        if not payload.get("ok"):
            raise RuntimeError(payload.get("error", f"bridge API query failed for realm {realm}"))
        data = payload.get("data") or {}
        rows = ((data.get("result") or {}).get("data") or {}).get("latestChanges") or []
        if realm == "filesystem":
            rows = enrich_filesystem_rows(rows, emacsclient_bin)
        results[realm] = rows
    return results


def build_response_feed(
    *,
    request_payload: Dict[str, Any],
    results: Dict[str, List[Dict[str, Any]]],
    source_mode: str,
) -> ET.Element:
    feed = ET.Element(atom_tag("feed"))
    ET.SubElement(feed, atom_tag("id")).text = f"urn:singine:query-response:{uuid.uuid4()}"
    ET.SubElement(feed, atom_tag("title")).text = "Singine latest changes across realms response"
    ET.SubElement(feed, atom_tag("updated")).text = utc_now()
    author = ET.SubElement(feed, atom_tag("author"))
    ET.SubElement(author, atom_tag("name")).text = "singine"
    ET.SubElement(feed, singine_tag("queryMode")).text = request_payload.get("query_mode", source_mode)
    ET.SubElement(feed, singine_tag("sourceMode")).text = source_mode
    ET.SubElement(feed, singine_tag("causalityPolicy")).text = "xwalk-by-source-kind-and-realm"

    for realm, rows in results.items():
        ET.SubElement(feed, atom_tag("category"), {"term": realm, "label": "realm"})
        for row in rows:
            entry = ET.SubElement(feed, atom_tag("entry"))
            ET.SubElement(entry, atom_tag("id")).text = row.get("iri") or f"urn:singine:latest-change:{uuid.uuid4()}"
            ET.SubElement(entry, atom_tag("title")).text = row.get("label") or row.get("iri") or "(unlabeled)"
            ET.SubElement(entry, atom_tag("updated")).text = row.get("mtime") or utc_now()
            ET.SubElement(entry, atom_tag("category"), {"term": realm, "label": "realm"})
            ET.SubElement(entry, atom_tag("category"), {"term": row.get("source_kind") or "unknown", "label": "source-kind"})
            ET.SubElement(entry, singine_tag("realm")).text = realm
            ET.SubElement(entry, singine_tag("entityType")).text = row.get("entity_type") or ""
            ET.SubElement(entry, singine_tag("sourceName")).text = row.get("source_name") or ""
            ET.SubElement(entry, singine_tag("sourceRootPath")).text = row.get("source_root_path") or ""
            ET.SubElement(entry, singine_tag("xwalkCode")).text = f"{realm}:{row.get('source_kind') or 'unknown'}"
            ET.SubElement(entry, singine_tag("causalityKey")).text = "|".join(
                [
                    realm,
                    row.get("source_name") or "",
                    row.get("source_kind") or "",
                    row.get("mtime") or "",
                    row.get("iri") or "",
                ]
            )
            if row.get("path"):
                link = ET.SubElement(entry, atom_tag("link"))
                link.set("rel", "alternate")
                link.set("href", row["path"])
            summary = ET.SubElement(entry, atom_tag("summary"))
            summary.text = row.get("snippet") or row.get("filesystem_summary") or ""
            content_payload = dict(row)
            content_payload["classified_realm"] = classify_realm(row)
            content = ET.SubElement(entry, atom_tag("content"), {"type": "application/json"})
            content.text = json.dumps(content_payload, sort_keys=True)
    return feed


def summarize_feed(path: Path) -> Dict[str, Any]:
    tree = ET.parse(path)
    root = tree.getroot()
    entries = root.findall(atom_tag("entry"))
    realms: Dict[str, int] = {}
    for entry in entries:
        realm_value = entry.findtext(singine_tag("realm")) or "unknown"
        realms[realm_value] = realms.get(realm_value, 0) + 1
    return {
        "path": str(path),
        "title": root.findtext(atom_tag("title")),
        "updated": root.findtext(atom_tag("updated")),
        "entry_count": len(entries),
        "realms": realms,
    }
