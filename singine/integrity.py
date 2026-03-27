"""Workspace integrity checker.

Reads rules from an XML file, evaluates them against a workspace root,
persists results to SQLite, and reports a summary.

CLI entry point: singine check integrity <workspace>
Emacs entry point: M-x singine-check-integrity  (via singine-ws.el)
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional

# ── Default paths ────────────────────────────────────────────────────────────

DEFAULT_RULES_PATH = Path.home() / "ws" / "etc" / "integrity" / "rules.xml"
DEFAULT_DB_PATH    = Path.home() / "ws" / "etc" / "integrity" / "results.db"

# ── Data model ───────────────────────────────────────────────────────────────

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


@dataclass
class RuleResult:
    rule_id: str
    name: str
    severity: str          # error | warning | info
    passed: bool
    details: List[str] = field(default_factory=list)

    @property
    def status_label(self) -> str:
        if self.passed:
            return "PASS"
        return {"error": "FAIL", "warning": "WARN", "info": "INFO"}.get(
            self.severity, "FAIL"
        )


@dataclass
class CheckRun:
    workspace: Path
    rules_path: Path
    timestamp: str
    results: List[RuleResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results if r.severity == "error")

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if not r.passed and r.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.results if not r.passed and r.severity == "warning")


# ── XML rule loader ──────────────────────────────────────────────────────────

@dataclass
class Rule:
    rule_id: str
    severity: str
    name: str
    description: str
    check_el: ET.Element   # the <check> element


def load_rules(rules_path: Path) -> List[Rule]:
    tree = ET.parse(rules_path)
    root = tree.getroot()
    rules: List[Rule] = []
    for el in root.findall("rule"):
        rule_id  = el.get("id", "")
        severity = el.get("severity", "error")
        name     = (el.findtext("name") or "").strip()
        desc     = (el.findtext("description") or "").strip()
        check_el = el.find("check")
        if check_el is None:
            continue
        rules.append(Rule(rule_id, severity, name, desc, check_el))
    return rules


# ── Check implementations ────────────────────────────────────────────────────

def _iter_files(root: Path, exclude_dirs: List[str]) -> Iterator[Path]:
    """Walk root, skipping excluded directory names."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in exclude_dirs and not d.startswith(".")
        ]
        for fname in filenames:
            yield Path(dirpath) / fname


def _glob_match(name: str, patterns: List[str]) -> bool:
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def check_no_pattern_outside_root(
    ws: Path, check_el: ET.Element
) -> tuple[bool, List[str]]:
    allowed_root  = check_el.findtext("root") or ""
    allowed_abs   = (ws / allowed_root).resolve()
    patterns      = [p.text for p in check_el.findall("patterns/pattern") if p.text]
    exclude_dirs  = [d.text for d in check_el.findall("exclude-dirs/dir") if d.text]
    violations: List[str] = []

    for f in _iter_files(ws, exclude_dirs):
        try:
            resolved = f.resolve()
        except Exception:
            continue
        # Skip if inside the allowed root
        try:
            resolved.relative_to(allowed_abs)
            continue
        except ValueError:
            pass
        if _glob_match(f.name, patterns):
            violations.append(str(f.relative_to(ws)))

    return (len(violations) == 0, violations)


def check_path_must_not_exist(
    ws: Path, check_el: ET.Element
) -> tuple[bool, List[str]]:
    path_str = check_el.findtext("path") or ""
    target   = ws / path_str
    if target.exists() or target.is_symlink():
        return (False, [str(target.relative_to(ws))])
    return (True, [])


def check_no_pattern_under(
    ws: Path, check_el: ET.Element
) -> tuple[bool, List[str]]:
    dir_rel  = check_el.findtext("dir") or ""
    root     = ws / dir_rel
    patterns = [p.text for p in check_el.findall("patterns/pattern") if p.text]
    if not root.exists():
        return (True, [])
    violations: List[str] = []
    for f in _iter_files(root, []):
        if _glob_match(f.name, patterns):
            violations.append(str(f.relative_to(ws)))
    return (len(violations) == 0, violations)


