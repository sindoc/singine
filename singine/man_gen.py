"""
man_gen.py — singine man generate command handler.

Delegates to man/generate_man.py via subprocess so that the man page pipeline
can be invoked as:

  singine man generate --page all
  singine man generate --page cleanup --db data/singine-man.db
  singine man flc list
  singine man citizen register <id> --label "Jay H"

This module is imported lazily from command.py only when the man generate
subcommand is actually invoked.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT    = Path(__file__).resolve().parent.parent
GENERATOR    = REPO_ROOT / "man" / "generate_man.py"
DEFAULT_DB   = REPO_ROOT / "data" / "singine-man.db"
DEFAULT_SILKPAGE = REPO_ROOT.parent / "silkpage" / "templates" / "site" / "default" / "src" / "xml" / "en"


def _run_generator(argv: list[str]) -> int:
    cmd = [sys.executable, str(GENERATOR)] + argv
    result = subprocess.run(cmd)
    return result.returncode


def cmd_man_generate(args: argparse.Namespace) -> int:
    """Dispatch singine man generate → man/generate_man.py generate."""
    sub_argv = ["generate"]

    page = getattr(args, "man_page", None) or "all"
    sub_argv += ["--page", page]

    db = getattr(args, "man_db", None)
    sub_argv += ["--db", db or str(DEFAULT_DB)]

    out = getattr(args, "man_out_dir", None)
    if out:
        sub_argv += ["--out-dir", out]

    if getattr(args, "man_pg", False):
        sub_argv.append("--pg")

    citizen = getattr(args, "citizen_id", None)
    if citizen:
        sub_argv += ["--citizen-id", citizen]

    return _run_generator(sub_argv)


def cmd_man_seed(args: argparse.Namespace) -> int:
    """Dispatch singine man seed → man/generate_man.py seed."""
    root = getattr(args, "silkpage_root", None) or str(DEFAULT_SILKPAGE)
    db   = getattr(args, "man_db", None) or str(DEFAULT_DB)
    sub_argv = ["seed", "--silkpage-root", root, "--db", db]
    layout = getattr(args, "layout", None)
    if layout:
        sub_argv += ["--layout", layout]
    return _run_generator(sub_argv)


def cmd_man_migrate(args: argparse.Namespace) -> int:
    """Dispatch singine man migrate → man/generate_man.py migrate."""
    db     = getattr(args, "man_db", None) or str(DEFAULT_DB)
    pg_url = getattr(args, "pg_url", None) or "postgresql://localhost:5432/singine"
    tables = getattr(args, "tables", "all")
    return _run_generator(["migrate", "--db", db, "--pg-url", pg_url, "--tables", tables])


def cmd_man_flc_list(args: argparse.Namespace) -> int:
    """List FLC codes in the man page DB."""
    db = getattr(args, "man_db", None) or str(DEFAULT_DB)
    return _run_generator(["flc", "list", "--db", db])


def cmd_man_flc_show(args: argparse.Namespace) -> int:
    """Show a single FLC code."""
    db   = getattr(args, "man_db", None) or str(DEFAULT_DB)
    code = getattr(args, "flc_code", "MANP")
    return _run_generator(["flc", "show", code, "--db", db])


def cmd_man_citizen_register(args: argparse.Namespace) -> int:
    """Register a community-active data citizen."""
    db  = getattr(args, "man_db", None) or str(DEFAULT_DB)
    cid = getattr(args, "citizen_id", "")
    sub_argv = [
        "citizen", "register", cid,
        "--label",       getattr(args, "citizen_label", cid),
        "--community",   getattr(args, "community", "sindoc"),
        "--profile-url", getattr(args, "profile_url", ""),
        "--email",       getattr(args, "citizen_email", ""),
        "--flc-mandate", getattr(args, "flc_mandate", "MANP,SIDM,DCTZ"),
        "--db",          db,
    ]
    return _run_generator(sub_argv)
