"""Notebook-friendly zip-code neighborhood demo with messaging and publication outputs."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import uuid
import xml.etree.ElementTree as ET
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


DEMO_ROWS = [
    {
        "zip_code": "1000",
        "country_code": "BE",
        "municipality": "Brussels",
        "neighborhood": "Pentagon Centre",
        "life_phase_tendency": "early-career-and-student-mobility",
        "community_pattern": "multilingual services, civic institutions, and dense public transport",
        "languages": ["en", "fr", "nl"],
        "wikipedia": {
            "en": "City_of_Brussels",
            "fr": "Bruxelles-ville",
            "nl": "Stad_Brussel",
        },
        "collibra_codes": {
            "zip": "ZIP-BE-1000",
            "life_phase": "LIFE-EARLY",
            "community": "COMM-CIVIC-DENSE",
        },
    },
    {
        "zip_code": "1030",
        "country_code": "BE",
        "municipality": "Schaerbeek",
        "neighborhood": "Helmet",
        "life_phase_tendency": "family-forming-and-migrant-entrepreneurship",
        "community_pattern": "schools, small commerce, diaspora associations, and mixed housing",
        "languages": ["en", "fr", "nl", "ar"],
        "wikipedia": {
            "en": "Schaerbeek",
            "fr": "Schaerbeek",
            "nl": "Schaarbeek",
        },
        "collibra_codes": {
            "zip": "ZIP-BE-1030",
            "life_phase": "LIFE-FAMILY",
            "community": "COMM-SCHOOL-COMMERCE",
        },
    },
    {
        "zip_code": "1060",
        "country_code": "BE",
        "municipality": "Saint-Gilles",
        "neighborhood": "Parvis",
        "life_phase_tendency": "creative-professional-and-active-aging-mix",
        "community_pattern": "health practices, cultural venues, and high street proximity",
        "languages": ["en", "fr", "nl", "es"],
        "wikipedia": {
            "en": "Saint-Gilles,_Belgium",
            "fr": "Saint-Gilles_(Bruxelles)",
            "nl": "Sint-Gillis_(Brussel)",
        },
        "collibra_codes": {
            "zip": "ZIP-BE-1060",
            "life_phase": "LIFE-CREATIVE-AGING",
            "community": "COMM-HEALTH-CULTURE",
        },
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")


def _git_context(repo_root: Path) -> Dict[str, Any]:
    def _run(args: List[str]) -> str:
        try:
            proc = subprocess.run(args, cwd=repo_root, capture_output=True, text=True, timeout=10, check=False)
        except Exception:
            return ""
        return (proc.stdout or proc.stderr).strip()

    return {
        "repo_root": str(repo_root),
        "branch": _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "head": _run(["git", "rev-parse", "HEAD"]),
        "status_excerpt": _run(["git", "status", "--short"]),
    }


def _domain_ddl() -> str:
    return """
CREATE TABLE IF NOT EXISTS domain_event (
    event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
    subject_id TEXT, subject_urn TEXT, actor_id TEXT,
    occurred_at TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}');
