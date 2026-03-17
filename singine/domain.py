"""Domain layer commands for Singine.

Provides direct CLI access to the master data, event, transaction, and
reference data stores that back the Humble IDP Java domain layer.
All operations target a SQLite database whose schema is initialised by
:class:`idp.db.SchemaBootstrap` in the Java module.

Command families
----------------
``singine domain master``
    CRUD for Collibra-aligned master data records
    (BusinessTerm, BusinessCapability, BusinessProcess, DataCategory).

``singine domain event``
    Append-only event log inspection and manual event injection.

``singine domain tx``
    Governed transaction lifecycle management
    (policy evaluations, governance decisions, mandate grants, auth flows).

``singine domain refdata``
    Reference data code-set browsing and seeding
    (scenario-codes, iata-codes, unicode-mapping).

``singine domain schema``
    Schema bootstrap and inspection utilities.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Collibra types derived from the Singine metamodel ──────────────────────

COLLIBRA_ASSET_TYPES = [
    "BUSINESS_ASSET", "DATA_ASSET", "GOVERNANCE_ASSET", "TECHNOLOGY_ASSET",
    "ISSUE", "BUSINESS_CAPABILITY", "BUSINESS_PROCESS", "BUSINESS_TERM",
    "DATA_CATEGORY", "DATABASE", "SCHEMA", "TABLE", "COLUMN", "DATA_ELEMENT",
    "POLICY", "RULE", "STANDARD",
]

MASTER_DATA_TABLES: Dict[str, str] = {
    "BusinessTerm":       "business_term",
    "BusinessCapability": "business_capability",
    "BusinessProcess":    "business_process",
    "DataCategory":       "data_category",
}

EVENT_TYPES = [
    "IDENTITY_LOGIN", "IDENTITY_LOGOUT", "IDENTITY_TOKEN_ISSUED",
    "IDENTITY_TOKEN_REVOKED", "IDENTITY_PASSWORD_CHANGED",
    "AI_SESSION_STARTED", "AI_SESSION_CLOSED", "AI_SESSION_FLUSHED",
    "GOVERNANCE_MANDATE_ISSUED", "GOVERNANCE_MANDATE_EXPIRED",
    "GOVERNANCE_POLICY_EVALUATED", "GOVERNANCE_DECISION_RECORDED",
    "CATALOG_ASSET_REGISTERED", "CATALOG_ASSET_UPDATED", "CATALOG_ASSET_DEPRECATED",
]

TRANSACTION_TYPES = [
    "POLICY_EVALUATION", "POLICY_APPROVAL", "POLICY_SYNC",
    "GOVERNANCE_DECISION",
    "MANDATE_GRANT", "MANDATE_REVOKE",
    "AUTH_LOGIN", "AUTH_TOKEN_EXCHANGE", "AUTH_REFRESH", "AUTH_LOGOUT",
]

TRANSACTION_STATUSES = ["PENDING", "APPROVED", "REJECTED", "COMPLETED", "FAILED", "EXPIRED"]


# ── Schema DDL (mirrors SchemaBootstrap.java) ───────────────────────────────

_DDL = """
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


# ── Helpers ─────────────────────────────────────────────────────────────────

def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


def _print_table(rows: List[sqlite3.Row], keys: List[str]) -> None:
    if not rows:
        print("(no records)")
        return
    widths = {k: max(len(k), max(len(str(row[k] or "")) for row in rows)) for k in keys}
    header = "  ".join(k.ljust(widths[k]) for k in keys)
    sep = "  ".join("─" * widths[k] for k in keys)
    print(header)
    print(sep)
    for row in rows:
        print("  ".join(str(row[k] or "").ljust(widths[k]) for k in keys))


# ── Schema commands ─────────────────────────────────────────────────────────

