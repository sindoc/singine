#!/usr/bin/env python3
"""
collect.py — Committee result-set collector.

Gathers two result sets into report/committee-results.json:
  1. disk  — disk-space analysis (same schema as go/scanner/main.go)
  2. gov   — singine governance state from gh/sync-logseq
              (SQLite when seeded, schema+rules when empty)

Usage:
  python3 collect.py [--home <dir>] [--logseq-db <path>] [--out <file>]

singine invocation:
  singine runtime exec-external python3 cleanup/collect.py
"""

from __future__ import annotations

import json
import os
import platform
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Repo layout (relative to this file) ──────────────────────────────────────
# SYNC_LOGSEQ_PATH env var overrides the default sibling-repo location so this
# script works whether cleanup/ lives inside the singine repo or alongside it.

SCRIPT_DIR   = Path(__file__).resolve().parent
REPO_ROOT    = SCRIPT_DIR.parent
_default_logseq = REPO_ROOT / "gh" / "sync-logseq"    # ws/singine/../gh/sync-logseq
LOGSEQ_PROJ  = Path(os.environ.get("SYNC_LOGSEQ_PATH", str(_default_logseq)))
DEFAULT_DB   = LOGSEQ_PROJ / "data" / "sync-logseq.db"
REPORT_DIR   = SCRIPT_DIR / "report"


# ── Known disk targets (mirrors go/scanner/main.go knownTargets) ──────────────

_TARGETS = [
    dict(id="jetbrains-idea2020-tomcat",
         label="IntelliJ IDEA 2020.2 — Tomcat server cache",
         posix="AppData/Local/JetBrains/IntelliJIdea2020.2/tomcat",
         win="AppData/Local/JetBrains/IntelliJIdea2020.2/tomcat",
         category="ide-cache", risk="safe",
         notes="Tomcat runtime output from a 2020 IntelliJ install."),
    dict(id="jetbrains-idea2020-all",
         label="IntelliJ IDEA 2020.2 — full system directory",
         posix="AppData/Local/JetBrains/IntelliJIdea2020.2",
         win="AppData/Local/JetBrains/IntelliJIdea2020.2",
         category="ide-cache", risk="review",
         notes="Safe to delete if you no longer use IntelliJ 2020.2."),
    dict(id="dropbox-backup-2020-mar",
         label="Dropbox — full user backup 2020-03",
         posix="Dropbox/backup/20200315T195649_Jay_Users.tar.gz",
         win="Dropbox/backup/20200315T195649_Jay_Users.tar.gz",
         category="backup", risk="review",
         notes="6-year-old full user backup. Verify newer backup exists first."),
    dict(id="dropbox-backup-2020-jan",
         label="Dropbox — full user backup 2020-01",
         posix="Dropbox/backup/20200126T184105_Jay_Users.tar.gz",
         win="Dropbox/backup/20200126T184105_Jay_Users.tar.gz",
         category="backup", risk="review",
         notes="6-year-old full user backup."),
    dict(id="claude-desktop-cache",
         label="Claude desktop app — LocalCache",
         posix="AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache",
         win="AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache",
         category="app-cache", risk="review",
         notes="Conversation cache. Clears chat history from the desktop app."),
    dict(id="claude-cli-old-2148",
         label="Claude CLI — old version 2.1.148",
         posix=".local/share/claude/versions/2.1.148",
         win=".local/share/claude/versions/2.1.148",
         category="old-binary", risk="safe",
         notes="Superseded by 2.1.150."),
    dict(id="claude-cli-old-2149",
         label="Claude CLI — old version 2.1.149",
         posix=".local/share/claude/versions/2.1.149",
         win=".local/share/claude/versions/2.1.149",
         category="old-binary", risk="safe",
         notes="Superseded by 2.1.150."),
    dict(id="tibco-zip-library",
         label="TIBCO BW 6.3.1 zip — local duplicate (Dropbox copy is canonical)",
         posix="Library/Articles/TIBCO/TIBCO DocAndBinaries/TIB_BW-dev_6.3.1_win_x86_64.zip",
         win="Library/Articles/TIBCO/TIBCO DocAndBinaries/TIB_BW-dev_6.3.1_win_x86_64.zip",
         category="duplicate", risk="safe",
         notes="Identical copy lives in Dropbox/Library."),
    dict(id="oracle-adf-zip-library",
         label="Oracle ADF training zip — local duplicate",
         posix="Library/Articles/Oracle/training/adf/oracle-adf-training.zip",
         win="Library/Articles/Oracle/training/adf/oracle-adf-training.zip",
         category="duplicate", risk="safe",
         notes="Identical copy lives in Dropbox/Library."),
    dict(id="dropbox-installer-idea",
         label="Dropbox/Downloads — IntelliJ IDEA 2020.3.1 installer",
         posix="Dropbox/Downloads/ideaIU-2020.3.1.exe",
         win="Dropbox/Downloads/ideaIU-2020.3.1.exe",
         category="installer", risk="safe",
         notes="Already installed."),
    dict(id="dropbox-installer-nitro",
         label="Dropbox/Downloads — Nitro Pro 13 MSI",
         posix="Dropbox/Downloads/nitro_pro13_ba_x64.msi",
         win="Dropbox/Downloads/nitro_pro13_ba_x64.msi",
         category="installer", risk="safe"),
    dict(id="dropbox-installer-xampp",
         label="Dropbox/Downloads — XAMPP installer",
         posix="Dropbox/Downloads/xampp-windows-x64-8.0.0-3-VS16-installer.exe",
         win="Dropbox/Downloads/xampp-windows-x64-8.0.0-3-VS16-installer.exe",
         category="installer", risk="safe"),
    dict(id="dropbox-installer-deepl",
         label="Dropbox/Downloads — DeepL installer",
         posix="Dropbox/Downloads/DeepLSetup.exe",
         win="Dropbox/Downloads/DeepLSetup.exe",
         category="installer", risk="safe"),
    dict(id="logseq-old-version",
         label="Logseq — old app version 0.10.15",
         posix="AppData/Local/Logseq/app-0.10.15",
         win="AppData/Local/Logseq/app-0.10.15",
         category="app-cache", risk="review"),
]


