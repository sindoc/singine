"""singine query — multi-backend query dispatcher.

API version: 1.0

Each backend accepts a positional ``query`` argument and emits a JSON
envelope of the form::

    {
      "ok": true,
      "api_version": "1.0",
      "backend": "<backend>",
      "query": "<query text>",
      "ts": "<ISO-8601 UTC>",
      "result": { ... }
    }

Backends
--------
git      ``git log``/``show``/``status``/``diff``/``files`` via subprocess
emacs    ``emacsclient --eval`` over a running Emacs daemon
logseq   Logseq HTTP API ``q`` action
xml      XPath search over local XML files
sql      Raw SQL against a SQLite database
sparql   SPARQL over the bridge SQLite DB (delegates to cortex_bridge)
graphql  GraphQL over the bridge SQLite DB (delegates to cortex_bridge)
docker   ``docker ps``/``inspect``/``images``/``logs`` via subprocess
sys      ``<sys-request>`` / ``<sys-response>`` XML envelope for system state
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from . import cortex_bridge

QUERY_API_VERSION = "1.0"

# ── Shared helpers ─────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _envelope(ok: bool, backend: str, query: str, **kwargs: Any) -> Dict[str, Any]:
    return {
        "ok": ok,
        "api_version": QUERY_API_VERSION,
        "backend": backend,
        "query": query,
        "ts": _now_iso(),
        **kwargs,
    }


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2))


# ── git ────────────────────────────────────────────────────────────────────────


def _run_git(action: str, query: str, repo: str, limit: int) -> Dict[str, Any]:
    repo_path = Path(repo).expanduser().resolve()
    base = ["git", "-C", str(repo_path)]
    if action == "log":
        cmd = base + ["log", "--oneline", "--no-decorate", f"-n{limit}", f"--grep={query}"]
    elif action == "show":
        cmd = base + ["show", "--stat", query]
    elif action == "status":
        cmd = base + ["status", "--short"]
    elif action == "diff":
        cmd = base + ["diff", "--stat", query or "HEAD"]
    elif action == "files":
        cmd = base + ["ls-files", "--cached", "--others", "--exclude-standard"]
        if query:
            cmd.append(query)
    else:
        return {"error": f"unknown action: {action}"}

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        lines = proc.stdout.splitlines()
        return {
            "action": action,
            "repo": str(repo_path),
            "lines": lines,
            "count": len(lines),
            "returncode": proc.returncode,
        }
    except FileNotFoundError:
        return {"error": "git not found in PATH"}
    except subprocess.TimeoutExpired:
        return {"error": "git command timed out"}


def cmd_query_git(args: argparse.Namespace) -> int:
    result = _run_git(args.action, args.query, args.repo, args.limit)
    ok = "error" not in result
    _print_json(_envelope(ok=ok, backend="git", query=args.query, result=result))
    return 0 if ok else 1


# ── emacs ──────────────────────────────────────────────────────────────────────


def _run_emacs(expr: str, bin_path: str, socket: Optional[str]) -> Dict[str, Any]:
    cmd = [bin_path, "--eval", expr, "--no-wait"]
    if socket:
        cmd = [bin_path, "--socket-name", socket, "--eval", expr, "--no-wait"]
    # Drop --no-wait for eval so we get the return value
    cmd = [bin_path]
    if socket:
        cmd += ["--socket-name", socket]
    cmd += ["--eval", expr]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return {
            "expr": expr,
            "output": proc.stdout.strip(),
            "returncode": proc.returncode,
        }
    except FileNotFoundError:
        return {"error": f"emacsclient not found: {bin_path}"}
    except subprocess.TimeoutExpired:
        return {"error": "emacsclient timed out — is an Emacs daemon running?"}


def cmd_query_emacs(args: argparse.Namespace) -> int:
    result = _run_emacs(args.query, args.bin, getattr(args, "socket", None))
    ok = "error" not in result
    _print_json(_envelope(ok=ok, backend="emacs", query=args.query, result=result))
    return 0 if ok else 1


# ── logseq ─────────────────────────────────────────────────────────────────────


def _run_logseq(q_expr: str, base_url: str, token: str, timeout: int) -> Dict[str, Any]:
    from urllib.error import URLError

    url = base_url.rstrip("/") + "/api"
    body = json.dumps({"method": "logseq.db.q", "args": [q_expr]}).encode("utf-8")
    req = Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {"q": q_expr, "data": data}
    except URLError as exc:
        return {"error": str(exc), "q": q_expr}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "q": q_expr}


def cmd_query_logseq(args: argparse.Namespace) -> int:
    result = _run_logseq(args.query, args.base_url, args.token, args.timeout)
    ok = "error" not in result
    _print_json(_envelope(ok=ok, backend="logseq", query=args.query, result=result))
    return 0 if ok else 1


# ── xml ────────────────────────────────────────────────────────────────────────


def _run_xml(xpath: str, path: str, glob: str) -> Dict[str, Any]:
    search_root = Path(path).expanduser()
    if search_root.is_file():
        files = [search_root]
    else:
        files = list(search_root.glob(glob))

    matches: List[Dict[str, Any]] = []
    errors: List[str] = []
    for f in sorted(files):
        try:
            tree = ET.parse(str(f))
            for elem in tree.findall(xpath):
                matches.append({
                    "file": str(f),
                    "tag": elem.tag,
                    "attrib": dict(elem.attrib),
                    "text": (elem.text or "").strip() or None,
                })
        except ET.ParseError as exc:
            errors.append(f"{f}: {exc}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{f}: {exc}")

    result: Dict[str, Any] = {
        "xpath": xpath,
        "files_scanned": len(files),
        "match_count": len(matches),
        "matches": matches,
    }
    if errors:
        result["errors"] = errors
    return result


def cmd_query_xml(args: argparse.Namespace) -> int:
    result = _run_xml(args.query, args.path, args.glob)
    ok = "error" not in result
    _print_json(_envelope(ok=ok, backend="xml", query=args.query, result=result))
    return 0


# ── sql ────────────────────────────────────────────────────────────────────────


def _run_sql(statement: str, db_path: str) -> Dict[str, Any]:
    import sqlite3

    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        try:
            cur = con.execute(statement)
            rows = [dict(r) for r in cur.fetchall()]
            return {"statement": statement, "rows": rows, "count": len(rows)}
        finally:
            con.close()
    except sqlite3.Error as exc:
        return {"error": str(exc), "statement": statement}


def cmd_query_sql(args: argparse.Namespace) -> int:
    result = _run_sql(args.query, args.db)
    ok = "error" not in result
    _print_json(_envelope(ok=ok, backend="sql", query=args.query, result=result))
    return 0 if ok else 1


# ── sparql ─────────────────────────────────────────────────────────────────────


def cmd_query_sparql(args: argparse.Namespace) -> int:
    db = Path(args.db).expanduser()
    try:
        bridge = cortex_bridge.BridgeDB(db)
        data = bridge.sparql(args.query)
    except Exception as exc:  # noqa: BLE001
        data = {"error": str(exc)}
    ok = "error" not in data
    _print_json(_envelope(ok=ok, backend="sparql", query=args.query, result=data))
    return 0 if ok else 1


# ── graphql ────────────────────────────────────────────────────────────────────


def cmd_query_graphql(args: argparse.Namespace) -> int:
    db = Path(args.db).expanduser()
    try:
        bridge = cortex_bridge.BridgeDB(db)
        data = bridge.graphql(args.query)
    except Exception as exc:  # noqa: BLE001
        data = {"error": str(exc)}
    ok = "error" not in data
    _print_json(_envelope(ok=ok, backend="graphql", query=args.query, result=data))
    return 0 if ok else 1


# ── docker ─────────────────────────────────────────────────────────────────────


def _run_docker(action: str, query: str, fmt: str) -> Dict[str, Any]:
    if action == "ps":
        cmd = ["docker", "ps", "--format", "{{json .}}"]
    elif action == "images":
        cmd = ["docker", "images", "--format", "{{json .}}"]
    elif action == "inspect":
        if not query:
            return {"error": "inspect requires a container/image name as query"}
        cmd = ["docker", "inspect", query]
    elif action == "logs":
        if not query:
            return {"error": "logs requires a container name as query"}
        cmd = ["docker", "logs", "--tail", "50", query]
    else:
        return {"error": f"unknown action: {action}"}

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        raw = proc.stdout.strip()
        # docker ps/images emit one JSON object per line
        if action in {"ps", "images"}:
            rows = []
            for line in raw.splitlines():
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        rows.append({"raw": line})
            return {"action": action, "rows": rows, "count": len(rows), "returncode": proc.returncode}
        # inspect returns a JSON array
        if action == "inspect":
            try:
                items = json.loads(raw) if raw else []
            except json.JSONDecodeError:
                items = [{"raw": raw}]
            return {"action": action, "items": items, "returncode": proc.returncode}
        # logs: plain text lines
        lines = raw.splitlines()
        return {"action": action, "lines": lines, "count": len(lines), "returncode": proc.returncode}
    except FileNotFoundError:
        return {"error": "docker not found in PATH"}
    except subprocess.TimeoutExpired:
        return {"error": "docker command timed out"}


def cmd_query_docker(args: argparse.Namespace) -> int:
    result = _run_docker(args.action, args.query, getattr(args, "format", "json"))
    ok = "error" not in result
    _print_json(_envelope(ok=ok, backend="docker", query=args.query, result=result))
    return 0 if ok else 1


# ── sys ────────────────────────────────────────────────────────────────────────
# The <sys/> protocol models a request/response pair as XML elements.
# Request:  <sys-request id="..." api-version="1.0"><query>...</query></sys-request>
# Response: <sys-response id="..." request-ref="..." api-version="1.0">
#             <platform>...</platform><python>...</python><env>...</env>
#           </sys-response>


def _build_sys_request_xml(req_id: str, query: str) -> ET.Element:
    root = ET.Element("sys-request", {"id": req_id, "api-version": QUERY_API_VERSION})
    q_el = ET.SubElement(root, "query")
    q_el.text = query
    return root


def _build_sys_response_xml(
    resp_id: str, req_id: str, query: str, facts: Dict[str, Any]
) -> ET.Element:
    root = ET.Element(
        "sys-response",
        {"id": resp_id, "request-ref": req_id, "api-version": QUERY_API_VERSION},
    )
    ET.SubElement(root, "query-echo").text = query

    plat_el = ET.SubElement(root, "platform")
    ET.SubElement(plat_el, "system").text = facts.get("system", "")
    ET.SubElement(plat_el, "node").text = facts.get("node", "")
    ET.SubElement(plat_el, "machine").text = facts.get("machine", "")
    ET.SubElement(plat_el, "release").text = facts.get("release", "")

    py_el = ET.SubElement(root, "python")
    ET.SubElement(py_el, "version").text = facts.get("python_version", "")
    ET.SubElement(py_el, "executable").text = facts.get("python_executable", "")

    env_el = ET.SubElement(root, "env")
    for k, v in sorted(facts.get("env_subset", {}).items()):
        e = ET.SubElement(env_el, "var", {"name": k})
        e.text = v

    ET.SubElement(root, "ts").text = facts.get("ts", "")
    return root


def _collect_sys_facts(query: str) -> Dict[str, Any]:
    env_keys = ["SINGINE_CORTEX_DB", "COLLIBRA_EDGE_DIR", "HOME", "SHELL", "TERM"]
    return {
        "system": platform.system(),
        "node": platform.node(),
        "machine": platform.machine(),
        "release": platform.release(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "env_subset": {k: os.environ.get(k, "") for k in env_keys},
        "ts": _now_iso(),
    }


def _write_xml(path: Path, element: ET.Element) -> None:
    ET.indent(element)
    tree = ET.ElementTree(element)
    ET.indent(tree)
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(path), encoding="utf-8", xml_declaration=True)


def cmd_query_sys(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    req_id = str(uuid.uuid4())
    resp_id = str(uuid.uuid4())
    facts = _collect_sys_facts(args.query)

    req_xml = _build_sys_request_xml(req_id, args.query)
    resp_xml = _build_sys_response_xml(resp_id, req_id, args.query, facts)

    req_path = output_dir / "sys.request.xml"
    resp_path = output_dir / "sys.response.xml"
    _write_xml(req_path, req_xml)
    _write_xml(resp_path, resp_xml)

    payload = _envelope(
        ok=True,
        backend="sys",
        query=args.query,
        result={
            "request_id": req_id,
            "response_id": resp_id,
            "request_path": str(req_path),
            "response_path": str(resp_path),
            "facts": facts,
        },
    )
    _print_json(payload)
    return 0


# ── Parser registration ────────────────────────────────────────────────────────


def add_query_backends(query_sub: argparse.ArgumentParser) -> None:
    """Register the multi-backend query subcommands onto an existing query sub-parser.

    Adds: git, emacs, logseq, xml, sql, sparql, graphql, docker, sys.
    The caller (command.py) owns the top-level ``query`` parser and any
    pre-existing subcommands (latest-changes, read-atom).
    """

    # ── git ──────────────────────────────────────────────────────────────────
    git_p = query_sub.add_parser("git", help="Query a git repository (log/show/status/diff/files)")
    git_p.add_argument("query", nargs="?", default="", help="Grep pattern, ref, or path")
    git_p.add_argument("--action", choices=["log", "show", "status", "diff", "files"], default="log")
    git_p.add_argument("--repo", default=".", help="Git repository path (default: cwd)")
    git_p.add_argument("--limit", type=int, default=20, help="Maximum log entries")
    git_p.set_defaults(func=cmd_query_git)

    # ── emacs ─────────────────────────────────────────────────────────────────
    emacs_p = query_sub.add_parser("emacs", help="Eval an Elisp expression via emacsclient")
    emacs_p.add_argument("query", help="Elisp expression to evaluate")
    emacs_p.add_argument("--bin", default="emacsclient", help="emacsclient binary (default: emacsclient)")
    emacs_p.add_argument("--socket", default=None, help="Emacs daemon socket name")
    emacs_p.set_defaults(func=cmd_query_emacs)

    # ── logseq ────────────────────────────────────────────────────────────────
    logseq_p = query_sub.add_parser("logseq", help="Run a Datalog query against the Logseq HTTP API")
    logseq_p.add_argument("query", help="Datalog q-expression, e.g. '[:find ?b :where [?b :block/name]]'")
    logseq_p.add_argument("--base-url", default="http://127.0.0.1:12315", help="Logseq HTTP API base URL")
    logseq_p.add_argument("--token", required=True, help="Logseq API token")
    logseq_p.add_argument("--timeout", type=int, default=10)
    logseq_p.set_defaults(func=cmd_query_logseq)

    # ── xml ───────────────────────────────────────────────────────────────────
    xml_p = query_sub.add_parser("xml", help="XPath search over local XML files")
    xml_p.add_argument("query", help="XPath expression, e.g. './/domain' or './/*[@id]'")
    xml_p.add_argument("--path", required=True, help="File or directory to scan")
    xml_p.add_argument("--glob", default="*.xml", help="Glob pattern when --path is a directory (default: *.xml)")
    xml_p.set_defaults(func=cmd_query_xml)

    # ── sql ───────────────────────────────────────────────────────────────────
    sql_p = query_sub.add_parser("sql", help="Run a SQL statement against the local SQLite bridge DB")
    sql_p.add_argument("query", help="SQL statement")
    sql_p.add_argument("--db", default="/tmp/sqlite.db", help="SQLite database path (default: /tmp/sqlite.db)")
    sql_p.set_defaults(func=cmd_query_sql)

    # ── sparql ────────────────────────────────────────────────────────────────
    sparql_p = query_sub.add_parser("sparql", help="SPARQL over the bridge SQLite DB")
    sparql_p.add_argument("query", help="SPARQL SELECT statement")
    sparql_p.add_argument("--db", default="/tmp/sqlite.db", help="SQLite database path")
    sparql_p.set_defaults(func=cmd_query_sparql)

    # ── graphql ───────────────────────────────────────────────────────────────
    graphql_p = query_sub.add_parser("graphql", help="GraphQL-shaped query over the bridge SQLite DB")
    graphql_p.add_argument("query", help="GraphQL query string")
    graphql_p.add_argument("--db", default="/tmp/sqlite.db", help="SQLite database path")
    graphql_p.set_defaults(func=cmd_query_graphql)

    # ── docker ────────────────────────────────────────────────────────────────
    docker_p = query_sub.add_parser("docker", help="Query docker (ps/images/inspect/logs)")
    docker_p.add_argument("query", nargs="?", default="", help="Container/image name for inspect or logs")
    docker_p.add_argument("--action", choices=["ps", "images", "inspect", "logs"], default="ps")
    docker_p.set_defaults(func=cmd_query_docker)

    # ── sys ───────────────────────────────────────────────────────────────────
    sys_p = query_sub.add_parser(
        "sys",
        help="<sys-request>/<sys-response> XML envelope querying local system state",
    )
    sys_p.add_argument("query", help="Free-text query label embedded in the <sys-request> element")
    sys_p.add_argument(
        "--output-dir",
        default="/tmp/singine-sys-query",
        help="Directory for sys.request.xml and sys.response.xml (default: /tmp/singine-sys-query)",
    )
    sys_p.set_defaults(func=cmd_query_sys)