def check_symlink_target_under(
    ws: Path, check_el: ET.Element
) -> tuple[bool, List[str]]:
    violations: List[str] = []
    for sl_el in check_el.findall("symlinks/symlink"):
        name     = sl_el.get("name", "")
        expected = sl_el.get("expected-prefix", "")
        link     = ws / name
        if not link.is_symlink():
            # Symlink not present — not a violation (repo may not be cloned yet)
            continue
        target = Path(os.readlink(link))
        if not target.is_absolute():
            target = (ws / target).resolve()
        expected_abs = (ws / expected).resolve()
        try:
            target.relative_to(expected_abs)
        except ValueError:
            violations.append(
                f"{name} -> {os.readlink(link)}  (expected prefix: {expected})"
            )
    return (len(violations) == 0, violations)


def _git_remotes(repo_path: Path) -> List[str]:
    """Return all remote URLs for a git repo, or [] on failure."""
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo_path), "remote", "-v"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        urls: List[str] = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                urls.append(parts[1])
        return list(set(urls))
    except Exception:
        return []


def _find_git_repos(root: Path, depth: int = 3) -> Iterator[Path]:
    """Yield directories containing a .git, up to depth levels deep."""
    if depth < 0:
        return
    if not root.is_dir():
        return
    git_dir = root / ".git"
    if git_dir.exists():
        yield root
        return  # don't recurse inside a repo
    for child in root.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            yield from _find_git_repos(child, depth - 1)


def check_no_sindoc_origin_under(
    ws: Path, check_el: ET.Element
) -> tuple[bool, List[str]]:
    violations: List[str] = []
    for dir_el in check_el.findall("dirs/dir"):
        dir_rel = dir_el.text or ""
        root    = ws / dir_rel
        for repo in _find_git_repos(root):
            for url in _git_remotes(repo):
                if "sindoc" in url:
                    violations.append(
                        f"{repo.relative_to(ws)}  remote: {url}"
                    )
    return (len(violations) == 0, violations)


def check_no_remote_matching_under(
    ws: Path, check_el: ET.Element
) -> tuple[bool, List[str]]:
    dir_rel  = check_el.findtext("dir") or ""
    pattern  = check_el.findtext("forbidden-pattern") or ""
    root     = ws / dir_rel
    violations: List[str] = []
    for repo in _find_git_repos(root):
        for url in _git_remotes(repo):
            if pattern in url:
                violations.append(
                    f"{repo.relative_to(ws)}  remote: {url}"
                )
    return (len(violations) == 0, violations)


def check_no_git_repos_under(
    ws: Path, check_el: ET.Element
) -> tuple[bool, List[str]]:
    dir_rel  = check_el.findtext("dir") or ""
    root     = ws / dir_rel
    if not root.exists():
        return (True, [])
    violations: List[str] = []
    for child in root.iterdir():
        if child.is_dir() and (child / ".git").exists():
            violations.append(str(child.relative_to(ws)))
    return (len(violations) == 0, violations)


# ── Dispatcher ───────────────────────────────────────────────────────────────

_CHECKS = {
    "no-pattern-outside-root": check_no_pattern_outside_root,
    "path-must-not-exist":     check_path_must_not_exist,
    "no-pattern-under":        check_no_pattern_under,
    "symlink-target-under":    check_symlink_target_under,
    "no-sindoc-origin-under":  check_no_sindoc_origin_under,
    "no-remote-matching-under": check_no_remote_matching_under,
    "no-git-repos-under":      check_no_git_repos_under,
}


def evaluate(ws: Path, rules: List[Rule]) -> List[RuleResult]:
    results: List[RuleResult] = []
    for rule in rules:
        check_type = rule.check_el.get("type", "")
        fn = _CHECKS.get(check_type)
        if fn is None:
            results.append(RuleResult(
                rule.rule_id, rule.name, rule.severity, False,
                [f"Unknown check type: {check_type}"]
            ))
            continue
        try:
            passed, details = fn(ws, rule.check_el)
        except Exception as exc:
            passed, details = False, [f"Check raised an exception: {exc}"]
        results.append(RuleResult(rule.rule_id, rule.name, rule.severity, passed, details))
    return results


