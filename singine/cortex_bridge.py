"""SQLite bridge for Singine, Silkpage, Claude, and Codex data.

This module builds a physical SQLite schema that approximates a small RDF graph:
entities, statements, and text fragments. It also supports a narrow SPARQL-to-SQL
translation layer for common graph lookup patterns and a JSON-oriented CLI that
the local Singine server can call.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_DB_PATH = Path("/tmp/sqlite.db")
MAX_TEXT_BYTES = 512 * 1024
MAX_JSONL_FRAGMENTS = 500

PREFIXES = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "prov": "http://www.w3.org/ns/prov#",
    "schema": "http://schema.org/",
    "singine": "http://singine.io/ontology#",
    "knowyourai": "https://github.com/sindoc/knowyourai-framework/blob/main/ontology.owl#",
}

RDF_TYPE = PREFIXES["rdf"] + "type"
RDFS_LABEL = PREFIXES["rdfs"] + "label"
DCTERMS_SOURCE = PREFIXES["dcterms"] + "source"
SCHEMA_PATH = PREFIXES["schema"] + "path"
SCHEMA_DATE_MODIFIED = PREFIXES["schema"] + "dateModified"
SINGINE_CONTAINS = PREFIXES["singine"] + "contains"
SINGINE_LINKS_TO = PREFIXES["singine"] + "linksTo"
SINGINE_PART_OF = PREFIXES["singine"] + "partOf"
SINGINE_RUNTIME = PREFIXES["singine"] + "runtime"
SINGINE_STATUS = PREFIXES["singine"] + "status"
RDF_ABOUT = PREFIXES["rdf"] + "about"
RDF_RESOURCE = PREFIXES["rdf"] + "resource"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}:{hashlib.sha1(value.encode('utf-8')).hexdigest()[:16]}"


def normalize_label(value: str) -> str:
    text = re.sub(r"\s+", " ", value.strip())
    return text or value


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def expand_term(term: str) -> str:
    term = term.strip()
    if term.startswith("<") and term.endswith(">"):
        return term[1:-1]
    if ":" in term:
        prefix, suffix = term.split(":", 1)
        if prefix in PREFIXES:
            return PREFIXES[prefix] + suffix
    return term


def compact_iri(iri: str) -> str:
    for prefix, base in PREFIXES.items():
        if iri.startswith(base):
            return f"{prefix}:{iri[len(base):]}"
    return iri


def qname_to_iri(name: str) -> str:
    if name.startswith("{") and "}" in name:
        namespace, local = name[1:].split("}", 1)
        return namespace + local
    return expand_term(name)


def guess_kind(path: Path) -> str:
    if path.suffix == ".md":
        return "markdown"
    if path.suffix == ".jsonl":
        return "jsonl"
    if path.suffix == ".json":
        return "json"
    if path.suffix in {".xml", ".xsl", ".xslt"}:
        return "xml"
    if path.suffix in {".sql", ".sqlite", ".db"}:
        return "binary-db"
    return "file"


def safe_read_text(path: Path, max_bytes: int = MAX_TEXT_BYTES) -> Optional[str]:
    try:
        data = path.read_bytes()[:max_bytes]
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("latin-1")
        except Exception:
            return None
    except Exception:
        return None


def xml_local_name(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def child_text(element: ET.Element) -> str:
    parts = [element.text or ""]
    for child in list(element):
        parts.append(child.tail or "")
    return normalize_label("".join(parts))


def iter_logseq_graphs(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    graphs: List[Path] = []
    for child in root.rglob("*"):
        if "version-files" in child.parts:
            continue
        if child.is_dir() and (child / "pages").is_dir() and (child / "journals").is_dir():
            graphs.append(child)
    return sorted(set(graphs))


def iter_files(root: Path, include_hidden: bool = False) -> Iterable[Path]:
    if not root.exists():
        return []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if not include_hidden and any(part.startswith(".") for part in path.parts):
            continue
        yield path


def extract_markdown_links(text: str) -> List[str]:
    return [normalize_label(m.group(1)) for m in re.finditer(r"\[\[([^\]]+)\]\]", text)]


def split_jsonl_fragments(text: str) -> List[str]:
    fragments: List[str] = []
    for index, line in enumerate(text.splitlines()):
        if not line.strip():
            continue
        fragments.append(line[:4000])
        if index + 1 >= MAX_JSONL_FRAGMENTS:
            break
    return fragments


@dataclass
class SourceSpec:
    name: str
    kind: str
    root_path: Path
    metadata: Dict[str, Any]


class BridgeDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def setup(self) -> None:
        self.conn.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS sources (
              source_id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              kind TEXT NOT NULL,
              root_path TEXT NOT NULL,
              metadata_json TEXT NOT NULL,
              scanned_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS entities (
              entity_id TEXT PRIMARY KEY,
              source_id TEXT NOT NULL,
              entity_type TEXT NOT NULL,
              iri TEXT NOT NULL UNIQUE,
              label TEXT,
              path TEXT,
              mtime TEXT,
              metadata_json TEXT NOT NULL,
              FOREIGN KEY (source_id) REFERENCES sources(source_id)
            );

            CREATE TABLE IF NOT EXISTS statements (
              stmt_id TEXT PRIMARY KEY,
              source_id TEXT NOT NULL,
              subject_id TEXT NOT NULL,
              predicate TEXT NOT NULL,
              object_value TEXT,
              object_entity_id TEXT,
              object_datatype TEXT,
              object_kind TEXT NOT NULL,
              FOREIGN KEY (source_id) REFERENCES sources(source_id),
              FOREIGN KEY (subject_id) REFERENCES entities(entity_id),
              FOREIGN KEY (object_entity_id) REFERENCES entities(entity_id)
            );

            CREATE TABLE IF NOT EXISTS fragments (
              fragment_id TEXT PRIMARY KEY,
              entity_id TEXT NOT NULL,
              source_id TEXT NOT NULL,
              seq INTEGER NOT NULL,
              text TEXT NOT NULL,
              metadata_json TEXT NOT NULL,
              FOREIGN KEY (entity_id) REFERENCES entities(entity_id),
              FOREIGN KEY (source_id) REFERENCES sources(source_id)
            );

            CREATE TABLE IF NOT EXISTS query_templates (
              template_name TEXT PRIMARY KEY,
              sparql_shape TEXT NOT NULL,
              sql_shape TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
            CREATE INDEX IF NOT EXISTS idx_entities_source ON entities(source_id);
            CREATE INDEX IF NOT EXISTS idx_statements_subject_pred ON statements(subject_id, predicate);
            CREATE INDEX IF NOT EXISTS idx_statements_object_entity ON statements(object_entity_id);
            CREATE INDEX IF NOT EXISTS idx_fragments_entity ON fragments(entity_id);
            """
        )
        self.conn.executemany(
            "INSERT OR REPLACE INTO query_templates(template_name, sparql_shape, sql_shape) VALUES (?, ?, ?)",
            [
                (
                    "type_lookup",
                    "SELECT ?s WHERE { ?s a <Type> . } LIMIT n",
                    "SELECT e.iri AS s FROM entities e JOIN statements st ON st.subject_id=e.entity_id "
                    "WHERE st.predicate=rdf:type AND st.object_value=<Type> LIMIT n",
                ),
                (
                    "type_with_label",
                    "SELECT ?s ?label WHERE { ?s a <Type> ; rdfs:label ?label . } LIMIT n",
                    "SELECT e.iri AS s, e.label FROM entities e WHERE e.entity_type=<Type> LIMIT n",
                ),
                (
                    "property_literal",
                    "SELECT ?s WHERE { ?s <Predicate> \"literal\" . } LIMIT n",
                    "SELECT DISTINCT e.iri AS s FROM statements st JOIN entities e ON e.entity_id=st.subject_id "
                    "WHERE st.predicate=<Predicate> AND st.object_value=\"literal\" LIMIT n",
                ),
                (
                    "outbound_relations",
                    "SELECT ?o WHERE { <Subject> <Predicate> ?o . } LIMIT n",
                    "SELECT COALESCE(obj.iri, st.object_value) AS o FROM statements st "
                    "LEFT JOIN entities obj ON obj.entity_id=st.object_entity_id "
                    "JOIN entities subj ON subj.entity_id=st.subject_id "
                    "WHERE subj.iri=<Subject> AND st.predicate=<Predicate> LIMIT n",
                ),
            ],
        )
        self.conn.commit()

    def reset(self) -> None:
        self.conn.executescript(
            """
            DELETE FROM fragments;
            DELETE FROM statements;
            DELETE FROM entities;
            DELETE FROM sources;
            """
        )
        self.conn.commit()

    def upsert_source(self, spec: SourceSpec) -> str:
        source_id = stable_id("src", f"{spec.kind}:{spec.root_path}")
        self.conn.execute(
            """
            INSERT OR REPLACE INTO sources(source_id, name, kind, root_path, metadata_json, scanned_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                spec.name,
                spec.kind,
                str(spec.root_path),
                json.dumps(spec.metadata, sort_keys=True),
                utc_now(),
            ),
        )
        return source_id

    def ensure_entity(
        self,
        *,
        source_id: str,
        entity_type: str,
        iri: str,
        label: Optional[str],
        path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        mtime: Optional[str] = None,
    ) -> str:
        entity_id = stable_id("ent", iri)
        self.conn.execute(
            """
            INSERT INTO entities(entity_id, source_id, entity_type, iri, label, path, mtime, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(iri) DO UPDATE SET
              source_id=excluded.source_id,
              entity_type=excluded.entity_type,
              label=COALESCE(excluded.label, entities.label),
              path=COALESCE(excluded.path, entities.path),
              mtime=COALESCE(excluded.mtime, entities.mtime),
              metadata_json=excluded.metadata_json
            """,
            (
                entity_id,
                source_id,
                entity_type,
                iri,
                label,
                path,
                mtime,
                json.dumps(metadata or {}, sort_keys=True),
            ),
        )
        return entity_id

    def add_statement(
        self,
        *,
        source_id: str,
        subject_id: str,
        predicate: str,
        object_value: Optional[str] = None,
        object_entity_id: Optional[str] = None,
        object_datatype: Optional[str] = None,
        object_kind: str = "literal",
    ) -> None:
        key = "|".join(
            [
                source_id,
                subject_id,
                predicate,
                object_value or "",
                object_entity_id or "",
                object_datatype or "",
                object_kind,
            ]
        )
        stmt_id = stable_id("stmt", key)
        self.conn.execute(
            """
            INSERT OR REPLACE INTO statements(
              stmt_id, source_id, subject_id, predicate, object_value, object_entity_id, object_datatype, object_kind
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (stmt_id, source_id, subject_id, predicate, object_value, object_entity_id, object_datatype, object_kind),
        )

    def add_fragment(
        self,
        *,
        source_id: str,
        entity_id: str,
        seq: int,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        fragment_id = stable_id("frag", f"{entity_id}:{seq}:{text[:256]}")
        self.conn.execute(
            """
            INSERT OR REPLACE INTO fragments(fragment_id, entity_id, source_id, seq, text, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (fragment_id, entity_id, source_id, seq, text, json.dumps(metadata or {}, sort_keys=True)),
        )

    def commit(self) -> None:
        self.conn.commit()

    def list_sources(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT s.*,
                   COUNT(DISTINCT e.entity_id) AS entity_count,
                   COUNT(DISTINCT f.fragment_id) AS fragment_count
            FROM sources s
            LEFT JOIN entities e ON e.source_id=s.source_id
            LEFT JOIN fragments f ON f.source_id=s.source_id
            GROUP BY s.source_id
            ORDER BY s.name
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def search(self, text: str, limit: int = 20) -> List[Dict[str, Any]]:
        q = f"%{text.lower()}%"
        rows = self.conn.execute(
            """
            SELECT e.iri,
                   e.label,
                   e.entity_type,
                   e.path,
                   src.name AS source_name,
                   substr(f.text, 1, 280) AS snippet
            FROM fragments f
            JOIN entities e ON e.entity_id=f.entity_id
            JOIN sources src ON src.source_id=e.source_id
            WHERE lower(f.text) LIKE ?
            ORDER BY e.label, f.seq
            LIMIT ?
            """,
            (q, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def entity(self, iri: str) -> Dict[str, Any]:
        entity = self.conn.execute(
            "SELECT * FROM entities WHERE iri = ?",
            (iri,),
        ).fetchone()
        if not entity:
            raise KeyError(iri)
        statements = self.conn.execute(
            """
            SELECT st.predicate,
                   st.object_value,
                   st.object_kind,
                   obj.iri AS object_iri,
                   obj.label AS object_label
            FROM statements st
            LEFT JOIN entities obj ON obj.entity_id=st.object_entity_id
            WHERE st.subject_id = ?
            ORDER BY st.predicate, st.object_value
            """,
            (entity["entity_id"],),
        ).fetchall()
        fragments = self.conn.execute(
            """
            SELECT seq, substr(text, 1, 400) AS text
            FROM fragments
            WHERE entity_id = ?
            ORDER BY seq
            LIMIT 20
            """,
            (entity["entity_id"],),
        ).fetchall()
        return {
            "entity": dict(entity),
            "statements": [dict(row) for row in statements],
            "fragments": [dict(row) for row in fragments],
        }

    def sparql(self, query: str) -> Dict[str, Any]:
        sql, params, columns = translate_sparql(query)
        rows = self.conn.execute(sql, params).fetchall()
        return {
            "sparql": query,
            "sql": sql,
            "params": list(params),
            "rows": [{columns[i]: row[i] for i in range(len(columns))} for row in rows],
        }

    def graphql(self, query: str) -> Dict[str, Any]:
        return execute_graphql(self, query)


def ingest_file_entity(db: BridgeDB, source_id: str, source_name: str, path: Path, root_path: Path) -> str:
    stat = path.stat()
    rel_path = str(path.relative_to(root_path))
    iri = f"urn:{slugify(source_name)}:file:{rel_path}"
    entity_id = db.ensure_entity(
        source_id=source_id,
        entity_type=guess_kind(path),
        iri=iri,
        label=path.stem,
        path=str(path),
        mtime=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        metadata={"size_bytes": stat.st_size, "relative_path": rel_path},
    )
    db.add_statement(source_id=source_id, subject_id=entity_id, predicate=RDF_TYPE, object_value=guess_kind(path))
    db.add_statement(source_id=source_id, subject_id=entity_id, predicate=RDFS_LABEL, object_value=path.stem)
    db.add_statement(source_id=source_id, subject_id=entity_id, predicate=DCTERMS_SOURCE, object_value=source_name)
    db.add_statement(source_id=source_id, subject_id=entity_id, predicate=SCHEMA_PATH, object_value=str(path))
    db.add_statement(
        source_id=source_id,
        subject_id=entity_id,
        predicate=SCHEMA_DATE_MODIFIED,
        object_value=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    )
    return entity_id


def ingest_text_file(
    db: BridgeDB,
    *,
    source_id: str,
    source_name: str,
    path: Path,
    root_path: Path,
    jsonl_mode: bool = False,
) -> None:
    entity_id = ingest_file_entity(db, source_id, source_name, path, root_path)
    text = safe_read_text(path)
    if not text:
        return
    if jsonl_mode:
        for seq, fragment in enumerate(split_jsonl_fragments(text), start=1):
            db.add_fragment(source_id=source_id, entity_id=entity_id, seq=seq, text=fragment)
    else:
        db.add_fragment(source_id=source_id, entity_id=entity_id, seq=1, text=text[:MAX_TEXT_BYTES])


def ingest_logseq_graph(db: BridgeDB, graph_path: Path) -> None:
    source_name = f"singine:{graph_path.name}"
    source_id = db.upsert_source(
        SourceSpec(
            name=source_name,
            kind="logseq-graph",
            root_path=graph_path,
            metadata={"family": "singine", "graph_name": graph_path.name},
        )
    )
    pages_by_label: Dict[str, str] = {}

    for md_path in sorted(list((graph_path / "pages").glob("*.md")) + list((graph_path / "journals").glob("*.md"))):
        entity_id = ingest_file_entity(db, source_id, source_name, md_path, graph_path)
        text = safe_read_text(md_path) or ""
        db.add_fragment(source_id=source_id, entity_id=entity_id, seq=1, text=text)
        label = md_path.stem.replace("_", " ")
        pages_by_label[normalize_label(label)] = entity_id
        db.add_statement(source_id=source_id, subject_id=entity_id, predicate=RDF_TYPE, object_value="logseq-page")
        db.add_statement(source_id=source_id, subject_id=entity_id, predicate=RDFS_LABEL, object_value=label)

        for seq, line in enumerate(text.splitlines(), start=1):
            match = re.search(r"^\s*-\s*(TODO|DOING|DONE|LATER|NOW|WAITING|CANCELED)\s+(.+)$", line)
            if not match:
                continue
            status = match.group(1)
            task_text = normalize_label(match.group(2))
            task_iri = f"{md_path.as_uri()}#todo-{seq}"
            task_id = db.ensure_entity(
                source_id=source_id,
                entity_type="task",
                iri=task_iri,
                label=task_text[:160],
                path=str(md_path),
                metadata={"status": status, "line": seq},
            )
            db.add_statement(source_id=source_id, subject_id=task_id, predicate=RDF_TYPE, object_value="task")
            db.add_statement(source_id=source_id, subject_id=task_id, predicate=RDFS_LABEL, object_value=task_text)
            db.add_statement(source_id=source_id, subject_id=task_id, predicate=SINGINE_PART_OF, object_entity_id=entity_id, object_kind="entity")
            db.add_statement(source_id=source_id, subject_id=task_id, predicate=SINGINE_STATUS, object_value=status)
            db.add_fragment(source_id=source_id, entity_id=task_id, seq=1, text=task_text)

        for link_label in extract_markdown_links(text):
            target_iri = f"urn:{slugify(source_name)}:page:{slugify(link_label)}"
            target_id = db.ensure_entity(
                source_id=source_id,
                entity_type="logseq-page-ref",
                iri=target_iri,
                label=link_label,
                metadata={"kind": "page-ref"},
            )
            db.add_statement(source_id=source_id, subject_id=entity_id, predicate=SINGINE_LINKS_TO, object_entity_id=target_id, object_kind="entity")

    for label, entity_id in pages_by_label.items():
        iri = f"urn:{slugify(source_name)}:page:{slugify(label)}"
        db.ensure_entity(
            source_id=source_id,
            entity_type="logseq-page",
            iri=iri,
            label=label,
            metadata={"resolved": True},
        )


def ingest_silkpage(db: BridgeDB, repo_root: Path) -> None:
    root = repo_root / "silkpage"
    if not root.exists():
        return
    source_name = "silkpage"
    source_id = db.upsert_source(
        SourceSpec(name=source_name, kind="filesystem", root_path=root, metadata={"family": "silkpage"})
    )
    for path in iter_files(root):
        if path.name == ".DS_Store":
            continue
        if path.suffix in {".md", ".xml", ".xsl", ".xslt", ".txt"}:
            ingest_text_file(db, source_id=source_id, source_name=source_name, path=path, root_path=root)
        else:
            ingest_file_entity(db, source_id, source_name, path, root)


def rdf_entity_label(subject: ET.Element) -> Optional[str]:
    preferred = [
        f"{{{PREFIXES['skos']}}}prefLabel",
        f"{{{PREFIXES['rdfs']}}}label",
        f"{{{PREFIXES['dc']}}}title",
    ]
    for tag in preferred:
        child = subject.find(tag)
        if child is not None:
            text = child_text(child)
            if text:
                return text
    return None


def ensure_rdf_entity(
    db: BridgeDB,
    *,
    source_id: str,
    iri: str,
    entity_type: str,
    label: Optional[str],
    source_path: Path,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    return db.ensure_entity(
        source_id=source_id,
        entity_type=entity_type,
        iri=iri,
        label=label,
        path=str(source_path),
        metadata=metadata,
    )


def ingest_rdf_properties(
    db: BridgeDB,
    *,
    source_id: str,
    path: Path,
    subject_id: str,
    subject_iri: str,
    element: ET.Element,
    blank_counter: List[int],
) -> None:
    for child in list(element):
        predicate = qname_to_iri(child.tag)
        resource = child.attrib.get(f"{{{PREFIXES['rdf']}}}resource")
        about = child.attrib.get(f"{{{PREFIXES['rdf']}}}about")
        nested = list(child)
        if resource:
            object_id = ensure_rdf_entity(
                db,
                source_id=source_id,
                iri=resource,
                entity_type="resource",
                label=None,
                source_path=path,
                metadata={"format": "rdf-xml", "placeholder": True},
            )
            db.add_statement(
                source_id=source_id,
                subject_id=subject_id,
                predicate=predicate,
                object_entity_id=object_id,
                object_kind="entity",
            )
            continue
        if about and xml_local_name(child.tag) == "Description":
            ingest_rdf_node(
                db,
                source_id=source_id,
                path=path,
                subject_iri=about,
                subject=child,
                blank_counter=blank_counter,
            )
            continue
        if nested:
            blank_counter[0] += 1
            nested_iri = f"{subject_iri}#blank-{blank_counter[0]}"
            nested_type = qname_to_iri(child.tag)
            nested_label = rdf_entity_label(child)
            nested_id = ensure_rdf_entity(
                db,
                source_id=source_id,
                iri=nested_iri,
                entity_type=compact_iri(nested_type),
                label=nested_label,
                source_path=path,
                metadata={"format": "rdf-xml", "blank_node": True},
            )
            db.add_statement(source_id=source_id, subject_id=nested_id, predicate=RDF_TYPE, object_value=nested_type)
            if nested_label:
                db.add_statement(source_id=source_id, subject_id=nested_id, predicate=RDFS_LABEL, object_value=nested_label)
            ingest_rdf_properties(
                db,
                source_id=source_id,
                path=path,
                subject_id=nested_id,
                subject_iri=nested_iri,
                element=child,
                blank_counter=blank_counter,
            )
            db.add_statement(
                source_id=source_id,
                subject_id=subject_id,
                predicate=predicate,
                object_entity_id=nested_id,
                object_kind="entity",
            )
            continue
        text = child_text(child)
        if text:
            db.add_statement(source_id=source_id, subject_id=subject_id, predicate=predicate, object_value=text)


def ingest_rdf_node(
    db: BridgeDB,
    *,
    source_id: str,
    path: Path,
    subject_iri: str,
    subject: ET.Element,
    blank_counter: List[int],
) -> str:
    subject_type = qname_to_iri(subject.tag)
    subject_label = rdf_entity_label(subject)
    subject_id = ensure_rdf_entity(
        db,
        source_id=source_id,
        iri=subject_iri,
        entity_type=compact_iri(subject_type),
        label=subject_label,
        source_path=path,
        metadata={"format": "rdf-xml"},
    )
    db.add_statement(source_id=source_id, subject_id=subject_id, predicate=RDF_TYPE, object_value=subject_type)
    if subject_label:
        db.add_statement(source_id=source_id, subject_id=subject_id, predicate=RDFS_LABEL, object_value=subject_label)
    ingest_rdf_properties(
        db,
        source_id=source_id,
        path=path,
        subject_id=subject_id,
        subject_iri=subject_iri,
        element=subject,
        blank_counter=blank_counter,
    )
    return subject_id


def ingest_rdf_file(db: BridgeDB, source_id: str, source_name: str, path: Path, root_path: Path) -> None:
    entity_id = ingest_file_entity(db, source_id, source_name, path, root_path)
    text = safe_read_text(path)
    if text:
        db.add_fragment(source_id=source_id, entity_id=entity_id, seq=1, text=text[:MAX_TEXT_BYTES])
    tree = ET.parse(path)
    root = tree.getroot()
    blank_counter = [0]
    for index, subject in enumerate(list(root), start=1):
        about = subject.attrib.get(f"{{{PREFIXES['rdf']}}}about")
        subject_iri = about or f"{path.as_uri()}#node-{index}"
        subject_id = ingest_rdf_node(
            db,
            source_id=source_id,
            path=path,
            subject_iri=subject_iri,
            subject=subject,
            blank_counter=blank_counter,
        )
        db.add_statement(
            source_id=source_id,
            subject_id=subject_id,
            predicate=DCTERMS_SOURCE,
            object_value=source_name,
        )


def ingest_knowyourai(db: BridgeDB) -> None:
    root = Path.home() / "ws" / "git" / "github" / "sindoc" / "knowyourai-framework"
    if not root.exists():
        return
    source_name = "knowyourai"
    source_id = db.upsert_source(
        SourceSpec(
            name=source_name,
            kind="rdf-knowledge-pack",
            root_path=root,
            metadata={"family": "knowyourai", "format": "rdf-xml"},
        )
    )
    for path in sorted(root.glob("*.rdf")):
        ingest_rdf_file(db, source_id, source_name, path, root)
    for path in sorted(root.glob("*.owl")):
        ingest_rdf_file(db, source_id, source_name, path, root)


def can_reach_logseq_api(base_url: str) -> bool:
    probe_url = base_url.rstrip("/") + "/api"
    request = urllib.request.Request(probe_url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=1.5) as response:
            return response.status < 500
    except urllib.error.HTTPError as exc:
        return exc.code in {400, 401, 403, 404, 405}
    except Exception:
        return False


def load_logseq_api_client(base_url: str, token: Optional[str]) -> Optional[Any]:
    if not token or not can_reach_logseq_api(base_url):
        return None
    try:
        from .logseq_api import LogseqAPIClient
    except Exception:
        return None
    client = LogseqAPIClient(base_url=base_url, token=token)
    try:
        if client.test_connection():
            return client
    except Exception:
        return None
    return None


def ingest_logseq_api_graph(db: BridgeDB, client: Any) -> Optional[Dict[str, Any]]:
    try:
        graph = client.get_current_graph() or {}
    except Exception:
        return None

    graph_name = graph.get("name") or "api-graph"
    graph_path = Path(graph.get("path") or f"logseq://{graph_name}")
    source_name = f"singine:{graph_name}"
    source_id = db.upsert_source(
        SourceSpec(
            name=source_name,
            kind="logseq-api",
            root_path=graph_path,
            metadata={"family": "singine", "graph_name": graph_name, "mode": "api"},
        )
    )
    graph_iri = f"urn:singine:logseq-api:graph:{slugify(graph_name)}"
    graph_entity_id = db.ensure_entity(
        source_id=source_id,
        entity_type="logseq-graph",
        iri=graph_iri,
        label=graph_name,
        path=str(graph_path),
        metadata=graph,
    )
    db.add_statement(source_id=source_id, subject_id=graph_entity_id, predicate=RDF_TYPE, object_value="logseq-graph")
    db.add_statement(source_id=source_id, subject_id=graph_entity_id, predicate=RDFS_LABEL, object_value=graph_name)
    db.add_statement(source_id=source_id, subject_id=graph_entity_id, predicate=SINGINE_RUNTIME, object_value="logseq-http-api")

    todos = []
    try:
        todos = client.query_todos()
    except Exception:
        todos = []

    for index, todo in enumerate(todos, start=1):
        uuid = todo.get("uuid") or stable_id("logseq-api-block", json.dumps(todo, sort_keys=True))
        content = normalize_label(todo.get("content") or "")
        marker = todo.get("marker") or "TODO"
        page = todo.get("page", {}) or {}
        page_name = page.get("name") or graph_name
        page_iri = f"urn:singine:logseq-api:page:{slugify(page_name)}"
        page_entity_id = db.ensure_entity(
            source_id=source_id,
            entity_type="logseq-page",
            iri=page_iri,
            label=page_name,
            metadata={"source": "api"},
        )
        db.add_statement(source_id=source_id, subject_id=page_entity_id, predicate=RDF_TYPE, object_value="logseq-page")
        db.add_statement(source_id=source_id, subject_id=page_entity_id, predicate=RDFS_LABEL, object_value=page_name)
        db.add_statement(source_id=source_id, subject_id=graph_entity_id, predicate=SINGINE_CONTAINS, object_entity_id=page_entity_id, object_kind="entity")

        task_iri = f"urn:singine:logseq-api:block:{uuid}"
        task_id = db.ensure_entity(
            source_id=source_id,
            entity_type="task",
            iri=task_iri,
            label=content[:160],
            metadata={"status": marker, "source": "api", "uuid": uuid},
        )
        db.add_statement(source_id=source_id, subject_id=task_id, predicate=RDF_TYPE, object_value="task")
        db.add_statement(source_id=source_id, subject_id=task_id, predicate=RDFS_LABEL, object_value=content)
        db.add_statement(source_id=source_id, subject_id=task_id, predicate=SINGINE_STATUS, object_value=marker)
        db.add_statement(source_id=source_id, subject_id=task_id, predicate=SINGINE_PART_OF, object_entity_id=page_entity_id, object_kind="entity")
        if content:
            db.add_fragment(source_id=source_id, entity_id=task_id, seq=index, text=content, metadata={"source": "api"})

    return {"graph_name": graph_name, "graph_path": str(graph_path), "todos_ingested": len(todos)}


def ingest_claude(db: BridgeDB, claude_root: Path) -> None:
    if not claude_root.exists():
        return
    source_name = "claude"
    source_id = db.upsert_source(
        SourceSpec(name=source_name, kind="agent-home", root_path=claude_root, metadata={"family": "claude"})
    )
    curated: List[Tuple[Path, bool]] = []
    curated.append((claude_root / "history.jsonl", True))
    curated.extend((path, True) for path in sorted((claude_root / "projects").rglob("*.jsonl")))
    curated.extend((path, False) for path in sorted((claude_root / "plans").glob("*.md")))
    curated.extend((path, False) for path in sorted((claude_root / "todos").glob("*.json")))
    for path, jsonl_mode in curated:
        if path.exists():
            ingest_text_file(
                db,
                source_id=source_id,
                source_name=source_name,
                path=path,
                root_path=claude_root,
                jsonl_mode=jsonl_mode,
            )


def ingest_codex(db: BridgeDB, codex_root: Path) -> None:
    if not codex_root.exists():
        return
    source_name = "codex"
    source_id = db.upsert_source(
        SourceSpec(name=source_name, kind="agent-home", root_path=codex_root, metadata={"family": "codex"})
    )
    curated: List[Tuple[Path, bool]] = [
        (codex_root / "history.jsonl", True),
        (codex_root / "config.toml", False),
        (codex_root / "version.json", False),
        (codex_root / "models_cache.json", False),
    ]
    curated.extend((path, False) for path in sorted((codex_root / "sessions").rglob("*")) if path.is_file())
    curated.extend((path, False) for path in sorted((codex_root / "memories").rglob("*")) if path.is_file())
    for path, jsonl_mode in curated:
        if path.exists():
            if path.suffix in {".sqlite", ".db"}:
                ingest_file_entity(db, source_id, source_name, path, codex_root)
            else:
                ingest_text_file(
                    db,
                    source_id=source_id,
                    source_name=source_name,
                    path=path,
                    root_path=codex_root,
                    jsonl_mode=jsonl_mode,
                )


def build_bridge(db_path: Path, repo_root: Path) -> Dict[str, Any]:
    db = BridgeDB(db_path)
    try:
        db.setup()
        db.reset()
        logseq_api_mode: Dict[str, Any] = {"enabled": False}
        api_client = load_logseq_api_client(
            os.environ.get("LOGSEQ_API_URL", "http://127.0.0.1:12315"),
            os.environ.get("LOGSEQ_API_TOKEN"),
        )
        if api_client is not None:
            api_result = ingest_logseq_api_graph(db, api_client)
            logseq_api_mode = {"enabled": True, "result": api_result}
        for graph in iter_logseq_graphs(Path.home() / "ws" / "logseq"):
            ingest_logseq_graph(db, graph)
        ingest_knowyourai(db)
        ingest_silkpage(db, repo_root)
        ingest_claude(db, Path.home() / ".claude")
        ingest_codex(db, Path.home() / ".codex")
        db.commit()
        return {
            "db_path": str(db_path),
            "jdbc_url": f"jdbc:sqlite:{db_path}",
            "logseq_api": logseq_api_mode,
            "sources": db.list_sources(),
        }
    finally:
        db.close()


def translate_sparql(query: str) -> Tuple[str, Sequence[Any], List[str]]:
    normalized = " ".join(query.strip().split())
    limit_match = re.search(r"\bLIMIT\s+(\d+)\b", normalized, re.IGNORECASE)
    limit = int(limit_match.group(1)) if limit_match else 20

    patterns: List[Tuple[re.Pattern[str], Any]] = [
        (
            re.compile(
                r"SELECT\s+\?s\s+WHERE\s*\{\s*\?s\s+(?:a|rdf:type|<[^>]+type>)\s+([^\s]+)\s*\.\s*\}",
                re.IGNORECASE,
            ),
            lambda m: (
                """
                SELECT DISTINCT e.iri AS s
                FROM entities e
                JOIN statements st ON st.subject_id=e.entity_id
                WHERE st.predicate = ? AND st.object_value = ?
                ORDER BY e.label
                LIMIT ?
                """,
                (RDF_TYPE, expand_term(m.group(1)), limit),
                ["s"],
            ),
        ),
        (
            re.compile(
                r"SELECT\s+\?s\s+\?label\s+WHERE\s*\{\s*\?s\s+(?:a|rdf:type)\s+([^\s]+)\s*;\s*(?:rdfs:label|<[^>]+label>)\s+\?label\s*\.\s*\}",
                re.IGNORECASE,
            ),
            lambda m: (
                """
                SELECT DISTINCT e.iri AS s, e.label AS label
                FROM entities e
                JOIN statements st ON st.subject_id=e.entity_id
                WHERE st.predicate = ? AND st.object_value = ?
                ORDER BY e.label
                LIMIT ?
                """,
                (RDF_TYPE, expand_term(m.group(1)), limit),
                ["s", "label"],
            ),
        ),
        (
            re.compile(
                r'SELECT\s+\?s\s+WHERE\s*\{\s*\?s\s+([^\s]+)\s+"([^"]+)"\s*\.\s*\}',
                re.IGNORECASE,
            ),
            lambda m: (
                """
                SELECT DISTINCT e.iri AS s
                FROM statements st
                JOIN entities e ON e.entity_id=st.subject_id
                WHERE st.predicate = ? AND st.object_value = ?
                ORDER BY e.label
                LIMIT ?
                """,
                (expand_term(m.group(1)), m.group(2), limit),
                ["s"],
            ),
        ),
        (
            re.compile(
                r"SELECT\s+\?o\s+WHERE\s*\{\s*([^\s]+)\s+([^\s]+)\s+\?o\s*\.\s*\}",
                re.IGNORECASE,
            ),
            lambda m: (
                """
                SELECT COALESCE(obj.iri, st.object_value) AS o
                FROM statements st
                JOIN entities subj ON subj.entity_id=st.subject_id
                LEFT JOIN entities obj ON obj.entity_id=st.object_entity_id
                WHERE subj.iri = ? AND st.predicate = ?
                ORDER BY o
                LIMIT ?
                """,
                (expand_term(m.group(1)), expand_term(m.group(2)), limit),
                ["o"],
            ),
        ),
        (
            re.compile(
                r"SELECT\s+\?s\s+\?o\s+WHERE\s*\{\s*\?s\s+([^\s]+)\s+\?o\s*\.\s*\}",
                re.IGNORECASE,
            ),
            lambda m: (
                """
                SELECT subj.iri AS s, COALESCE(obj.iri, st.object_value) AS o
                FROM statements st
                JOIN entities subj ON subj.entity_id=st.subject_id
                LEFT JOIN entities obj ON obj.entity_id=st.object_entity_id
                WHERE st.predicate = ?
                ORDER BY s, o
                LIMIT ?
                """,
                (expand_term(m.group(1)), limit),
                ["s", "o"],
            ),
        ),
    ]

    for pattern, builder in patterns:
        match = pattern.search(normalized)
        if match:
            return builder(match)

    raise ValueError(
        "Unsupported SPARQL shape. Supported patterns: type lookup, type+label, property literal, outbound relation, predicate scan."
    )


def parse_graphql_arguments(argument_text: str) -> Dict[str, str]:
    pairs = re.findall(r'(\w+)\s*:\s*"([^"]*)"|(\w+)\s*:\s*(\d+)', argument_text)
    result: Dict[str, str] = {}
    for a, b, c, d in pairs:
        if a:
            result[a] = b
        elif c:
            result[c] = d
    return result


def graphql_fields(selection: str) -> List[str]:
    return [field for field in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", selection) if field not in {"query"}]


def project_rows(rows: List[Dict[str, Any]], fields: List[str]) -> List[Dict[str, Any]]:
    if not fields:
        return rows
    projected: List[Dict[str, Any]] = []
    for row in rows:
        projected.append({field: row.get(field) for field in fields if field in row})
    return projected


def execute_graphql(db: BridgeDB, query: str) -> Dict[str, Any]:
    compact = " ".join(query.strip().split())

    if re.search(r"\bsources\s*\{", compact):
        fields = graphql_fields(compact[compact.index("sources"):])
        return {"data": {"sources": project_rows(db.list_sources(), fields)}}

    search_match = re.search(r"search\s*\(([^)]*)\)\s*\{([^}]*)\}", compact)
    if search_match:
        args = parse_graphql_arguments(search_match.group(1))
        rows = db.search(args.get("text", ""), limit=int(args.get("limit", "20")))
        return {"data": {"search": project_rows(rows, graphql_fields(search_match.group(2)))}} 

    entity_match = re.search(r'entity\s*\(([^)]*)\)\s*\{([^}]*)\}', compact)
    if entity_match:
        args = parse_graphql_arguments(entity_match.group(1))
        result = db.entity(args.get("iri", ""))
        body = result["entity"]
        body["statements"] = result["statements"]
        body["fragments"] = result["fragments"]
        return {"data": {"entity": body}}

    sparql_match = re.search(r'sparql\s*\(([^)]*)\)\s*\{([^}]*)\}', compact)
    if sparql_match:
        args = parse_graphql_arguments(sparql_match.group(1))
        result = db.sparql(args.get("query", ""))
        selection = graphql_fields(sparql_match.group(2))
        payload = {field: result.get(field) for field in selection if field in result}
        if "rows" in selection:
            payload["rows"] = result["rows"]
        return {"data": {"sparql": payload}}

    raise ValueError("Unsupported GraphQL shape. Supported roots: sources, search, entity, sparql.")


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and query the Singine Cortex SQLite bridge.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path (default: /tmp/sqlite.db)")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Build the merged SQLite bridge")
    build.add_argument("--repo-root", default=str(Path(__file__).resolve().parent.parent))

    sub.add_parser("sources", help="List merged sources")

    search = sub.add_parser("search", help="Full-text search across fragments")
    search.add_argument("text")
    search.add_argument("--limit", type=int, default=20)

    entity = sub.add_parser("entity", help="Show an entity with statements and fragments")
    entity.add_argument("iri")

    sparql = sub.add_parser("sparql", help="Translate a limited SPARQL query to SQL and execute it")
    sparql.add_argument("query")

    graphql = sub.add_parser("graphql", help="Run a GraphQL-shaped query over the bridge")
    graphql.add_argument("query")

    sub.add_parser("jdbc-url", help="Print the JDBC URL for the bridge database")

    http = sub.add_parser("http", help="JSON wrapper for server-side delegation")
    http.add_argument("--action", choices=["sources", "search", "entity", "sparql", "graphql"], required=True)
    http.add_argument("--query")
    http.add_argument("--entity")
    http.add_argument("--limit", type=int, default=20)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    db_path = Path(args.db).expanduser()

    if args.command == "build":
        result = build_bridge(db_path, Path(args.repo_root).expanduser())
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "jdbc-url":
        print(f"jdbc:sqlite:{db_path}")
        return 0

    db = BridgeDB(db_path)
    try:
        db.setup()
        if args.command == "sources":
            print(json.dumps(db.list_sources(), indent=2))
            return 0
        if args.command == "search":
            print(json.dumps(db.search(args.text, limit=args.limit), indent=2))
            return 0
        if args.command == "entity":
            print(json.dumps(db.entity(args.iri), indent=2))
            return 0
        if args.command == "sparql":
            print(json.dumps(db.sparql(args.query), indent=2))
            return 0
        if args.command == "graphql":
            print(json.dumps(db.graphql(args.query), indent=2))
            return 0
        if args.command == "http":
            if args.action == "sources":
                payload = {"ok": True, "sources": db.list_sources()}
            elif args.action == "search":
                payload = {"ok": True, "results": db.search(args.query or "", limit=args.limit)}
            elif args.action == "entity":
                payload = {"ok": True, "result": db.entity(args.entity or "")}
            elif args.action == "graphql":
                payload = {"ok": True, "result": db.graphql(args.query or "")}
            else:
                payload = {"ok": True, "result": db.sparql(args.query or "")}
            print(json.dumps(payload))
            return 0
        parser.error(f"Unknown command: {args.command}")
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
