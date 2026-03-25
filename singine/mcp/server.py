"""Singine Collibra MCP server.

Exposes Collibra-ingested domain data, AI sessions, and governance decisions
as MCP tools backed by a local SQLite database.

Usage (stdio transport — default for MCP clients):
    singine mcp serve --db /tmp/singine-mcp-test.db

Usage (SSE transport — for browser / HTTP clients):
    singine mcp serve --db /tmp/singine-mcp-test.db --transport sse --port 8765

Databases exposed
-----------------
A single SQLite file is expected to contain all three schema groups:

  Domain tables:
    business_term, business_capability, business_process,
    data_category, domain_event, governed_transaction,
    reference_data_entry

  AI session tables (optional — gracefully absent):
    ai_sessions, ai_interactions, ai_mandates

  Governance tables (optional — gracefully absent):
    approvals, decisions, invocation_counters

All tables can also be queried via the ``execute_sql`` tool (SELECT only).
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP


# ── server bootstrap ──────────────────────────────────────────────────────────

mcp = FastMCP("singine-collibra")

# Database path is set once at server start via configure().
_DB_PATH: str = ""


def configure(db_path: str) -> None:
    """Set the database path before serving."""
    global _DB_PATH
    _DB_PATH = str(Path(db_path).expanduser())


# ── database helpers ──────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    if not _DB_PATH:
        raise RuntimeError("DB path not configured — call configure(path) first")
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(sql: str, params: tuple = ()) -> list[dict]:
    conn = _conn()
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _table_exists(name: str) -> bool:
    conn = _conn()
    try:
        r = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        return r is not None
    finally:
        conn.close()


# ── tools: domain — master data ───────────────────────────────────────────────

_MASTER_TABLES = {
    "BusinessTerm":       "business_term",
    "BusinessCapability": "business_capability",
    "BusinessProcess":    "business_process",
    "DataCategory":       "data_category",
}


@mcp.tool()
def list_assets(
    asset_type: str = "BusinessTerm",
    limit: int = 50,
) -> list[dict]:
    """List Collibra assets of a given type.

    Args:
        asset_type: One of BusinessTerm, BusinessCapability, BusinessProcess, DataCategory.
        limit: Maximum number of records to return (default 50).
    """
    table = _MASTER_TABLES.get(asset_type)
    if not table:
        raise ValueError(
            f"Unknown asset_type '{asset_type}'. "
            f"Choose from: {', '.join(_MASTER_TABLES)}"
        )
    return _rows(f"SELECT * FROM {table} ORDER BY name LIMIT ?", (limit,))


@mcp.tool()
def find_assets(
    query: str,
    asset_type: str = "BusinessTerm",
    limit: int = 20,
) -> list[dict]:
    """Search Collibra assets by name or definition fragment (case-insensitive).

    Args:
        query: Text fragment to search for.
        asset_type: One of BusinessTerm, BusinessCapability, BusinessProcess, DataCategory.
        limit: Maximum number of records to return (default 20).
    """
    table = _MASTER_TABLES.get(asset_type)
    if not table:
        raise ValueError(f"Unknown asset_type '{asset_type}'.")
    like = f"%{query}%"
    # business_term uses 'definition'; other tables use 'description'
    text_col = "definition" if asset_type == "BusinessTerm" else "description"
    return _rows(
        f"SELECT * FROM {table} WHERE name LIKE ? OR {text_col} LIKE ? "
        f"ORDER BY name LIMIT ?",
        (like, like, limit),
    )


@mcp.tool()
def get_asset(asset_type: str, asset_id: str) -> dict | None:
    """Retrieve a single Collibra asset by its primary key id.

    Args:
        asset_type: One of BusinessTerm, BusinessCapability, BusinessProcess, DataCategory.
        asset_id: The UUID primary key of the asset.
    """
    table = _MASTER_TABLES.get(asset_type)
    if not table:
        raise ValueError(f"Unknown asset_type '{asset_type}'.")
    rows = _rows(f"SELECT * FROM {table} WHERE id = ?", (asset_id,))
    return rows[0] if rows else None


# ── tools: domain — events ────────────────────────────────────────────────────

@mcp.tool()
def list_domain_events(
    event_type: str | None = None,
    subject_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List domain events, optionally filtered by type or subject.

    Args:
        event_type: Optional event type filter (e.g. CATALOG_ASSET_REGISTERED).
        subject_id: Optional subject UUID to filter events for a specific asset.
        limit: Maximum number of events to return (default 50, newest first).
    """
    wheres = []
    params: list[Any] = []
    if event_type:
        wheres.append("event_type = ?")
        params.append(event_type)
    if subject_id:
        wheres.append("subject_id = ?")
        params.append(subject_id)
    where = ("WHERE " + " AND ".join(wheres)) if wheres else ""
    params.append(limit)
    rows = _rows(
        f"SELECT * FROM domain_event {where} ORDER BY occurred_at DESC LIMIT ?",
        tuple(params),
    )
    for row in rows:
        if row.get("payload"):
            try:
                row["payload"] = json.loads(row["payload"])
            except (json.JSONDecodeError, TypeError):
                pass
    return rows