"""


def _append_domain_event(db_path: Path, event_type: str, subject_id: str, actor_id: str, payload: Dict[str, Any]) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_domain_ddl())
    conn.execute(
        """INSERT INTO domain_event
           (event_id, event_type, subject_id, subject_urn, actor_id, occurred_at, payload)
           VALUES (?,?,?,?,?,?,?)""",
        (
            str(uuid.uuid4()),
            event_type,
            subject_id,
            f"urn:singine:demo:{subject_id}",
            actor_id,
            _now(),
            json.dumps(payload, sort_keys=True),
        ),
    )
    conn.commit()
    conn.close()


def _message_topology(demo_id: str) -> Dict[str, Any]:
    return {
        "rabbitmq": {
            "raw": {
                "exchange": "singine.raw.messaging",
                "routing_key": f"{demo_id}.raw",
                "queue": f"{demo_id}.raw.queue",
            },
            "staging": {
                "exchange": "singine.staging.messaging",
                "routing_key": f"{demo_id}.staging",
                "queue": f"{demo_id}.staging.queue",
            },
        },
        "kafka": {
            "topic": f"singine.datastreaming.{demo_id}.v1",
            "consumer_group": f"{demo_id}.analytics",
        },
        "lambda": {
            "function_name": f"{demo_id}-publisher",
            "purpose": "Publish staging payloads into Kafka and notebook-facing APIs.",
        },
    }


def _row_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = deepcopy(row)
    payload["standard_languages"] = row["languages"]
    payload["source"] = "synthetic-demo"
    payload["mapping_protocol"] = {
        "wikipedia": row["wikipedia"],
        "collibra_codes": row["collibra_codes"],
    }
    return payload


def build_zip_neighborhood_demo(*, title: str = "Zip Neighborhood Messaging Demo") -> Dict[str, Any]:
    demo_id = _slug(title or "zip-neighborhood-demo")
    rows = [_row_payload(row) for row in DEMO_ROWS]
    topology = _message_topology(demo_id)
    raw_messages = [
        {
            "stage": "raw",
            "broker": "rabbitmq",
            "exchange": topology["rabbitmq"]["raw"]["exchange"],
            "routing_key": topology["rabbitmq"]["raw"]["routing_key"],
            "payload": row,
        }
        for row in rows
    ]
    staging_messages = [
        {
            "stage": "staging",
            "broker": "rabbitmq",
            "exchange": topology["rabbitmq"]["staging"]["exchange"],
            "routing_key": topology["rabbitmq"]["staging"]["routing_key"],
            "payload": {
                **row,
                "curation_status": "standards-aligned",
                "publication_formats": ["markdown", "xml", "json", "mediawiki"],
            },
        }
        for row in rows
    ]
    kafka_messages = [
        {
            "stage": "stream",
            "broker": "kafka",
            "topic": topology["kafka"]["topic"],
            "key": row["zip_code"],
            "payload": {
                "zip_code": row["zip_code"],
                "life_phase_tendency": row["life_phase_tendency"],
                "community_pattern": row["community_pattern"],
                "languages": row["languages"],
                "collibra_codes": row["collibra_codes"],
            },
        }
        for row in rows
    ]
    notebook_import = {
        "python": [
            "from singine.zip_neighborhood_demo import build_zip_neighborhood_demo",
            "demo = build_zip_neighborhood_demo()",
            "demo['messages']['kafka'][0]",
        ],
        "collibra_notebook": "import singine; from singine.zip_neighborhood_demo import build_zip_neighborhood_demo",
        "databricks": "import singine\nfrom singine.zip_neighborhood_demo import build_zip_neighborhood_demo",
    }
    protocol = {
        "source_markdown": "Markdown fragments are canonical drafting units.",
        "xml_projection": "Each markdown fragment has an XML rendering suitable for downstream transformation.",
        "json_projection": "JSON is the API- and notebook-facing envelope.",
        "mediawiki_projection": "MediaWiki text is emitted for wiki-native publication.",
    }
    return {
        "demo_id": demo_id,
        "title": title,
        "generated_at": _now(),
        "purpose": "First demo aligning raw/staging RabbitMQ, Kafka streaming, lambda publication, notebook import, multilingual mapping, and publication artefacts.",
        "topology": topology,
        "datasets": rows,
        "messages": {
            "raw": raw_messages,
            "staging": staging_messages,
            "kafka": kafka_messages,
        },
        "notebook_import": notebook_import,
        "protocol": protocol,
    }


def render_markdown(demo: Dict[str, Any]) -> str:
    lines = [
        f"# {demo['title']}",
        "",
        f"- demo-id:: {demo['demo_id']}",
        f"- generated-at:: {demo['generated_at']}",
        f"- kafka-topic:: {demo['topology']['kafka']['topic']}",
        f"- lambda-function:: {demo['topology']['lambda']['function_name']}",
        "",
        "## Zip Code Rows",
    ]
    for row in demo["datasets"]:
        lines.extend(
            [
                f"### {row['zip_code']} {row['municipality']} / {row['neighborhood']}",
                f"- life-phase:: {row['life_phase_tendency']}",
                f"- community-pattern:: {row['community_pattern']}",
                f"- languages:: {', '.join(row['languages'])}",
                f"- collibra-zip-code:: {row['collibra_codes']['zip']}",
                f"- wikipedia-en:: {row['wikipedia'].get('en', '')}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def render_mediawiki(demo: Dict[str, Any]) -> str:
    lines = [
        f"= {demo['title']} =",
        "",
        f"* demo-id: {demo['demo_id']}",
        f"* kafka-topic: {demo['topology']['kafka']['topic']}",
        "",
        "== Zip Code Rows ==",
    ]
    for row in demo["datasets"]:
        lines.extend(
            [
                f"=== {row['zip_code']} {row['municipality']} / {row['neighborhood']} ===",
                f"* life phase: {row['life_phase_tendency']}",
                f"* community pattern: {row['community_pattern']}",
                f"* languages: {', '.join(row['languages'])}",
                f"* Collibra zip code: {row['collibra_codes']['zip']}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def render_xml(demo: Dict[str, Any]) -> str:
    root = ET.Element("zip-neighborhood-demo", {"id": demo["demo_id"]})
    ET.SubElement(root, "title").text = demo["title"]
    topology = ET.SubElement(root, "topology")
    rabbit = ET.SubElement(topology, "rabbitmq")
    for stage in ["raw", "staging"]:
        node = ET.SubElement(rabbit, stage)
        for key, value in demo["topology"]["rabbitmq"][stage].items():
            ET.SubElement(node, key).text = value
    kafka = ET.SubElement(topology, "kafka")
    ET.SubElement(kafka, "topic").text = demo["topology"]["kafka"]["topic"]
    ET.SubElement(kafka, "consumer-group").text = demo["topology"]["kafka"]["consumer_group"]
    rows = ET.SubElement(root, "rows")
    for row in demo["datasets"]:
        row_el = ET.SubElement(rows, "row", {"zip-code": row["zip_code"]})
        for key in ["country_code", "municipality", "neighborhood", "life_phase_tendency", "community_pattern"]:
            ET.SubElement(row_el, key).text = row[key]
        langs = ET.SubElement(row_el, "languages")
        for lang in row["languages"]:
            ET.SubElement(langs, "language").text = lang
    return ET.tostring(root, encoding="unicode")


def write_zip_neighborhood_demo_bundle(
    *,
    output_dir: Path,
    title: str = "Zip Neighborhood Messaging Demo",
    domain_db: Optional[Path] = None,
    actor_id: str = "singine",
) -> Dict[str, Any]:
    demo = build_zip_neighborhood_demo(title=title)
    repo_root = Path(__file__).resolve().parent.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_dir = output_dir / "rabbitmq" / "raw"
    staging_dir = output_dir / "rabbitmq" / "staging"
    kafka_dir = output_dir / "kafka"
    publication_dir = output_dir / "publication"
    for path in [raw_dir, staging_dir, kafka_dir, publication_dir]:
        path.mkdir(parents=True, exist_ok=True)

    for idx, message in enumerate(demo["messages"]["raw"], start=1):
        (raw_dir / f"{idx:02d}-{message['payload']['zip_code']}.json").write_text(json.dumps(message, indent=2) + "\n", encoding="utf-8")
    for idx, message in enumerate(demo["messages"]["staging"], start=1):
        (staging_dir / f"{idx:02d}-{message['payload']['zip_code']}.json").write_text(json.dumps(message, indent=2) + "\n", encoding="utf-8")
    (kafka_dir / "topic.json").write_text(json.dumps(demo["messages"]["kafka"], indent=2) + "\n", encoding="utf-8")

    markdown = render_markdown(demo)
    mediawiki = render_mediawiki(demo)
    xml_text = render_xml(demo)

    (publication_dir / "demo.md").write_text(markdown, encoding="utf-8")
    (publication_dir / "demo.mediawiki").write_text(mediawiki, encoding="utf-8")
    (publication_dir / "demo.xml").write_text(xml_text, encoding="utf-8")
    (publication_dir / "demo.json").write_text(json.dumps(demo, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "demo": demo,
        "git_context": _git_context(repo_root),
        "artifacts": {
            "raw_dir": str(raw_dir),
            "staging_dir": str(staging_dir),
            "kafka_topic_file": str(kafka_dir / "topic.json"),
            "markdown": str(publication_dir / "demo.md"),
            "xml": str(publication_dir / "demo.xml"),
            "json": str(publication_dir / "demo.json"),
            "mediawiki": str(publication_dir / "demo.mediawiki"),
        },
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    if domain_db:
        event_payload = {
            "demo_id": demo["demo_id"],
            "output_dir": str(output_dir),
            "artifacts": manifest["artifacts"],
            "kafka_topic": demo["topology"]["kafka"]["topic"],
        }
        _append_domain_event(domain_db, "AI_SESSION_STARTED", demo["demo_id"], actor_id, event_payload)
        _append_domain_event(domain_db, "CATALOG_ASSET_REGISTERED", demo["demo_id"], actor_id, event_payload)
        manifest["domain_db"] = str(domain_db)

    return manifest
