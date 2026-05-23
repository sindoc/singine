#!/usr/bin/env python3
"""
generate_man.py — Man page pipeline: silkpage sidebar metadata → roff .1

Three-phase pipeline governed by Collibra FLC mandate (flc_manifest.json):

  seed      Parse silkpage XML → populate SQLite sidebar_entries + flc_assets
  generate  SQLite/pg lookup → roff man pages under man/singine-*.1
  migrate   SQLite → PostgreSQL (via V004__man_pages_pg.sql DDL)

Usage:
  python3 man/generate_man.py seed \
      --silkpage-root ws/silkpage/templates/site/default/src/xml/en \
      --db data/singine-man.db

  python3 man/generate_man.py generate \
      --db data/singine-man.db [--page all|<id>] [--out-dir man/]

  python3 man/generate_man.py migrate \
      --db data/singine-man.db --pg-url postgresql://localhost:5432/singine

  python3 man/generate_man.py flc list --db data/singine-man.db
  python3 man/generate_man.py flc show MANP --db data/singine-man.db

singine invocation:
  singine man generate --page all
  singine runtime exec-external python3 man/generate_man.py generate --db data/singine-man.db
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree as ET

SCRIPT_DIR   = Path(__file__).resolve().parent
REPO_ROOT    = SCRIPT_DIR.parent
SCHEMA_SQL   = SCRIPT_DIR / "db" / "V004__man_pages.sql"
FLC_MANIFEST = SCRIPT_DIR / "flc_manifest.json"
DEFAULT_DB   = REPO_ROOT / "data" / "singine-man.db"
DEFAULT_OUT  = SCRIPT_DIR                    # man/ dir alongside this script
MAN_VERSION  = "singine 0.2.0"
MAN_DATE     = "2026-05-23"


# ── Database helpers ─────────────────────────────────────────────────────────

def _gen_id(prefix: str = "mgn") -> str:
    return f"{prefix}-{uuid.uuid4()}"


def open_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def apply_schema(con: sqlite3.Connection) -> None:
    """Apply V001–V004 schemas (idempotent — CREATE TABLE IF NOT EXISTS)."""
    # Apply V004 directly; earlier schemas are expected to exist already.
    # If running standalone, apply V004 even if earlier tables are absent
    # (sidebar/man tables don't reference V001–V003 tables).
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    # Remove INSERT OR IGNORE for schema_migrations if table doesn't exist yet
    stmts = [s.strip() for s in sql.split(";") if s.strip()]
    for stmt in stmts:
        try:
            con.execute(stmt)
        except sqlite3.OperationalError as e:
            # schema_migrations may not exist in standalone mode — skip
            if "schema_migrations" in str(e).lower() or "no such table" in str(e).lower():
                continue
            raise
    con.commit()


# ── FLC manifest ─────────────────────────────────────────────────────────────

def load_flc_manifest() -> dict[str, Any]:
    if FLC_MANIFEST.exists():
        return json.loads(FLC_MANIFEST.read_text(encoding="utf-8"))
    return {}


def seed_flc_from_manifest(con: sqlite3.Connection, manifest: dict) -> int:
    rows = 0
    for flc in manifest.get("flc_codes", []):
        con.execute(
            """INSERT OR IGNORE INTO flc_assets
               (flc_code, label, description, asset_type, dw_system,
                mandate_start, mandate_end, contract_id)
               VALUES (?,?,?,?,?,?,?,?)""",
            (flc["code"], flc["label"], flc.get("description",""),
             flc["asset_type"], flc.get("dw_system","singine"),
             manifest.get("mandate_start","2026-01-01"),
             manifest.get("mandate_end","2026-12-31"),
             manifest.get("contract_id","c.contract.man-pipeline-1yr")),
        )
        rows += con.execute("SELECT changes()").fetchone()[0]

    for dim in manifest.get("dw_dimension_mapping", {}).get("dimensions", []):
        gen_id = _gen_id("dim")
        con.execute(
            """INSERT OR IGNORE INTO dw_dimensions
               (gen_id, flc_code, dimension, axis)
               VALUES (?,?,?,?)""",
            (gen_id, dim["flc"], dim["dimension"], dim.get("axis","")),
        )
    con.commit()
    return rows


def seed_migration_services(con: sqlite3.Connection, manifest: dict) -> int:
    rows = 0
    for svc in manifest.get("mule_to_springboot_services", []):
        gen_id = _gen_id("msvc")
        con.execute(
            """INSERT OR IGNORE INTO migration_services
               (gen_id, service_name, from_tech, to_tech, flc_code, status, collibra_contract)
               VALUES (?,?,?,?,?,?,?)""",
            (gen_id, svc["service_name"], svc.get("from_tech","mule"),
             svc.get("to_tech","springboot"), svc.get("flc_code","MIGR"),
             svc.get("status","pending"),
             manifest.get("contract_id","c.contract.man-pipeline-1yr")),
        )
        rows += con.execute("SELECT changes()").fetchone()[0]
    con.commit()
    return rows


# ── Silkpage XML parsing ──────────────────────────────────────────────────────

def _text(el: Optional[ET.Element], default: str = "") -> str:
    if el is None:
        return default
    return (el.text or "").strip()


def _parse_layout(layout_xml: Path) -> list[dict]:
    """Parse layout.xml <toc> tree into a flat list of nav entries."""
    if not layout_xml.exists():
        return []
    tree = ET.parse(str(layout_xml))
    root = tree.getroot()
    entries: list[dict] = []

    def walk(node: ET.Element, depth: int, parent_href: str) -> None:
        for toc in node.findall("toc") + node.findall("tocentry"):
            page = toc.get("page","")
            d    = toc.get("dir","")
            fn   = toc.get("filename","index.html")
            href = ("/" + d + "/" + fn) if d else ("/" + fn)
            href = re.sub(r"//+", "/", href)
            entries.append({"page": page, "dir": d, "href": href, "depth": depth})
            walk(toc, depth + 1, href)

    walk(root, 0, "/")
    return entries


def _parse_webpage(xml_path: Path) -> dict[str, Any]:
    """Extract metadata from a silkpage <webpage> XML file."""
    meta: dict[str, Any] = {
        "id": "", "title": "", "summary": "", "keywords": "",
        "sections": [],
    }
    if not xml_path.exists():
        return meta
    try:
        tree = ET.parse(str(xml_path))
        root = tree.getroot()
        meta["id"] = root.get("id", xml_path.stem)
        head = root.find("head")
        if head is not None:
            meta["title"]    = _text(head.find("title"))
            meta["summary"]  = _text(head.find("summary"))
            meta["keywords"] = _text(head.find("keywords"))
        meta["sections"] = [
            {"id": sec.get("id",""), "title": _text(sec.find("title"))}
            for sec in root.findall("section")
        ]
    except ET.ParseError:
        pass
    return meta


def seed_sidebar_entries(
    con: sqlite3.Connection,
    silkpage_root: Path,
    layout_xml: Optional[Path] = None,
    flc_code: str = "SIDM",
) -> int:
    layout = layout_xml or (silkpage_root / "layout.xml")
    toc    = _parse_layout(layout)
    rows   = 0

    # Discover all XML files if no TOC found
    if not toc:
        for xml_path in sorted(silkpage_root.glob("*.xml")):
            if xml_path.name in ("layout.xml",):
                continue
            toc.append({"page": xml_path.name, "dir": "", "href": "/"+xml_path.stem, "depth": 0})

    for entry in toc:
        page_file = entry.get("page","")
        if not page_file:
            continue
        xml_path = silkpage_root / page_file
        meta     = _parse_webpage(xml_path)
        page_id  = meta["id"] or Path(page_file).stem
        gen_id   = _gen_id("se")

        # Resolve effective FLC for this page (all are SIDM by default)
        con.execute(
            """INSERT OR IGNORE INTO sidebar_entries
               (gen_id, page_id, nav_label, nav_href, depth,
                title, summary, keywords, section_ids, silkpage_src, flc_code)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (gen_id, page_id,
             meta["title"] or page_id,
             entry["href"], entry["depth"],
             meta["title"], meta["summary"], meta["keywords"],
             json.dumps([s["id"] for s in meta["sections"]]),
             str(xml_path.relative_to(silkpage_root) if xml_path.is_relative_to(silkpage_root) else xml_path),
             flc_code),
        )
        rows += con.execute("SELECT changes()").fetchone()[0]

    con.commit()
    return rows