# ── Size helpers ─────────────────────────────────────────────────────────────

def dir_size(path: Path) -> int:
    total = 0
    try:
        for entry in path.rglob("*"):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat().st_size
            except OSError:
                pass
    except OSError:
        pass
    return total


def path_size(path: Path) -> int:
    if not path.exists():
        return -1
    if path.is_dir():
        return dir_size(path)
    try:
        return path.stat().st_size
    except OSError:
        return -1


def human_size(b: int) -> str:
    if b < 0:
        return "not found"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(b) < 1024.0:
            return f"{b:.1f} {unit}"
        b /= 1024.0
    return f"{b:.1f} PB"


# ── singine command helpers ──────────────────────────────────────────────────

def singine_cmd(abs_path: str) -> str:
    return f'singine runtime exec-external bin/scan delete --path "{abs_path}"'


def shell_cmd(abs_path: str) -> str:
    if platform.system() == "Windows":
        return f"powershell.exe -Command \"Remove-Item -Recurse -Force '{abs_path}'\""
    return f"rm -rf {abs_path!r}"


def win_cmd(abs_path: str) -> str:
    return f"Remove-Item -Recurse -Force '{abs_path}'"


# ── Disk result set ──────────────────────────────────────────────────────────

def collect_disk(home_dir: Path) -> dict[str, Any]:
    is_win = platform.system() == "Windows"
    items = []
    total_reclaimable = 0

    for t in _TARGETS:
        rel = t["win"] if is_win else t["posix"]
        abs_path = home_dir / rel
        size = path_size(abs_path)
        home_rel = "~/" + rel.replace("\\", "/")
        item: dict[str, Any] = {
            "id":          t["id"],
            "label":       t["label"],
            "path":        home_rel,
            "abs_path":    str(abs_path),
            "size_bytes":  size,
            "size_human":  human_size(size),
            "category":    t["category"],
            "risk":        t["risk"],
            "singine_cmd": singine_cmd(str(abs_path)),
            "shell_cmd":   shell_cmd(str(abs_path)),
            "win_cmd":     win_cmd(str(abs_path)),
            "notes":       t.get("notes", ""),
        }
        items.append(item)
        if size > 0 and t["risk"] in ("safe", "review"):
            total_reclaimable += size

    items.sort(key=lambda x: x["size_bytes"], reverse=True)

    return {
        "scanned_at":               datetime.now(timezone.utc).isoformat(),
        "os":                       platform.system().lower(),
        "home_dir":                 str(home_dir),
        "items":                    items,
        "total_reclaimable_bytes":  total_reclaimable,
        "total_reclaimable_human":  human_size(total_reclaimable),
    }