def cmd_domain_schema_init(args: argparse.Namespace) -> int:
    """Initialise the domain schema in a SQLite database."""
    conn = _connect(args.db)
    for stmt in _DDL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    conn.commit()
    conn.close()
    print(f"schema initialised: {args.db}")
    return 0


def cmd_domain_schema_tables(args: argparse.Namespace) -> int:
    """List tables present in the domain database."""
    conn = _connect(args.db)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    conn.close()
    if args.json:
        _print_json([r["name"] for r in rows])
    else:
        for r in rows:
            print(r["name"])
    return 0


# ── Master data commands ────────────────────────────────────────────────────

def cmd_domain_master_list(args: argparse.Namespace) -> int:
    """List master data records of a given type."""
    table = MASTER_DATA_TABLES.get(args.type)
    if not table:
        print(f"error: unknown type '{args.type}'. Choose from: {', '.join(MASTER_DATA_TABLES)}", file=sys.stderr)
        return 1
    conn = _connect(args.db)
    rows = conn.execute(f"SELECT * FROM {table} ORDER BY name").fetchall()
    conn.close()
    if args.json:
        _print_json([dict(r) for r in rows])
    else:
        _print_table(rows, ["id", "name", "collibra_type", "collibra_id"])
    return 0


def cmd_domain_master_find(args: argparse.Namespace) -> int:
    """Find master data records by name fragment."""
    table = MASTER_DATA_TABLES.get(args.type)
    if not table:
        print(f"error: unknown type '{args.type}'.", file=sys.stderr)
        return 1
    conn = _connect(args.db)
    rows = conn.execute(
        f"SELECT * FROM {table} WHERE name LIKE ? ORDER BY name",
        (f"%{args.name}%",)
    ).fetchall()
    conn.close()
    if args.json:
        _print_json([dict(r) for r in rows])
    else:
        _print_table(rows, ["id", "name", "collibra_type", "collibra_id"])
    return 0


def cmd_domain_master_add(args: argparse.Namespace) -> int:
    """Insert a master data record."""
    table = MASTER_DATA_TABLES.get(args.type)
    if not table:
        print(f"error: unknown type '{args.type}'.", file=sys.stderr)
        return 1
    record_id = args.id or str(uuid.uuid4())
    collibra_type = args.collibra_type or {
        "BusinessTerm": "BUSINESS_TERM",
        "BusinessCapability": "BUSINESS_CAPABILITY",
        "BusinessProcess": "BUSINESS_PROCESS",
        "DataCategory": "DATA_CATEGORY",
    }[args.type]
    conn = _connect(args.db)
    cols = "id, name, collibra_id, collibra_type, collibra_name"
    vals = (record_id, args.name, args.collibra_id or "", collibra_type, args.name)
    conn.execute(f"INSERT OR REPLACE INTO {table} ({cols}) VALUES (?,?,?,?,?)", vals)
    conn.commit()
    conn.close()
    result = {"id": record_id, "type": args.type, "name": args.name}
    if args.json:
        _print_json(result)
    else:
        print(f"added: {args.type} '{args.name}'  id={record_id}")
    return 0


# ── Event commands ───────────────────────────────────────────────────────────

def cmd_domain_event_log(args: argparse.Namespace) -> int:
    """Show recent domain events."""
    conn = _connect(args.db)
    where, params = [], []
    if args.subject_id:
        where.append("subject_id = ?")
        params.append(args.subject_id)
    if args.event_type:
        where.append("event_type = ?")
        params.append(args.event_type)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    limit = args.limit or 50
    rows = conn.execute(
        f"SELECT * FROM domain_event {clause} ORDER BY occurred_at DESC LIMIT ?",
        (*params, limit)
    ).fetchall()
    conn.close()
    if args.json:
        _print_json([dict(r) for r in rows])
    else:
        _print_table(rows, ["event_id", "event_type", "subject_id", "actor_id", "occurred_at"])
    return 0