# ── Roff man page rendering ───────────────────────────────────────────────────

def _roff_escape(text: str) -> str:
    return (text
            .replace("\\", "\\\\")
            .replace("-", "\\-")
            .replace("'", "\\'")
            .replace("`", "\\`"))


def _render_man_page(
    page_id: str,
    sidebar: dict[str, Any],
    flc_info: dict[str, Any],
    dimensions: list[dict],
    citizens: list[dict],
    migration_svcs: list[dict],
    db_source: str,
) -> str:
    title_uc  = page_id.upper().replace("-", "\\-")
    title_esc = _roff_escape(sidebar.get("title") or page_id)
    summary   = _roff_escape(sidebar.get("summary") or f"Singine {page_id} page")
    keywords  = sidebar.get("keywords","")
    sections  = json.loads(sidebar.get("section_ids") or "[]")
    flc_code  = flc_info.get("flc_code","MANP")
    mandate   = f'{flc_info.get("mandate_start","2026-01-01")} — {flc_info.get("mandate_end","2026-12-31")}'
    contract  = flc_info.get("contract_id","c.contract.man-pipeline-1yr")

    lines = [
        f'.TH {title_uc} 1 "{MAN_DATE}" "{MAN_VERSION}" "User Commands"',
        ".SH NAME",
        f"{_roff_escape(page_id)} \\- {summary}",
        ".SH SYNOPSIS",
        f".B singine man {page_id}",
        ".SH DESCRIPTION",
        f"This page was generated from silkpage sidebar metadata (FLC: {flc_code}).",
        ".PP",
        summary,
        ".PP",
        f"Source: {_roff_escape(str(sidebar.get('silkpage_src','')))}",
    ]

    if keywords:
        lines += [
            ".PP",
            f"Keywords: {_roff_escape(keywords)}",
        ]

    if sections:
        lines += [".SH SECTIONS"]
        for sid in sections:
            if sid:
                lines += [f".TP", f".B {_roff_escape(sid)}"]

    # FLC governance block
    lines += [
        ".SH FLC GOVERNANCE",
        f".TP",
        f".B FLC Code",
        flc_code,
        f".TP",
        f".B Mandate",
        _roff_escape(mandate),
        f".TP",
        f".B Contract",
        _roff_escape(contract),
        f".TP",
        f".B DB Source",
        db_source,
    ]

    if dimensions:
        lines += [".SH DATA WAREHOUSE DIMENSIONS"]
        for dim in dimensions:
            d = dim.get("dimension") or ""
            a = dim.get("axis") or ""
            if d:
                lines += [f".TP", f".B {d} ({a})"]
                lines += [dim.get("description") or ""]

    if citizens:
        lines += [".SH DATA CITIZENS"]
        for cit in citizens:
            cid   = _roff_escape(cit.get("citizen_id",""))
            label = _roff_escape(cit.get("label",""))
            role  = cit.get("role","contributor")
            url   = cit.get("public_profile_url","")
            lines += [f".TP", f".B {cid} ({role})"]
            lines += [label]
            if url:
                lines += [f"Profile: {_roff_escape(url)}"]

    if migration_svcs:
        lines += [".SH MIGRATION SERVICES (MULE → SPRING BOOT)"]
        for svc in migration_svcs:
            name   = _roff_escape(svc.get("service_name",""))
            status = svc.get("status","pending")
            src    = svc.get("from_tech","mule")
            tgt    = svc.get("to_tech","springboot")
            lines += [f".TP", f".B {name}"]
            lines += [f"Status: {status}  |  {src} \\(-> {tgt}"]

    lines += [
        ".SH SEE ALSO",
        ".BR singine (1),",
        ".BR singine-man (1)",
        ".SH SINGINE INVOCATION",
        ".nf",
        f"singine man {page_id}",
        f"singine man generate --page {page_id} --db data/singine-man.db",
        ".fi",
    ]

    return "\n".join(lines) + "\n"