# ── Governance result set ─────────────────────────────────────────────────────

_GOV_RULES_SOURCE = LOGSEQ_PROJ / "src" / "governance" / "rules.ts"
_SCHEMA_SOURCE    = LOGSEQ_PROJ / "src" / "db" / "migrations" / "001_init.sql"


def _parse_governance_rules_ts() -> list[dict[str, str]]:
    """Extract GOV rule IDs and titles from rules.ts without requiring Node."""
    rules = []
    try:
        text = _GOV_RULES_SOURCE.read_text(encoding="utf-8")
        import re
        blocks = re.findall(
            r"\{\s*id:\s*'(GOV-\d+)'.*?title:\s*'([^']+)'.*?applies:\s*'([^']+)'.*?rule:\s*'([^']+)'",
            text, re.DOTALL
        )
        for gid, title, applies, rule in blocks:
            rules.append({"id": gid, "title": title, "applies": applies.strip(),
                          "rule": rule.strip()})
    except Exception:
        pass
    return rules


def collect_governance(db_path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "db_path":      str(db_path),
        "db_state":     "not_initialized",
        "rules":        _parse_governance_rules_ts(),
        "tables":       {},
        "summary":      {},
    }

    if not db_path.exists():
        result["note"] = (
            "Database not yet seeded. Run: "
            "cd gh/sync-logseq && npm install && tsx src/cli/index.ts seed"
        )
        return result

    result["db_state"] = "initialized"
    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        def count(table: str) -> int:
            return cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        def rows(table: str, limit: int = 50) -> list[dict]:
            cur.execute(f"SELECT * FROM {table} ORDER BY created_at DESC LIMIT ?", (limit,))
            return [dict(r) for r in cur.fetchall()]

        result["summary"] = {
            "questions":   count("questions"),
            "responses":   count("responses"),
            "executions":  count("executions"),
            "audit_log":   count("audit_log"),
            "human_tasks": count("human_tasks"),
            "logseq_sync": count("logseq_sync"),
        }

        # Recent/open items for committee review
        result["tables"] = {
            "human_tasks_open": rows("human_tasks") if result["summary"]["human_tasks"] else [],
            "executions_failed": [
                r for r in rows("executions", 100)
                if r.get("status") in ("failed", "awaiting_human")
            ],
            "audit_recent": rows("audit_log", 20),
        }
        con.close()
    except Exception as exc:
        result["db_error"] = str(exc)

    return result


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Collect committee result sets")
    parser.add_argument("--home",       default="", help="Home directory")
    parser.add_argument("--logseq-db",  default=str(DEFAULT_DB), help="Path to sync-logseq SQLite DB")
    parser.add_argument("--out",        default="", help="Output JSON path")
    parser.add_argument("--pretty",     action="store_true", default=True)
    args = parser.parse_args()

    home = Path(args.home) if args.home else Path.home()
    db   = Path(args.logseq_db)

    print("collecting disk result set...",   file=sys.stderr)
    disk = collect_disk(home)

    print("collecting governance result set...", file=sys.stderr)
    gov  = collect_governance(db)

    payload = {
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "generator":      "cleanup/collect.py",
        "result_sets": {
            "disk":       disk,
            "governance": gov,
        },
    }

    out_path = Path(args.out) if args.out else REPORT_DIR / "committee-results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    indent = 2 if args.pretty else None
    out_path.write_text(json.dumps(payload, indent=indent, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    print(f"written: {out_path}", file=sys.stderr)

    # Print a brief summary to stdout
    total = disk["total_reclaimable_human"]
    gov_state = gov["db_state"]
    gov_rules = len(gov.get("rules", []))
    print(json.dumps({
        "ok": True,
        "disk_total_reclaimable": total,
        "disk_items": len(disk["items"]),
        "governance_db": gov_state,
        "governance_rules": gov_rules,
        "output": str(out_path),
    }, indent=2))


if __name__ == "__main__":
    main()