# ── SQLite persistence ───────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS run (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    workspace TEXT NOT NULL,
    rules_path TEXT NOT NULL,
    passed    INTEGER NOT NULL,
    error_count   INTEGER NOT NULL,
    warning_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS rule_result (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id    INTEGER NOT NULL REFERENCES run(id),
    rule_id   TEXT NOT NULL,
    name      TEXT NOT NULL,
    severity  TEXT NOT NULL,
    passed    INTEGER NOT NULL,
    details   TEXT NOT NULL
);
"""


def persist(run: CheckRun, db_path: Path) -> int:
    """Write run results to SQLite.  Returns the new run id."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(_SCHEMA)
    cur = con.execute(
        "INSERT INTO run (timestamp, workspace, rules_path, passed, error_count, warning_count) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            run.timestamp,
            str(run.workspace),
            str(run.rules_path),
            int(run.passed),
            run.error_count,
            run.warning_count,
        ),
    )
    run_id = cur.lastrowid
    for r in run.results:
        con.execute(
            "INSERT INTO rule_result (run_id, rule_id, name, severity, passed, details) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, r.rule_id, r.name, r.severity, int(r.passed), json.dumps(r.details)),
        )
    con.commit()
    con.close()
    return run_id


def load_last_run(db_path: Path) -> Optional[dict]:
    """Return the most recent run summary from SQLite as a dict, or None."""
    if not db_path.exists():
        return None
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT * FROM run ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        con.close()
        return None
    run_id = row["id"]
    results = con.execute(
        "SELECT * FROM rule_result WHERE run_id = ?", (run_id,)
    ).fetchall()
    con.close()
    return {
        "run": dict(row),
        "results": [dict(r) for r in results],
    }


# ── Reporting ────────────────────────────────────────────────────────────────

_SEVERITY_ICON = {"error": "✗", "warning": "△", "info": "ℹ"}
_PASS_ICON = "✓"


def print_report(run: CheckRun) -> None:
    col_id   = max(len(r.rule_id) for r in run.results) if run.results else 8
    col_name = max(len(r.name) for r in run.results) if run.results else 20
    col_id   = max(col_id, 7)
    col_name = max(col_name, 20)

    header = f"{'Rule':<{col_id}}  {'Name':<{col_name}}  {'Sev':<7}  Status"
    print(header)
    print("-" * len(header))

    for r in run.results:
        icon = _PASS_ICON if r.passed else _SEVERITY_ICON.get(r.severity, "?")
        line = f"{r.rule_id:<{col_id}}  {r.name:<{col_name}}  {r.severity:<7}  {icon} {r.status_label}"
        print(line)
        if not r.passed and r.details:
            for d in r.details[:5]:
                print(f"{'':>{col_id + 2}}  {d}")
            if len(r.details) > 5:
                print(f"{'':>{col_id + 2}}  ... and {len(r.details) - 5} more")

    print()
    status = "CLEAN" if run.passed else "VIOLATIONS FOUND"
    print(
        f"Workspace : {run.workspace}\n"
        f"Rules     : {run.rules_path}\n"
        f"Timestamp : {run.timestamp}\n"
        f"Result    : {status}  "
        f"(errors: {run.error_count}, warnings: {run.warning_count})"
    )


# ── Public entry point ───────────────────────────────────────────────────────

def run_check(
    workspace: Path,
    rules_path: Optional[Path] = None,
    db_path: Optional[Path] = None,
    output_json: bool = False,
    show_last: bool = False,
) -> int:
    """Run integrity checks.  Returns 0 if all error-level rules pass, 1 otherwise."""
    rules_path = rules_path or DEFAULT_RULES_PATH
    db_path    = db_path    or DEFAULT_DB_PATH
    workspace  = workspace.expanduser().resolve()

    if show_last:
        data = load_last_run(db_path)
        if data is None:
            print("No previous run found in", db_path, file=sys.stderr)
            return 1
        print(json.dumps(data, indent=2))
        return 0

    if not rules_path.exists():
        print(f"Rules file not found: {rules_path}", file=sys.stderr)
        return 1

    rules   = load_rules(rules_path)
    results = evaluate(workspace, rules)
    ts      = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    check_run = CheckRun(workspace, rules_path, ts, results)

    persist(check_run, db_path)

    if output_json:
        out = {
            "timestamp": ts,
            "workspace": str(workspace),
            "passed": check_run.passed,
            "error_count": check_run.error_count,
            "warning_count": check_run.warning_count,
            "results": [
                {
                    "rule_id":  r.rule_id,
                    "name":     r.name,
                    "severity": r.severity,
                    "passed":   r.passed,
                    "details":  r.details,
                }
                for r in results
            ],
        }
        print(json.dumps(out, indent=2))
    else:
        print_report(check_run)

    return 0 if check_run.passed else 1