# ── Phase: generate ──────────────────────────────────────────────────────────

def cmd_generate(
    db_path: Path,
    page: str,
    out_dir: Path,
    db_source: str = "sqlite",
    citizen_id: Optional[str] = None,
) -> int:
    con = open_db(db_path)
    apply_schema(con)

    # Load FLC for MANP
    flc_row = con.execute(
        "SELECT * FROM flc_assets WHERE flc_code='MANP'"
    ).fetchone()
    flc_info = dict(flc_row) if flc_row else {}

    if page == "all":
        entries = con.execute("SELECT * FROM sidebar_entries").fetchall()
    else:
        entries = con.execute(
            "SELECT * FROM sidebar_entries WHERE page_id=?", (page,)
        ).fetchall()

    if not entries:
        print(f"No sidebar entries found for page={page!r}. Run 'seed' first.", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    for row in entries:
        sb      = dict(row)
        pid     = sb["page_id"]
        man_id  = f"singine-{pid}-1"

        # Load DW dimensions for MANP (deduplicate by dimension+axis)
        seen_dims: set[tuple] = set()
        dims = []
        for r in con.execute(
            "SELECT * FROM dw_dimensions WHERE flc_code='MANP'"
        ).fetchall():
            key = (r["dimension"], r["axis"] or "")
            if key not in seen_dims:
                seen_dims.add(key)
                dims.append(dict(r))

        # Load data citizens for this page
        cit_rows = con.execute(
            """SELECT dc.*, mpc.role
               FROM data_citizens dc
               JOIN man_page_citizens mpc ON mpc.citizen_id = dc.citizen_id
               JOIN man_pages mp ON mp.gen_id = mpc.man_page_id
               WHERE mp.page_id=?""",
            (man_id,)
        ).fetchall()
        citizens = [dict(r) for r in cit_rows]

        # If citizen_id provided and not yet linked, add it
        if citizen_id and not citizens:
            dc_row = con.execute(
                "SELECT * FROM data_citizens WHERE citizen_id=?", (citizen_id,)
            ).fetchone()
            if dc_row:
                citizens = [{**dict(dc_row), "role": "contributor"}]

        # Load migration services referencing this man page
        migr_rows = con.execute(
            """SELECT ms.* FROM migration_services ms
               JOIN man_pages mp ON mp.gen_id = ms.man_page_id
               WHERE mp.page_id=?""",
            (man_id,)
        ).fetchall()
        migr_svcs = [dict(r) for r in migr_rows]

        content = _render_man_page(
            page_id=pid,
            sidebar=sb,
            flc_info=flc_info,
            dimensions=dims,
            citizens=citizens,
            migration_svcs=migr_svcs,
            db_source=db_source,
        )

        out_file = out_dir / f"singine-{pid}.1"
        out_file.write_text(content, encoding="utf-8")

        # Upsert into man_pages table
        existing = con.execute("SELECT gen_id FROM man_pages WHERE page_id=?", (man_id,)).fetchone()
        if existing:
            con.execute(
                """UPDATE man_pages SET content_roff=?, generated_at=?, output_path=?, db_source=?
                   WHERE page_id=?""",
                (content, datetime.now(timezone.utc).isoformat(),
                 str(out_file), db_source, man_id),
            )
        else:
            gen_id = _gen_id("mp")
            con.execute(
                """INSERT INTO man_pages
                   (gen_id, page_id, flc_code, sidebar_id, title,
                    content_roff, db_source, output_path)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (gen_id, man_id, "MANP", sb["gen_id"],
                 sb.get("title") or pid,
                 content, db_source, str(out_file)),
            )

        con.commit()
        print(f"  generated: {out_file}", file=sys.stderr)
        count += 1

    print(json.dumps({"ok": True, "generated": count, "out_dir": str(out_dir)}))
    return 0


# ── Phase: seed ──────────────────────────────────────────────────────────────

def cmd_seed(
    db_path: Path,
    silkpage_root: Path,
    layout_xml: Optional[Path] = None,
) -> int:
    con = open_db(db_path)
    apply_schema(con)

    manifest = load_flc_manifest()
    flc_rows = seed_flc_from_manifest(con, manifest)
    migr_rows = seed_migration_services(con, manifest)
    sb_rows   = seed_sidebar_entries(con, silkpage_root, layout_xml)

    print(json.dumps({
        "ok":              True,
        "db":              str(db_path),
        "flc_inserted":    flc_rows,
        "migr_inserted":   migr_rows,
        "sidebar_seeded":  sb_rows,
    }))
    return 0


# ── Phase: migrate (SQLite → PostgreSQL) ─────────────────────────────────────

def cmd_migrate(
    db_path: Path,
    pg_url: str,
    tables: str = "all",
) -> int:
    """Emit SQL INSERT statements for PostgreSQL from SQLite rows."""
    con = open_db(db_path)
    apply_schema(con)

    target_tables = (
        ["flc_assets","dw_dimensions","sidebar_entries",
         "man_pages","data_citizens","man_page_citizens","migration_services"]
        if tables == "all"
        else tables.split(",")
    )

    pg_ddl = (SCRIPT_DIR / "db" / "V004__man_pages_pg.sql").read_text(encoding="utf-8")
    print("-- PostgreSQL migration generated by generate_man.py")
    print(f"-- Source SQLite: {db_path}")
    print(f"-- Date: {datetime.now(timezone.utc).isoformat()}")
    print()
    print(pg_ddl)
    print()

    for table in target_tables:
        try:
            rows = con.execute(f"SELECT * FROM {table}").fetchall()
        except sqlite3.OperationalError:
            print(f"-- SKIP: table {table} not found in SQLite", file=sys.stderr)
            continue
        if not rows:
            continue
        cols = [d[0] for d in con.execute(f"SELECT * FROM {table} LIMIT 0").description]
        col_list = ", ".join(f'"{c}"' for c in cols)
        print(f"-- {table}: {len(rows)} rows")
        print(f"INSERT INTO {table} ({col_list}) VALUES")
        val_lines = []
        for row in rows:
            vals = []
            for v in row:
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                else:
                    escaped = str(v).replace("'","''")
                    vals.append(f"'{escaped}'")
            val_lines.append("  (" + ", ".join(vals) + ")")
        print(",\n".join(val_lines) + ";")
        print()

    print(f"-- Migration complete. Apply via: psql {pg_url} -f <this_file>")
    return 0


# ── Phase: flc ───────────────────────────────────────────────────────────────

def cmd_flc_list(db_path: Path) -> int:
    con = open_db(db_path)
    apply_schema(con)
    rows = con.execute(
        "SELECT flc_code, label, asset_type, mandate_start, mandate_end FROM flc_assets ORDER BY flc_code"
    ).fetchall()
    if not rows:
        print("No FLC assets found. Run 'seed' first.", file=sys.stderr)
        return 1
    for r in rows:
        print(f"{r['flc_code']}  {r['label']:<22}  {r['asset_type']:<22}  {r['mandate_start']} — {r['mandate_end']}")
    return 0


def cmd_flc_show(db_path: Path, code: str) -> int:
    con = open_db(db_path)
    apply_schema(con)
    row = con.execute("SELECT * FROM flc_assets WHERE flc_code=?", (code,)).fetchone()
    if not row:
        print(f"FLC code {code!r} not found.", file=sys.stderr)
        return 1
    print(json.dumps(dict(row), indent=2))
    dims = con.execute(
        "SELECT dimension, axis, description FROM dw_dimensions WHERE flc_code=?", (code,)
    ).fetchall()
    print("\nDW Dimensions:")
    for d in dims:
        print(f"  {d['dimension']:<12}  axis={d['axis']:<15}  {d['description'] or ''}")
    return 0


# ── Data citizen helpers ──────────────────────────────────────────────────────

def cmd_citizen_register(
    db_path: Path,
    citizen_id: str,
    label: str,
    community: str = "sindoc",
    profile_url: str = "",
    email: str = "",
    flc_mandate: str = "MANP,SIDM,DCTZ",
) -> int:
    con = open_db(db_path)
    apply_schema(con)
    con.execute(
        """INSERT OR REPLACE INTO data_citizens
           (citizen_id, label, community, public_profile_url, email, flc_mandate)
           VALUES (?,?,?,?,?,?)""",
        (citizen_id, label, community, profile_url, email, flc_mandate),
    )
    con.commit()
    print(json.dumps({"ok": True, "citizen_id": citizen_id}))
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="generate_man.py",
        description="Man page pipeline: silkpage sidebar metadata → roff .1 (FLC-governed)",
    )
    sub = ap.add_subparsers(dest="phase", required=True)

    # seed
    p_seed = sub.add_parser("seed", help="Parse silkpage XML → populate SQLite")
    p_seed.add_argument("--silkpage-root", required=True, help="Dir containing webpage XML files")
    p_seed.add_argument("--layout",        default="",   help="layout.xml path (default: <root>/layout.xml)")
    p_seed.add_argument("--db",            default=str(DEFAULT_DB))

    # generate
    p_gen = sub.add_parser("generate", help="DB lookup → roff man pages")
    p_gen.add_argument("--db",         default=str(DEFAULT_DB))
    p_gen.add_argument("--page",       default="all", help="Page id or 'all'")
    p_gen.add_argument("--out-dir",    default=str(DEFAULT_OUT))
    p_gen.add_argument("--pg",         action="store_true", help="Mark db_source as 'pg'")
    p_gen.add_argument("--citizen-id", default="", help="Bind a data citizen ID to generated pages")

    # migrate
    p_mig = sub.add_parser("migrate", help="SQLite → PostgreSQL INSERT statements")
    p_mig.add_argument("--db",       default=str(DEFAULT_DB))
    p_mig.add_argument("--pg-url",   default="postgresql://localhost:5432/singine")
    p_mig.add_argument("--tables",   default="all", help="Comma-separated table list or 'all'")

    # flc
    p_flc = sub.add_parser("flc", help="FLC asset operations")
    flc_sub = p_flc.add_subparsers(dest="flc_cmd", required=True)
    p_flc_list = flc_sub.add_parser("list", help="List all FLC codes")
    p_flc_list.add_argument("--db", default=str(DEFAULT_DB))
    p_flc_show = flc_sub.add_parser("show", help="Show a single FLC code")
    p_flc_show.add_argument("code")
    p_flc_show.add_argument("--db", default=str(DEFAULT_DB))

    # citizen
    p_cit = sub.add_parser("citizen", help="Data citizen registration")
    cit_sub = p_cit.add_subparsers(dest="cit_cmd", required=True)
    p_cit_reg = cit_sub.add_parser("register", help="Register a data citizen")
    p_cit_reg.add_argument("citizen_id")
    p_cit_reg.add_argument("--label",       required=True)
    p_cit_reg.add_argument("--community",   default="sindoc")
    p_cit_reg.add_argument("--profile-url", default="")
    p_cit_reg.add_argument("--email",       default="")
    p_cit_reg.add_argument("--flc-mandate", default="MANP,SIDM,DCTZ")
    p_cit_reg.add_argument("--db",          default=str(DEFAULT_DB))

    args = ap.parse_args(argv)

    if args.phase == "seed":
        return cmd_seed(
            db_path=Path(args.db),
            silkpage_root=Path(args.silkpage_root),
            layout_xml=Path(args.layout) if args.layout else None,
        )

    if args.phase == "generate":
        return cmd_generate(
            db_path=Path(args.db),
            page=args.page,
            out_dir=Path(args.out_dir),
            db_source="pg" if args.pg else "sqlite",
            citizen_id=args.citizen_id or None,
        )

    if args.phase == "migrate":
        return cmd_migrate(
            db_path=Path(args.db),
            pg_url=args.pg_url,
            tables=args.tables,
        )

    if args.phase == "flc":
        if args.flc_cmd == "list":
            return cmd_flc_list(Path(args.db))
        return cmd_flc_show(Path(args.db), args.code)

    if args.phase == "citizen":
        if args.cit_cmd == "register":
            return cmd_citizen_register(
                db_path=Path(args.db),
                citizen_id=args.citizen_id,
                label=args.label,
                community=args.community,
                profile_url=args.profile_url,
                email=args.email,
                flc_mandate=args.flc_mandate,
            )

    return 1


if __name__ == "__main__":
    sys.exit(main())
