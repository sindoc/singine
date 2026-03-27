"""Seed a test SQLite database with representative Collibra domain data.

Usage:
    python -m singine.mcp.seed [--db /tmp/singine-test.db]
    singine mcp seed [--db /tmp/singine-test.db]

Creates a fully-seeded domain database covering all seven tables from
the domain DDL (mirroring SchemaBootstrap.java), plus the AI sessions
schema and the AI access governance schema.  The seed data represents
a plausible Singine / Collibra deployment so that MCP tool calls return
useful non-trivial results.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────────────

def _now(offset_days: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=offset_days)).isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


# ── DDL (copy of domain.py + AI schemas) ─────────────────────────────────────

_DOMAIN_DDL = """
CREATE TABLE IF NOT EXISTS business_term (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, definition TEXT,
    business_unit TEXT, collibra_id TEXT NOT NULL DEFAULT '',
    collibra_type TEXT NOT NULL, collibra_name TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS business_capability (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
    domain TEXT, owner TEXT, collibra_id TEXT NOT NULL DEFAULT '',
    collibra_type TEXT NOT NULL, collibra_name TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS business_process (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
    capability_id TEXT, owner TEXT, collibra_id TEXT NOT NULL DEFAULT '',
    collibra_type TEXT NOT NULL, collibra_name TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS data_category (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
    parent_id TEXT, collibra_id TEXT NOT NULL DEFAULT '',
    collibra_type TEXT NOT NULL, collibra_name TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS domain_event (
    event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
    subject_id TEXT, subject_urn TEXT, actor_id TEXT,
    occurred_at TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS idx_event_subject ON domain_event (subject_id);
CREATE INDEX IF NOT EXISTS idx_event_type    ON domain_event (event_type);

CREATE TABLE IF NOT EXISTS governed_transaction (
    transaction_id TEXT PRIMARY KEY, type TEXT NOT NULL, status TEXT NOT NULL,
    initiator_id TEXT, subject_id TEXT, ai_system TEXT, policy_pack_ref TEXT,
    reason TEXT, payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL, completed_at TEXT);
CREATE INDEX IF NOT EXISTS idx_tx_subject ON governed_transaction (subject_id);

CREATE TABLE IF NOT EXISTS reference_data_entry (
    id TEXT PRIMARY KEY, code_set TEXT NOT NULL, code TEXT NOT NULL,
    label TEXT, description TEXT, collibra_id TEXT NOT NULL DEFAULT '',
    collibra_type TEXT NOT NULL, collibra_name TEXT NOT NULL,
    UNIQUE (code_set, code));
"""

_AI_DDL = """
CREATE TABLE IF NOT EXISTS ai_sessions (
    session_id TEXT PRIMARY KEY, provider TEXT NOT NULL,
    model TEXT NOT NULL, session_urn TEXT NOT NULL,
    provider_object_ref TEXT NOT NULL,
    started_at TEXT NOT NULL, ended_at TEXT,
    status TEXT NOT NULL, metadata_json TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS ai_interactions (
    interaction_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    role TEXT NOT NULL, content TEXT NOT NULL,
    metadata_json TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS ai_mandates (
    mandate_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    action_name TEXT NOT NULL, resource TEXT NOT NULL,
    decision TEXT NOT NULL, note TEXT NOT NULL);
"""

_GOVERNANCE_DDL = """
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
    ai_system TEXT NOT NULL, environment TEXT NOT NULL,
    network_mode TEXT NOT NULL, execution_env TEXT NOT NULL,
    resource_kind TEXT NOT NULL, resource_value TEXT NOT NULL,
    command_prefix TEXT NOT NULL, operation TEXT NOT NULL,
    activity_id TEXT NOT NULL, granted_by TEXT NOT NULL,
    rationale TEXT NOT NULL, op_result_json TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
    ai_system TEXT NOT NULL, trust_level TEXT NOT NULL,
    environment TEXT NOT NULL, network_mode TEXT NOT NULL,
    execution_env TEXT NOT NULL, command_text TEXT NOT NULL,
    command_prefix TEXT NOT NULL, operation TEXT NOT NULL,
    activity_id TEXT NOT NULL, repo_resource_id TEXT NOT NULL,
    resource_ids_json TEXT NOT NULL, decision TEXT NOT NULL,
    rationale TEXT NOT NULL, requires_approval INTEGER NOT NULL,
    major_change INTEGER NOT NULL, idp_context_json TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS invocation_counters (
    scope TEXT NOT NULL, key TEXT NOT NULL,
    ai_system TEXT NOT NULL, environment TEXT NOT NULL,
    operation TEXT NOT NULL, activity_id TEXT NOT NULL,
    count INTEGER NOT NULL, last_invoked_at TEXT NOT NULL,
    PRIMARY KEY (scope, key, ai_system, environment, operation, activity_id));
"""


# ── seed data ────────────────────────────────────────────────────────────────

def _seed_domain(conn: sqlite3.Connection) -> None:
    cap_id_data = _uid()
    cap_id_ai = _uid()
    cap_id_gov = _uid()

    proc_id_ingest = _uid()
    proc_id_catalog = _uid()

    term_id_bt = _uid()
    term_id_dp = _uid()
    term_id_asset = _uid()

    cat_id_personal = _uid()
    cat_id_financial = _uid()
    cat_id_operational = _uid()

    # Business capabilities
    conn.executemany(
        "INSERT OR IGNORE INTO business_capability VALUES (?,?,?,?,?,?,?,?)",
        [
            (cap_id_data, "Data Governance", "Owns all data cataloguing, quality, and stewardship", "Data Office", "skh",
             "coll-cap-001", "BusinessCapability", "Data Governance"),
            (cap_id_ai, "AI Session Management", "Governed AI interactions across Claude, Codex, and OpenAI", "Platform", "skh",
             "coll-cap-002", "BusinessCapability", "AI Session Management"),
            (cap_id_gov, "Policy Enforcement", "Policy evaluation, approval workflows, and mandate tracking", "Compliance", "skh",
             "coll-cap-003", "BusinessCapability", "Policy Enforcement"),
        ],
    )

    # Business processes
    conn.executemany(
        "INSERT OR IGNORE INTO business_process VALUES (?,?,?,?,?,?,?,?)",
        [
            (proc_id_ingest, "Collibra Edge Ingest", "Import assets from Collibra Edge agent into local SQLite",
             cap_id_data, "skh", "coll-proc-001", "BusinessProcess", "Collibra Edge Ingest"),
            (proc_id_catalog, "Asset Cataloguing", "Register, update, and deprecate data assets in the catalog",
             cap_id_data, "skh", "coll-proc-002", "BusinessProcess", "Asset Cataloguing"),
        ],
    )

    # Business terms
    conn.executemany(
        "INSERT OR IGNORE INTO business_term VALUES (?,?,?,?,?,?,?)",
        [
            (term_id_bt, "Business Term", "A canonical definition managed in the Collibra glossary",
             "Data Office", "coll-term-001", "BusinessTerm", "Business Term"),
            (term_id_dp, "Data Product", "A governed, discoverable data asset exposed via a defined interface",
             "Data Office", "coll-term-002", "BusinessTerm", "Data Product"),
            (term_id_asset, "Collibra Asset", "Any entity registered and managed in the Collibra data catalog",
             "Platform", "coll-term-003", "BusinessTerm", "Collibra Asset"),
        ],
    )

    # Data categories
    conn.executemany(
        "INSERT OR IGNORE INTO data_category VALUES (?,?,?,?,?,?,?)",
        [
            (cat_id_personal, "Personal Data", "Data relating to an identified or identifiable natural person",
             None, "coll-cat-001", "DataCategory", "Personal Data"),
            (cat_id_financial, "Financial Data", "Revenue, cost, and P&L data under financial regulation",
             None, "coll-cat-002", "DataCategory", "Financial Data"),
            (cat_id_operational, "Operational Data", "Runtime metrics, logs, and telemetry",
             None, "coll-cat-003", "DataCategory", "Operational Data"),
        ],
    )

    # Domain events
    conn.executemany(
        "INSERT OR IGNORE INTO domain_event VALUES (?,?,?,?,?,?,?)",
        [
            (_uid(), "CATALOG_ASSET_REGISTERED", term_id_bt,
             "urn:singine:term:business-term", "skh", _now(-5),
             json.dumps({"source": "collibra-edge", "asset_type": "BusinessTerm"})),
            (_uid(), "CATALOG_ASSET_REGISTERED", term_id_dp,
             "urn:singine:term:data-product", "skh", _now(-4),
             json.dumps({"source": "collibra-edge", "asset_type": "BusinessTerm"})),
            (_uid(), "AI_SESSION_STARTED", None,
             "urn:singine:ai:session:test-001", "skh", _now(-3),
             json.dumps({"provider": "claude", "model": "claude-sonnet-4-6"})),
            (_uid(), "GOVERNANCE_POLICY_EVALUATED", proc_id_ingest,
             "urn:singine:process:edge-ingest", "skh", _now(-2),
             json.dumps({"policy_pack": "singine-policy", "result": "APPROVED"})),
            (_uid(), "CATALOG_ASSET_UPDATED", term_id_asset,
             "urn:singine:term:collibra-asset", "skh", _now(-1),
             json.dumps({"source": "collibra-edge", "change": "definition updated"})),
        ],
    )

    # Governed transactions
    conn.executemany(
        "INSERT OR IGNORE INTO governed_transaction VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            (_uid(), "POLICY_EVALUATION", "COMPLETED", "skh", proc_id_ingest,
             "claude", "singine-policy-v1", "Approve Collibra Edge ingest",
             json.dumps({"operation": "read", "resource": "/tmp/sqlite.db"}),
             _now(-3), _now(-3)),
            (_uid(), "GOVERNANCE_DECISION", "APPROVED", "skh", cap_id_data,
             "claude", "singine-policy-v1", "Read data governance capability",
             json.dumps({"operation": "read", "path": "/singine/domain/capability"}),
             _now(-2), _now(-2)),
            (_uid(), "MANDATE_GRANT", "COMPLETED", "skh", None,
             "claude", None, "Grant read access to domain DB",
             json.dumps({"resource": "domain.db", "action": "read"}),
             _now(-1), _now(-1)),
        ],
    )

    # Reference data
    conn.executemany(
        "INSERT OR IGNORE INTO reference_data_entry VALUES (?,?,?,?,?,?,?,?)",
        [
            (_uid(), "scenario-codes", "SC-001", "Data Catalogue Review",
             "Periodic review of Collibra data catalogue entries",
             "coll-ref-001", "ReferenceData", "scenario-codes/SC-001"),
            (_uid(), "scenario-codes", "SC-002", "AI Governance Audit",
             "Review of AI session mandates and approvals",
             "coll-ref-002", "ReferenceData", "scenario-codes/SC-002"),
            (_uid(), "iata-codes", "DXB", "Dubai International Airport",
             "IATA code DXB — Dubai Intl",
             "coll-ref-003", "ReferenceData", "iata-codes/DXB"),
            (_uid(), "iata-codes", "LHR", "London Heathrow Airport",
             "IATA code LHR — Heathrow",
             "coll-ref-004", "ReferenceData", "iata-codes/LHR"),
        ],
    )


def _seed_ai(conn: sqlite3.Connection) -> None:
    s1 = _uid()
    s2 = _uid()
    conn.executemany(
        "INSERT OR IGNORE INTO ai_sessions VALUES (?,?,?,?,?,?,?,?,?)",
        [
            (s1, "claude", "claude-sonnet-4-6",
             f"urn:singine:ai:session:{s1}", f"ref:{s1}",
             _now(-5), _now(-5), "CLOSED",
             json.dumps({"topic": "JVM runtime governance"})),
            (s2, "claude", "claude-opus-4-6",
             f"urn:singine:ai:session:{s2}", f"ref:{s2}",
             _now(-1), None, "OPEN",
             json.dumps({"topic": "Collibra MCP server"})),
        ],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO ai_interactions VALUES (?,?,?,?,?,?)",
        [
            (_uid(), s1, _now(-5), "user",
             "Let's build the JVM runtime governance layer.", "{}"),
            (_uid(), s1, _now(-5), "assistant",
             "I'll create singine runtime java with SDKMAN-backed registry.", "{}"),
            (_uid(), s2, _now(-1), "user",
             "Now build a reliable Collibra-based MCP server tested with SQLite.", "{}"),
        ],
    )
    conn.execute(
        "INSERT OR IGNORE INTO ai_mandates VALUES (?,?,?,?,?,?,?)",
        (_uid(), s1, _now(-5), "read_file",
         "/private/tmp/singine-personal-os/runtime/java/registry.json",
         "APPROVED", "needed to read Java registry"),
    )


def _seed_governance(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO approvals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (_uid(), _now(-3), "claude", "dev", "offline", "local",
             "file", "/Users/skh/ws/git/github/sindoc/singine/singine/command.py",
             "read", "read", "filesAboutTopic", "skh",
             "reading command.py to extend runtime commands",
             json.dumps({"status": "ok"})),
        ],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (_uid(), _now(-3), "claude", "trusted", "dev", "offline", "local",
             "read /singine/command.py", "read", "read",
             "filesAboutTopic",
             "singine/command.py",
             json.dumps(["/Users/skh/ws/git/github/sindoc/singine/singine/command.py"]),
             "APPROVED", "Safe read of internal project file", 0, 0,
             json.dumps({"user": "skh"})),
        ],
    )
    conn.execute(
        "INSERT OR REPLACE INTO invocation_counters VALUES (?,?,?,?,?,?,?,?)",
        ("project", "singine", "claude", "dev", "read", "filesAboutTopic",
         12, _now(-1)),
    )


# ── main ─────────────────────────────────────────────────────────────────────

def run(db_path: str) -> None:
    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    for ddl in (_DOMAIN_DDL, _AI_DDL, _GOVERNANCE_DDL):
        for stmt in ddl.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)

    _seed_domain(conn)
    _seed_ai(conn)
    _seed_governance(conn)
    conn.commit()
    conn.close()
    print(f"seeded: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a Singine MCP test database")
    parser.add_argument("--db", default="/tmp/singine-mcp-test.db",
                        help="Path to the SQLite database (default: /tmp/singine-mcp-test.db)")
    args = parser.parse_args()
    run(args.db)


if __name__ == "__main__":
    main()