# ── tools: domain — transactions ──────────────────────────────────────────────

@mcp.tool()
def list_transactions(
    tx_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List governed transactions (policy evaluations, mandate grants, decisions).

    Args:
        tx_type: Optional type filter (POLICY_EVALUATION, GOVERNANCE_DECISION, MANDATE_GRANT, …).
        status: Optional status filter (PENDING, APPROVED, REJECTED, COMPLETED, FAILED, EXPIRED).
        limit: Maximum number of transactions (default 50, newest first).
    """
    wheres = []
    params: list[Any] = []
    if tx_type:
        wheres.append("type = ?")
        params.append(tx_type)
    if status:
        wheres.append("status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(wheres)) if wheres else ""
    params.append(limit)
    rows = _rows(
        f"SELECT * FROM governed_transaction {where} ORDER BY created_at DESC LIMIT ?",
        tuple(params),
    )
    for row in rows:
        if row.get("payload"):
            try:
                row["payload"] = json.loads(row["payload"])
            except (json.JSONDecodeError, TypeError):
                pass
    return rows


# ── tools: domain — reference data ───────────────────────────────────────────

@mcp.tool()
def list_reference_data(
    code_set: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """List reference data entries (scenario-codes, iata-codes, etc.).

    Args:
        code_set: Optional code-set name filter (e.g. 'scenario-codes', 'iata-codes').
        limit: Maximum number of entries (default 100).
    """
    if code_set:
        return _rows(
            "SELECT * FROM reference_data_entry WHERE code_set = ? ORDER BY code LIMIT ?",
            (code_set, limit),
        )
    return _rows(
        "SELECT * FROM reference_data_entry ORDER BY code_set, code LIMIT ?",
        (limit,),
    )


# ── tools: AI sessions ────────────────────────────────────────────────────────

@mcp.tool()
def list_ai_sessions(limit: int = 20) -> list[dict]:
    """List recent AI sessions (Claude / Codex / OpenAI).

    Args:
        limit: Maximum number of sessions (default 20, newest first).
    """
    if not _table_exists("ai_sessions"):
        return []
    rows = _rows(
        "SELECT session_id, provider, model, session_urn, started_at, ended_at, status "
        "FROM ai_sessions ORDER BY started_at DESC LIMIT ?",
        (limit,),
    )
    return rows


@mcp.tool()
def get_ai_session(session_id: str) -> dict | None:
    """Return full details of an AI session including its interactions and mandates.

    Args:
        session_id: The session UUID.
    """
    if not _table_exists("ai_sessions"):
        return None
    sessions = _rows("SELECT * FROM ai_sessions WHERE session_id = ?", (session_id,))
    if not sessions:
        return None
    session = sessions[0]
    session["interactions"] = _rows(
        "SELECT * FROM ai_interactions WHERE session_id = ? ORDER BY created_at",
        (session_id,),
    )
    session["mandates"] = _rows(
        "SELECT * FROM ai_mandates WHERE session_id = ? ORDER BY created_at",
        (session_id,),
    )
    if session.get("metadata_json"):
        try:
            session["metadata"] = json.loads(session["metadata_json"])
        except (json.JSONDecodeError, TypeError):
            pass
    return session


# ── tools: governance ─────────────────────────────────────────────────────────

@mcp.tool()
def list_governance_approvals(
    ai_system: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List AI access governance approvals.

    Args:
        ai_system: Optional filter by AI system (e.g. 'claude', 'codex').
        limit: Maximum number of approvals (default 50, newest first).
    """
    if not _table_exists("approvals"):
        return []
    if ai_system:
        return _rows(
            "SELECT * FROM approvals WHERE ai_system = ? ORDER BY created_at DESC LIMIT ?",
            (ai_system, limit),
        )
    return _rows(
        "SELECT * FROM approvals ORDER BY created_at DESC LIMIT ?", (limit,)
    )


@mcp.tool()
def list_governance_decisions(
    ai_system: str | None = None,
    decision: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List AI governance decisions (APPROVED / REJECTED).

    Args:
        ai_system: Optional filter by AI system.
        decision: Optional filter by decision value ('APPROVED', 'REJECTED').
        limit: Maximum number of records (default 50, newest first).
    """
    if not _table_exists("decisions"):
        return []
    wheres = []
    params: list[Any] = []
    if ai_system:
        wheres.append("ai_system = ?")
        params.append(ai_system)
    if decision:
        wheres.append("decision = ?")
        params.append(decision)
    where = ("WHERE " + " AND ".join(wheres)) if wheres else ""
    params.append(limit)
    rows = _rows(
        f"SELECT * FROM decisions {where} ORDER BY created_at DESC LIMIT ?",
        tuple(params),
    )
    for row in rows:
        for field in ("resource_ids_json", "idp_context_json"):
            if row.get(field):
                try:
                    row[field] = json.loads(row[field])
                except (json.JSONDecodeError, TypeError):
                    pass
    return rows


@mcp.tool()
def get_invocation_summary(
    ai_system: str | None = None,
) -> list[dict]:
    """Summarise AI invocation counters grouped by scope and key.

    Args:
        ai_system: Optional filter by AI system.
    """
    if not _table_exists("invocation_counters"):
        return []
    if ai_system:
        return _rows(
            "SELECT * FROM invocation_counters WHERE ai_system = ? "
            "ORDER BY count DESC",
            (ai_system,),
        )
    return _rows(
        "SELECT * FROM invocation_counters ORDER BY count DESC"
    )


# ── tools: cross-cutting ──────────────────────────────────────────────────────

@mcp.tool()
def execute_sql(sql: str, params: list | None = None) -> list[dict]:
    """Execute a read-only (SELECT) SQL query against the domain database.

    Only SELECT statements are permitted.  All other statements are rejected
    to protect the integrity of the governed data.

    Args:
        sql: A SELECT SQL statement.
        params: Optional list of positional parameters for the query (? placeholders).
    """
    # Guard: only allow SELECT statements
    normalised = sql.strip().upper()
    if not normalised.startswith("SELECT") or re.search(
        r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|ATTACH|DETACH|PRAGMA)\b",
        normalised,
    ):
        raise ValueError(
            "Only SELECT statements are permitted via execute_sql."
        )
    return _rows(sql, tuple(params) if params else ())


@mcp.tool()
def list_tables() -> list[str]:
    """List all tables present in the Singine domain database."""
    rows = _rows(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    return [r["name"] for r in rows]


@mcp.tool()
def describe_table(table_name: str) -> list[dict]:
    """Return column information for a given table.

    Args:
        table_name: The table to inspect.
    """
    # Validate table exists to avoid injection
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", table_name):
        raise ValueError(f"Invalid table name: {table_name!r}")
    if not _table_exists(table_name):
        raise ValueError(f"Table does not exist: {table_name!r}")
    conn = _conn()
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── resources ─────────────────────────────────────────────────────────────────

@mcp.resource("singine://domain/schema")
def domain_schema_resource() -> str:
    """Return a JSON summary of all tables and their columns."""
    tables = list_tables()
    schema: dict = {}
    for t in tables:
        schema[t] = describe_table(t)
    return json.dumps(schema, indent=2)


@mcp.resource("singine://domain/capabilities")
def capabilities_resource() -> str:
    """Return all business capabilities as JSON."""
    return json.dumps(list_assets("BusinessCapability", limit=200), indent=2)


@mcp.resource("singine://domain/terms")
def terms_resource() -> str:
    """Return all business terms as JSON."""
    return json.dumps(list_assets("BusinessTerm", limit=200), indent=2)


# ── server entry point ────────────────────────────────────────────────────────

def serve(db_path: str, transport: str = "stdio", port: int = 8765) -> None:
    """Start the MCP server.

    Args:
        db_path: Path to the SQLite database.
        transport: 'stdio' (default) or 'sse'.
        port: HTTP port when using SSE transport.
    """
    configure(db_path)
    if transport == "sse":
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