def cmd_domain_event_append(args: argparse.Namespace) -> int:
    """Manually append a domain event."""
    event_id = str(uuid.uuid4())
    now = _now()
    payload = args.payload or "{}"
    conn = _connect(args.db)
    conn.execute(
        """INSERT INTO domain_event
           (event_id, event_type, subject_id, subject_urn, actor_id, occurred_at, payload)
           VALUES (?,?,?,?,?,?,?)""",
        (event_id, args.event_type, args.subject_id, args.subject_urn,
         args.actor_id, now, payload)
    )
    conn.commit()
    conn.close()
    result = {"event_id": event_id, "event_type": args.event_type,
              "subject_id": args.subject_id, "occurred_at": now}
    if args.json:
        _print_json(result)
    else:
        print(f"appended: {args.event_type}  event_id={event_id}  subject={args.subject_id}")
    return 0


# ── Transaction commands ─────────────────────────────────────────────────────

def cmd_domain_tx_list(args: argparse.Namespace) -> int:
    """List governed transactions."""
    conn = _connect(args.db)
    where, params = [], []
    if args.status:
        where.append("status = ?")
        params.append(args.status.upper())
    if args.tx_type:
        where.append("type = ?")
        params.append(args.tx_type.upper())
    if args.subject_id:
        where.append("subject_id = ?")
        params.append(args.subject_id)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    rows = conn.execute(
        f"SELECT * FROM governed_transaction {clause} ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    if args.json:
        _print_json([dict(r) for r in rows])
    else:
        _print_table(rows, ["transaction_id", "type", "status", "subject_id", "ai_system", "created_at"])
    return 0


def cmd_domain_tx_create(args: argparse.Namespace) -> int:
    """Create a governed transaction."""
    tx_id = str(uuid.uuid4())
    now = _now()
    conn = _connect(args.db)
    conn.execute(
        """INSERT INTO governed_transaction
           (transaction_id, type, status, initiator_id, subject_id, ai_system,
            policy_pack_ref, reason, payload, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (tx_id, args.tx_type.upper(), "PENDING", args.initiator_id, args.subject_id,
         args.ai_system, args.policy_pack_ref, args.reason, args.payload or "{}", now)
    )
    conn.commit()
    conn.close()
    result = {"transaction_id": tx_id, "type": args.tx_type.upper(),
              "status": "PENDING", "subject_id": args.subject_id, "created_at": now}
    if args.json:
        _print_json(result)
    else:
        print(f"created: {args.tx_type.upper()}  tx_id={tx_id}  subject={args.subject_id}")
    return 0


def cmd_domain_tx_update(args: argparse.Namespace) -> int:
    """Update the status of a governed transaction."""
    new_status = args.status.upper()
    completed_at = _now() if new_status != "PENDING" else None
    conn = _connect(args.db)
    cur = conn.execute(
        "UPDATE governed_transaction SET status=?, completed_at=? WHERE transaction_id=?",
        (new_status, completed_at, args.tx_id)
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        print(f"error: transaction '{args.tx_id}' not found", file=sys.stderr)
        return 1
    result = {"transaction_id": args.tx_id, "status": new_status, "completed_at": completed_at}
    if args.json:
        _print_json(result)
    else:
        print(f"updated: {args.tx_id} → {new_status}")
    return 0


# ── Reference data commands ──────────────────────────────────────────────────

def cmd_domain_refdata_list(args: argparse.Namespace) -> int:
    """List reference data entries."""
    conn = _connect(args.db)
    if args.code_set:
        rows = conn.execute(
            "SELECT * FROM reference_data_entry WHERE code_set=? ORDER BY code",
            (args.code_set,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT code_set, count(*) as count FROM reference_data_entry GROUP BY code_set ORDER BY code_set"
        ).fetchall()
    conn.close()
    if args.json:
        _print_json([dict(r) for r in rows])
    else:
        if args.code_set:
            _print_table(rows, ["code", "label", "description", "collibra_type"])
        else:
            _print_table(rows, ["code_set", "count"])
    return 0


def cmd_domain_refdata_add(args: argparse.Namespace) -> int:
    """Add a reference data entry."""
    entry_id = str(uuid.uuid4())
    collibra_type = args.collibra_type or "DATA_ELEMENT"
    conn = _connect(args.db)
    conn.execute(
        """INSERT INTO reference_data_entry
           (id, code_set, code, label, description, collibra_id, collibra_type, collibra_name)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(code_set, code) DO UPDATE SET
               label=excluded.label, description=excluded.description""",
        (entry_id, args.code_set, args.code, args.label, args.description or "",
         args.collibra_id or "", collibra_type, args.code)
    )
    conn.commit()
    conn.close()
    result = {"id": entry_id, "code_set": args.code_set, "code": args.code}
    if args.json:
        _print_json(result)
    else:
        print(f"added: [{args.code_set}] {args.code}  '{args.label}'")
    return 0


# ── Parser registration ──────────────────────────────────────────────────────

def add_domain_parser(sub: argparse._SubParsersAction) -> None:
    """Register ``singine domain`` and all its subcommand families."""

    domain_parser = sub.add_parser(
        "domain",
        help="Domain layer — master data, events, transactions, and reference data (SQLite)",
    )
    domain_parser.set_defaults(func=lambda a: (domain_parser.print_help(), 1)[1])
    domain_sub = domain_parser.add_subparsers(dest="domain_family")

    db_kwargs = dict(default=":memory:", help="SQLite database path (default: :memory:)")

    # ── schema ───────────────────────────────────────────────────────────────
    schema_parser = domain_sub.add_parser("schema", help="Schema bootstrap and inspection")
    schema_parser.set_defaults(func=lambda a: (schema_parser.print_help(), 1)[1])
    schema_sub = schema_parser.add_subparsers(dest="schema_action")

    p = schema_sub.add_parser("init", help="Initialise domain schema in a SQLite database")
    p.add_argument("--db", **db_kwargs)
    p.set_defaults(func=cmd_domain_schema_init)

    p = schema_sub.add_parser("tables", help="List tables in the domain database")
    p.add_argument("--db", **db_kwargs)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_domain_schema_tables)

    # ── master ───────────────────────────────────────────────────────────────
    master_parser = domain_sub.add_parser(
        "master",
        help="Master data records aligned with Collibra asset types",
    )
    master_parser.set_defaults(func=lambda a: (master_parser.print_help(), 1)[1])
    master_sub = master_parser.add_subparsers(dest="master_action")

    type_choices = list(MASTER_DATA_TABLES.keys())

    p = master_sub.add_parser("list", help="List master data records")
    p.add_argument("--type", required=True, choices=type_choices,
                   help="Record type (BusinessTerm|BusinessCapability|BusinessProcess|DataCategory)")
    p.add_argument("--db", **db_kwargs)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_domain_master_list)

    p = master_sub.add_parser("find", help="Find records by name fragment")
    p.add_argument("--type", required=True, choices=type_choices)
    p.add_argument("--name", required=True, help="Name fragment to match")
    p.add_argument("--db", **db_kwargs)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_domain_master_find)

    p = master_sub.add_parser("add", help="Insert a master data record")
    p.add_argument("--type", required=True, choices=type_choices)
    p.add_argument("--name", required=True, help="Record name")
    p.add_argument("--id", help="Override UUID")
    p.add_argument("--collibra-id", dest="collibra_id", default="", help="Collibra asset UUID")
    p.add_argument("--collibra-type", dest="collibra_type",
                   choices=COLLIBRA_ASSET_TYPES, help="Collibra asset type override")
    p.add_argument("--db", **db_kwargs)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_domain_master_add)

    # ── event ─────────────────────────────────────────────────────────────────
    event_parser = domain_sub.add_parser("event", help="Domain event log")
    event_parser.set_defaults(func=lambda a: (event_parser.print_help(), 1)[1])
    event_sub = event_parser.add_subparsers(dest="event_action")

    p = event_sub.add_parser("log", help="Show recent domain events")
    p.add_argument("--db", **db_kwargs)
    p.add_argument("--subject-id", dest="subject_id", help="Filter by subject ID")
    p.add_argument("--event-type", dest="event_type", choices=EVENT_TYPES,
                   help="Filter by event type")
    p.add_argument("--limit", type=int, default=50, help="Maximum results (default: 50)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_domain_event_log)

    p = event_sub.add_parser("append", help="Manually append a domain event")
    p.add_argument("--db", **db_kwargs)
    p.add_argument("--event-type", dest="event_type", required=True, choices=EVENT_TYPES)
    p.add_argument("--subject-id", dest="subject_id", required=True)
    p.add_argument("--subject-urn", dest="subject_urn", default="")
    p.add_argument("--actor-id", dest="actor_id", default="system")
    p.add_argument("--payload", default="{}", help="JSON payload string")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_domain_event_append)

    # ── tx ───────────────────────────────────────────────────────────────────
    tx_parser = domain_sub.add_parser("tx", help="Governed transaction lifecycle")
    tx_parser.set_defaults(func=lambda a: (tx_parser.print_help(), 1)[1])
    tx_sub = tx_parser.add_subparsers(dest="tx_action")

    p = tx_sub.add_parser("list", help="List governed transactions")
    p.add_argument("--db", **db_kwargs)
    p.add_argument("--status", choices=TRANSACTION_STATUSES, help="Filter by status")
    p.add_argument("--type", dest="tx_type", choices=TRANSACTION_TYPES, help="Filter by type")
    p.add_argument("--subject-id", dest="subject_id", help="Filter by subject ID")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_domain_tx_list)

    p = tx_sub.add_parser("create", help="Create a governed transaction")
    p.add_argument("--db", **db_kwargs)
    p.add_argument("--type", dest="tx_type", required=True, choices=TRANSACTION_TYPES)
    p.add_argument("--subject-id", dest="subject_id", required=True)
    p.add_argument("--initiator-id", dest="initiator_id", default="system")
    p.add_argument("--ai-system", dest="ai_system", help="AI system (claude, codex, …)")
    p.add_argument("--policy-pack-ref", dest="policy_pack_ref", help="Policy pack path")
    p.add_argument("--reason", help="Governance rationale")
    p.add_argument("--payload", default="{}", help="JSON payload")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_domain_tx_create)

    p = tx_sub.add_parser("update", help="Update status of a governed transaction")
    p.add_argument("--db", **db_kwargs)
    p.add_argument("--tx-id", dest="tx_id", required=True)
    p.add_argument("--status", required=True, choices=TRANSACTION_STATUSES)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_domain_tx_update)

    # ── refdata ───────────────────────────────────────────────────────────────
    refdata_parser = domain_sub.add_parser("refdata", help="Reference data code sets")
    refdata_parser.set_defaults(func=lambda a: (refdata_parser.print_help(), 1)[1])
    refdata_sub = refdata_parser.add_subparsers(dest="refdata_action")

    p = refdata_sub.add_parser("list", help="List reference data entries or code sets")
    p.add_argument("--db", **db_kwargs)
    p.add_argument("--code-set", dest="code_set", help="Show entries for one code set")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_domain_refdata_list)

    p = refdata_sub.add_parser("add", help="Add a reference data entry")
    p.add_argument("--db", **db_kwargs)
    p.add_argument("--code-set", dest="code_set", required=True)
    p.add_argument("--code", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--collibra-id", dest="collibra_id", default="")
    p.add_argument("--collibra-type", dest="collibra_type",
                   choices=COLLIBRA_ASSET_TYPES, default="DATA_ELEMENT")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_domain_refdata_add)
