"""PostgreSQL workflows for Singine.

This module provides a pragmatic SQLite -> PostgreSQL migration path backed by
Docker so the workstation does not need a native `psql` installation.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


def _run(
    cmd: Sequence[str],
    *,
    capture: bool = False,
    text: bool = True,
    input_data: Optional[str] = None,
    input_bytes: Optional[bytes] = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(cmd),
        capture_output=capture,
        text=text,
        input=input_data if text else input_bytes,
    )


def _emit_json(payload: Dict[str, Any]) -> int:
    print(json.dumps(payload))
    return 0 if payload.get("ok") else 1


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _sanitize_db_name(name: str) -> str:
    candidate = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip())
    candidate = re.sub(r"_+", "_", candidate).strip("_").lower()
    if not candidate:
        candidate = "singine"
    if candidate[0].isdigit():
        candidate = f"db_{candidate}"
    return candidate[:63]


def _map_sqlite_type(declared: str) -> str:
    token = (declared or "").strip().upper()
    if "INT" in token:
        return "bigint"
    if any(part in token for part in ("CHAR", "CLOB", "TEXT")):
        return "text"
    if "BLOB" in token:
        return "bytea"
    if any(part in token for part in ("REAL", "FLOA", "DOUB")):
        return "double precision"
    if any(part in token for part in ("NUMERIC", "DECIMAL", "BOOLEAN", "DATE", "TIME")):
        return "text"
    return "text"


@dataclass
class Column:
    name: str
    declared_type: str
    notnull: bool
    default_value: Optional[str]
    pk_order: int


@dataclass
class ForeignKey:
    id: int
    seq: int
    from_col: str
    ref_table: str
    ref_col: str
    on_update: str
    on_delete: str


@dataclass
class Table:
    name: str
    columns: List[Column]
    foreign_keys: List[ForeignKey]
    unique_constraints: List[Tuple[str, ...]]


def _sqlite_tables(db_path: Path) -> List[Table]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
        tables: List[Table] = []
        for (table_name,) in rows:
            columns = [
                Column(
                    name=row[1],
                    declared_type=row[2] or "",
                    notnull=bool(row[3]),
                    default_value=row[4],
                    pk_order=int(row[5] or 0),
                )
                for row in conn.execute(f"PRAGMA table_info({_quote_literal(table_name)})")
            ]
            foreign_keys = [
                ForeignKey(
                    id=int(row[0]),
                    seq=int(row[1]),
                    from_col=row[3],
                    ref_table=row[2],
                    ref_col=row[4],
                    on_update=row[5],
                    on_delete=row[6],
                )
                for row in conn.execute(f"PRAGMA foreign_key_list({_quote_literal(table_name)})")
            ]
            unique_constraints: List[Tuple[str, ...]] = []
            for idx in conn.execute(f"PRAGMA index_list({_quote_literal(table_name)})"):
                unique = bool(idx[2])
                origin = idx[3]
                if not unique or origin not in {"u", "c"}:
                    continue
                cols = tuple(
                    info[2]
                    for info in conn.execute(f"PRAGMA index_info({_quote_literal(idx[1])})")
                )
                if cols:
                    unique_constraints.append(cols)
            tables.append(Table(table_name, columns, foreign_keys, unique_constraints))
        return _toposort_tables(tables)
    finally:
        conn.close()


def _toposort_tables(tables: List[Table]) -> List[Table]:
    remaining = {table.name: table for table in tables}
    emitted: List[Table] = []
    while remaining:
        ready = [
            table
            for table in remaining.values()
            if all(fk.ref_table not in remaining for fk in table.foreign_keys)
        ]
        if not ready:
            emitted.extend(sorted(remaining.values(), key=lambda item: item.name))
            break
        for table in sorted(ready, key=lambda item: item.name):
            emitted.append(table)
            remaining.pop(table.name, None)
    return emitted


def _render_create_table(table: Table) -> str:
    defs: List[str] = []
    composite_pk = tuple(col.name for col in sorted(table.columns, key=lambda c: c.pk_order) if col.pk_order)
    inline_pk = len(composite_pk) == 1
    for col in table.columns:
        parts = [_quote_ident(col.name), _map_sqlite_type(col.declared_type)]
        if inline_pk and col.name == composite_pk[0]:
            parts.append("PRIMARY KEY")
        if col.notnull:
            parts.append("NOT NULL")
        if col.default_value is not None:
            parts.append(f"DEFAULT {col.default_value}")
        defs.append(" ".join(parts))
    if len(composite_pk) > 1:
        defs.append(f"PRIMARY KEY ({', '.join(_quote_ident(col) for col in composite_pk)})")
    for cols in sorted(set(table.unique_constraints)):
        defs.append(f"UNIQUE ({', '.join(_quote_ident(col) for col in cols)})")
    by_id: Dict[int, List[ForeignKey]] = {}
    for fk in table.foreign_keys:
        by_id.setdefault(fk.id, []).append(fk)
    for group in by_id.values():
        ordered = sorted(group, key=lambda item: item.seq)
        from_cols = ", ".join(_quote_ident(fk.from_col) for fk in ordered)
        ref_cols = ", ".join(_quote_ident(fk.ref_col) for fk in ordered)
        clause = (
            f"FOREIGN KEY ({from_cols}) REFERENCES {_quote_ident(ordered[0].ref_table)} ({ref_cols})"
        )
        if ordered[0].on_update and ordered[0].on_update != "NO ACTION":
            clause += f" ON UPDATE {ordered[0].on_update}"
        if ordered[0].on_delete and ordered[0].on_delete != "NO ACTION":
            clause += f" ON DELETE {ordered[0].on_delete}"
        defs.append(clause)
    inner = ",\n  ".join(defs)
    return f"CREATE TABLE {_quote_ident(table.name)} (\n  {inner}\n);"


def _docker_ps(name: str) -> Optional[Dict[str, str]]:
    result = _run(
        ["docker", "ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"],
        capture=True,
    )
    if result.returncode != 0:
        return None
    line = result.stdout.strip()
    if not line:
        return {}
    parts = line.split("\t")
    return {
        "name": parts[0],
        "status": parts[1] if len(parts) > 1 else "",
        "image": parts[2] if len(parts) > 2 else "",
    }


def _ensure_container(args: argparse.Namespace) -> Tuple[bool, str]:
    status = _docker_ps(args.container)
    if status is None:
        return False, "docker ps failed"
    if status:
        if not status["status"].startswith("Up "):
            started = _run(["docker", "start", args.container], capture=True)
            if started.returncode != 0:
                return False, started.stderr.strip() or "docker start failed"
        return True, "existing"

    volume = f"{args.container}-data"
    result = _run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            args.container,
            "--restart",
            "unless-stopped",
            "-e",
            f"POSTGRES_USER={args.user}",
            "-e",
            f"POSTGRES_PASSWORD={args.password}",
            "-e",
            "POSTGRES_DB=postgres",
            "-p",
            f"{args.host_port}:5432",
            "-v",
            f"{volume}:/var/lib/postgresql/data",
            args.image,
        ],
        capture=True,
    )
    if result.returncode != 0:
        return False, result.stderr.strip() or "docker run failed"
    return True, "created"


def _wait_ready(args: argparse.Namespace, timeout: int = 60) -> Tuple[bool, str]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = _run(
            ["docker", "exec", args.container, "pg_isready", "-U", args.user, "-d", "postgres"],
            capture=True,
        )
        if result.returncode == 0:
            return True, "ready"
        time.sleep(1)
    return False, "postgres did not become ready"


def _psql(args: argparse.Namespace, dbname: str, sql: str) -> subprocess.CompletedProcess:
    return _run(
        [
            "docker",
            "exec",
            "-i",
            args.container,
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            args.user,
            "-d",
            dbname,
        ],
        text=True,
        input_data=sql,
        capture=True,
    )


def _copy_table(args: argparse.Namespace, dbname: str, table: Table, db_path: Path) -> Tuple[bool, str, int]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cols = [col.name for col in table.columns]
        cursor = conn.execute(
            f'SELECT {", ".join(_quote_ident(col) for col in cols)} FROM {_quote_ident(table.name)}'
        )
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        count = 0
        for row in cursor:
            values = []
            for col in cols:
                value = row[col]
                if value is None:
                    values.append(r"\N")
                elif isinstance(value, bytes):
                    values.append("\\x" + value.hex())
                else:
                    values.append(str(value))
            writer.writerow(values)
            count += 1
        payload = out.getvalue()
    finally:
        conn.close()

    copy_sql = (
        f"COPY {_quote_ident(table.name)} ({', '.join(_quote_ident(col) for col in cols)}) "
        "FROM STDIN WITH (FORMAT csv, NULL '\\N');"
    )
    result = _run(
        [
            "docker",
            "exec",
            "-i",
            args.container,
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            args.user,
            "-d",
            dbname,
            "-c",
            copy_sql,
        ],
        text=True,
        input_data=payload,
        capture=True,
    )
    if result.returncode != 0:
        return False, result.stderr.strip() or f"COPY failed for {table.name}", count
    return True, "", count


def cmd_pg_create_database_from_sqlite(args: argparse.Namespace) -> int:
    sqlite_db = Path(args.sqlite_db).expanduser()
    if not sqlite_db.exists():
        msg = f"SQLite database not found: {sqlite_db}"
        if args.json:
            return _emit_json({"ok": False, "command": "pg create database fromSQLite", "error": msg})
        print(msg, file=sys.stderr)
        return 1

    db_name = args.db_name or _sanitize_db_name(sqlite_db.stem)
    if not args.json:
        print(
            f"[pg create database fromSQLite] sqlite={sqlite_db} db={db_name} "
            f"container={args.container} host=127.0.0.1 port={args.host_port}"
        )

    ok, detail = _ensure_container(args)
    if not ok:
        if args.json:
            return _emit_json({"ok": False, "command": "pg create database fromSQLite", "error": detail})
        print(detail, file=sys.stderr)
        return 1

    ok, detail = _wait_ready(args)
    if not ok:
        if args.json:
            return _emit_json({"ok": False, "command": "pg create database fromSQLite", "error": detail})
        print(detail, file=sys.stderr)
        return 1

    if args.replace:
        drop_sql = f"DROP DATABASE IF EXISTS {_quote_ident(db_name)};"
        dropped = _psql(args, "postgres", drop_sql)
        if dropped.returncode != 0:
            msg = dropped.stderr.strip() or f"Failed to drop database {db_name}"
            if args.json:
                return _emit_json({"ok": False, "command": "pg create database fromSQLite", "error": msg})
            print(msg, file=sys.stderr)
            return 1

    create_sql = (
        "SELECT 'present' FROM pg_database WHERE datname = "
        + _quote_literal(db_name)
        + ";\n"
        + f"CREATE DATABASE {_quote_ident(db_name)};"
    )
    created = _psql(args, "postgres", create_sql)
    if created.returncode != 0 and "already exists" not in (created.stderr or ""):
        msg = created.stderr.strip() or f"Failed to create database {db_name}"
        if args.json:
            return _emit_json({"ok": False, "command": "pg create database fromSQLite", "error": msg})
        print(msg, file=sys.stderr)
        return 1

    tables = _sqlite_tables(sqlite_db)
    schema_sql = "BEGIN;\nSET client_min_messages TO WARNING;\n"
    if args.replace:
        for table in reversed(tables):
            schema_sql += f"DROP TABLE IF EXISTS {_quote_ident(table.name)} CASCADE;\n"
    for table in tables:
        schema_sql += _render_create_table(table) + "\n"
    schema_sql += "COMMIT;\n"
    schema_result = _psql(args, db_name, schema_sql)
    if schema_result.returncode != 0:
        msg = schema_result.stderr.strip() or "Failed to create schema"
        if args.json:
            return _emit_json({"ok": False, "command": "pg create database fromSQLite", "error": msg})
        print(msg, file=sys.stderr)
        return 1

    imported: Dict[str, int] = {}
    for table in tables:
        ok, msg, count = _copy_table(args, db_name, table, sqlite_db)
        if not ok:
            if args.json:
                return _emit_json(
                    {
                        "ok": False,
                        "command": "pg create database fromSQLite",
                        "error": msg,
                        "table": table.name,
                    }
                )
            print(msg, file=sys.stderr)
            return 1
        imported[table.name] = count
        if not args.json:
            print(f"[pg create database fromSQLite] imported {table.name}: {count} row(s)")

    payload = {
        "ok": True,
        "command": "pg create database fromSQLite",
        "sqlite_db": str(sqlite_db),
        "postgres": {
            "container": args.container,
            "image": args.image,
            "host": "127.0.0.1",
            "port": args.host_port,
            "database": db_name,
            "user": args.user,
            "password": args.password,
            "jdbc_url": f"jdbc:postgresql://127.0.0.1:{args.host_port}/{db_name}",
            "edge_jdbc_url": f"jdbc:postgresql://host.docker.internal:{args.host_port}/{db_name}",
        },
        "tables": imported,
    }
    if args.json:
        return _emit_json(payload)

    print(f"[pg create database fromSQLite] jdbc=jdbc:postgresql://127.0.0.1:{args.host_port}/{db_name}")
    print(f"[pg create database fromSQLite] edge-jdbc=jdbc:postgresql://host.docker.internal:{args.host_port}/{db_name}")
    print(f"[pg create database fromSQLite] user={args.user} password={args.password}")
    return 0


def add_pg_parser(sub: argparse._SubParsersAction) -> None:
    pg_parser = sub.add_parser(
        "pg",
        help="PostgreSQL provisioning and migration workflows",
    )
    pg_parser.set_defaults(func=lambda a: (pg_parser.print_help(), 1)[1])
    pg_sub = pg_parser.add_subparsers(dest="pg_family")

    create_parser = pg_sub.add_parser("create", help="Create PostgreSQL resources")
    create_parser.set_defaults(func=lambda a: (create_parser.print_help(), 1)[1])
    create_sub = create_parser.add_subparsers(dest="pg_create_subject")

    create_database = create_sub.add_parser("database", help="Create a PostgreSQL database")
    create_database.set_defaults(func=lambda a: (create_database.print_help(), 1)[1])
    create_database_sub = create_database.add_subparsers(dest="pg_create_database_action")

    from_sqlite = create_database_sub.add_parser(
        "fromSQLite",
        help="Provision PostgreSQL in Docker and import a SQLite database into it",
    )
    from_sqlite.add_argument("sqlite_db", help="Path to the source SQLite database")
    from_sqlite.add_argument("--db-name", help="Target PostgreSQL database name (default: derived from SQLite file name)")
    from_sqlite.add_argument("--container", default="singine-pg", help="Docker container name (default: singine-pg)")
    from_sqlite.add_argument("--image", default="postgres:16-alpine", help="PostgreSQL Docker image (default: postgres:16-alpine)")
    from_sqlite.add_argument("--host-port", type=int, default=55432, help="Local host port to expose PostgreSQL on (default: 55432)")
    from_sqlite.add_argument("--user", default="singine", help="PostgreSQL superuser/login name (default: singine)")
    from_sqlite.add_argument("--password", default="singine", help="PostgreSQL password (default: singine)")
    from_sqlite.add_argument("--replace", action="store_true", help="Drop and recreate the target PostgreSQL database when it already exists")
    from_sqlite.add_argument("--json", action="store_true", help="Emit JSON")
    from_sqlite.set_defaults(func=cmd_pg_create_database_from_sqlite)
