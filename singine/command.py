"""Stable Singine command entrypoint.

This module intentionally avoids importing the older Python CLI surface at module
load time. It provides the data bridge, environment/context reporting, manpage
access, and a POSIX-friendly install flow.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PREFIX = Path.home() / ".local"
DEFAULT_GLOSSARY_ROOT = Path("/Users/skh/ws/today/00-WORK/morning_glossary_package")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_glossary_term(ttl_text: str, concept_name: str) -> Dict[str, str]:
    marker = f"ex:{concept_name} a skos:Concept ;"
    start = ttl_text.find(marker)
    if start == -1:
        return {}
    end = ttl_text.find("\n\n", start)
    block = ttl_text[start:end if end != -1 else None]
    result: Dict[str, str] = {}
    for key, label in [
        ("prefLabel", "label"),
        ("altLabel", "alt_label"),
        ("definition", "definition"),
        ("example", "example"),
    ]:
        token = f"skos:{key} "
        pos = block.find(token)
        if pos == -1:
            continue
        rest = block[pos + len(token):]
        quote_start = rest.find('"')
        quote_end = rest.find('"@en')
        if quote_start != -1 and quote_end != -1:
            result[label] = rest[quote_start + 1:quote_end]
    return result


def load_environment_glossary(glossary_root: Path) -> Dict[str, Any]:
    ttl_path = glossary_root / "glossary.skos.ttl"
    if not ttl_path.exists():
        return {"glossary_root": str(glossary_root), "available": False}
    ttl_text = _read_text(ttl_path)
    return {
        "glossary_root": str(glossary_root),
        "available": True,
        "terminal_context": _extract_glossary_term(ttl_text, "terminal-context"),
        "sourced_environment": _extract_glossary_term(ttl_text, "sourced-environment"),
    }


def terminal_context(shell_name: Optional[str] = None) -> Dict[str, Any]:
    env = os.environ
    shell = shell_name or Path(env.get("SHELL", "sh")).name
    path_entries = env.get("PATH", "").split(os.pathsep) if env.get("PATH") else []
    return {
        "shell": shell,
        "cwd": os.getcwd(),
        "user": env.get("USER") or env.get("LOGNAME"),
        "home": env.get("HOME"),
        "path_entries": path_entries,
        "python_executable": sys.executable,
        "virtual_env": env.get("VIRTUAL_ENV"),
        "bash_env": env.get("BASH_ENV"),
        "env_file": env.get("ENV"),
        "singine_env": env.get("SINGINE_ENV"),
        "singine_cortex_db": env.get("SINGINE_CORTEX_DB"),
    }


def sourced_environment() -> Dict[str, Any]:
    env = os.environ
    shell = Path(env.get("SHELL", "sh")).name
    if shell == "bash":
        rc_files = [".bash_profile", ".bash_login", ".profile", ".bashrc"]
    else:
        rc_files = [".profile"]
    existing = [str(Path.home() / rc) for rc in rc_files if (Path.home() / rc).exists()]
    return {
        "shell": shell,
        "startup_files_present": existing,
        "sourced_markers": {
            "BASH_ENV": env.get("BASH_ENV"),
            "ENV": env.get("ENV"),
        },
        "meta_root_candidates": [
            str(REPO_ROOT / ".meta"),
            str(Path.home() / ".meta"),
        ],
    }


def man_dir() -> Path:
    return REPO_ROOT / "man"


def installed_man_path(prefix: Path) -> Path:
    return prefix / "share" / "man" / "man1"


def launcher_script(repo_root: Path) -> str:
    return f"""#!/bin/sh
REPO_ROOT="{repo_root}"
if [ -n "$PYTHONPATH" ]; then
  PYTHONPATH="$REPO_ROOT:$PYTHONPATH"
else
  PYTHONPATH="$REPO_ROOT"
fi
export PYTHONPATH
exec python3 -m singine.command "$@"
"""


def install_manpages(prefix: Path) -> None:
    target = installed_man_path(prefix)
    target.mkdir(parents=True, exist_ok=True)
    for source in sorted(man_dir().glob("*.1")):
        shutil.copy2(source, target / source.name)


def install_launcher(prefix: Path) -> Path:
    bin_dir = prefix / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    target = bin_dir / "singine"
    target.write_text(launcher_script(REPO_ROOT), encoding="utf-8")
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return target


def shell_init_file(shell_name: str) -> Path:
    home = Path.home()
    if shell_name == "bash":
        return home / ".bashrc"
    return home / ".profile"


def ensure_shell_path(prefix: Path, shell_name: str) -> Path:
    rc = shell_init_file(shell_name)
    bin_line = f'export PATH="{prefix / "bin"}:$PATH"'
    man_line = f'export MANPATH="{prefix / "share" / "man"}:${{MANPATH:-}}"'
    payload = f"\n# singine\n{bin_line}\n{man_line}\n"
    if rc.exists():
        text = _read_text(rc)
        if bin_line in text and man_line in text:
            return rc
    with rc.open("a", encoding="utf-8") as handle:
        handle.write(payload)
    return rc


def ensure_shell_paths(prefix: Path, shell_name: str) -> Dict[str, str]:
    shells = ["bash", "sh"] if shell_name == "all" else [shell_name]
    updated: Dict[str, str] = {}
    for item in shells:
        updated[item] = str(ensure_shell_path(prefix, item))
    return updated


def install_ant_tool(json_output: bool = False) -> int:
    existing = shutil.which("ant")
    if existing:
        payload = {"ok": True, "tool": "ant", "installed": False, "path": existing}
        if json_output:
            print_json(payload)
        else:
            print(f"ant already installed: {existing}")
        return 0

    brew = shutil.which("brew")
    if not brew:
        payload = {
            "ok": False,
            "tool": "ant",
            "installed": False,
            "error": "Homebrew is not available on PATH; cannot install ant automatically.",
        }
        if json_output:
            print_json(payload)
        else:
            print(payload["error"], file=sys.stderr)
        return 1

    proc = subprocess.run([brew, "install", "ant"], capture_output=True, text=True, timeout=1800)
    payload = {
        "ok": proc.returncode == 0,
        "tool": "ant",
        "installed": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "path": shutil.which("ant"),
    }
    if json_output:
        print_json(payload)
    else:
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)
        if payload["ok"] and payload["path"]:
            print(f"ant installed: {payload['path']}")
    return 0 if payload["ok"] else 1


def install_xmldoclet_tool(json_output: bool = False) -> int:
    existing = sorted((Path.home() / ".m2").glob("repository/com/saxonica/xmldoclet/*/xmldoclet-*.jar"))
    if existing:
        payload = {
            "ok": True,
            "tool": "xmldoclet",
            "installed": False,
            "path": str(existing[-1]),
        }
        if json_output:
            print_json(payload)
        else:
            print(f"xmldoclet already installed: {payload['path']}")
        return 0

    mvn = shutil.which("mvn")
    if not mvn:
        brew = shutil.which("brew")
        if not brew:
            payload = {
                "ok": False,
                "tool": "xmldoclet",
                "installed": False,
                "error": "Maven is not available on PATH and Homebrew is not available to install it.",
            }
            if json_output:
                print_json(payload)
            else:
                print(payload["error"], file=sys.stderr)
            return 1

        mvn_install = subprocess.run([brew, "install", "maven"], capture_output=True, text=True, timeout=1800)
        if mvn_install.returncode != 0:
            payload = {
                "ok": False,
                "tool": "xmldoclet",
                "installed": False,
                "error": "Failed to install Maven with Homebrew.",
                "stdout": mvn_install.stdout,
                "stderr": mvn_install.stderr,
            }
            if json_output:
                print_json(payload)
            else:
                if mvn_install.stdout:
                    print(mvn_install.stdout, end="")
                if mvn_install.stderr:
                    print(mvn_install.stderr, end="", file=sys.stderr)
            return 1
        mvn = shutil.which("mvn")

    proc = subprocess.run(
        [
            mvn,
            "dependency:get",
            "-Dartifact=com.saxonica:xmldoclet:LATEST",
            "-Dtransitive=true",
        ],
        capture_output=True,
        text=True,
        timeout=1800,
    )
    existing = sorted((Path.home() / ".m2").glob("repository/com/saxonica/xmldoclet/*/xmldoclet-*.jar"))
    payload = {
        "ok": proc.returncode == 0 and bool(existing),
        "tool": "xmldoclet",
        "installed": proc.returncode == 0,
        "path": str(existing[-1]) if existing else None,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "artifact": "com.saxonica:xmldoclet:LATEST",
    }
    if json_output:
        print_json(payload)
    else:
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)
        if payload["ok"] and payload["path"]:
            print(f"xmldoclet installed: {payload['path']}")
    return 0 if payload["ok"] else 1


def install_git_filter_repo_tool(json_output: bool = False) -> int:
    existing = shutil.which("git-filter-repo")
    if existing:
        payload = {"ok": True, "tool": "git-filter-repo", "installed": False, "path": existing}
        if json_output:
            print_json(payload)
        else:
            print(f"git-filter-repo already installed: {existing}")
        return 0

    brew = shutil.which("brew")
    if not brew:
        payload = {
            "ok": False,
            "tool": "git-filter-repo",
            "installed": False,
            "error": "Homebrew is not available on PATH; cannot install git-filter-repo automatically.",
        }
        if json_output:
            print_json(payload)
        else:
            print(payload["error"], file=sys.stderr)
        return 1

    proc = subprocess.run([brew, "install", "git-filter-repo"], capture_output=True, text=True, timeout=1800)
    payload = {
        "ok": proc.returncode == 0,
        "tool": "git-filter-repo",
        "installed": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "path": shutil.which("git-filter-repo"),
    }
    if json_output:
        print_json(payload)
    else:
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)
        if payload["ok"] and payload["path"]:
            print(f"git-filter-repo installed: {payload['path']}")
    return 0 if payload["ok"] else 1


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2))


def run_capture(cmd: List[str]) -> Dict[str, Any]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except Exception as exc:
        return {
            "ok": False,
            "exit_code": None,
            "stdout": "",
            "stderr": str(exc),
        }


def _git_capture(args: Sequence[str], *, cwd: Path, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
        timeout=timeout,
    )


def _normalize_public_dir(raw_path: str) -> str:
    value = raw_path.strip().replace("\\", "/").strip("/")
    if not value:
        raise ValueError("public directory path must not be empty")
    if raw_path.startswith("/"):
        raise ValueError("public directory path must be relative, not absolute")
    parts = [part for part in value.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise ValueError("public directory path must not contain '.' or '..'")
    return "/".join(parts)


def _remote_aliases(remote_url: str, repo_root: Path) -> List[str]:
    aliases: List[str] = []
    cleaned = (remote_url or "").strip()
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    if "github.com:" in cleaned:
        cleaned = cleaned.split("github.com:", 1)[1]
    elif "github.com/" in cleaned:
        cleaned = cleaned.split("github.com/", 1)[1]
    cleaned = cleaned.strip("/")
    if cleaned:
        aliases.extend([
            f"github/{cleaned}",
            cleaned,
            cleaned.split("/")[-1],
        ])
    repo_name = repo_root.name
    if repo_name not in aliases:
        aliases.append(repo_name)
    short_alias = f"github/{repo_name}"
    if short_alias not in aliases:
        aliases.append(short_alias)
    seen: List[str] = []
    for alias in aliases:
        if alias not in seen:
            seen.append(alias)
    return seen


def _render_shell_lines(commands: List[List[str]]) -> List[str]:
    return [shlex.join(cmd) for cmd in commands]


def _list_local_branches(repo_root: Path) -> List[str]:
    result = _git_capture(["for-each-ref", "--format=%(refname:short)", "refs/heads"], cwd=repo_root, check=False)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _branch_contains_path(repo_root: Path, branch: str, pathspec: str) -> bool:
    result = _git_capture(["rev-list", "-n", "1", branch, "--", pathspec], cwd=repo_root, check=False)
    return result.returncode == 0 and bool(result.stdout.strip())


def _plan_git_rm_public_dir(args: argparse.Namespace) -> Dict[str, Any]:
    repo_dir = Path(args.repo_dir).expanduser().resolve()
    git_bin = shutil.which("git")
    filter_repo_bin = shutil.which("git-filter-repo")
    normalized_dir = _normalize_public_dir(args.public_dir)
    dir_with_slash = f"{normalized_dir}/"
    requested_branches = list(dict.fromkeys(args.branch or []))

    payload: Dict[str, Any] = {
        "ok": True,
        "repo": args.repo,
        "repo_dir": str(repo_dir),
        "remote": args.remote,
        "public_dir": normalized_dir,
        "public_dir_filter": dir_with_slash,
        "branches": [],
        "refs": [],
        "all_branches": bool(getattr(args, "all_branches", False)),
        "git_available": bool(git_bin),
        "filter_repo_available": bool(filter_repo_bin),
        "warnings": [],
    }

    if not git_bin:
        payload["ok"] = False
        payload["warnings"].append("git is not on PATH")
        return payload

    top = _git_capture(["rev-parse", "--show-toplevel"], cwd=repo_dir, check=False)
    if top.returncode != 0:
        payload["ok"] = False
        payload["warnings"].append("repo-dir is not inside a git worktree")
        payload["git_stderr"] = top.stderr.strip()
        return payload

    repo_root = Path(top.stdout.strip())
    payload["repo_root"] = str(repo_root)

    remote_result = _git_capture(["remote", "get-url", args.remote], cwd=repo_root, check=False)
    remote_url = remote_result.stdout.strip() if remote_result.returncode == 0 else ""
    payload["remote_url"] = remote_url
    aliases = _remote_aliases(remote_url, repo_root)
    payload["repo_aliases"] = aliases
    payload["repo_matches_current_repo"] = args.repo in aliases
    if not payload["repo_matches_current_repo"]:
        payload["warnings"].append(
            f"requested repo '{args.repo}' does not match detected aliases {aliases}"
        )

    auto_branches: List[str] = []
    if getattr(args, "all_branches", False):
        local_branches = _list_local_branches(repo_root)
        auto_branches = [branch for branch in local_branches if _branch_contains_path(repo_root, branch, dir_with_slash)]
        payload["all_branch_scan"] = {
            "scope": "local-heads",
            "scanned": local_branches,
            "matched": auto_branches,
        }
        payload["warnings"].append(
            "all-branch discovery only scans local heads; fetch any missing branches before rewriting"
        )

    branches = list(dict.fromkeys(requested_branches + auto_branches))
    if not branches:
        if getattr(args, "all_branches", False):
            raise ValueError(f"no local branches contain '{dir_with_slash}'")
        raise ValueError("at least one --branch is required unless you pass -all")
    payload["branches"] = branches
    payload["refs"] = [f"refs/heads/{branch}" for branch in branches]

    branch_status: List[Dict[str, Any]] = []
    for branch in branches:
        ref = f"refs/heads/{branch}"
        show_ref = _git_capture(["show-ref", "--verify", ref], cwd=repo_root, check=False)
        branch_status.append({
            "branch": branch,
            "ref": ref,
            "exists_locally": show_ref.returncode == 0,
        })
        if show_ref.returncode != 0:
            payload["warnings"].append(f"branch '{branch}' is not present locally under {ref}")
    payload["branch_status"] = branch_status

    rewrite_commands = [
        shlex.join(["git", "filter-repo", "--path", dir_with_slash, "--invert-paths", "--refs", *payload["refs"]]),
        "git for-each-ref --format='delete %(refname)' refs/original | git update-ref --stdin",
        shlex.join(["git", "reflog", "expire", "--expire=now", "--all"]),
        shlex.join(["git", "gc", "--prune=now"]),
    ]
    push_commands = [
        ["git", "push", "--force-with-lease", args.remote, f"refs/heads/{branch}:refs/heads/{branch}"]
        for branch in branches
    ]
    verify_commands = [
        ["git", "fetch", args.remote, "--prune"],
        ["git", "log", "--", dir_with_slash],
    ]
    payload["commands"] = {
        "rewrite": rewrite_commands,
        "push": _render_shell_lines(push_commands),
        "verify": _render_shell_lines(verify_commands),
    }
    payload["recommended_workflow"] = [
        "Work in a dedicated rewrite clone, not in your normal development checkout.",
        "Rewrite every affected branch with git-filter-repo so the directory disappears from history, not just from HEAD.",
        "Force-push each rewritten branch after temporarily handling any branch protection rules.",
        "Ask collaborators to reclone or hard-reset after the rewrite so the deleted history does not get reintroduced.",
    ]
    if not filter_repo_bin:
        payload["warnings"].append("git-filter-repo is not on PATH; install it before running the rewrite step")
    return payload


def _print_git_rm_public_dir_plan(payload: Dict[str, Any]) -> None:
    print(f"repo: {payload['repo']} ({payload.get('remote_url') or 'remote URL unavailable'})")
    print(f"repo dir: {payload['repo_dir']}")
    print(f"public dir: {payload['public_dir_filter']}")
    print(f"branches: {', '.join(payload['branches'])}")
    print("")
    print("Why this is not plain git rm:")
    print("Removing the directory from the current branch tip is not enough.")
    print("You need a history rewrite so the directory disappears from every targeted branch history.")
    print("")
    print("Recommended workflow:")
    for step in payload["recommended_workflow"]:
        print(f"- {step}")
    print("")
    print("Rewrite commands:")
    for line in payload["commands"]["rewrite"]:
        print(f"  {line}")
    print("")
    print("Push commands:")
    for line in payload["commands"]["push"]:
        print(f"  {line}")
    print("")
    print("Verification commands:")
    for line in payload["commands"]["verify"]:
        print(f"  {line}")
    if payload.get("warnings"):
        print("")
        print("Warnings:")
        for warning in payload["warnings"]:
            print(f"- {warning}")


def cmd_git_rm_public_dir(args: argparse.Namespace) -> int:
    try:
        payload = _plan_git_rm_public_dir(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.execute:
        if not payload.get("ok"):
            if args.json:
                print_json(payload)
            else:
                _print_git_rm_public_dir_plan(payload)
            return 1
        if not payload.get("filter_repo_available"):
            print("git-filter-repo is required for --execute", file=sys.stderr)
            return 1
        repo_root = Path(payload["repo_root"])
        rewrite = subprocess.run(
            [
                "git-filter-repo",
                "--path", payload["public_dir_filter"],
                "--invert-paths",
                "--refs", *payload["refs"],
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        payload["execute"] = {
            "ran": True,
            "returncode": rewrite.returncode,
            "stdout": rewrite.stdout,
            "stderr": rewrite.stderr,
        }
        if args.json:
            print_json(payload)
        else:
            _print_git_rm_public_dir_plan(payload)
            print("")
            if rewrite.stdout.strip():
                print(rewrite.stdout.rstrip())
            if rewrite.stderr.strip():
                print(rewrite.stderr.rstrip(), file=sys.stderr)
        return 0 if rewrite.returncode == 0 else 1

    if args.json:
        print_json(payload)
    else:
        _print_git_rm_public_dir_plan(payload)
    return 0 if payload.get("ok") else 1


def runtime_capabilities() -> Dict[str, Any]:
    java = run_capture(["java", "-XshowSettings:vm", "-version"])
    racket = run_capture(["racket", "--version"]) if shutil.which("racket") else {"ok": False, "stderr": "racket not found"}
    emacs = run_capture(["emacs", "--version"]) if shutil.which("emacs") else {"ok": False, "stderr": "emacs not found"}
    return {
        "jvm": {
            "available": java.get("exit_code") == 0,
            "vm_settings": (java.get("stderr") or "").splitlines()[:12],
            "gc_link": "indirect-runtime-observation",
        },
        "racket": {
            "available": racket.get("ok", False),
            "version": (racket.get("stdout") or racket.get("stderr") or "").splitlines()[:1],
            "tail_recursion": "native-in-racket-runtime-when-invoked",
        },
        "emacs": {
            "available": emacs.get("ok", False),
            "version": (emacs.get("stdout") or emacs.get("stderr") or "").splitlines()[:1],
            "dot_emacs": str(Path.home() / ".emacs") if (Path.home() / ".emacs").exists() else None,
            "dot_emacs_d": str(Path.home() / ".emacs.d") if (Path.home() / ".emacs.d").exists() else None,
            "elisp_compatibility": True,
        },
    }


def cmd_context(args: argparse.Namespace) -> int:
    glossary = load_environment_glossary(Path(args.glossary_root).expanduser())
    payload = {
        "terminal_context": terminal_context(args.shell),
        "sourced_environment": sourced_environment(),
        "glossary": glossary,
    }
    if args.json:
        print_json(payload)
    else:
        print(f"shell: {payload['terminal_context']['shell']}")
        print(f"cwd: {payload['terminal_context']['cwd']}")
        print(f"python: {payload['terminal_context']['python_executable']}")
        print(f"path entries: {len(payload['terminal_context']['path_entries'])}")
        print(f"startup files: {', '.join(payload['sourced_environment']['startup_files_present']) or '(none)'}")
        if glossary.get("available"):
            tc = glossary["terminal_context"]
            se = glossary["sourced_environment"]
            print(f"terminal context: {tc.get('definition', '')}")
            print(f"sourced environment: {se.get('definition', '')}")
    return 0


def _run_cortex_bridge(argv: Sequence[str]) -> int:
    from . import cortex_bridge
    return cortex_bridge.main(list(argv))


def _run_xml_matrix(argv: Sequence[str]) -> int:
    from . import xml_matrix
    return xml_matrix.main(list(argv))


def cmd_bridge_build(args: argparse.Namespace) -> int:
    return _run_cortex_bridge(["--db", args.db, "build", "--repo-root", str(REPO_ROOT)])


def cmd_bridge_ingest_edge(args: argparse.Namespace) -> int:
    """Ingest assets from a Collibra Edge endpoint into the bridge DB."""
    import json as _json
    from . import cortex_bridge
    base_url = (getattr(args, "url", "") or "").strip()
    if not base_url:
        base_url = os.environ.get("COLLIBRA_DGC_URL", "https://localhost").strip()
    site_id  = (getattr(args, "site_id", "") or os.environ.get("COLLIBRA_EDGE_SITE_ID", "")).strip()
    verify   = getattr(args, "verify_tls", False)
    db_path  = Path(args.db).expanduser()
    db = cortex_bridge.BridgeDB(db_path)
    try:
        db.setup()
        result = cortex_bridge.ingest_collibra_edge(db, base_url, site_id=site_id, verify_tls=verify)
        db.commit()
        print(_json.dumps(result, indent=2))
    finally:
        db.close()
    return 0


def cmd_bridge_passthrough(args: argparse.Namespace) -> int:
    command = [args.subcommand]
    if args.subcommand == "search":
        command.extend([args.text, "--limit", str(args.limit)])
    elif args.subcommand == "entity":
        command.append(args.iri)
    elif args.subcommand == "latest-changes":
        command.extend(["--limit", str(args.limit)])
        if getattr(args, "realm", None):
            command.extend(["--realm", args.realm])
        if getattr(args, "source_kind", None):
            command.extend(["--source-kind", args.source_kind])
    elif args.subcommand in {"sparql", "graphql"}:
        command.append(args.query)
    return _run_cortex_bridge(["--db", args.db] + command)


def cmd_jdbc_url(args: argparse.Namespace) -> int:
    return _run_cortex_bridge(["--db", args.db, "jdbc-url"])


def cmd_xml_matrix(args: argparse.Namespace) -> int:
    return _run_xml_matrix(
        [
            "--db", args.db,
            "--repo-root", str(REPO_ROOT),
            "--output-dir", args.output_dir,
        ]
    )


def cmd_query_latest_changes(args: argparse.Namespace) -> int:
    from .atom_query import (
        build_request_feed,
        build_response_feed,
        parse_request_feed,
        query_latest_changes_api,
        query_latest_changes_local,
        write_xml,
    )

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    request_path = Path(args.request).expanduser() if args.request else (output_dir / "latest-changes.request.atom")
    response_path = Path(args.response).expanduser() if args.response else (output_dir / "latest-changes.response.atom")

    if args.request and not args.write_request:
        request_payload = parse_request_feed(request_path)
    else:
        request_payload = {
            "query_name": "latest-changes-across-realms",
            "query_mode": "api" if args.api_base_url else "local",
            "limit": args.limit,
            "realms": args.realm or ["internal-graph", "external-graph", "filesystem"],
            "api_base_url": args.api_base_url,
        }
        write_xml(
            request_path,
            build_request_feed(
                limit=args.limit,
                realms=request_payload["realms"],
                query_mode=request_payload["query_mode"],
                api_base_url=args.api_base_url,
            ),
        )

    realms = request_payload.get("realms") or args.realm
    limit = int(request_payload.get("limit") or args.limit)
    api_base_url = request_payload.get("api_base_url") or args.api_base_url
    source_mode = "api" if api_base_url else "local"

    if api_base_url:
        results = query_latest_changes_api(
            api_base_url=api_base_url,
            limit=limit,
            realms=realms,
            timeout=args.timeout,
            emacsclient_bin=args.emacsclient_bin,
        )
    else:
        results = query_latest_changes_local(
            db_path=Path(args.db).expanduser(),
            limit=limit,
            realms=realms,
            emacsclient_bin=args.emacsclient_bin,
        )

    write_xml(
        response_path,
        build_response_feed(
            request_payload=request_payload,
            results=results,
            source_mode=source_mode,
        ),
    )

    payload = {
        "ok": True,
        "request_path": str(request_path),
        "response_path": str(response_path),
        "query_mode": source_mode,
        "realms": realms,
        "counts": {realm: len(rows) for realm, rows in results.items()},
    }
    if args.json:
        print_json(payload)
    else:
        print(response_path)
    return 0


def cmd_query_read_atom(args: argparse.Namespace) -> int:
    from .atom_query import summarize_feed

    payload = summarize_feed(Path(args.atom_path).expanduser())
    if args.json:
        print_json(payload)
    else:
        print(f"title: {payload.get('title') or '(none)'}")
        print(f"updated: {payload.get('updated') or '(none)'}")
        print(f"entries: {payload.get('entry_count', 0)}")
        for realm, count in sorted((payload.get("realms") or {}).items()):
            print(f"{realm}: {count}")
    return 0


def cmd_realm_check(args: argparse.Namespace) -> int:
    from .realm_ops import (
        build_audit_response_feed,
        build_request_feed,
        parse_feed,
        resolve_schedule_inputs,
        run_audit,
        write_xml,
    )

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved = resolve_schedule_inputs(realms=args.realm, domains=args.domain, services=args.service)
    request_path = Path(args.request).expanduser() if args.request else (output_dir / "realm-check.request.atom")
    response_path = Path(args.response).expanduser() if args.response else (output_dir / "realm-check.response.atom")

    if args.read_request:
        request_payload = parse_feed(request_path)
    else:
        request_payload = {
            "request_kind": "realm-check",
            **resolved,
        }
        write_xml(
            request_path,
            build_request_feed(
                request_kind="realm-check",
                realms=resolved["realms"],
                domains=resolved["domains"],
                services=resolved["services"],
                output_dir=str(output_dir),
            ),
        )

    results = run_audit(
        realms=request_payload["realms"],
        domains=request_payload["domains"],
        services=request_payload["services"],
    )
    write_xml(
        response_path,
        build_audit_response_feed(request_payload=request_payload, results=results),
    )
    payload = {
        "ok": True,
        "request_path": str(request_path),
        "response_path": str(response_path),
        "realms": request_payload["realms"],
        "domains": request_payload["domains"],
        "services": request_payload["services"],
        "counts": {realm: len(rows) for realm, rows in results.items()},
    }
    if args.json:
        print_json(payload)
    else:
        print(response_path)
    return 0


def cmd_realm_cron_write(args: argparse.Namespace) -> int:
    from .realm_ops import (
        build_cron_response_feed,
        build_request_feed,
        default_audit_command,
        resolve_schedule_inputs,
        write_cron_file,
        write_xml,
    )

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved = resolve_schedule_inputs(realms=args.realm, domains=args.domain, services=args.service)
    request_path = Path(args.request).expanduser() if args.request else (output_dir / "realm-cron.request.atom")
    response_path = Path(args.response).expanduser() if args.response else (output_dir / "realm-cron.response.atom")
    cron_path = Path(args.cron_file).expanduser() if args.cron_file else (output_dir / "realm-audit.cron")
    check_response_path = output_dir / "realm-check.response.atom"

    request_payload = {
        "request_kind": "realm-cron",
        **resolved,
        "cron_expression": args.cron,
        "output_dir": str(output_dir),
    }
    write_xml(
        request_path,
        build_request_feed(
            request_kind="realm-cron",
            realms=resolved["realms"],
            domains=resolved["domains"],
            services=resolved["services"],
            cron_expression=args.cron,
            output_dir=str(output_dir),
        ),
    )
    command = default_audit_command(
        request_path=request_path,
        response_path=check_response_path,
        realms=resolved["realms"],
        domains=resolved["domains"],
        services=resolved["services"],
    )
    write_cron_file(cron_path, args.cron, command)
    write_xml(
        response_path,
        build_cron_response_feed(request_payload=request_payload, command=command),
    )
    payload = {
        "ok": True,
        "request_path": str(request_path),
        "response_path": str(response_path),
        "cron_file": str(cron_path),
        "command": command,
        "cron_expression": args.cron,
    }
    if args.json:
        print_json(payload)
    else:
        print(cron_path)
    return 0


def cmd_realm_broadcast(args: argparse.Namespace) -> int:
    from .realm_ops import (
        DEFAULT_TOPIC_TARGETS,
        build_broadcast_feed,
        build_request_feed,
        resolve_schedule_inputs,
        write_xml,
    )

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved = resolve_schedule_inputs(realms=args.realm, domains=args.domain, services=None)
    targets = args.target or list(DEFAULT_TOPIC_TARGETS)
    request_path = Path(args.request).expanduser() if args.request else (output_dir / "realm-broadcast.request.atom")
    response_path = Path(args.response).expanduser() if args.response else (output_dir / "realm-broadcast.response.atom")
    write_xml(
        request_path,
        build_request_feed(
            request_kind="realm-topic-broadcast",
            realms=resolved["realms"],
            domains=resolved["domains"],
            services=[],
            topic=args.topic,
            targets=targets,
            output_dir=str(output_dir),
        ),
    )
    write_xml(
        response_path,
        build_broadcast_feed(
            topic=args.topic,
            targets=targets,
            domains=resolved["domains"],
            realms=resolved["realms"],
        ),
    )
    payload = {
        "ok": True,
        "request_path": str(request_path),
        "response_path": str(response_path),
        "topic": args.topic,
        "targets": targets,
    }
    if args.json:
        print_json(payload)
    else:
        print(response_path)
    return 0


def cmd_realm_read_atom(args: argparse.Namespace) -> int:
    from .realm_ops import summarize_feed

    payload = summarize_feed(Path(args.atom_path).expanduser())
    if args.json:
        print_json(payload)
    else:
        print(f"title: {payload.get('title') or '(none)'}")
        print(f"updated: {payload.get('updated') or '(none)'}")
        print(f"entries: {payload.get('entry_count', 0)}")
        for realm, count in sorted((payload.get("realms") or {}).items()):
            print(f"{realm}: {count}")
        for service, count in sorted((payload.get("services") or {}).items()):
            print(f"{service}: {count}")
    return 0


def cmd_man(args: argparse.Namespace) -> int:
    page = man_dir() / f"{args.topic}.1"
    if not page.exists():
        print(f"Unknown manpage topic: {args.topic}", file=sys.stderr)
        return 1
    if args.raw:
        print(page)
        return 0
    man_bin = shutil.which("man")
    if man_bin:
        env = dict(os.environ)
        env["MANPATH"] = str(man_dir()) + os.pathsep + env.get("MANPATH", "")
        return subprocess.call([man_bin, args.topic], env=env)
    print(_read_text(page))
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    if getattr(args, "subject", "singine") == "ant":
        return install_ant_tool(json_output=getattr(args, "json", False))
    if getattr(args, "subject", "singine") == "xmldoclet":
        return install_xmldoclet_tool(json_output=getattr(args, "json", False))
    if getattr(args, "subject", "singine") == "git-filter-repo":
        return install_git_filter_repo_tool(json_output=getattr(args, "json", False))

    prefix = Path(args.prefix).expanduser()
    launcher = install_launcher(prefix)
    install_manpages(prefix)
    shell_updates = ensure_shell_paths(prefix, args.shell)
    installed_tools: List[Dict[str, Any]] = []
    if getattr(args, "mode", "base") == "workstation":
        tool_result = {"tool": "git-filter-repo", "ok": install_git_filter_repo_tool(json_output=False) == 0}
        installed_tools.append(tool_result)
    payload = {
        "prefix": str(prefix),
        "launcher": str(launcher),
        "manpath": str(installed_man_path(prefix)),
        "shell_init": shell_updates,
        "shell": args.shell,
        "mode": getattr(args, "mode", "base"),
        "tools": installed_tools,
    }
    if args.json:
        print_json(payload)
    else:
        print(f"installed launcher: {launcher}")
        print(f"installed manpages: {installed_man_path(prefix)}")
        print(f"updated shell init: {shell_updates}")
        if installed_tools:
            print(f"install mode: {payload['mode']}")
            for item in installed_tools:
                print(f"tool {item['tool']}: {'ok' if item['ok'] else 'failed'}")
        print("open a new shell or run:")
        for _, rc in shell_updates.items():
            print(f". {rc}")
    if any(not item["ok"] for item in installed_tools):
        return 1
    return 0


def cmd_template_create(args: argparse.Namespace) -> int:
    from .template import (
        create_maven_template,
        create_npm_template,
        default_java_package,
        default_maven_args,
        default_npm_args,
    )

    name = args.name
    target_dir_arg = Path(args.dir).expanduser() if args.dir else None

    if args.kind == "maven":
        defaults = default_maven_args(name)
        group_id = args.group_id or defaults["group_id"]
        artifact_id = args.artifact_id or defaults["artifact_id"]
        target_dir = target_dir_arg if target_dir_arg is not None else Path.cwd() / artifact_id
        try:
            result = create_maven_template(
                name=name,
                target_dir=target_dir,
                group_id=group_id,
                artifact_id=artifact_id,
                version=args.version,
                package_name=args.package_name or default_java_package(group_id, artifact_id),
                java_version=args.java_version,
                description=args.description or f"{name} generated by Singine for Maven builds.",
                force=args.force,
            )
        except OSError as exc:
            payload = {"ok": False, "kind": args.kind, "error": str(exc), "target_dir": str(target_dir)}
            if args.json:
                print_json(payload)
            else:
                print(f"template creation failed: {payload['error']}", file=sys.stderr)
                print(f"target dir: {payload['target_dir']}", file=sys.stderr)
            return 1
    else:
        defaults = default_npm_args(name, scope=args.scope or "")
        version = args.version if args.version != "0.1.0-SNAPSHOT" else "0.1.0"
        package_name = args.package_name or defaults["package_name"]
        target_leaf = package_name.split("/", 1)[-1] if package_name.startswith("@") else package_name
        target_dir = target_dir_arg if target_dir_arg is not None else Path.cwd() / target_leaf
        try:
            result = create_npm_template(
                name=name,
                target_dir=target_dir,
                package_name=package_name,
                version=version,
                description=args.description or f"{name} generated by Singine for npm workflows.",
                module_type=args.module_type,
                force=args.force,
            )
        except OSError as exc:
            payload = {"ok": False, "kind": args.kind, "error": str(exc), "target_dir": str(target_dir)}
            if args.json:
                print_json(payload)
            else:
                print(f"template creation failed: {payload['error']}", file=sys.stderr)
                print(f"target dir: {payload['target_dir']}", file=sys.stderr)
            return 1

    payload = result.to_dict()
    if args.json:
        print_json(payload)
    else:
        print(f"created {payload['kind']} template: {payload['target_dir']}")
        print(f"package: {payload['package_name']}")
        for file_path in payload["files"]:
            print(f"  {file_path}")
    return 0


def cmd_template_list(args: argparse.Namespace) -> int:
    from .template import list_template_library

    payload = {
        "ok": True,
        "items": list_template_library(family=getattr(args, "family", None)),
    }
    if args.json:
        print_json(payload)
    else:
        for item in payload["items"]:
            print(f"{item['name']} [{item['family']}]")
            print(f"  {item['description']}")
            print(f"  {item['reference_command']}")
    return 0


def cmd_template_materialize(args: argparse.Namespace) -> int:
    from .template import materialize_library_entry

    try:
        payload = materialize_library_entry(
            name=args.name,
            output_dir=Path(args.output_dir).expanduser(),
            title=getattr(args, "title", None),
        )
    except KeyError:
        error = {"ok": False, "error": f"unknown template library entry: {args.name}"}
        if args.json:
            print_json(error)
        else:
            print(error["error"], file=sys.stderr)
        return 1

    if args.json:
        print_json(payload)
    else:
        print(payload["artifacts"].get("markdown") or payload["artifacts"].get("json"))
    return 0


def cmd_dotfiles_inspect(args: argparse.Namespace) -> int:
    from .dotfiles import build_payload

    payload = build_payload(
        home_dir=Path(args.home_dir).expanduser(),
        dotfiles_repo=Path(args.dotfiles_repo).expanduser(),
    )
    print_json(payload)
    return 0


def cmd_dotfiles_dashboard(args: argparse.Namespace) -> int:
    from .dotfiles import write_dashboard

    payload = write_dashboard(
        output_dir=Path(args.output_dir).expanduser(),
        home_dir=Path(args.home_dir).expanduser(),
        dotfiles_repo=Path(args.dotfiles_repo).expanduser(),
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["artifacts"]["html"])
    return 0


def cmd_dotfiles_capture(args: argparse.Namespace) -> int:
    from .dotfiles import capture_target

    try:
        payload = capture_target(
            name=args.name,
            home_dir=Path(args.home_dir).expanduser(),
            dotfiles_repo=Path(args.dotfiles_repo).expanduser(),
        )
    except KeyError:
        print_json({"ok": False, "error": f"unknown dotfile target: {args.name}"})
        return 1
    except FileNotFoundError as exc:
        print_json({"ok": False, "error": f"missing source path: {exc}"})
        return 1
    if args.json:
        print_json(payload)
    else:
        print(payload["target"])
    return 0


def cmd_intranet_control_center(args: argparse.Namespace) -> int:
    from .control_center import write_control_center

    payload = write_control_center(
        output_dir=Path(args.output_dir).expanduser(),
        home_dir=Path(args.home_dir).expanduser(),
        dotfiles_repo=Path(args.dotfiles_repo).expanduser(),
        ai_root_dir=Path(args.ai_root_dir).expanduser(),
        repo_ai_dir=Path(args.repo_ai_dir).expanduser(),
        repo_root=REPO_ROOT,
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["artifacts"]["html"])
    return 0


def cmd_intranet_publish(args: argparse.Namespace) -> int:
    from .intranet_deploy import write_publish_bundle

    payload = write_publish_bundle(
        site_root=Path(args.site_root).expanduser(),
        deploy_root=Path(args.deploy_root).expanduser(),
        silkpage_root=Path(args.silkpage_root).expanduser(),
        ssl_dir=Path(args.ssl_dir).expanduser(),
        domain=args.domain,
        sync=not args.no_sync,
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["artifacts"]["html"])
    return 0


def cmd_intranet_cert_bootstrap(args: argparse.Namespace) -> int:
    from .intranet_deploy import bootstrap_local_tls

    payload = bootstrap_local_tls(
        ssl_dir=Path(args.ssl_dir).expanduser(),
        domain=args.domain,
        force=args.force,
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["server_cert"])
    return 0


def cmd_gen_command_capture(args: argparse.Namespace) -> int:
    from .cmdlib import record_command

    payload = record_command(
        raw_command=args.raw,
        shell=args.shell,
        pwd=args.pwd,
        exit_code=args.exit_code,
        history_id=args.history_id,
        pid=args.pid,
        session=args.session,
        root_dir=Path(args.root_dir).expanduser() if args.root_dir else None,
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["history_path"])
    return 0


def cmd_gen_command_list(args: argparse.Namespace) -> int:
    from .cmdlib import write_command_list

    payload = write_command_list(
        root_dir=Path(args.root_dir).expanduser() if args.root_dir else None,
        output_dir=Path(args.output_dir).expanduser() if args.output_dir else None,
        since_days=args.since_days,
        limit=args.limit,
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["artifacts"]["html"])
    return 0


def cmd_proof_specimen(args: argparse.Namespace) -> int:
    from .font_proof import build_specimen

    payload = build_specimen(
        output_dir=Path(args.output_dir).expanduser(),
        fonts=args.fonts,
        title=args.title,
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["artifacts"]["pdf"])
    return 0


def cmd_proof_showcase(args: argparse.Namespace) -> int:
    from .font_proof import build_showcase

    payload = build_showcase(
        output_dir=Path(args.output_dir).expanduser(),
        font=args.font,
        title=args.title,
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["artifacts"]["pdf"])
    return 0


def cmd_proof_harfbuzz(args: argparse.Namespace) -> int:
    from .font_proof import build_harfbuzz_preview

    payload = build_harfbuzz_preview(
        font=args.font,
        text=args.text,
        output_dir=Path(args.output_dir).expanduser(),
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["artifacts"]["pdf"])
    return 0


def cmd_proof_suite(args: argparse.Namespace) -> int:
    from .font_proof import build_suite

    payload = build_suite(
        output_dir=Path(args.output_dir).expanduser(),
        specimen_fonts=args.fonts,
        showcase_font=args.showcase_font,
        hb_font=args.hb_font,
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["showcase"]["artifacts"]["pdf"])
    return 0


def cmd_template_create(args: argparse.Namespace) -> int:
    from .template import (
        create_maven_template,
        create_npm_template,
        default_java_package,
        default_maven_args,
        default_npm_args,
    )

    name = args.name
    target_dir_arg = Path(args.dir).expanduser() if args.dir else None

    if args.kind == "maven":
        defaults = default_maven_args(name)
        group_id = args.group_id or defaults["group_id"]
        artifact_id = args.artifact_id or defaults["artifact_id"]
        target_dir = target_dir_arg if target_dir_arg is not None else Path.cwd() / artifact_id
        try:
            result = create_maven_template(
                name=name,
                target_dir=target_dir,
                group_id=group_id,
                artifact_id=artifact_id,
                version=args.version,
                package_name=args.package_name or default_java_package(group_id, artifact_id),
                java_version=args.java_version,
                description=args.description or f"{name} generated by Singine for Maven builds.",
                force=args.force,
            )
        except OSError as exc:
            payload = {"ok": False, "kind": args.kind, "error": str(exc), "target_dir": str(target_dir)}
            if args.json:
                print_json(payload)
            else:
                print(f"template creation failed: {payload['error']}", file=sys.stderr)
                print(f"target dir: {payload['target_dir']}", file=sys.stderr)
            return 1
    else:
        defaults = default_npm_args(name, scope=args.scope or "")
        version = args.version if args.version != "0.1.0-SNAPSHOT" else "0.1.0"
        package_name = args.package_name or defaults["package_name"]
        target_leaf = package_name.split("/", 1)[-1] if package_name.startswith("@") else package_name
        target_dir = target_dir_arg if target_dir_arg is not None else Path.cwd() / target_leaf
        try:
            result = create_npm_template(
                name=name,
                target_dir=target_dir,
                package_name=package_name,
                version=version,
                description=args.description or f"{name} generated by Singine for npm workflows.",
                module_type=args.module_type,
                force=args.force,
            )
        except OSError as exc:
            payload = {"ok": False, "kind": args.kind, "error": str(exc), "target_dir": str(target_dir)}
            if args.json:
                print_json(payload)
            else:
                print(f"template creation failed: {payload['error']}", file=sys.stderr)
                print(f"target dir: {payload['target_dir']}", file=sys.stderr)
            return 1

    payload = result.to_dict()
    if args.json:
        print_json(payload)
    else:
        print(f"created {payload['kind']} template: {payload['target_dir']}")
        print(f"package: {payload['package_name']}")
        for file_path in payload["files"]:
            print(f"  {file_path}")
    return 0


def cmd_template_list(args: argparse.Namespace) -> int:
    from .template import list_template_library

    payload = {
        "ok": True,
        "items": list_template_library(family=getattr(args, "family", None)),
    }
    if args.json:
        print_json(payload)
    else:
        for item in payload["items"]:
            print(f"{item['name']} [{item['family']}]")
            print(f"  {item['description']}")
            print(f"  {item['reference_command']}")
    return 0


def cmd_template_materialize(args: argparse.Namespace) -> int:
    from .template import materialize_library_entry

    try:
        payload = materialize_library_entry(
            name=args.name,
            output_dir=Path(args.output_dir).expanduser(),
            title=getattr(args, "title", None),
        )
    except KeyError:
        error = {"ok": False, "error": f"unknown template library entry: {args.name}"}
        if args.json:
            print_json(error)
        else:
            print(error["error"], file=sys.stderr)
        return 1

    if args.json:
        print_json(payload)
    else:
        print(payload["artifacts"].get("markdown") or payload["artifacts"].get("json"))
    return 0


def cmd_dotfiles_inspect(args: argparse.Namespace) -> int:
    from .dotfiles import build_payload

    payload = build_payload(
        home_dir=Path(args.home_dir).expanduser(),
        dotfiles_repo=Path(args.dotfiles_repo).expanduser(),
    )
    print_json(payload)
    return 0


def cmd_dotfiles_dashboard(args: argparse.Namespace) -> int:
    from .dotfiles import write_dashboard

    payload = write_dashboard(
        output_dir=Path(args.output_dir).expanduser(),
        home_dir=Path(args.home_dir).expanduser(),
        dotfiles_repo=Path(args.dotfiles_repo).expanduser(),
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["artifacts"]["html"])
    return 0


def cmd_dotfiles_capture(args: argparse.Namespace) -> int:
    from .dotfiles import capture_target

    try:
        payload = capture_target(
            name=args.name,
            home_dir=Path(args.home_dir).expanduser(),
            dotfiles_repo=Path(args.dotfiles_repo).expanduser(),
        )
    except KeyError:
        print_json({"ok": False, "error": f"unknown dotfile target: {args.name}"})
        return 1
    except FileNotFoundError as exc:
        print_json({"ok": False, "error": f"missing source path: {exc}"})
        return 1
    if args.json:
        print_json(payload)
    else:
        print(payload["target"])
    return 0


def cmd_intranet_control_center(args: argparse.Namespace) -> int:
    from .control_center import write_control_center

    payload = write_control_center(
        output_dir=Path(args.output_dir).expanduser(),
        home_dir=Path(args.home_dir).expanduser(),
        dotfiles_repo=Path(args.dotfiles_repo).expanduser(),
        ai_root_dir=Path(args.ai_root_dir).expanduser(),
        repo_ai_dir=Path(args.repo_ai_dir).expanduser(),
        repo_root=REPO_ROOT,
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["artifacts"]["html"])
    return 0


def cmd_intranet_publish(args: argparse.Namespace) -> int:
    from .intranet_deploy import write_publish_bundle

    payload = write_publish_bundle(
        site_root=Path(args.site_root).expanduser(),
        deploy_root=Path(args.deploy_root).expanduser(),
        silkpage_root=Path(args.silkpage_root).expanduser(),
        ssl_dir=Path(args.ssl_dir).expanduser(),
        domain=args.domain,
        sync=not args.no_sync,
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["artifacts"]["html"])
    return 0


def cmd_intranet_cert_bootstrap(args: argparse.Namespace) -> int:
    from .intranet_deploy import bootstrap_local_tls

    payload = bootstrap_local_tls(
        ssl_dir=Path(args.ssl_dir).expanduser(),
        domain=args.domain,
        force=args.force,
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["server_cert"])
    return 0


def cmd_gen_command_capture(args: argparse.Namespace) -> int:
    from .cmdlib import record_command

    payload = record_command(
        raw_command=args.raw,
        shell=args.shell,
        pwd=args.pwd,
        exit_code=args.exit_code,
        history_id=args.history_id,
        pid=args.pid,
        session=args.session,
        root_dir=Path(args.root_dir).expanduser() if args.root_dir else None,
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["history_path"])
    return 0


def cmd_gen_command_list(args: argparse.Namespace) -> int:
    from .cmdlib import write_command_list

    payload = write_command_list(
        root_dir=Path(args.root_dir).expanduser() if args.root_dir else None,
        output_dir=Path(args.output_dir).expanduser() if args.output_dir else None,
        since_days=args.since_days,
        limit=args.limit,
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["artifacts"]["html"])
    return 0


def cmd_proof_specimen(args: argparse.Namespace) -> int:
    from .font_proof import build_specimen

    payload = build_specimen(
        output_dir=Path(args.output_dir).expanduser(),
        fonts=args.fonts,
        title=args.title,
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["artifacts"]["pdf"])
    return 0


def cmd_proof_showcase(args: argparse.Namespace) -> int:
    from .font_proof import build_showcase

    payload = build_showcase(
        output_dir=Path(args.output_dir).expanduser(),
        font=args.font,
        title=args.title,
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["artifacts"]["pdf"])
    return 0


def cmd_proof_harfbuzz(args: argparse.Namespace) -> int:
    from .font_proof import build_harfbuzz_preview

    payload = build_harfbuzz_preview(
        font=args.font,
        text=args.text,
        output_dir=Path(args.output_dir).expanduser(),
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["artifacts"]["pdf"])
    return 0


def cmd_proof_suite(args: argparse.Namespace) -> int:
    from .font_proof import build_suite

    payload = build_suite(
        output_dir=Path(args.output_dir).expanduser(),
        specimen_fonts=args.fonts,
        showcase_font=args.showcase_font,
        hb_font=args.hb_font,
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["showcase"]["artifacts"]["pdf"])
    return 0


def cmd_runtime_inspect(args: argparse.Namespace) -> int:
    payload = {
        "terminal_context": terminal_context(None),
        "sourced_environment": sourced_environment(),
        "runtime_capabilities": runtime_capabilities(),
    }
    print_json(payload)
    return 0


def cmd_runtime_exec(args: argparse.Namespace) -> int:
    payload: Dict[str, Any] = {
        "terminal_context": terminal_context(None),
        "sourced_environment": sourced_environment(),
        "runtime_capabilities": runtime_capabilities(),
        "requested_command": args.command_args,
    }
    if not args.command_args:
        payload["ok"] = False
        payload["exception"] = {"type": "UsageError", "message": "No singine subcommand provided."}
        print_json(payload)
        return 2

    cmd = [sys.executable, "-m", "singine.command"] + args.command_args
    result = run_capture(cmd)
    payload["ok"] = result["ok"]
    payload["exit_code"] = result["exit_code"]
    payload["stdout"] = result["stdout"]
    payload["stderr"] = result["stderr"]
    if not result["ok"]:
        payload["exception"] = {
            "type": "SingineCommandFailure",
            "message": f"Wrapped singine command exited with code {result['exit_code']}.",
        }
    print_json(payload)
    return 0 if result["ok"] else 1


def cmd_runtime_exec_external(args: argparse.Namespace) -> int:
    """Execute an arbitrary external binary inside the singine runtime envelope.

    Sanctioned execution gate for binaries such as collibractl.  The runtime
    envelope captures terminal context, sourced environment, and runtime
    capabilities alongside the command output so every external call is
    traceable.

    The binary must exist on PATH or be given as an absolute path.  No shell
    interpolation is performed — arguments are passed as a list directly to
    subprocess.run so there is no injection surface.

    Session context is appended to the payload under ``session`` when a
    SINGINE_SESSION_TOKEN environment variable is present.

    Usage:
        singine runtime exec-external collibractl community create --name "Foo" --output json
        singine runtime exec-external collibractl asset import --file /tmp/a.csv --domain-id <uuid>
    """
    payload: Dict[str, Any] = {
        "terminal_context": terminal_context(None),
        "sourced_environment": sourced_environment(),
        "runtime_capabilities": runtime_capabilities(),
        "requested_command": args.command_args,
    }

    session_token = os.environ.get("SINGINE_SESSION_TOKEN")
    if session_token:
        payload["session"] = {"token_present": True, "token_prefix": session_token[:8] + "…"}

    if not args.command_args:
        payload["ok"] = False
        payload["exception"] = {"type": "UsageError", "message": "No external command provided."}
        print_json(payload)
        return 2

    binary = args.command_args[0]
    resolved = shutil.which(binary)
    if resolved is None:
        # Fall back to ~/.local/bin (added by singine install but may not be on PATH
        # in all shell contexts, e.g. inside Electron or a non-login shell)
        local_bin = Path.home() / ".local" / "bin" / binary
        resolved = str(local_bin) if local_bin.exists() else None

    if resolved is None:
        payload["ok"] = False
        payload["exception"] = {
            "type": "BinaryNotFound",
            "message": (
                f"'{binary}' not found on PATH or in ~/.local/bin.  "
                f"Install it first: e.g. install -m 755 {binary} ~/.local/bin/{binary}"
            ),
        }
        print_json(payload)
        return 127

    cmd = [resolved] + args.command_args[1:]
    result = run_capture(cmd)
    payload["ok"] = result["ok"]
    payload["exit_code"] = result["exit_code"]
    payload["stdout"] = result["stdout"]
    payload["stderr"] = result["stderr"]
    payload["resolved_binary"] = resolved
    if not result["ok"]:
        payload["exception"] = {
            "type": "ExternalCommandFailure",
            "message": f"'{binary}' exited with code {result['exit_code']}.",
        }
    print_json(payload)
    return 0 if result["ok"] else 1


# ── Java runtime governance (singine runtime java) ───────────────────────────

def _java_registry_path() -> Path:
    """Locate the Singine Java runtime registry.

    Resolution order:
      1. SINGINE_REGISTRY env var (explicit path to registry.json)
      2. SINGINE_ROOT env var + /runtime/java/registry.json
      3. Hardcoded canonical location
    """
    if r := os.environ.get("SINGINE_REGISTRY"):
        return Path(r)
    if root := os.environ.get("SINGINE_ROOT"):
        return Path(root) / "runtime" / "java" / "registry.json"
    return Path("/private/tmp/singine-personal-os/runtime/java/registry.json")


def _java_load_registry() -> Dict[str, Any]:
    path = _java_registry_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Java registry not found at {path}. "
            "Set SINGINE_ROOT or SINGINE_REGISTRY to point to the registry."
        )
    import json as _json
    return _json.loads(path.read_text(encoding="utf-8"))


def _java_resolve_alias(registry: Dict[str, Any], alias: str) -> Dict[str, Any]:
    for v in registry.get("versions", []):
        if v["alias"] == alias:
            return v
    known = [v["alias"] for v in registry.get("versions", [])]
    raise ValueError(f"Unknown Java alias '{alias}'. Known aliases: {', '.join(known)}")


def _java_read_reqs_singine(directory: Path) -> Optional[str]:
    """Extract :java alias from reqs.singine in the given directory."""
    cfg = directory / "reqs.singine"
    if not cfg.exists():
        return None
    import re
    text = cfg.read_text(encoding="utf-8")
    m = re.search(r':java\s+"([^"]+)"', text)
    return m.group(1) if m else None


def _java_resolve_for_dir(registry: Dict[str, Any], directory: Path) -> tuple[str, str]:
    """Return (alias, source) via the three-step resolution chain."""
    # Step 1: reqs.singine
    alias = _java_read_reqs_singine(directory)
    if alias:
        return alias, "reqs.singine"
    # Step 2: application-map (keyed by directory base name)
    appmap = registry.get("application_map", {})
    alias = appmap.get(directory.name)
    if alias:
        return alias, "application-map"
    # Step 3: policy default
    alias = registry.get("policy", {}).get("default", "lts")
    return alias, "policy-default"


def _java_sdkman_home() -> Path:
    return Path(os.environ.get("SDKMAN_DIR", str(Path.home() / ".sdkman")))


def cmd_runtime_java_list(args: argparse.Namespace) -> int:
    try:
        registry = _java_load_registry()
    except FileNotFoundError as exc:
        print(f"[singine runtime java] ERROR: {exc}", file=sys.stderr)
        return 1

    versions = registry.get("versions", [])
    appmap = registry.get("application_map", {})
    default = registry.get("policy", {}).get("default", "lts")

    if getattr(args, "json", False):
        print_json({"versions": versions, "application_map": appmap, "default": default})
        return 0

    print()
    print(f"{'ALIAS':<12}  {'SDKMAN ID':<28}  {'MAJOR':<8}  {'STATUS':<10}  NOTES")
    print("─" * 80)
    for v in versions:
        marker = " ◀ default" if v["alias"] == default else ""
        print(f"{v['alias']:<12}  {v['sdkman_id']:<28}  {str(v['major']):<8}  {v['status']:<10}  {v.get('notes','')}{marker}")
    print()
    if appmap:
        print(f"{'APPLICATION':<30}  ALIAS")
        print("─" * 45)
        for app, alias in appmap.items():
            print(f"{app:<30}  {alias}")
        print()
    return 0


def cmd_runtime_java_inspect(args: argparse.Namespace) -> int:
    try:
        registry = _java_load_registry()
    except FileNotFoundError as exc:
        print(f"[singine runtime java] ERROR: {exc}", file=sys.stderr)
        return 1

    directory = Path(args.dir).resolve() if getattr(args, "dir", None) else Path.cwd()
    alias, source = _java_resolve_for_dir(registry, directory)
    try:
        version_entry = _java_resolve_alias(registry, alias)
    except ValueError as exc:
        print(f"[singine runtime java] ERROR: {exc}", file=sys.stderr)
        return 1

    sdkman_home = _java_sdkman_home()
    candidate = sdkman_home / "candidates" / "java" / version_entry["sdkman_id"]

    payload = {
        "directory": str(directory),
        "source": source,
        "alias": alias,
        "sdkman_id": version_entry["sdkman_id"],
        "major": version_entry["major"],
        "distribution": version_entry["distribution"],
        "status": version_entry["status"],
        "installed": candidate.exists(),
        "java_home": str(candidate),
    }

    if getattr(args, "json", False):
        print_json(payload)
        return 0

    print(f"directory   : {payload['directory']}")
    print(f"source      : {payload['source']}")
    print(f"alias       : {payload['alias']}")
    print(f"sdkman_id   : {payload['sdkman_id']}")
    print(f"major       : {payload['major']}  ({payload['distribution']})")
    print(f"status      : {payload['status']}")
    print(f"installed   : {'yes' if payload['installed'] else 'no — run: singine runtime java install ' + alias}")
    print(f"java_home   : {payload['java_home']}")
    return 0


def cmd_runtime_java_env(args: argparse.Namespace) -> int:
    """Print export statements so callers can eval: eval $(singine runtime java env)"""
    try:
        registry = _java_load_registry()
    except FileNotFoundError as exc:
        print(f"[singine runtime java] ERROR: {exc}", file=sys.stderr)
        return 1

    if getattr(args, "alias", None):
        alias = args.alias
        source = "explicit"
    else:
        alias, source = _java_resolve_for_dir(registry, Path.cwd())

    try:
        version_entry = _java_resolve_alias(registry, alias)
    except ValueError as exc:
        print(f"[singine runtime java] ERROR: {exc}", file=sys.stderr)
        return 1

    sdkman_home = _java_sdkman_home()
    java_home = sdkman_home / "candidates" / "java" / version_entry["sdkman_id"]

    if getattr(args, "json", False):
        print_json({"alias": alias, "source": source, "java_home": str(java_home),
                    "sdkman_id": version_entry["sdkman_id"]})
        return 0

    # Shell-eval-safe output
    print(f'export JAVA_HOME="{java_home}"')
    print(f'export PATH="{java_home}/bin:$PATH"')
    return 0


def cmd_runtime_java_install(args: argparse.Namespace) -> int:
    try:
        registry = _java_load_registry()
        version_entry = _java_resolve_alias(registry, args.alias)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[singine runtime java] ERROR: {exc}", file=sys.stderr)
        return 1

    sdkman_id = version_entry["sdkman_id"]
    sdkman_init = _java_sdkman_home() / "bin" / "sdkman-init.sh"
    if not sdkman_init.exists():
        print(f"[singine runtime java] ERROR: SDKMAN not found at {sdkman_init}", file=sys.stderr)
        return 1

    print(f"[singine runtime java] Installing {sdkman_id} via SDKMAN...")
    cmd = ["bash", "-c", f'source "{sdkman_init}" && sdk install java "{sdkman_id}"']
    result = subprocess.run(cmd)
    return result.returncode


# ── JVM language registry (Groovy, Clojure) ──────────────────────────────────

def _jvm_registry_path() -> Path:
    if r := os.environ.get("SINGINE_JVM_REGISTRY"):
        return Path(r)
    if root := os.environ.get("SINGINE_ROOT"):
        return Path(root) / "runtime" / "jvm" / "registry.json"
    return Path("/private/tmp/singine-personal-os/runtime/jvm/registry.json")


def _jvm_load_registry() -> Dict[str, Any]:
    path = _jvm_registry_path()
    if not path.exists():
        raise FileNotFoundError(
            f"JVM registry not found at {path}. "
            "Set SINGINE_ROOT or SINGINE_JVM_REGISTRY."
        )
    import json as _json
    return _json.loads(path.read_text(encoding="utf-8"))


def _jvm_lang_read_reqs(directory: Path, lang: str) -> Optional[str]:
    """Read :groovy / :clojure key from reqs.singine."""
    import re
    cfg = directory / "reqs.singine"
    if not cfg.exists():
        return None
    m = re.search(rf':{lang}\s+"([^"]+)"', cfg.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def _jvm_lang_resolve_for_dir(registry: Dict, lang: str, directory: Path) -> tuple[str, str]:
    alias = _jvm_lang_read_reqs(directory, lang)
    if alias:
        return alias, "reqs.singine"
    appmap = registry.get(lang, {}).get("application_map", {})
    alias = appmap.get(directory.name)
    if alias:
        return alias, "application-map"
    alias = registry.get(lang, {}).get("policy", {}).get("default", "lts")
    return alias, "policy-default"


def _jvm_lang_resolve_entry(registry: Dict, lang: str, alias: str) -> Dict[str, Any]:
    for v in registry.get(lang, {}).get("versions", []):
        if v["alias"] == alias:
            return v
    known = [v["alias"] for v in registry.get(lang, {}).get("versions", [])]
    raise ValueError(f"Unknown {lang} alias '{alias}'. Known: {', '.join(known)}")


def _make_runtime_lang_commands(lang: str) -> tuple:
    """Factory returning (list_fn, inspect_fn, env_fn, install_fn) for a JVM language."""

    def cmd_list(args: argparse.Namespace) -> int:
        try:
            registry = _jvm_load_registry()
        except FileNotFoundError as exc:
            print(f"[singine runtime {lang}] ERROR: {exc}", file=sys.stderr)
            return 1
        versions = registry.get(lang, {}).get("versions", [])
        default = registry.get(lang, {}).get("policy", {}).get("default", "")
        manager = registry.get(lang, {}).get("manager", "sdkman")
        if getattr(args, "json", False):
            print_json({"lang": lang, "manager": manager, "versions": versions, "default": default})
            return 0
        print(f"\n{lang.upper()} versions  (manager: {manager})\n")
        print(f"{'ALIAS':<12}  {'VERSION/ID':<28}  {'STATUS':<10}  NOTES")
        print("─" * 72)
        for v in versions:
            vid = v.get("sdkman_id") or v.get("cli_version") or v.get("lib_version", "?")
            marker = " ◀ default" if v["alias"] == default else ""
            print(f"{v['alias']:<12}  {vid:<28}  {v['status']:<10}  {v.get('notes','')}{marker}")
        print()
        return 0

    def cmd_inspect(args: argparse.Namespace) -> int:
        try:
            registry = _jvm_load_registry()
        except FileNotFoundError as exc:
            print(f"[singine runtime {lang}] ERROR: {exc}", file=sys.stderr)
            return 1
        directory = Path(args.dir).resolve() if getattr(args, "dir", None) else Path.cwd()
        alias, source = _jvm_lang_resolve_for_dir(registry, lang, directory)
        try:
            entry = _jvm_lang_resolve_entry(registry, lang, alias)
        except ValueError as exc:
            print(f"[singine runtime {lang}] ERROR: {exc}", file=sys.stderr)
            return 1
        manager = registry.get(lang, {}).get("manager", "sdkman")
        payload = {"lang": lang, "manager": manager, "directory": str(directory),
                   "source": source, "alias": alias, **entry}
        if manager == "sdkman":
            sdkman_id = entry.get("sdkman_id", alias)
            candidate = _java_sdkman_home() / "candidates" / lang / sdkman_id
            payload["installed"] = candidate.exists()
            payload["home"] = str(candidate)
        elif manager == "brew":
            import shutil
            payload["installed"] = bool(shutil.which(lang) or shutil.which("clj"))
        if getattr(args, "json", False):
            print_json(payload)
            return 0
        for k, v in payload.items():
            print(f"{k:<12}: {v}")
        return 0

    def cmd_env(args: argparse.Namespace) -> int:
        try:
            registry = _jvm_load_registry()
        except FileNotFoundError as exc:
            print(f"[singine runtime {lang}] ERROR: {exc}", file=sys.stderr)
            return 1
        alias = getattr(args, "alias", None) or _jvm_lang_resolve_for_dir(registry, lang, Path.cwd())[0]
        try:
            entry = _jvm_lang_resolve_entry(registry, lang, alias)
        except ValueError as exc:
            print(f"[singine runtime {lang}] ERROR: {exc}", file=sys.stderr)
            return 1
        manager = registry.get(lang, {}).get("manager", "sdkman")
        if manager == "sdkman":
            sdkman_id = entry.get("sdkman_id", alias)
            home = _java_sdkman_home() / "candidates" / lang / sdkman_id
            payload = {"alias": alias, "sdkman_id": sdkman_id, "home": str(home)}
            if getattr(args, "json", False):
                print_json(payload)
                return 0
            print(f'export {lang.upper()}_HOME="{home}"')
            print(f'export PATH="{home}/bin:$PATH"')
        else:
            payload = {"alias": alias, "manager": "brew", "note": f"Managed by brew; run: brew upgrade {lang}"}
            if getattr(args, "json", False):
                print_json(payload)
                return 0
            print(f"# {lang} is brew-managed; activate via: brew upgrade {registry.get(lang, {}).get('brew_formula', lang)}")
        return 0

    def cmd_install(args: argparse.Namespace) -> int:
        try:
            registry = _jvm_load_registry()
            entry = _jvm_lang_resolve_entry(registry, lang, args.alias)
        except (FileNotFoundError, ValueError) as exc:
            print(f"[singine runtime {lang}] ERROR: {exc}", file=sys.stderr)
            return 1
        manager = registry.get(lang, {}).get("manager", "sdkman")
        if manager == "sdkman":
            sdkman_id = entry.get("sdkman_id", args.alias)
            sdkman_init = _java_sdkman_home() / "bin" / "sdkman-init.sh"
            if not sdkman_init.exists():
                print(f"[singine runtime {lang}] ERROR: SDKMAN not found", file=sys.stderr)
                return 1
            print(f"[singine runtime {lang}] Installing {sdkman_id} via SDKMAN...")
            result = subprocess.run(["bash", "-c", f'source "{sdkman_init}" && sdk install {lang} "{sdkman_id}"'])
            return result.returncode
        else:
            formula = registry.get(lang, {}).get("brew_formula", lang)
            print(f"[singine runtime {lang}] {lang.capitalize()} is brew-managed. Run:")
            print(f"  brew install {formula}")
            return 0

    return cmd_list, cmd_inspect, cmd_env, cmd_install


_groovy_list, _groovy_inspect, _groovy_env, _groovy_install = _make_runtime_lang_commands("groovy")
_clojure_list, _clojure_inspect, _clojure_env, _clojure_install = _make_runtime_lang_commands("clojure")


# ── JVM dependency aggregation (singine runtime jvm deps) ─────────────────────

def _m2_exists(group: str, artifact: str, version: str) -> bool:
    """Check if a Maven artifact exists in the local ~/.m2 cache."""
    m2 = Path.home() / ".m2" / "repository"
    jar = m2 / group.replace(".", "/") / artifact / version / f"{artifact}-{version}.jar"
    return jar.exists()


def _jvm_parse_lein(path: Path) -> List[Dict[str, Any]]:
    """Parse :dependencies from a Leiningen project.clj."""
    import re
    text = path.read_text(encoding="utf-8")
    deps: List[Dict[str, Any]] = []
    in_deps = False
    for line in text.splitlines():
        stripped = line.strip()
        if ":dependencies" in stripped:
            in_deps = True
        if not in_deps:
            continue
        m = re.search(r'\[([a-zA-Z0-9._\-]+(?:/[a-zA-Z0-9._\-]+)?)\s+"([^"]+)"\]', stripped)
        if m:
            coord, version = m.group(1), m.group(2)
            if "/" in coord:
                group, artifact = coord.split("/", 1)
            else:
                group = artifact = coord
            deps.append({"group": group, "artifact": artifact, "version": version, "scope": "compile"})
        # Stop when we exit the :dependencies vector
        if in_deps and stripped.startswith(":") and ":dependencies" not in stripped and deps:
            break
    return deps


def _jvm_parse_deps_edn(path: Path) -> List[Dict[str, Any]]:
    """Parse :deps from a Clojure CLI deps.edn."""
    import re
    text = path.read_text(encoding="utf-8")
    deps: List[Dict[str, Any]] = []
    for m in re.finditer(r'([a-zA-Z0-9._\-]+/[a-zA-Z0-9._\-]+)\s*\{:mvn/version\s+"([^"]+)"\}', text):
        coord, version = m.group(1), m.group(2)
        group, artifact = coord.split("/", 1)
        deps.append({"group": group, "artifact": artifact, "version": version, "scope": "compile"})
    return deps


def _jvm_parse_gradle(path: Path) -> List[Dict[str, Any]]:
    """Parse dependencies from a Gradle Groovy DSL build.gradle."""
    import re
    text = path.read_text(encoding="utf-8")
    deps: List[Dict[str, Any]] = []
    scope_kw = r'(?:compileOnly|implementation|runtimeOnly|api|testImplementation|xmlDoclet|annotationProcessor)'
    for m in re.finditer(
        rf'({scope_kw})\s+[\'"]([a-zA-Z0-9._\-]+):([a-zA-Z0-9._\-]+):([0-9][^\s\'"]*)[\'"]',
        text,
    ):
        scope, group, artifact, version = m.group(1), m.group(2), m.group(3), m.group(4)
        deps.append({"group": group, "artifact": artifact, "version": version, "scope": scope})
    return deps


def _jvm_aggregate_deps() -> Dict[str, Any]:
    """Aggregate JVM deps from singine, collibra, and silkpage."""
    configs = [
        {
            "name": "singine-core",
            "path": Path.home() / "ws/git/github/sindoc/singine/core",
            "parsers": [("project.clj", _jvm_parse_lein), ("deps.edn", _jvm_parse_deps_edn)],
        },
        {
            "name": "collibra-edge",
            "path": Path.home() / "ws/git/github/sindoc/collibra/edge/java",
            "parsers": [("build.gradle", _jvm_parse_gradle)],
        },
        {
            "name": "silkpage-core",
            "path": Path.home() / "ws/git/github/sindoc/silkpage/core",
            "parsers": [],
        },
    ]

    projects: List[Dict[str, Any]] = []
    all_deps: Dict[str, Dict] = {}  # (group, artifact, version) → dep + which projects use it

    for cfg in configs:
        seen: set = set()
        project_deps: List[Dict] = []
        sources: List[str] = []

        for filename, parser_fn in cfg["parsers"]:
            build_file = cfg["path"] / filename
            if not build_file.exists():
                continue
            sources.append(filename)
            for dep in parser_fn(build_file):
                key = (dep["group"], dep["artifact"], dep["version"])
                if key in seen:
                    continue
                seen.add(key)
                dep["in_m2"] = _m2_exists(dep["group"], dep["artifact"], dep["version"])
                project_deps.append(dep)
                if key not in all_deps:
                    all_deps[key] = {**dep, "used_by": []}
                all_deps[key]["used_by"].append(cfg["name"])

        projects.append({
            "name": cfg["name"],
            "path": str(cfg["path"]),
            "sources": sources,
            "deps": project_deps,
        })

    shared = [v for v in all_deps.values() if len(v["used_by"]) > 1]
    return {"projects": projects, "total_unique": len(all_deps), "shared": shared}


def cmd_runtime_jvm_deps(args: argparse.Namespace) -> int:
    project_filter = getattr(args, "project", None)
    data = _jvm_aggregate_deps()

    if project_filter:
        data["projects"] = [p for p in data["projects"] if p["name"] == project_filter]
        if not data["projects"]:
            known = [p["name"] for p in _jvm_aggregate_deps()["projects"]]
            print(f"[singine runtime jvm] Unknown project '{project_filter}'. Known: {', '.join(known)}", file=sys.stderr)
            return 1

    if getattr(args, "json", False):
        print_json(data)
        return 0

    for proj in data["projects"]:
        header = f"── {proj['name']}  ({', '.join(proj['sources']) or 'no build files found'})  {proj['path']}"
        print(f"\n{header}")
        print("─" * min(len(header), 100))
        if not proj["deps"]:
            print("  (no Maven/Gradle dependencies declared)")
            continue
        print(f"  {'SCOPE':<14}  {'GROUP':<30}  {'ARTIFACT':<28}  {'VERSION':<14}  M2")
        print(f"  {'─'*14}  {'─'*30}  {'─'*28}  {'─'*14}  ──")
        for dep in proj["deps"]:
            m2 = "✓" if dep["in_m2"] else "·"
            print(f"  {dep['scope']:<14}  {dep['group']:<30}  {dep['artifact']:<28}  {dep['version']:<14}  {m2}")
    print(f"\nTotal unique deps: {data['total_unique']}")
    if data["shared"]:
        print(f"Shared across projects ({len(data['shared'])}):")
        for dep in data["shared"]:
            print(f"  {dep['group']}:{dep['artifact']}:{dep['version']}  ← {', '.join(dep['used_by'])}")
    print()
    return 0


def cmd_server_inspect(args: argparse.Namespace) -> int:
    from .server_surface import server_descriptor

    payload = server_descriptor(
        REPO_ROOT,
        host=args.host,
        port=args.port,
        environment_type=args.environment_type,
    )
    if args.json:
        print_json(payload)
    else:
        server = payload["server"]
        print(f"environment: {payload['environment_type']}")
        print(f"base_url: {server['base_url']}")
        print(f"bind_host: {server['bind_host']}")
        print(f"activity taxonomy: {payload['activity_api']['taxonomy_path']}")
        print(f"activity count: {payload['activity_api']['activity_count']}")
        print(f"docker edge compose: {payload['docker']['edge_compose']}")
        print(f"git branch: {payload['git']['branch'] or '(unknown)'}")
    return 0


def cmd_server_health(args: argparse.Namespace) -> int:
    from .server_surface import ping_server

    base_url = f"http://{args.host}:{args.port}"
    payload = ping_server(base_url, timeout=args.timeout)
    if args.json:
        print_json(payload)
    else:
        if payload.get("ok"):
            print(f"{base_url}/health -> {payload.get('status')} {payload.get('raw_text', '')}")
        else:
            print(f"{base_url}/health -> error: {payload.get('error')}", file=sys.stderr)
    return 0 if payload.get("ok") else 1


def cmd_server_bridge(args: argparse.Namespace) -> int:
    from .server_surface import query_bridge

    base_url = f"http://{args.host}:{args.port}"
    payload = query_bridge(
        base_url,
        action=args.action,
        query=args.query,
        entity=args.entity,
        limit=args.limit,
        realm=getattr(args, "realm", None),
        source_kind=getattr(args, "source_kind", None),
        timeout=args.timeout,
    )
    if args.json:
        print_json(payload)
    else:
        if payload.get("ok"):
            data = payload.get("data")
            if isinstance(data, str):
                print(data)
            else:
                print(json.dumps(data, indent=2))
        else:
            print(payload.get("error", "bridge request failed"), file=sys.stderr)
    return 0 if payload.get("ok") else 1


def cmd_server_test_case(args: argparse.Namespace) -> int:
    from .server_surface import create_server_test_case

    case_root = Path(args.case_root).expanduser()
    try:
        payload = create_server_test_case(
            case_root,
            REPO_ROOT,
            host=args.host,
            port=args.port,
            logseq_url=args.logseq_url,
        )
        if args.run:
            proc = subprocess.run(
                [sys.executable, "-m", "unittest", "py.tests.test_server_surface_commands", "-v"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=60,
            )
            payload["runner"] = {
                "command": "python3 -m unittest py.tests.test_server_surface_commands -v",
                "ok": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
    except Exception as exc:
        payload = {"ok": False, "error": str(exc)}

    if args.json:
        print_json(payload)
        return 0 if payload.get("ok") else 1

    if not payload.get("ok"):
        print(payload.get("error", "server test case generation failed"), file=sys.stderr)
        return 1

    print(f"Created test case at {payload['case_root']}")
    print(f"Readme: {payload['readme_path']}")
    print(f"Activity: {payload['activity_path']}")
    for command in payload["commands"]:
        print(command)
    if args.run and "runner" in payload:
        print(f"Runner exit: {payload['runner']['exit_code']}")
    return 0


def cmd_logseq_inspect(args: argparse.Namespace) -> int:
    from .server_surface import logseq_descriptor

    payload = logseq_descriptor(REPO_ROOT, base_url=args.base_url)
    if args.json:
        print_json(payload)
    else:
        print(f"base_url: {payload['base_url']}")
        print(f"api_endpoint: {payload['api_endpoint']}")
        print(f"token_present: {payload['token_present']}")
        print(f"filesystem fallback: {payload['filesystem_hint']}")
    return 0


def cmd_logseq_ping(args: argparse.Namespace) -> int:
    from .server_surface import ping_logseq

    token = args.token or os.environ.get("LOGSEQ_API_TOKEN")
    payload = ping_logseq(args.base_url, token=token, timeout=args.timeout)
    if args.json:
        print_json(payload)
    else:
        if payload.get("ok"):
            print(f"{payload['base_url']}/api -> {payload.get('status')}")
        else:
            print(payload.get("error", "logseq API request failed"), file=sys.stderr)
    return 0 if payload.get("ok") else 1


def cmd_logseq_graphs(args: argparse.Namespace) -> int:
    from .logseq_org import discover_graphs

    roots = [Path(root).expanduser() for root in args.root] if args.root else None
    graphs = discover_graphs(roots)
    payload = {
        "ok": True,
        "search_roots": [str(root) for root in (roots or [])],
        "graphs": [graph.to_dict() for graph in graphs],
    }
    if args.json:
        print_json(payload)
    else:
        for graph in graphs:
            print(f"{graph.name}\t{graph.root}\t{graph.source_kind}")
    return 0


def cmd_logseq_export_org(args: argparse.Namespace) -> int:
    from .logseq_org import resolve_graph, render_graph_to_org, write_graph_org

    if args.pages_only and args.journals_only:
        print("--pages-only and --journals-only are mutually exclusive", file=sys.stderr)
        return 1
    roots = [Path(root).expanduser() for root in args.root] if args.root else None
    graph = resolve_graph(args.graph, roots)
    include_pages = not args.journals_only
    include_journals = not args.pages_only
    if args.output:
        output_path = write_graph_org(
            graph,
            Path(args.output),
            include_pages=include_pages,
            include_journals=include_journals,
            limit=args.limit,
        )
        payload = {
            "ok": True,
            "graph": graph.to_dict(),
            "output_path": str(output_path),
            "limit": args.limit,
        }
        if args.json:
            print_json(payload)
        else:
            print(output_path)
        return 0

    org_text = render_graph_to_org(
        graph,
        include_pages=include_pages,
        include_journals=include_journals,
        limit=args.limit,
    )
    if args.json:
        print_json({"ok": True, "graph": graph.to_dict(), "org": org_text})
    else:
        print(org_text, end="")
    return 0


def cmd_logseq_export_xml(args: argparse.Namespace) -> int:
    from .logseq_org import export_org_to_xml, resolve_graph, write_graph_org

    if args.pages_only and args.journals_only:
        print("--pages-only and --journals-only are mutually exclusive", file=sys.stderr)
        return 1
    roots = [Path(root).expanduser() for root in args.root] if args.root else None
    graph = resolve_graph(args.graph, roots)
    org_path = write_graph_org(
        graph,
        Path(args.org_output),
        include_pages=not args.journals_only,
        include_journals=not args.pages_only,
        limit=args.limit,
    )
    payload = export_org_to_xml(
        org_path,
        Path(args.xml_output),
        Path(args.om_to_xml_repo),
        emacs_bin=args.emacs_bin,
        extra_load_paths=[Path(path) for path in args.elisp_load_path],
    )
    payload["graph"] = graph.to_dict()
    payload["generated_org_path"] = str(org_path)
    if args.json:
        print_json(payload)
    else:
        if payload.get("ok"):
            print(payload["xml_path"])
        else:
            print(payload.get("stderr") or "Emacs XML export failed", file=sys.stderr)
    return 0 if payload.get("ok") else 1


def cmd_snapshot_save(args: argparse.Namespace) -> int:
    from .server_surface import save_snapshot

    output_path = Path(args.output).expanduser()
    token = args.logseq_token or os.environ.get("LOGSEQ_API_TOKEN")
    payload = save_snapshot(
        output_path,
        REPO_ROOT,
        host=args.host,
        port=args.port,
        environment_type=args.environment_type,
        logseq_url=args.logseq_url,
        logseq_token=token,
    )
    if args.json:
        print_json(payload)
    else:
        print(f"saved snapshot: {payload['output_path']}")
    return 0


# ── Java runtime governance (singine runtime java) ───────────────────────────

def _java_registry_path() -> Path:
    """Locate the Singine Java runtime registry.

    Resolution order:
      1. SINGINE_REGISTRY env var (explicit path to registry.json)
      2. SINGINE_ROOT env var + /runtime/java/registry.json
      3. Hardcoded canonical location
    """
    if r := os.environ.get("SINGINE_REGISTRY"):
        return Path(r)
    if root := os.environ.get("SINGINE_ROOT"):
        return Path(root) / "runtime" / "java" / "registry.json"
    return Path("/private/tmp/singine-personal-os/runtime/java/registry.json")


def _java_load_registry() -> Dict[str, Any]:
    path = _java_registry_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Java registry not found at {path}. "
            "Set SINGINE_ROOT or SINGINE_REGISTRY to point to the registry."
        )
    import json as _json
    return _json.loads(path.read_text(encoding="utf-8"))


def _java_resolve_alias(registry: Dict[str, Any], alias: str) -> Dict[str, Any]:
    for v in registry.get("versions", []):
        if v["alias"] == alias:
            return v
    known = [v["alias"] for v in registry.get("versions", [])]
    raise ValueError(f"Unknown Java alias '{alias}'. Known aliases: {', '.join(known)}")


def _java_read_reqs_singine(directory: Path) -> Optional[str]:
    """Extract :java alias from reqs.singine in the given directory."""
    cfg = directory / "reqs.singine"
    if not cfg.exists():
        return None
    import re
    text = cfg.read_text(encoding="utf-8")
    m = re.search(r':java\s+"([^"]+)"', text)
    return m.group(1) if m else None


def _java_resolve_for_dir(registry: Dict[str, Any], directory: Path) -> tuple[str, str]:
    """Return (alias, source) via the three-step resolution chain."""
    # Step 1: reqs.singine
    alias = _java_read_reqs_singine(directory)
    if alias:
        return alias, "reqs.singine"
    # Step 2: application-map (keyed by directory base name)
    appmap = registry.get("application_map", {})
    alias = appmap.get(directory.name)
    if alias:
        return alias, "application-map"
    # Step 3: policy default
    alias = registry.get("policy", {}).get("default", "lts")
    return alias, "policy-default"


def _java_sdkman_home() -> Path:
    return Path(os.environ.get("SDKMAN_DIR", str(Path.home() / ".sdkman")))


def cmd_runtime_java_list(args: argparse.Namespace) -> int:
    try:
        registry = _java_load_registry()
    except FileNotFoundError as exc:
        print(f"[singine runtime java] ERROR: {exc}", file=sys.stderr)
        return 1

    versions = registry.get("versions", [])
    appmap = registry.get("application_map", {})
    default = registry.get("policy", {}).get("default", "lts")

    if getattr(args, "json", False):
        print_json({"versions": versions, "application_map": appmap, "default": default})
        return 0

    print()
    print(f"{'ALIAS':<12}  {'SDKMAN ID':<28}  {'MAJOR':<8}  {'STATUS':<10}  NOTES")
    print("─" * 80)
    for v in versions:
        marker = " ◀ default" if v["alias"] == default else ""
        print(f"{v['alias']:<12}  {v['sdkman_id']:<28}  {str(v['major']):<8}  {v['status']:<10}  {v.get('notes','')}{marker}")
    print()
    if appmap:
        print(f"{'APPLICATION':<30}  ALIAS")
        print("─" * 45)
        for app, alias in appmap.items():
            print(f"{app:<30}  {alias}")
        print()
    return 0


def cmd_runtime_java_inspect(args: argparse.Namespace) -> int:
    try:
        registry = _java_load_registry()
    except FileNotFoundError as exc:
        print(f"[singine runtime java] ERROR: {exc}", file=sys.stderr)
        return 1

    directory = Path(args.dir).resolve() if getattr(args, "dir", None) else Path.cwd()
    alias, source = _java_resolve_for_dir(registry, directory)
    try:
        version_entry = _java_resolve_alias(registry, alias)
    except ValueError as exc:
        print(f"[singine runtime java] ERROR: {exc}", file=sys.stderr)
        return 1

    sdkman_home = _java_sdkman_home()
    candidate = sdkman_home / "candidates" / "java" / version_entry["sdkman_id"]

    payload = {
        "directory": str(directory),
        "source": source,
        "alias": alias,
        "sdkman_id": version_entry["sdkman_id"],
        "major": version_entry["major"],
        "distribution": version_entry["distribution"],
        "status": version_entry["status"],
        "installed": candidate.exists(),
        "java_home": str(candidate),
    }

    if getattr(args, "json", False):
        print_json(payload)
        return 0

    print(f"directory   : {payload['directory']}")
    print(f"source      : {payload['source']}")
    print(f"alias       : {payload['alias']}")
    print(f"sdkman_id   : {payload['sdkman_id']}")
    print(f"major       : {payload['major']}  ({payload['distribution']})")
    print(f"status      : {payload['status']}")
    print(f"installed   : {'yes' if payload['installed'] else 'no — run: singine runtime java install ' + alias}")
    print(f"java_home   : {payload['java_home']}")
    return 0


def cmd_runtime_java_env(args: argparse.Namespace) -> int:
    """Print export statements so callers can eval: eval $(singine runtime java env)"""
    try:
        registry = _java_load_registry()
    except FileNotFoundError as exc:
        print(f"[singine runtime java] ERROR: {exc}", file=sys.stderr)
        return 1

    if getattr(args, "alias", None):
        alias = args.alias
        source = "explicit"
    else:
        alias, source = _java_resolve_for_dir(registry, Path.cwd())

    try:
        version_entry = _java_resolve_alias(registry, alias)
    except ValueError as exc:
        print(f"[singine runtime java] ERROR: {exc}", file=sys.stderr)
        return 1

    sdkman_home = _java_sdkman_home()
    java_home = sdkman_home / "candidates" / "java" / version_entry["sdkman_id"]

    if getattr(args, "json", False):
        print_json({"alias": alias, "source": source, "java_home": str(java_home),
                    "sdkman_id": version_entry["sdkman_id"]})
        return 0

    # Shell-eval-safe output
    print(f'export JAVA_HOME="{java_home}"')
    print(f'export PATH="{java_home}/bin:$PATH"')
    return 0


def cmd_runtime_java_install(args: argparse.Namespace) -> int:
    try:
        registry = _java_load_registry()
        version_entry = _java_resolve_alias(registry, args.alias)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[singine runtime java] ERROR: {exc}", file=sys.stderr)
        return 1

    sdkman_id = version_entry["sdkman_id"]
    sdkman_init = _java_sdkman_home() / "bin" / "sdkman-init.sh"
    if not sdkman_init.exists():
        print(f"[singine runtime java] ERROR: SDKMAN not found at {sdkman_init}", file=sys.stderr)
        return 1

    print(f"[singine runtime java] Installing {sdkman_id} via SDKMAN...")
    cmd = ["bash", "-c", f'source "{sdkman_init}" && sdk install java "{sdkman_id}"']
    result = subprocess.run(cmd)
    return result.returncode


# ── JVM language registry (Groovy, Clojure) ──────────────────────────────────

def _jvm_registry_path() -> Path:
    if r := os.environ.get("SINGINE_JVM_REGISTRY"):
        return Path(r)
    if root := os.environ.get("SINGINE_ROOT"):
        return Path(root) / "runtime" / "jvm" / "registry.json"
    return Path("/private/tmp/singine-personal-os/runtime/jvm/registry.json")


def _jvm_load_registry() -> Dict[str, Any]:
    path = _jvm_registry_path()
    if not path.exists():
        raise FileNotFoundError(
            f"JVM registry not found at {path}. "
            "Set SINGINE_ROOT or SINGINE_JVM_REGISTRY."
        )
    import json as _json
    return _json.loads(path.read_text(encoding="utf-8"))


def _jvm_lang_read_reqs(directory: Path, lang: str) -> Optional[str]:
    """Read :groovy / :clojure key from reqs.singine."""
    import re
    cfg = directory / "reqs.singine"
    if not cfg.exists():
        return None
    m = re.search(rf':{lang}\s+"([^"]+)"', cfg.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def _jvm_lang_resolve_for_dir(registry: Dict, lang: str, directory: Path) -> tuple[str, str]:
    alias = _jvm_lang_read_reqs(directory, lang)
    if alias:
        return alias, "reqs.singine"
    appmap = registry.get(lang, {}).get("application_map", {})
    alias = appmap.get(directory.name)
    if alias:
        return alias, "application-map"
    alias = registry.get(lang, {}).get("policy", {}).get("default", "lts")
    return alias, "policy-default"


def _jvm_lang_resolve_entry(registry: Dict, lang: str, alias: str) -> Dict[str, Any]:
    for v in registry.get(lang, {}).get("versions", []):
        if v["alias"] == alias:
            return v
    known = [v["alias"] for v in registry.get(lang, {}).get("versions", [])]
    raise ValueError(f"Unknown {lang} alias '{alias}'. Known: {', '.join(known)}")


def _make_runtime_lang_commands(lang: str) -> tuple:
    """Factory returning (list_fn, inspect_fn, env_fn, install_fn) for a JVM language."""

    def cmd_list(args: argparse.Namespace) -> int:
        try:
            registry = _jvm_load_registry()
        except FileNotFoundError as exc:
            print(f"[singine runtime {lang}] ERROR: {exc}", file=sys.stderr)
            return 1
        versions = registry.get(lang, {}).get("versions", [])
        default = registry.get(lang, {}).get("policy", {}).get("default", "")
        manager = registry.get(lang, {}).get("manager", "sdkman")
        if getattr(args, "json", False):
            print_json({"lang": lang, "manager": manager, "versions": versions, "default": default})
            return 0
        print(f"\n{lang.upper()} versions  (manager: {manager})\n")
        print(f"{'ALIAS':<12}  {'VERSION/ID':<28}  {'STATUS':<10}  NOTES")
        print("─" * 72)
        for v in versions:
            vid = v.get("sdkman_id") or v.get("cli_version") or v.get("lib_version", "?")
            marker = " ◀ default" if v["alias"] == default else ""
            print(f"{v['alias']:<12}  {vid:<28}  {v['status']:<10}  {v.get('notes','')}{marker}")
        print()
        return 0

    def cmd_inspect(args: argparse.Namespace) -> int:
        try:
            registry = _jvm_load_registry()
        except FileNotFoundError as exc:
            print(f"[singine runtime {lang}] ERROR: {exc}", file=sys.stderr)
            return 1
        directory = Path(args.dir).resolve() if getattr(args, "dir", None) else Path.cwd()
        alias, source = _jvm_lang_resolve_for_dir(registry, lang, directory)
        try:
            entry = _jvm_lang_resolve_entry(registry, lang, alias)
        except ValueError as exc:
            print(f"[singine runtime {lang}] ERROR: {exc}", file=sys.stderr)
            return 1
        manager = registry.get(lang, {}).get("manager", "sdkman")
        payload = {"lang": lang, "manager": manager, "directory": str(directory),
                   "source": source, "alias": alias, **entry}
        if manager == "sdkman":
            sdkman_id = entry.get("sdkman_id", alias)
            candidate = _java_sdkman_home() / "candidates" / lang / sdkman_id
            payload["installed"] = candidate.exists()
            payload["home"] = str(candidate)
        elif manager == "brew":
            import shutil
            payload["installed"] = bool(shutil.which(lang) or shutil.which("clj"))
        if getattr(args, "json", False):
            print_json(payload)
            return 0
        for k, v in payload.items():
            print(f"{k:<12}: {v}")
        return 0

    def cmd_env(args: argparse.Namespace) -> int:
        try:
            registry = _jvm_load_registry()
        except FileNotFoundError as exc:
            print(f"[singine runtime {lang}] ERROR: {exc}", file=sys.stderr)
            return 1
        alias = getattr(args, "alias", None) or _jvm_lang_resolve_for_dir(registry, lang, Path.cwd())[0]
        try:
            entry = _jvm_lang_resolve_entry(registry, lang, alias)
        except ValueError as exc:
            print(f"[singine runtime {lang}] ERROR: {exc}", file=sys.stderr)
            return 1
        manager = registry.get(lang, {}).get("manager", "sdkman")
        if manager == "sdkman":
            sdkman_id = entry.get("sdkman_id", alias)
            home = _java_sdkman_home() / "candidates" / lang / sdkman_id
            payload = {"alias": alias, "sdkman_id": sdkman_id, "home": str(home)}
            if getattr(args, "json", False):
                print_json(payload)
                return 0
            print(f'export {lang.upper()}_HOME="{home}"')
            print(f'export PATH="{home}/bin:$PATH"')
        else:
            payload = {"alias": alias, "manager": "brew", "note": f"Managed by brew; run: brew upgrade {lang}"}
            if getattr(args, "json", False):
                print_json(payload)
                return 0
            print(f"# {lang} is brew-managed; activate via: brew upgrade {registry.get(lang, {}).get('brew_formula', lang)}")
        return 0

    def cmd_install(args: argparse.Namespace) -> int:
        try:
            registry = _jvm_load_registry()
            entry = _jvm_lang_resolve_entry(registry, lang, args.alias)
        except (FileNotFoundError, ValueError) as exc:
            print(f"[singine runtime {lang}] ERROR: {exc}", file=sys.stderr)
            return 1
        manager = registry.get(lang, {}).get("manager", "sdkman")
        if manager == "sdkman":
            sdkman_id = entry.get("sdkman_id", args.alias)
            sdkman_init = _java_sdkman_home() / "bin" / "sdkman-init.sh"
            if not sdkman_init.exists():
                print(f"[singine runtime {lang}] ERROR: SDKMAN not found", file=sys.stderr)
                return 1
            print(f"[singine runtime {lang}] Installing {sdkman_id} via SDKMAN...")
            result = subprocess.run(["bash", "-c", f'source "{sdkman_init}" && sdk install {lang} "{sdkman_id}"'])
            return result.returncode
        else:
            formula = registry.get(lang, {}).get("brew_formula", lang)
            print(f"[singine runtime {lang}] {lang.capitalize()} is brew-managed. Run:")
            print(f"  brew install {formula}")
            return 0

    return cmd_list, cmd_inspect, cmd_env, cmd_install


_groovy_list, _groovy_inspect, _groovy_env, _groovy_install = _make_runtime_lang_commands("groovy")
_clojure_list, _clojure_inspect, _clojure_env, _clojure_install = _make_runtime_lang_commands("clojure")


# ── JVM dependency aggregation (singine runtime jvm deps) ─────────────────────

def _m2_exists(group: str, artifact: str, version: str) -> bool:
    """Check if a Maven artifact exists in the local ~/.m2 cache."""
    m2 = Path.home() / ".m2" / "repository"
    jar = m2 / group.replace(".", "/") / artifact / version / f"{artifact}-{version}.jar"
    return jar.exists()


def _jvm_parse_lein(path: Path) -> List[Dict[str, Any]]:
    """Parse :dependencies from a Leiningen project.clj."""
    import re
    text = path.read_text(encoding="utf-8")
    deps: List[Dict[str, Any]] = []
    in_deps = False
    for line in text.splitlines():
        stripped = line.strip()
        if ":dependencies" in stripped:
            in_deps = True
        if not in_deps:
            continue
        m = re.search(r'\[([a-zA-Z0-9._\-]+(?:/[a-zA-Z0-9._\-]+)?)\s+"([^"]+)"\]', stripped)
        if m:
            coord, version = m.group(1), m.group(2)
            if "/" in coord:
                group, artifact = coord.split("/", 1)
            else:
                group = artifact = coord
            deps.append({"group": group, "artifact": artifact, "version": version, "scope": "compile"})
        # Stop when we exit the :dependencies vector
        if in_deps and stripped.startswith(":") and ":dependencies" not in stripped and deps:
            break
    return deps


def _jvm_parse_deps_edn(path: Path) -> List[Dict[str, Any]]:
    """Parse :deps from a Clojure CLI deps.edn."""
    import re
    text = path.read_text(encoding="utf-8")
    deps: List[Dict[str, Any]] = []
    for m in re.finditer(r'([a-zA-Z0-9._\-]+/[a-zA-Z0-9._\-]+)\s*\{:mvn/version\s+"([^"]+)"\}', text):
        coord, version = m.group(1), m.group(2)
        group, artifact = coord.split("/", 1)
        deps.append({"group": group, "artifact": artifact, "version": version, "scope": "compile"})
    return deps


def _jvm_parse_gradle(path: Path) -> List[Dict[str, Any]]:
    """Parse dependencies from a Gradle Groovy DSL build.gradle."""
    import re
    text = path.read_text(encoding="utf-8")
    deps: List[Dict[str, Any]] = []
    scope_kw = r'(?:compileOnly|implementation|runtimeOnly|api|testImplementation|xmlDoclet|annotationProcessor)'
    for m in re.finditer(
        rf'({scope_kw})\s+[\'"]([a-zA-Z0-9._\-]+):([a-zA-Z0-9._\-]+):([0-9][^\s\'"]*)[\'"]',
        text,
    ):
        scope, group, artifact, version = m.group(1), m.group(2), m.group(3), m.group(4)
        deps.append({"group": group, "artifact": artifact, "version": version, "scope": scope})
    return deps


def _jvm_aggregate_deps() -> Dict[str, Any]:
    """Aggregate JVM deps from singine, collibra, and silkpage."""
    configs = [
        {
            "name": "singine-core",
            "path": Path.home() / "ws/git/github/sindoc/singine/core",
            "parsers": [("project.clj", _jvm_parse_lein), ("deps.edn", _jvm_parse_deps_edn)],
        },
        {
            "name": "collibra-edge",
            "path": Path.home() / "ws/git/github/sindoc/collibra/edge/java",
            "parsers": [("build.gradle", _jvm_parse_gradle)],
        },
        {
            "name": "silkpage-core",
            "path": Path.home() / "ws/git/github/sindoc/silkpage/core",
            "parsers": [],
        },
    ]

    projects: List[Dict[str, Any]] = []
    all_deps: Dict[str, Dict] = {}  # (group, artifact, version) → dep + which projects use it

    for cfg in configs:
        seen: set = set()
        project_deps: List[Dict] = []
        sources: List[str] = []

        for filename, parser_fn in cfg["parsers"]:
            build_file = cfg["path"] / filename
            if not build_file.exists():
                continue
            sources.append(filename)
            for dep in parser_fn(build_file):
                key = (dep["group"], dep["artifact"], dep["version"])
                if key in seen:
                    continue
                seen.add(key)
                dep["in_m2"] = _m2_exists(dep["group"], dep["artifact"], dep["version"])
                project_deps.append(dep)
                if key not in all_deps:
                    all_deps[key] = {**dep, "used_by": []}
                all_deps[key]["used_by"].append(cfg["name"])

        projects.append({
            "name": cfg["name"],
            "path": str(cfg["path"]),
            "sources": sources,
            "deps": project_deps,
        })

    shared = [v for v in all_deps.values() if len(v["used_by"]) > 1]
    return {"projects": projects, "total_unique": len(all_deps), "shared": shared}


def cmd_runtime_jvm_deps(args: argparse.Namespace) -> int:
    project_filter = getattr(args, "project", None)
    data = _jvm_aggregate_deps()

    if project_filter:
        data["projects"] = [p for p in data["projects"] if p["name"] == project_filter]
        if not data["projects"]:
            known = [p["name"] for p in _jvm_aggregate_deps()["projects"]]
            print(f"[singine runtime jvm] Unknown project '{project_filter}'. Known: {', '.join(known)}", file=sys.stderr)
            return 1

    if getattr(args, "json", False):
        print_json(data)
        return 0

    for proj in data["projects"]:
        header = f"── {proj['name']}  ({', '.join(proj['sources']) or 'no build files found'})  {proj['path']}"
        print(f"\n{header}")
        print("─" * min(len(header), 100))
        if not proj["deps"]:
            print("  (no Maven/Gradle dependencies declared)")
            continue
        print(f"  {'SCOPE':<14}  {'GROUP':<30}  {'ARTIFACT':<28}  {'VERSION':<14}  M2")
        print(f"  {'─'*14}  {'─'*30}  {'─'*28}  {'─'*14}  ──")
        for dep in proj["deps"]:
            m2 = "✓" if dep["in_m2"] else "·"
            print(f"  {dep['scope']:<14}  {dep['group']:<30}  {dep['artifact']:<28}  {dep['version']:<14}  {m2}")
    print(f"\nTotal unique deps: {data['total_unique']}")
    if data["shared"]:
        print(f"Shared across projects ({len(data['shared'])}):")
        for dep in data["shared"]:
            print(f"  {dep['group']}:{dep['artifact']}:{dep['version']}  ← {', '.join(dep['used_by'])}")
    print()
    return 0


def cmd_server_inspect(args: argparse.Namespace) -> int:
    from .server_surface import server_descriptor

    payload = server_descriptor(
        REPO_ROOT,
        host=args.host,
        port=args.port,
        environment_type=args.environment_type,
    )
    if args.json:
        print_json(payload)
    else:
        server = payload["server"]
        print(f"environment: {payload['environment_type']}")
        print(f"base_url: {server['base_url']}")
        print(f"bind_host: {server['bind_host']}")
        print(f"activity taxonomy: {payload['activity_api']['taxonomy_path']}")
        print(f"activity count: {payload['activity_api']['activity_count']}")
        print(f"docker edge compose: {payload['docker']['edge_compose']}")
        print(f"git branch: {payload['git']['branch'] or '(unknown)'}")
    return 0


def cmd_server_health(args: argparse.Namespace) -> int:
    from .server_surface import ping_server

    base_url = f"http://{args.host}:{args.port}"
    payload = ping_server(base_url, timeout=args.timeout)
    if args.json:
        print_json(payload)
    else:
        if payload.get("ok"):
            print(f"{base_url}/health -> {payload.get('status')} {payload.get('raw_text', '')}")
        else:
            print(f"{base_url}/health -> error: {payload.get('error')}", file=sys.stderr)
    return 0 if payload.get("ok") else 1


def cmd_server_bridge(args: argparse.Namespace) -> int:
    from .server_surface import query_bridge

    base_url = f"http://{args.host}:{args.port}"
    payload = query_bridge(
        base_url,
        action=args.action,
        query=args.query,
        entity=args.entity,
        limit=args.limit,
        realm=getattr(args, "realm", None),
        source_kind=getattr(args, "source_kind", None),
        timeout=args.timeout,
    )
    if args.json:
        print_json(payload)
    else:
        if payload.get("ok"):
            data = payload.get("data")
            if isinstance(data, str):
                print(data)
            else:
                print(json.dumps(data, indent=2))
        else:
            print(payload.get("error", "bridge request failed"), file=sys.stderr)
    return 0 if payload.get("ok") else 1


def cmd_server_test_case(args: argparse.Namespace) -> int:
    from .server_surface import create_server_test_case

    case_root = Path(args.case_root).expanduser()
    try:
        payload = create_server_test_case(
            case_root,
            REPO_ROOT,
            host=args.host,
            port=args.port,
            logseq_url=args.logseq_url,
        )
        if args.run:
            proc = subprocess.run(
                [sys.executable, "-m", "unittest", "py.tests.test_server_surface_commands", "-v"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=60,
            )
            payload["runner"] = {
                "command": "python3 -m unittest py.tests.test_server_surface_commands -v",
                "ok": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
    except Exception as exc:
        payload = {"ok": False, "error": str(exc)}

    if args.json:
        print_json(payload)
        return 0 if payload.get("ok") else 1

    if not payload.get("ok"):
        print(payload.get("error", "server test case generation failed"), file=sys.stderr)
        return 1

    print(f"Created test case at {payload['case_root']}")
    print(f"Readme: {payload['readme_path']}")
    print(f"Activity: {payload['activity_path']}")
    for command in payload["commands"]:
        print(command)
    if args.run and "runner" in payload:
        print(f"Runner exit: {payload['runner']['exit_code']}")
    return 0


def cmd_logseq_inspect(args: argparse.Namespace) -> int:
    from .server_surface import logseq_descriptor

    payload = logseq_descriptor(REPO_ROOT, base_url=args.base_url)
    if args.json:
        print_json(payload)
    else:
        print(f"base_url: {payload['base_url']}")
        print(f"api_endpoint: {payload['api_endpoint']}")
        print(f"token_present: {payload['token_present']}")
        print(f"filesystem fallback: {payload['filesystem_hint']}")
    return 0


def cmd_logseq_ping(args: argparse.Namespace) -> int:
    from .server_surface import ping_logseq

    token = args.token or os.environ.get("LOGSEQ_API_TOKEN")
    payload = ping_logseq(args.base_url, token=token, timeout=args.timeout)
    if args.json:
        print_json(payload)
    else:
        if payload.get("ok"):
            print(f"{payload['base_url']}/api -> {payload.get('status')}")
        else:
            print(payload.get("error", "logseq API request failed"), file=sys.stderr)
    return 0 if payload.get("ok") else 1


def cmd_logseq_graphs(args: argparse.Namespace) -> int:
    from .logseq_org import discover_graphs

    roots = [Path(root).expanduser() for root in args.root] if args.root else None
    graphs = discover_graphs(roots)
    payload = {
        "ok": True,
        "search_roots": [str(root) for root in (roots or [])],
        "graphs": [graph.to_dict() for graph in graphs],
    }
    if args.json:
        print_json(payload)
    else:
        for graph in graphs:
            print(f"{graph.name}\t{graph.root}\t{graph.source_kind}")
    return 0


def cmd_logseq_export_org(args: argparse.Namespace) -> int:
    from .logseq_org import resolve_graph, render_graph_to_org, write_graph_org

    if args.pages_only and args.journals_only:
        print("--pages-only and --journals-only are mutually exclusive", file=sys.stderr)
        return 1
    roots = [Path(root).expanduser() for root in args.root] if args.root else None
    graph = resolve_graph(args.graph, roots)
    include_pages = not args.journals_only
    include_journals = not args.pages_only
    if args.output:
        output_path = write_graph_org(
            graph,
            Path(args.output),
            include_pages=include_pages,
            include_journals=include_journals,
            limit=args.limit,
        )
        payload = {
            "ok": True,
            "graph": graph.to_dict(),
            "output_path": str(output_path),
            "limit": args.limit,
        }
        if args.json:
            print_json(payload)
        else:
            print(output_path)
        return 0

    org_text = render_graph_to_org(
        graph,
        include_pages=include_pages,
        include_journals=include_journals,
        limit=args.limit,
    )
    if args.json:
        print_json({"ok": True, "graph": graph.to_dict(), "org": org_text})
    else:
        print(org_text, end="")
    return 0


def cmd_logseq_export_xml(args: argparse.Namespace) -> int:
    from .logseq_org import export_org_to_xml, resolve_graph, write_graph_org

    if args.pages_only and args.journals_only:
        print("--pages-only and --journals-only are mutually exclusive", file=sys.stderr)
        return 1
    roots = [Path(root).expanduser() for root in args.root] if args.root else None
    graph = resolve_graph(args.graph, roots)
    org_path = write_graph_org(
        graph,
        Path(args.org_output),
        include_pages=not args.journals_only,
        include_journals=not args.pages_only,
        limit=args.limit,
    )
    payload = export_org_to_xml(
        org_path,
        Path(args.xml_output),
        Path(args.om_to_xml_repo),
        emacs_bin=args.emacs_bin,
        extra_load_paths=[Path(path) for path in args.elisp_load_path],
    )
    payload["graph"] = graph.to_dict()
    payload["generated_org_path"] = str(org_path)
    if args.json:
        print_json(payload)
    else:
        if payload.get("ok"):
            print(payload["xml_path"])
        else:
            print(payload.get("stderr") or "Emacs XML export failed", file=sys.stderr)
    return 0 if payload.get("ok") else 1


def cmd_snapshot_save(args: argparse.Namespace) -> int:
    from .server_surface import save_snapshot

    output_path = Path(args.output).expanduser()
    token = args.logseq_token or os.environ.get("LOGSEQ_API_TOKEN")
    payload = save_snapshot(
        output_path,
        REPO_ROOT,
        host=args.host,
        port=args.port,
        environment_type=args.environment_type,
        logseq_url=args.logseq_url,
        logseq_token=token,
    )
    if args.json:
        print_json(payload)
    else:
        print(f"saved snapshot: {payload['output_path']}")
    return 0


def cmd_auth_totp_init(args: argparse.Namespace) -> int:
    from .auth_totp import profile_from_args, save_profile

    profile = profile_from_args(args)
    payload = profile.to_dict()
    if args.state:
        payload["state_path"] = str(save_profile(Path(args.state).expanduser(), profile))
    payload["qr_ready"] = False
    payload["qr_note"] = "Use the otpauth URI with a QR-capable renderer later, or import it directly into 1Password or Google Authenticator."
    print_json(payload)
    return 0


def cmd_auth_totp_uri(args: argparse.Namespace) -> int:
    from .auth_totp import profile_from_args

    profile = profile_from_args(args)
    payload = {
        "issuer": profile.issuer,
        "account_name": profile.account_name,
        "provider_hint": profile.provider_hint,
        "otpauth_uri": profile.uri(),
        "compatibility": {
            "onepassword": "supported via standard otpauth URI import",
            "google_authenticator": "supported via standard otpauth URI import",
            "microsoft_authenticator": "planned; same TOTP shape, app validation still pending",
        },
    }
    if args.json:
        print_json(payload)
    else:
        print(payload["otpauth_uri"])
    return 0


def cmd_auth_totp_code(args: argparse.Namespace) -> int:
    from .auth_totp import profile_from_args

    profile = profile_from_args(args)
    payload = {
        "issuer": profile.issuer,
        "account_name": profile.account_name,
        "code": profile.current_code(),
        "period": profile.period,
        "digits": profile.digits,
    }
    if args.json:
        print_json(payload)
    else:
        print(payload["code"])
    return 0


def cmd_auth_totp_verify(args: argparse.Namespace) -> int:
    from .auth_totp import profile_from_args, verify_totp

    profile = profile_from_args(args)
    payload = verify_totp(
        args.code,
        profile.secret,
        period=profile.period,
        digits=profile.digits,
        algorithm=profile.algorithm,
        window=args.window,
    )
    payload["issuer"] = profile.issuer
    payload["account_name"] = profile.account_name
    print_json(payload)
    return 0 if payload.get("ok") else 1


def cmd_auth_login(args: argparse.Namespace) -> int:
    from .auth_totp import profile_from_args, verify_totp

    profile = profile_from_args(args)
    verified = verify_totp(
        args.code,
        profile.secret,
        period=profile.period,
        digits=profile.digits,
        algorithm=profile.algorithm,
        window=args.window,
    )
    if not verified.get("ok"):
        print_json({"ok": False, "error": verified.get("error"), "account_name": profile.account_name})
        return 1
    # TOTP verified — delegate to singine idp login for governed token exchange
    from .idp import cmd_idp_login, DEFAULT_IDP_URL

    # Attach the idp_url attribute that cmd_idp_login expects
    args.idp_url = getattr(args, "idp_url", DEFAULT_IDP_URL)
    args.user_urn = None
    return cmd_idp_login(args)


def cmd_model_catalog(args: argparse.Namespace) -> int:
    from .model_catalog import catalog

    payload = catalog()
    if args.json:
        print_json(payload)
        return 0
    print("Singine model catalog")
    print()
    for section in ["bootstrappers", "auth_operations", "master_data", "reference_data", "entity_families"]:
        print(f"{section.replace('_', ' ')}:")
        for item in payload[section]:
            print(f"  - {item['name']}: {item['description']}")
            print(f"    ref: {item['reference']}")
        print()
    print("collibra bridge:")
    print(f"  asset types: {', '.join(payload['collibra_bridge']['asset_types'])}")
    print(f"  domain types: {', '.join(payload['collibra_bridge']['domain_types'])}")
    print(f"  relation types: {', '.join(payload['collibra_bridge']['relation_types'])}")
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    server = args.server.rstrip("/")
    body = {"id": args.id, "decision": args.decision}
    if args.reason:
        body["reason"] = args.reason
    import urllib.request, ssl
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{server}/decide",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            result = json.loads(resp.read())
    except Exception as exc:
        result = {"ok": False, "error": str(exc), "id": args.id}
    if args.json:
        print_json(result)
    else:
        if result.get("ok"):
            print(f"decision: {result.get('decision')}")
            print(f"id:       {result.get('id')}")
            print(f"urn:      {result.get('urn')}")
            print(f"ts:       {result.get('ts')}")
        else:
            print(f"error: {result.get('error')}", file=sys.stderr)
            return 1
    return 0


def cmd_model_inspect(args: argparse.Namespace) -> int:
    from .model_catalog import inspect_object

    try:
        payload = inspect_object(args.name)
    except KeyError:
        print_json({"ok": False, "error": f"unknown model object: {args.name}"})
        return 1
    print_json(payload)
    return 0


def cmd_campaign_dataset_plan(args: argparse.Namespace) -> int:
    from .dataset_campaign import launch_dataset_campaign, write_campaign

    payload = launch_dataset_campaign(
        title=args.title,
        brief=args.brief,
        active_contracts=args.contract,
        active_contacts=args.contact,
        trusted_realms=args.trusted_realm,
        vocabulary_terms=args.vocabulary_term,
    )
    if args.output:
        output_path = write_campaign(Path(args.output).expanduser(), payload)
        payload["output_path"] = str(output_path)
    if args.json:
        print_json(payload)
    else:
        print(payload.get("output_path") or json.dumps(payload, indent=2))
    return 0


def cmd_demo_zip_neighborhood(args: argparse.Namespace) -> int:
    from .zip_neighborhood_demo import write_zip_neighborhood_demo_bundle

    manifest = write_zip_neighborhood_demo_bundle(
        output_dir=Path(args.output_dir).expanduser(),
        title=args.title,
        domain_db=Path(args.db).expanduser() if args.db else None,
        actor_id=args.actor_id,
    )
    if args.json:
        print_json(manifest)
    else:
        print(manifest["artifacts"]["markdown"])
    return 0


def cmd_platform_blueprint(args: argparse.Namespace) -> int:
    from .platform_blueprint import write_platform_blueprint_bundle

    manifest = write_platform_blueprint_bundle(
        output_dir=Path(args.output_dir).expanduser(),
        title=args.title,
    )
    if args.json:
        print_json(manifest)
    else:
        print(manifest["artifacts"]["markdown"])
    return 0


def cmd_essay_personal_os(args: argparse.Namespace) -> int:
    from .personal_os import write_personal_os_bundle

    manifest = write_personal_os_bundle(
        output_dir=Path(args.output_dir).expanduser(),
        title=args.title,
        onepager=Path(args.onepager).expanduser(),
        metamodel_root=Path(args.metamodel_root).expanduser(),
    )
    if args.json:
        print_json(manifest)
    else:
        print(manifest["artifacts"]["markdown"])
    return 0


# ---------------------------------------------------------------------------
# smtp — test and send via SMTP
# ---------------------------------------------------------------------------

def _load_idp_smtp_config() -> Dict[str, Any]:
    """Read SMTP settings from humble-idp/config/idp.properties, if present."""
    idp_dir = Path.home() / "ws" / "today" / "X0-DigitalIdentity" / "humble-idp"
    props_path = idp_dir / "config" / "idp.properties"
    cfg: Dict[str, Any] = {}
    if not props_path.exists():
        return cfg
    for line in props_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            cfg[k.strip()] = v.strip()
    return cfg


def _op_read(ref: str, fallback: str = "") -> str:
    """Read a 1Password reference via op-read.sh (mirrors cmd_idp_op_read)."""
    humble_idp_dir = Path.home() / "ws" / "today" / "X0-DigitalIdentity" / "humble-idp"
    op_read_sh = humble_idp_dir / "scripts" / "op-read.sh"
    if op_read_sh.exists():
        result = subprocess.run(
            ["bash", str(op_read_sh), ref, fallback],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    # inline fallback: op CLI directly
    result = subprocess.run(
        ["op", "read", "--no-newline", ref],
        capture_output=True, text=True, check=False,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return fallback


def _resolve_smtp_args(args: argparse.Namespace) -> Dict[str, Any]:
    """Merge CLI args > env > idp.properties > 1Password for SMTP settings.

    Property precedence (highest first):
      1. CLI flag  (--user, --password, --host, --port, --from)
      2. Environment variable  (SMTP_USER, SMTP_PASSWORD, SMTP_HOST, SMTP_PORT, SMTP_FROM)
      3. idp.properties plain value  (idp.smtp_user, idp.smtp_host, …)
      4. 1Password via idp.properties op-ref  (idp.smtp_user_op_ref, idp.smtp_password_op_ref, …)
    """
    idp = _load_idp_smtp_config()

    def _op(key: str) -> str:
        ref = idp.get(key, "")
        return _op_read(ref) if ref.startswith("op://") else ""

    host = (
        getattr(args, "host", None)
        or os.environ.get("SMTP_HOST")
        or idp.get("idp.smtp_host", "localhost")
    )
    port = int(
        getattr(args, "port", None)
        or os.environ.get("SMTP_PORT", "")
        or idp.get("idp.smtp_port", "587")
    )
    user = (
        getattr(args, "user", None)
        or os.environ.get("SMTP_USER")
        or idp.get("idp.smtp_user", "")
        or _op("idp.smtp_user_op_ref")
    )
    from_addr = (
        getattr(args, "from_addr", None)
        or os.environ.get("SMTP_FROM")
        or idp.get("idp.smtp_from", "")
        or _op("idp.smtp_from_op_ref")
    )
    password = (
        getattr(args, "password", None)
        or os.environ.get("SMTP_PASSWORD")
        or _op("idp.smtp_password_op_ref")
    )
    return {"host": host, "port": port, "user": user, "from_addr": from_addr, "password": password}


def cmd_smtp_test(args: argparse.Namespace) -> int:
    """Test SMTP connectivity: connect, EHLO, optional auth."""
    import smtplib
    import ssl as ssl_mod

    cfg = _resolve_smtp_args(args)
    host, port, user, password = cfg["host"], cfg["port"], cfg["user"], cfg["password"]

    print(f"[smtp test] host={host} port={port} user={user or '(none)'}")

    try:
        use_ssl = port == 465
        if use_ssl:
            ctx = ssl_mod.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl_mod.CERT_NONE
            print(f"[smtp test] connecting with implicit SSL/TLS ...")
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=10) as smtp:
                code, banner = smtp.ehlo()
                print(f"[smtp test] EHLO {code}: {banner.decode(errors='replace')}")
                if user and password:
                    smtp.login(user, password)
                    print(f"[smtp test] AUTH ok (user={user})")
                elif user:
                    print(f"[smtp test] skipping AUTH — no password provided")
                print("[smtp test] OK")
        else:
            print(f"[smtp test] connecting with STARTTLS ...")
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                code, banner = smtp.ehlo()
                print(f"[smtp test] EHLO {code}: {banner.decode(errors='replace')}")
                if smtp.has_extn("STARTTLS"):
                    ctx = ssl_mod.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl_mod.CERT_NONE
                    smtp.starttls(context=ctx)
                    smtp.ehlo()
                    print(f"[smtp test] STARTTLS negotiated")
                if user and password:
                    smtp.login(user, password)
                    print(f"[smtp test] AUTH ok (user={user})")
                elif user:
                    print(f"[smtp test] skipping AUTH — no password provided")
                print("[smtp test] OK")
    except Exception as exc:
        print(f"[smtp test] FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_smtp_send(args: argparse.Namespace) -> int:
    """Send a test email (defaults: to=self, subject/body are boilerplate)."""
    import smtplib
    import ssl as ssl_mod
    from email.message import EmailMessage

    cfg = _resolve_smtp_args(args)
    host, port, user, password, from_addr = (
        cfg["host"], cfg["port"], cfg["user"], cfg["password"], cfg["from_addr"]
    )
    to_addr = getattr(args, "to", None) or from_addr or user
    subject = getattr(args, "subject", None) or "singine smtp test"
    body = getattr(args, "body", None) or f"singine smtp self-test from {from_addr or user} via {host}:{port}"

    if not to_addr:
        print("[smtp send] --to is required (or set idp.smtp_from in idp.properties)", file=sys.stderr)
        return 1

    msg = EmailMessage()
    msg["From"] = from_addr or user or to_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    print(f"[smtp send] host={host} port={port} from={msg['From']} to={to_addr}")

    try:
        use_ssl = port == 465
        if use_ssl:
            ctx = ssl_mod.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl_mod.CERT_NONE
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=15) as smtp:
                smtp.ehlo()
                if user and password:
                    smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=15) as smtp:
                smtp.ehlo()
                if smtp.has_extn("STARTTLS"):
                    ctx = ssl_mod.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl_mod.CERT_NONE
                    smtp.starttls(context=ctx)
                    smtp.ehlo()
                if user and password:
                    smtp.login(user, password)
                smtp.send_message(msg)
        print(f"[smtp send] sent — check {to_addr}")
    except Exception as exc:
        print(f"[smtp send] FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------------------
# singe — SINGE Is Not Generally Expansive (template engine + people registry)
# ---------------------------------------------------------------------------

def cmd_singe_render(args: argparse.Namespace) -> int:
    """Render a template string, replacing @mentions with governed identities."""
    from .singe import build_registry, render as singe_render
    registry = build_registry()
    fmt = getattr(args, "fmt", "display") or "display"
    template = " ".join(args.template) if isinstance(args.template, list) else args.template
    if not template or template == "-":
        template = sys.stdin.read()
    print(singe_render(template, registry, fmt=fmt))
    return 0


def cmd_singe_people(args: argparse.Namespace) -> int:
    """List all people in the registry."""
    from .singe import build_registry
    registry = build_registry()
    if getattr(args, "json", False):
        import json as _json
        out = []
        for p in registry.all_people():
            out.append({
                "key": p.key,
                "display": p.display,
                "aliases": p.aliases,
                "email": p.email,
                "urn": p.urn,
                "note": p.note,
            })
        print(_json.dumps(out, indent=2))
    else:
        for p in registry.all_people():
            aliases = ", ".join(p.aliases) if p.aliases else ""
            note = f"  — {p.note}" if p.note else ""
            alias_str = f"  [{aliases}]" if aliases else ""
            print(f"@{p.key:<14} {p.display:<28}{alias_str}{note}")
    return 0


def cmd_singe_who(args: argparse.Namespace) -> int:
    """Resolve a single @mention and show full details."""
    from .singe import build_registry
    registry = build_registry()
    mention = args.mention.lstrip("@")
    person = registry.resolve(mention)
    if person is None:
        print(f"[singe who] no match for @{mention}", file=sys.stderr)
        return 1
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps({
            "key": person.key, "display": person.display,
            "aliases": person.aliases, "email": person.email,
            "urn": person.urn, "note": person.note,
        }, indent=2))
    else:
        print(f"@{mention}  →  {person.display}")
        if person.aliases:
            print(f"  aliases : {', '.join('@' + a for a in person.aliases)}")
        if person.email:
            print(f"  email   : {person.email}")
        if person.urn:
            print(f"  urn     : {person.urn}")
        if person.note:
            print(f"  note    : {person.note}")
    return 0


# ── singine ai ────────────────────────────────────────────────────────────────

def _ai_dir() -> Path:
    return REPO_ROOT / "ai"


def _ai_sessions_dir() -> Path:
    return _ai_dir() / "sessions"


def _ai_mandates_dir() -> Path:
    return _ai_dir() / "mandates"


def _ai_config_dir() -> Path:
    return _ai_dir() / "config"


def _edn_str(text: str, key: str, default: str = "") -> str:
    """Extract :key "string" from loose EDN text."""
    import re
    m = re.search(rf"{re.escape(key)}\s+\"([^\"]*)\"", text)
    return m.group(1) if m else default


def _edn_keyword(text: str, key: str, default: str = "") -> str:
    """Extract :key :KEYWORD from loose EDN text."""
    import re
    m = re.search(rf"{re.escape(key)}\s+:(\S+)", text)
    return m.group(1) if m else default


def _edn_int(text: str, key: str, default: int = 0) -> int:
    """Extract :key 42 from loose EDN text."""
    import re
    m = re.search(rf"{re.escape(key)}\s+(\d+)", text)
    return int(m.group(1)) if m else default


def _load_session(session_dir: Path) -> Dict[str, Any]:
    """Load a session directory into a plain dict."""
    s: Dict[str, Any] = {"id": session_dir.name, "dir": str(session_dir)}
    manifest  = session_dir / "manifest.edn"
    perms_f   = session_dir / "permissions.edn"
    commands_f = session_dir / "commands.edn"
    if manifest.exists():
        t = _read_text(manifest)
        s.update({
            "provider":        _edn_keyword(t, ":session/provider"),
            "model":           _edn_str(t, ":session/model"),
            "status":          _edn_keyword(t, ":session/status"),
            "started_at":      _edn_str(t, ":session/started-at"),
            "ended_at":        _edn_str(t, ":session/ended-at"),
            "topic":           _edn_str(t, ":session/topic"),
            "user":            _edn_str(t, ":session/user"),
            "command_count":   _edn_int(t, ":session/command-count"),
            "outcome_type":    _edn_keyword(t, ":outcome/type"),
            "outcome_summary": _edn_str(t, ":outcome/summary"),
            "manifest_raw":    t,
        })
    if perms_f.exists():
        import re
        t = _read_text(perms_f)
        s["permissions_granted"] = len(re.findall(r":permission/id", t))
        s["permissions_denied"]  = len(re.findall(r":permission/id", _edn_str(t, ":permissions/denied", "")))
        s["permissions_raw"] = t
    if commands_f.exists():
        s["commands_raw"] = _read_text(commands_f)
    return s


def cmd_ai_session_list(args: argparse.Namespace) -> int:
    """List all recorded sessions in singine/ai/sessions/."""
    sd = _ai_sessions_dir()
    if not sd.exists():
        print(f"[ai session list] no sessions directory: {sd}", file=sys.stderr)
        return 1
    sessions = sorted([d for d in sd.iterdir() if d.is_dir()])
    if not sessions:
        print("[ai session list] no sessions recorded")
        return 0
    loaded = [_load_session(s) for s in sessions]
    if getattr(args, "json", False):
        clean = [{k: v for k, v in s.items() if not k.endswith("_raw")} for s in loaded]
        print(json.dumps(clean, indent=2))
    else:
        print(f"{'ID':<40} {'PROVIDER':<10} {'MODEL':<26} {'STATUS':<10} STARTED")
        print("─" * 102)
        for s in loaded:
            print(
                f"{s['id']:<40} {s.get('provider','?'):<10} "
                f"{s.get('model','?'):<26} {s.get('status','?'):<10} "
                f"{s.get('started_at','?')[:10]}"
            )
    return 0


def cmd_ai_session_show(args: argparse.Namespace) -> int:
    """Print manifest, permissions, and outcome for a session."""
    session_dir = _ai_sessions_dir() / args.id
    if not session_dir.exists():
        print(f"[ai session show] unknown session: {args.id}", file=sys.stderr)
        return 1
    s = _load_session(session_dir)
    if getattr(args, "json", False):
        clean = {k: v for k, v in s.items() if not k.endswith("_raw")}
        print(json.dumps(clean, indent=2))
        return 0
    print(f"\nSession  : {s['id']}")
    print(f"  Provider : {s.get('provider','?')}  ({s.get('model','?')})")
    print(f"  Status   : {s.get('status','?')}")
    print(f"  User     : {s.get('user','?')}")
    print(f"  Period   : {s.get('started_at','?')[:10]}  →  {s.get('ended_at','?')[:10]}")
    print(f"  Topic    : {s.get('topic','?')[:80]}")
    print(f"  Commands : {s.get('command_count','?')}")
    print(f"  Outcome  : {s.get('outcome_type','?')} — {s.get('outcome_summary','')[:80]}")
    print(f"  Perms    : {s.get('permissions_granted', 0)} granted / {s.get('permissions_denied', 0)} denied")
    if getattr(args, "permissions", False) and "permissions_raw" in s:
        print("\n── permissions.edn " + "─" * 58)
        print(s["permissions_raw"])
    elif "permissions_raw" in s:
        print("\n  hint: use --permissions to show full permissions.edn")
    return 0


def cmd_ai_session_export(args: argparse.Namespace) -> int:
    """Export a session in the requested format (json or edn)."""
    session_dir = _ai_sessions_dir() / args.id
    if not session_dir.exists():
        print(f"[ai session export] unknown session: {args.id}", file=sys.stderr)
        return 1
    fmt = getattr(args, "fmt", "json")
    if fmt == "edn":
        for f in sorted(session_dir.glob("*.edn")):
            print(f";; ── {f.name} " + "─" * (60 - len(f.name)))
            print(_read_text(f))
        return 0
    s = _load_session(session_dir)
    if not getattr(args, "raw", False):
        s = {k: v for k, v in s.items() if not k.endswith("_raw")}
    print(json.dumps(s, indent=2))
    return 0


def cmd_ai_session_dashboard(args: argparse.Namespace) -> int:
    from .session_dashboard import write_dashboard

    payload = write_dashboard(
        output_dir=Path(args.output_dir).expanduser(),
        json_root_dir=Path(args.root_dir).expanduser(),
        repo_ai_dir=Path(args.repo_ai_dir).expanduser(),
        providers=args.provider,
        title=args.title,
        site_url=args.site_url,
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["artifacts"]["html"])
    return 0


def cmd_ai_mandate_list(args: argparse.Namespace) -> int:
    """List all stored mandates in singine/ai/mandates/."""
    md = _ai_mandates_dir()
    if not md.exists():
        print(f"[ai mandate list] no mandates directory: {md}", file=sys.stderr)
        return 1
    mandates = sorted(md.glob("*.edn"))
    if not mandates:
        print("[ai mandate list] no mandates stored")
        return 0
    if getattr(args, "json", False):
        out = []
        for m in mandates:
            t = _read_text(m)
            out.append({
                "file":      m.name,
                "id":        _edn_str(t, ":mandate/id"),
                "grantor":   _edn_str(t, ":mandate/grantor"),
                "grantee":   _edn_str(t, ":mandate/grantee"),
                "status":    _edn_keyword(t, ":mandate/status"),
                "issued_at": _edn_str(t, ":mandate/issued-at"),
            })
        print(json.dumps(out, indent=2))
    else:
        print(f"{'FILE':<30} {'GRANTOR':<12} {'STATUS':<12} ISSUED")
        print("─" * 72)
        for m in mandates:
            t = _read_text(m)
            print(
                f"{m.name:<30} {_edn_str(t, ':mandate/grantor'):<12} "
                f"{_edn_keyword(t, ':mandate/status'):<12} "
                f"{_edn_str(t, ':mandate/issued-at')[:10]}"
            )
    return 0


def cmd_ai_mandate_show(args: argparse.Namespace) -> int:
    """Print a mandate's full permissions and status."""
    import re
    md = _ai_mandates_dir()
    candidates: List[Path] = []
    if md.exists():
        candidates = list(md.glob(f"{args.id}*.edn"))
        if not candidates:
            candidates = [c for c in md.glob("*.edn") if args.id in c.stem]
    if not candidates:
        print(f"[ai mandate show] unknown mandate: {args.id}", file=sys.stderr)
        return 1
    m = candidates[0]
    t = _read_text(m)
    if getattr(args, "json", False):
        perms = re.findall(
            r':action "([^"]+)"\s+:resource "([^"]+)"\s+:decision "([^"]+)"', t
        )
        print(json.dumps({
            "file":       m.name,
            "id":         _edn_str(t, ":mandate/id"),
            "grantor":    _edn_str(t, ":mandate/grantor"),
            "status":     _edn_keyword(t, ":mandate/status"),
            "issued_at":  _edn_str(t, ":mandate/issued-at"),
            "expires_at": _edn_str(t, ":mandate/expires-at"),
            "permissions": [
                {"action": a, "resource": r, "decision": d} for a, r, d in perms
            ],
        }, indent=2))
    else:
        print(t)
    return 0


def cmd_ai_status(args: argparse.Namespace) -> int:
    """Show provider configuration and enabled status."""
    import re
    providers_edn = _ai_config_dir() / "providers.edn"
    if not providers_edn.exists():
        print(f"[ai status] providers.edn not found: {providers_edn}", file=sys.stderr)
        return 1
    t = _read_text(providers_edn)
    blocks = re.split(r"\{:provider/id", t)[1:]
    providers = []
    for block in blocks:
        pid   = re.search(r'"([^"]+)"', block)
        ptype = re.search(r":provider/type\s+:(\S+)", block)
        pname = re.search(r":provider/name\s+\"([^\"]+)\"", block)
        pendp = re.search(r":provider/endpoint\s+\"([^\"]*)\"", block)
        pver  = re.search(r":provider/version\s+\"([^\"]+)\"", block)
        penab = re.search(r":provider/enabled\s+(true|false)", block)
        providers.append({
            "id":       pid.group(1)   if pid   else "?",
            "type":     ptype.group(1) if ptype else "?",
            "name":     pname.group(1) if pname else "?",
            "endpoint": pendp.group(1) if pendp else "",
            "version":  pver.group(1)  if pver  else "?",
            "enabled":  penab.group(1) == "true" if penab else False,
        })
    if getattr(args, "json", False):
        print(json.dumps(providers, indent=2))
        return 0
    print(f"{'ID':<12} {'TYPE':<12} {'VERSION':<28} {'ON':<4} ENDPOINT")
    print("─" * 85)
    for p in providers:
        tick = "✓" if p["enabled"] else "✗"
        print(f"{p['id']:<12} {p['type']:<12} {p['version']:<28} {tick:<4} {p['endpoint']}")
    return 0


def cmd_ai_flush(args: argparse.Namespace) -> int:
    """Flush session EDN files to disk; optionally git-commit."""
    sd = _ai_sessions_dir()
    if not sd.exists():
        print(f"[ai flush] sessions dir not found: {sd}", file=sys.stderr)
        return 1
    session_id = getattr(args, "session", None)
    if session_id:
        targets = [sd / session_id]
        if not targets[0].exists():
            print(f"[ai flush] session not found: {session_id}", file=sys.stderr)
            return 1
    else:
        targets = [d for d in sorted(sd.iterdir()) if d.is_dir()]
    for t in targets:
        edns = list(t.glob("*.edn"))
        print(f"[ai flush] {t.name}  ({len(edns)} EDN files)")
    if getattr(args, "commit", False):
        files = [str(f) for tgt in targets for f in tgt.glob("*.edn")]
        if files:
            r = subprocess.run(["git", "add"] + files, cwd=REPO_ROOT,
                               capture_output=True, text=True)
            if r.returncode != 0:
                print(f"[ai flush] git add failed: {r.stderr.strip()}", file=sys.stderr)
                return 1
            ids = ", ".join(t.name for t in targets)
            msg = f"singine ai flush: {len(files)} EDN file(s) [{ids}]"
            r = subprocess.run(["git", "commit", "-m", msg], cwd=REPO_ROOT,
                               capture_output=True, text=True)
            if r.returncode != 0:
                print(f"[ai flush] git commit failed: {r.stderr.strip()}", file=sys.stderr)
                return 1
            print(f"[ai flush] committed: {msg}")
    return 0


# ---------------------------------------------------------------------------
# collibra — live REST API operations
# ---------------------------------------------------------------------------

def _collibra_ok(result: dict, args: argparse.Namespace) -> int:
    """Print collibra result envelope and return exit code."""
    if getattr(args, "json", True):
        print_json(result)
    else:
        data = result.get("data", [])
        if isinstance(data, list):
            for item in data:
                name = item.get("name") or item.get("displayName") or str(item)
                print(name)
        else:
            print(str(data))
    return 0 if result.get("ok") else 1


def _collibra_err(exc: Exception) -> int:
    print_json({"ok": False, "error": str(exc)})
    return 1


def cmd_collibra_env(args: argparse.Namespace) -> int:
    """Validate Collibra environment configuration."""
    from .collibra_rest import check_env
    print_json(check_env())
    return 0


def cmd_collibra_fetch_community(args: argparse.Namespace) -> int:
    from .collibra_rest import fetch_communities
    try:
        return _collibra_ok(
            fetch_communities(name=getattr(args, "name", None), limit=args.limit), args
        )
    except Exception as exc:
        return _collibra_err(exc)


def cmd_collibra_fetch_domain(args: argparse.Namespace) -> int:
    from .collibra_rest import fetch_domains
    try:
        return _collibra_ok(
            fetch_domains(
                community_id=getattr(args, "community", None),
                domain_type=getattr(args, "type", None),
                limit=args.limit,
            ),
            args,
        )
    except Exception as exc:
        return _collibra_err(exc)


def cmd_collibra_fetch_asset_type(args: argparse.Namespace) -> int:
    from .collibra_rest import fetch_asset_types
    try:
        return _collibra_ok(fetch_asset_types(), args)
    except Exception as exc:
        return _collibra_err(exc)


def cmd_collibra_fetch_view(args: argparse.Namespace) -> int:
    from .collibra_rest import fetch_views
    try:
        return _collibra_ok(
            fetch_views(location=getattr(args, "location", None), limit=args.limit), args
        )
    except Exception as exc:
        return _collibra_err(exc)


def cmd_collibra_fetch_workflow(args: argparse.Namespace) -> int:
    from .collibra_rest import fetch_workflows
    try:
        return _collibra_ok(fetch_workflows(limit=args.limit), args)
    except Exception as exc:
        return _collibra_err(exc)


def cmd_collibra_search(args: argparse.Namespace) -> int:
    from .collibra_rest import search_assets
    try:
        return _collibra_ok(
            search_assets(
                query=args.query,
                asset_type=getattr(args, "type", None),
                domain_id=getattr(args, "domain", None),
                limit=args.limit,
            ),
            args,
        )
    except Exception as exc:
        return _collibra_err(exc)



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="singine",
        description="Singine bridge, context, runtime, XML matrix, and local control command.",
    )
    sub = parser.add_subparsers(dest="command")

def _ai_dir() -> Path:
    return REPO_ROOT / "ai"


def _ai_sessions_dir() -> Path:
    return _ai_dir() / "sessions"


def _ai_mandates_dir() -> Path:
    return _ai_dir() / "mandates"


def _ai_config_dir() -> Path:
    return _ai_dir() / "config"


def _edn_str(text: str, key: str, default: str = "") -> str:
    """Extract :key "string" from loose EDN text."""
    import re
    m = re.search(rf"{re.escape(key)}\s+\"([^\"]*)\"", text)
    return m.group(1) if m else default


def _edn_keyword(text: str, key: str, default: str = "") -> str:
    """Extract :key :KEYWORD from loose EDN text."""
    import re
    m = re.search(rf"{re.escape(key)}\s+:(\S+)", text)
    return m.group(1) if m else default


def _edn_int(text: str, key: str, default: int = 0) -> int:
    """Extract :key 42 from loose EDN text."""
    import re
    m = re.search(rf"{re.escape(key)}\s+(\d+)", text)
    return int(m.group(1)) if m else default


def _load_session(session_dir: Path) -> Dict[str, Any]:
    """Load a session directory into a plain dict."""
    s: Dict[str, Any] = {"id": session_dir.name, "dir": str(session_dir)}
    manifest  = session_dir / "manifest.edn"
    perms_f   = session_dir / "permissions.edn"
    commands_f = session_dir / "commands.edn"
    if manifest.exists():
        t = _read_text(manifest)
        s.update({
            "provider":        _edn_keyword(t, ":session/provider"),
            "model":           _edn_str(t, ":session/model"),
            "status":          _edn_keyword(t, ":session/status"),
            "started_at":      _edn_str(t, ":session/started-at"),
            "ended_at":        _edn_str(t, ":session/ended-at"),
            "topic":           _edn_str(t, ":session/topic"),
            "user":            _edn_str(t, ":session/user"),
            "command_count":   _edn_int(t, ":session/command-count"),
            "outcome_type":    _edn_keyword(t, ":outcome/type"),
            "outcome_summary": _edn_str(t, ":outcome/summary"),
            "manifest_raw":    t,
        })
    if perms_f.exists():
        import re
        t = _read_text(perms_f)
        s["permissions_granted"] = len(re.findall(r":permission/id", t))
        s["permissions_denied"]  = len(re.findall(r":permission/id", _edn_str(t, ":permissions/denied", "")))
        s["permissions_raw"] = t
    if commands_f.exists():
        s["commands_raw"] = _read_text(commands_f)
    return s


def cmd_ai_session_list(args: argparse.Namespace) -> int:
    """List all recorded sessions in singine/ai/sessions/."""
    sd = _ai_sessions_dir()
    if not sd.exists():
        print(f"[ai session list] no sessions directory: {sd}", file=sys.stderr)
        return 1
    sessions = sorted([d for d in sd.iterdir() if d.is_dir()])
    if not sessions:
        print("[ai session list] no sessions recorded")
        return 0
    loaded = [_load_session(s) for s in sessions]
    if getattr(args, "json", False):
        clean = [{k: v for k, v in s.items() if not k.endswith("_raw")} for s in loaded]
        print(json.dumps(clean, indent=2))
    else:
        print(f"{'ID':<40} {'PROVIDER':<10} {'MODEL':<26} {'STATUS':<10} STARTED")
        print("─" * 102)
        for s in loaded:
            print(
                f"{s['id']:<40} {s.get('provider','?'):<10} "
                f"{s.get('model','?'):<26} {s.get('status','?'):<10} "
                f"{s.get('started_at','?')[:10]}"
            )
    return 0


def cmd_ai_session_show(args: argparse.Namespace) -> int:
    """Print manifest, permissions, and outcome for a session."""
    session_dir = _ai_sessions_dir() / args.id
    if not session_dir.exists():
        print(f"[ai session show] unknown session: {args.id}", file=sys.stderr)
        return 1
    s = _load_session(session_dir)
    if getattr(args, "json", False):
        clean = {k: v for k, v in s.items() if not k.endswith("_raw")}
        print(json.dumps(clean, indent=2))
        return 0
    print(f"\nSession  : {s['id']}")
    print(f"  Provider : {s.get('provider','?')}  ({s.get('model','?')})")
    print(f"  Status   : {s.get('status','?')}")
    print(f"  User     : {s.get('user','?')}")
    print(f"  Period   : {s.get('started_at','?')[:10]}  →  {s.get('ended_at','?')[:10]}")
    print(f"  Topic    : {s.get('topic','?')[:80]}")
    print(f"  Commands : {s.get('command_count','?')}")
    print(f"  Outcome  : {s.get('outcome_type','?')} — {s.get('outcome_summary','')[:80]}")
    print(f"  Perms    : {s.get('permissions_granted', 0)} granted / {s.get('permissions_denied', 0)} denied")
    if getattr(args, "permissions", False) and "permissions_raw" in s:
        print("\n── permissions.edn " + "─" * 58)
        print(s["permissions_raw"])
    elif "permissions_raw" in s:
        print("\n  hint: use --permissions to show full permissions.edn")
    return 0


def cmd_ai_session_export(args: argparse.Namespace) -> int:
    """Export a session in the requested format (json or edn)."""
    session_dir = _ai_sessions_dir() / args.id
    if not session_dir.exists():
        print(f"[ai session export] unknown session: {args.id}", file=sys.stderr)
        return 1
    fmt = getattr(args, "fmt", "json")
    if fmt == "edn":
        for f in sorted(session_dir.glob("*.edn")):
            print(f";; ── {f.name} " + "─" * (60 - len(f.name)))
            print(_read_text(f))
        return 0
    s = _load_session(session_dir)
    if not getattr(args, "raw", False):
        s = {k: v for k, v in s.items() if not k.endswith("_raw")}
    print(json.dumps(s, indent=2))
    return 0


def cmd_ai_session_dashboard(args: argparse.Namespace) -> int:
    from .session_dashboard import write_dashboard

    payload = write_dashboard(
        output_dir=Path(args.output_dir).expanduser(),
        json_root_dir=Path(args.root_dir).expanduser(),
        repo_ai_dir=Path(args.repo_ai_dir).expanduser(),
        providers=args.provider,
        title=args.title,
        site_url=args.site_url,
    )
    if args.json:
        print_json(payload)
    else:
        print(payload["artifacts"]["html"])
    return 0


def cmd_ai_mandate_list(args: argparse.Namespace) -> int:
    """List all stored mandates in singine/ai/mandates/."""
    md = _ai_mandates_dir()
    if not md.exists():
        print(f"[ai mandate list] no mandates directory: {md}", file=sys.stderr)
        return 1
    mandates = sorted(md.glob("*.edn"))
    if not mandates:
        print("[ai mandate list] no mandates stored")
        return 0
    if getattr(args, "json", False):
        out = []
        for m in mandates:
            t = _read_text(m)
            out.append({
                "file":      m.name,
                "id":        _edn_str(t, ":mandate/id"),
                "grantor":   _edn_str(t, ":mandate/grantor"),
                "grantee":   _edn_str(t, ":mandate/grantee"),
                "status":    _edn_keyword(t, ":mandate/status"),
                "issued_at": _edn_str(t, ":mandate/issued-at"),
            })
        print(json.dumps(out, indent=2))
    else:
        print(f"{'FILE':<30} {'GRANTOR':<12} {'STATUS':<12} ISSUED")
        print("─" * 72)
        for m in mandates:
            t = _read_text(m)
            print(
                f"{m.name:<30} {_edn_str(t, ':mandate/grantor'):<12} "
                f"{_edn_keyword(t, ':mandate/status'):<12} "
                f"{_edn_str(t, ':mandate/issued-at')[:10]}"
            )
    return 0


def cmd_ai_mandate_show(args: argparse.Namespace) -> int:
    """Print a mandate's full permissions and status."""
    import re
    md = _ai_mandates_dir()
    candidates: List[Path] = []
    if md.exists():
        candidates = list(md.glob(f"{args.id}*.edn"))
        if not candidates:
            candidates = [c for c in md.glob("*.edn") if args.id in c.stem]
    if not candidates:
        print(f"[ai mandate show] unknown mandate: {args.id}", file=sys.stderr)
        return 1
    m = candidates[0]
    t = _read_text(m)
    if getattr(args, "json", False):
        perms = re.findall(
            r':action "([^"]+)"\s+:resource "([^"]+)"\s+:decision "([^"]+)"', t
        )
        print(json.dumps({
            "file":       m.name,
            "id":         _edn_str(t, ":mandate/id"),
            "grantor":    _edn_str(t, ":mandate/grantor"),
            "status":     _edn_keyword(t, ":mandate/status"),
            "issued_at":  _edn_str(t, ":mandate/issued-at"),
            "expires_at": _edn_str(t, ":mandate/expires-at"),
            "permissions": [
                {"action": a, "resource": r, "decision": d} for a, r, d in perms
            ],
        }, indent=2))
    else:
        print(t)
    return 0


def cmd_ai_status(args: argparse.Namespace) -> int:
    """Show provider configuration and enabled status."""
    import re
    providers_edn = _ai_config_dir() / "providers.edn"
    if not providers_edn.exists():
        print(f"[ai status] providers.edn not found: {providers_edn}", file=sys.stderr)
        return 1
    t = _read_text(providers_edn)
    blocks = re.split(r"\{:provider/id", t)[1:]
    providers = []
    for block in blocks:
        pid   = re.search(r'"([^"]+)"', block)
        ptype = re.search(r":provider/type\s+:(\S+)", block)
        pname = re.search(r":provider/name\s+\"([^\"]+)\"", block)
        pendp = re.search(r":provider/endpoint\s+\"([^\"]*)\"", block)
        pver  = re.search(r":provider/version\s+\"([^\"]+)\"", block)
        penab = re.search(r":provider/enabled\s+(true|false)", block)
        providers.append({
            "id":       pid.group(1)   if pid   else "?",
            "type":     ptype.group(1) if ptype else "?",
            "name":     pname.group(1) if pname else "?",
            "endpoint": pendp.group(1) if pendp else "",
            "version":  pver.group(1)  if pver  else "?",
            "enabled":  penab.group(1) == "true" if penab else False,
        })
    if getattr(args, "json", False):
        print(json.dumps(providers, indent=2))
        return 0
    print(f"{'ID':<12} {'TYPE':<12} {'VERSION':<28} {'ON':<4} ENDPOINT")
    print("─" * 85)
    for p in providers:
        tick = "✓" if p["enabled"] else "✗"
        print(f"{p['id']:<12} {p['type']:<12} {p['version']:<28} {tick:<4} {p['endpoint']}")
    return 0


def cmd_ai_flush(args: argparse.Namespace) -> int:
    """Flush session EDN files to disk; optionally git-commit."""
    sd = _ai_sessions_dir()
    if not sd.exists():
        print(f"[ai flush] sessions dir not found: {sd}", file=sys.stderr)
        return 1
    session_id = getattr(args, "session", None)
    if session_id:
        targets = [sd / session_id]
        if not targets[0].exists():
            print(f"[ai flush] session not found: {session_id}", file=sys.stderr)
            return 1
    else:
        targets = [d for d in sorted(sd.iterdir()) if d.is_dir()]
    for t in targets:
        edns = list(t.glob("*.edn"))
        print(f"[ai flush] {t.name}  ({len(edns)} EDN files)")
    if getattr(args, "commit", False):
        files = [str(f) for tgt in targets for f in tgt.glob("*.edn")]
        if files:
            r = subprocess.run(["git", "add"] + files, cwd=REPO_ROOT,
                               capture_output=True, text=True)
            if r.returncode != 0:
                print(f"[ai flush] git add failed: {r.stderr.strip()}", file=sys.stderr)
                return 1
            ids = ", ".join(t.name for t in targets)
            msg = f"singine ai flush: {len(files)} EDN file(s) [{ids}]"
            r = subprocess.run(["git", "commit", "-m", msg], cwd=REPO_ROOT,
                               capture_output=True, text=True)
            if r.returncode != 0:
                print(f"[ai flush] git commit failed: {r.stderr.strip()}", file=sys.stderr)
                return 1
            print(f"[ai flush] committed: {msg}")
    return 0


# ---------------------------------------------------------------------------
# collibra — live REST API operations
# ---------------------------------------------------------------------------

def _collibra_ok(result: dict, args: argparse.Namespace) -> int:
    """Print collibra result envelope and return exit code."""
    if getattr(args, "json", True):
        print_json(result)
    else:
        data = result.get("data", [])
        if isinstance(data, list):
            for item in data:
                name = item.get("name") or item.get("displayName") or str(item)
                print(name)
        else:
            print(str(data))
    return 0 if result.get("ok") else 1


def _collibra_err(exc: Exception) -> int:
    print_json({"ok": False, "error": str(exc)})
    return 1


def cmd_collibra_env(args: argparse.Namespace) -> int:
    """Validate Collibra environment configuration."""
    from .collibra_rest import check_env
    print_json(check_env())
    return 0


def cmd_collibra_fetch_community(args: argparse.Namespace) -> int:
    from .collibra_rest import fetch_communities
    try:
        return _collibra_ok(
            fetch_communities(name=getattr(args, "name", None), limit=args.limit), args
        )
    except Exception as exc:
        return _collibra_err(exc)


def cmd_collibra_fetch_domain(args: argparse.Namespace) -> int:
    from .collibra_rest import fetch_domains
    try:
        return _collibra_ok(
            fetch_domains(
                community_id=getattr(args, "community", None),
                domain_type=getattr(args, "type", None),
                limit=args.limit,
            ),
            args,
        )
    except Exception as exc:
        return _collibra_err(exc)


def cmd_collibra_fetch_asset_type(args: argparse.Namespace) -> int:
    from .collibra_rest import fetch_asset_types
    try:
        return _collibra_ok(fetch_asset_types(), args)
    except Exception as exc:
        return _collibra_err(exc)


def cmd_collibra_fetch_view(args: argparse.Namespace) -> int:
    from .collibra_rest import fetch_views
    try:
        return _collibra_ok(
            fetch_views(location=getattr(args, "location", None), limit=args.limit), args
        )
    except Exception as exc:
        return _collibra_err(exc)


def cmd_collibra_fetch_workflow(args: argparse.Namespace) -> int:
    from .collibra_rest import fetch_workflows
    try:
        return _collibra_ok(fetch_workflows(limit=args.limit), args)
    except Exception as exc:
        return _collibra_err(exc)


def cmd_collibra_search(args: argparse.Namespace) -> int:
    from .collibra_rest import search_assets
    try:
        return _collibra_ok(
            search_assets(
                query=args.query,
                asset_type=getattr(args, "type", None),
                domain_id=getattr(args, "domain", None),
                limit=args.limit,
            ),
            args,
        )
    except Exception as exc:
        return _collibra_err(exc)



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="singine",
        description="Singine bridge, context, runtime, XML matrix, and local control command.",
    )
    sub = parser.add_subparsers(dest="command")

    context_parser = sub.add_parser("context", help="Show terminal context and sourced environment")
    context_parser.add_argument("--shell", choices=["bash", "sh"], help="Report context for a specific shell")
    context_parser.add_argument("--json", action="store_true", help="Emit JSON")
    context_parser.add_argument("--glossary-root", default=str(DEFAULT_GLOSSARY_ROOT))
    context_parser.set_defaults(func=cmd_context)

    bridge_parser = sub.add_parser("bridge", help="SQLite/JDBC bridge operations")
    bridge_parser.add_argument("--db", default="/tmp/sqlite.db", help="SQLite database path")
    bridge_sub = bridge_parser.add_subparsers(dest="subcommand")

    bridge_build = bridge_sub.add_parser("build", help="Build the merged SQLite database")
    bridge_build.add_argument("--db", default="/tmp/sqlite.db", help="SQLite database path")
    bridge_build.set_defaults(func=cmd_bridge_build)

    bridge_sources = bridge_sub.add_parser("sources", help="List bridge sources")
    bridge_sources.add_argument("--db", default="/tmp/sqlite.db", help="SQLite database path")
    bridge_sources.set_defaults(func=cmd_bridge_passthrough)

    bridge_search = bridge_sub.add_parser("search", help="Search bridge fragments")
    bridge_search.add_argument("--db", default="/tmp/sqlite.db", help="SQLite database path")
    bridge_search.add_argument("text")
    bridge_search.add_argument("--limit", type=int, default=20)
    bridge_search.set_defaults(func=cmd_bridge_passthrough)

    bridge_ingest_edge = bridge_sub.add_parser(
        "ingest-edge",
        help="Ingest assets from a running Collibra Edge / DGC endpoint into the bridge",
    )
    bridge_ingest_edge.add_argument(
        "--db", default="/tmp/sqlite.db", help="SQLite database path"
    )
    bridge_ingest_edge.add_argument(
        "--url", default="",
        help="Collibra DGC base URL (default: $COLLIBRA_DGC_URL or https://localhost)",
    )
    bridge_ingest_edge.add_argument(
        "--site-id", default="", dest="site_id",
        help="Logical site ID stored in entity metadata (default: $COLLIBRA_EDGE_SITE_ID)",
    )
    bridge_ingest_edge.add_argument(
        "--verify-tls", action="store_true", default=False, dest="verify_tls",
        help="Verify TLS certificates (default: off for self-signed dev certs)",
    )
    bridge_ingest_edge.set_defaults(func=cmd_bridge_ingest_edge)

    bridge_entity = bridge_sub.add_parser("entity", help="Inspect one bridge entity")
    bridge_entity.add_argument("--db", default="/tmp/sqlite.db", help="SQLite database path")
    bridge_entity.add_argument("iri")
    bridge_entity.set_defaults(func=cmd_bridge_passthrough)

    bridge_sparql = bridge_sub.add_parser("sparql", help="Run supported SPARQL on the bridge")
    bridge_sparql.add_argument("--db", default="/tmp/sqlite.db", help="SQLite database path")
    bridge_sparql.add_argument("query")
    bridge_sparql.set_defaults(func=cmd_bridge_passthrough)

    bridge_graphql = bridge_sub.add_parser("graphql", help="Run GraphQL-shaped queries over the bridge")
    bridge_graphql.add_argument("--db", default="/tmp/sqlite.db", help="SQLite database path")
    bridge_graphql.add_argument("query")
    bridge_graphql.set_defaults(func=cmd_bridge_passthrough)

    bridge_latest = bridge_sub.add_parser("latest-changes", help="List the most recently modified bridge entities across realms")
    bridge_latest.add_argument("--db", default="/tmp/sqlite.db", help="SQLite database path")
    bridge_latest.add_argument("--limit", type=int, default=20)
    bridge_latest.add_argument("--realm", choices=["internal-graph", "external-graph", "filesystem"])
    bridge_latest.add_argument("--source-kind", help="Exact source kind filter")
    bridge_latest.set_defaults(func=cmd_bridge_passthrough)

    jdbc_parser = sub.add_parser("jdbc-url", help="Print the SQLite JDBC URL")
    jdbc_parser.add_argument("--db", default="/tmp/sqlite.db", help="SQLite database path")
    jdbc_parser.set_defaults(func=cmd_jdbc_url)

    xml_parser = sub.add_parser("xml", help="Generate XML request/response matrices")
    xml_sub = xml_parser.add_subparsers(dest="xml_subcommand")

    xml_matrix = xml_sub.add_parser("matrix", help="Run scenarios across dimensions and data categories")
    xml_matrix.add_argument("--db", default="/tmp/sqlite.db", help="SQLite database path")
    xml_matrix.add_argument("--output-dir", default="/tmp/singine-xml-matrix", help="Directory for request/response/heatmap XML")
    xml_matrix.set_defaults(func=cmd_xml_matrix)

    query_parser = sub.add_parser(
        "query",
        help="Multi-backend query dispatcher (git/emacs/logseq/xml/sql/sparql/graphql/docker/sys) and Atom XML realm queries",
    )
    query_sub = query_parser.add_subparsers(dest="query_subcommand")
    query_parser.set_defaults(func=lambda a: (query_parser.print_help(), 1)[1])

    query_latest = query_sub.add_parser("latest-changes", help="Write an Atom request, query latest changes across realms, and write an Atom response")
    query_latest.add_argument("--db", default="/tmp/sqlite.db", help="SQLite database path for local mode")
    query_latest.add_argument("--api-base-url", help="Use the Singine HTTP API bridge instead of local SQLite, e.g. http://127.0.0.1:8080")
    query_latest.add_argument("--limit", type=int, default=20, help="Maximum entries per realm")
    query_latest.add_argument(
        "--realm",
        action="append",
        choices=["internal-graph", "external-graph", "filesystem"],
        default=None,
        help="Realm to query; repeatable",
    )
    query_latest.add_argument("--output-dir", default="/tmp/singine-query-atom", help="Directory for generated Atom files")
    query_latest.add_argument("--request", help="Existing Atom request file to read, or path to write when used with --write-request")
    query_latest.add_argument("--response", help="Response Atom output path")
    query_latest.add_argument("--write-request", action="store_true", help="Always write a fresh request Atom feed before running")
    query_latest.add_argument("--timeout", type=int, default=10, help="HTTP timeout for API mode")
    query_latest.add_argument("--emacsclient-bin", help="Optional emacsclient binary for filesystem summaries")
    query_latest.add_argument("--json", action="store_true", help="Emit JSON")
    query_latest.set_defaults(func=cmd_query_latest_changes)

    query_read = query_sub.add_parser("read-atom", help="Read a generated Atom request or response feed and summarise it")
    query_read.add_argument("atom_path", help="Path to an Atom XML file")
    query_read.add_argument("--json", action="store_true", help="Emit JSON")
    query_read.set_defaults(func=cmd_query_read_atom)

    from .query_dispatch import add_query_backends
    add_query_backends(query_sub)

    realm_parser = sub.add_parser("realm", help="Realm-oriented audits, cron specs, and topic broadcast feeds")
    realm_sub = realm_parser.add_subparsers(dest="realm_subcommand")
    realm_parser.set_defaults(func=lambda a: (realm_parser.print_help(), 1)[1])

    realm_check = realm_sub.add_parser("check", help="Run DNS/TLS/trust/vault checks across realms and write Atom request/response files")
    realm_check.add_argument("--realm", action="append", help="Realm name; repeatable. Domain names are also accepted as realm identifiers.")
    realm_check.add_argument("--domain", action="append", help="Domain or subdomain to audit; repeatable")
    realm_check.add_argument("--service", action="append", choices=["dns", "tls", "trust", "vault"], help="Service family to check; repeatable")
    realm_check.add_argument("--output-dir", default="/tmp/singine-realm")
    realm_check.add_argument("--request", help="Use this request Atom path instead of the default output location")
    realm_check.add_argument("--response", help="Use this response Atom path instead of the default output location")
    realm_check.add_argument("--read-request", action="store_true", help="Read an existing request Atom file instead of generating a new one")
    realm_check.add_argument("--json", action="store_true")
    realm_check.set_defaults(func=cmd_realm_check)

    realm_cron = realm_sub.add_parser("cron-write", help="Write a cron specification, command line, and Atom request/response files")
    realm_cron.add_argument("--cron", required=True, help="Cron expression, for example '*/30 * * * *'")
    realm_cron.add_argument("--realm", action="append", help="Realm name; repeatable")
    realm_cron.add_argument("--domain", action="append", help="Domain or subdomain to audit; repeatable")
    realm_cron.add_argument("--service", action="append", choices=["dns", "tls", "trust", "vault"], help="Service family to schedule; repeatable")
    realm_cron.add_argument("--output-dir", default="/tmp/singine-realm")
    realm_cron.add_argument("--request", help="Use this request Atom path instead of the default output location")
    realm_cron.add_argument("--response", help="Use this response Atom path instead of the default output location")
    realm_cron.add_argument("--cron-file", help="Write the generated cron line here")
    realm_cron.add_argument("--json", action="store_true")
    realm_cron.set_defaults(func=cmd_realm_cron_write)

    realm_broadcast = realm_sub.add_parser("broadcast-interest", help="Write an Atom feed that maps a topic to publication and platform targets")
    realm_broadcast.add_argument("--topic", default="dns-trust-vault-realm-operations")
    realm_broadcast.add_argument("--target", action="append", help="Named broadcast target; repeatable")
    realm_broadcast.add_argument("--realm", action="append", help="Realm name; repeatable")
    realm_broadcast.add_argument("--domain", action="append", help="Domain or subdomain; repeatable")
    realm_broadcast.add_argument("--output-dir", default="/tmp/singine-realm")
    realm_broadcast.add_argument("--request", help="Use this request Atom path instead of the default output location")
    realm_broadcast.add_argument("--response", help="Use this response Atom path instead of the default output location")
    realm_broadcast.add_argument("--json", action="store_true")
    realm_broadcast.set_defaults(func=cmd_realm_broadcast)

    realm_read = realm_sub.add_parser("read-atom", help="Read a generated realm Atom request or response feed and summarise it")
    realm_read.add_argument("atom_path", help="Path to an Atom XML file")
    realm_read.add_argument("--json", action="store_true", help="Emit JSON")
    realm_read.set_defaults(func=cmd_realm_read_atom)

    man_parser = sub.add_parser("man", help="Open or print Singine manpages")
    man_parser.add_argument("topic", nargs="?", default="singine")
    man_parser.add_argument("--raw", action="store_true", help="Print the file path instead of opening man")
    man_parser.set_defaults(func=cmd_man)

    install_parser = sub.add_parser("install", help="Install singine or selected local tool dependencies")
    install_parser.add_argument("subject", nargs="?", choices=["singine", "ant", "xmldoclet", "git-filter-repo"], default="singine")
    install_parser.add_argument("subject", nargs="?", choices=["singine", "ant", "xmldoclet"], default="singine")
    install_parser.add_argument("--prefix", default=str(DEFAULT_PREFIX))
    install_parser.add_argument("--shell", choices=["bash", "sh", "all"], default="all")
    install_parser.add_argument("--mode", choices=["base", "workstation"], default="base")
    install_parser.add_argument("--json", action="store_true")
    install_parser.set_defaults(func=cmd_install)

    git_parser = sub.add_parser("git", help="Git rewrite and repository hygiene helpers")
    git_sub = git_parser.add_subparsers(dest="git_subcommand")
    git_parser.set_defaults(func=lambda a: (git_parser.print_help(), 1)[1])

    git_rm_public_dir = git_sub.add_parser(
        "rm-public-dir",
        help="Plan or run a git-filter-repo rewrite that removes one public directory from selected branch histories",
    )
    git_rm_public_dir.add_argument("repo", help="Repo identifier, for example github/singine or github/sindoc/singine")
    git_rm_public_dir.add_argument("public_dir", help="Relative directory path to remove from history, for example prod/Q3")
    git_rm_public_dir.add_argument("--branch", action="append", help="Branch to rewrite; repeatable")
    git_rm_public_dir.add_argument("-all", "--all", dest="all_branches", action="store_true", help="Discover every local branch whose history contains the target directory")
    git_rm_public_dir.add_argument("--remote", default="origin", help="Git remote to inspect and push later")
    git_rm_public_dir.add_argument("--repo-dir", default=".", help="Local clone to inspect or rewrite")
    git_rm_public_dir.add_argument("--execute", action="store_true", help="Run git-filter-repo locally after planning")
    git_rm_public_dir.add_argument("--json", action="store_true", help="Emit the plan as JSON")
    git_rm_public_dir.set_defaults(func=cmd_git_rm_public_dir)

    template_parser = sub.add_parser("template", help="Generate Singine-aware project templates")
    template_sub = template_parser.add_subparsers(dest="template_command")
    template_parser.set_defaults(func=lambda a: (template_parser.print_help(), 1)[1])

    template_create = template_sub.add_parser(
        "create",
        help="Create a Maven or npm project skeleton with Singine-friendly defaults",
    )
    template_create.add_argument("kind", choices=["maven", "npm"])
    template_create.add_argument("name", help="Project name")
    template_create.add_argument(
        "--dir",
        default=None,
        help="Target directory for the generated template. Defaults to a new project directory under the current directory.",
    )
    template_create.add_argument("--description", help="Project description")
    template_create.add_argument("--force", action="store_true", help="Overwrite existing files")
    template_create.add_argument("--json", action="store_true", help="Emit template metadata as JSON")
    template_create.add_argument("--version", default="0.1.0-SNAPSHOT", help="Project version")
    template_create.add_argument("--group-id", help="Maven groupId")
    template_create.add_argument("--artifact-id", help="Maven artifactId")
    template_create.add_argument("--package-name", help="Java package or npm package name")
    template_create.add_argument("--java-version", default="17", help="Maven Java release target")
    template_create.add_argument("--scope", help="npm scope, without the leading @")
    template_create.add_argument(
        "--module-type",
        choices=["module", "commonjs"],
        default="module",
        help="npm package module format",
    )
    template_create.set_defaults(func=cmd_template_create)

    template_list = template_sub.add_parser(
        "list",
        help="List reusable bundle templates and archetypes registered in Singine",
    )
    template_list.add_argument(
        "--family",
        choices=["template", "archetype"],
        help="Filter the library to one family",
    )
    template_list.add_argument("--json", action="store_true")
    template_list.set_defaults(func=cmd_template_list)

    template_materialize = template_sub.add_parser(
        "materialize",
        help="Materialize a registered reusable template or archetype into an output directory",
    )
    template_materialize.add_argument("name", help="Library entry name, e.g. personal-os-essay")
    template_materialize.add_argument("--output-dir", "-o", required=True, help="Destination directory")
    template_materialize.add_argument("--title", help="Optional title override when supported")
    template_materialize.add_argument("--json", action="store_true")
    template_materialize.set_defaults(func=cmd_template_materialize)

    gen_parser = sub.add_parser("gen", help="Generate command-library and other publishable Singine assets")
    gen_sub = gen_parser.add_subparsers(dest="gen_subcommand")
    gen_parser.set_defaults(func=lambda a: (gen_parser.print_help(), 1)[1])

    gen_command = gen_sub.add_parser("command", help="Capture and publish central command-history assets")
    gen_command_sub = gen_command.add_subparsers(dest="gen_command_subcommand")
    gen_command.set_defaults(func=lambda a: (gen_command.print_help(), 1)[1])

    gen_command_capture = gen_command_sub.add_parser("capture", help="Append one raw shell command to the central Singine command history")
    gen_command_capture.add_argument("--raw", required=True, help="Raw command as typed in the shell history")
    gen_command_capture.add_argument("--shell", default="bash", help="Shell name that issued the command")
    gen_command_capture.add_argument("--pwd", default=os.getcwd(), help="Working directory at execution time")
    gen_command_capture.add_argument("--exit-code", type=int, default=0, help="Command exit status")
    gen_command_capture.add_argument("--history-id", type=int, help="Shell history index for the command")
    gen_command_capture.add_argument("--pid", type=int, help="Shell process id")
    gen_command_capture.add_argument("--session", help="Optional session identifier")
    gen_command_capture.add_argument("--root-dir", help="Command-library root directory (default: ~/.singine/command-library)")
    gen_command_capture.add_argument("--json", action="store_true", help="Emit JSON")
    gen_command_capture.set_defaults(func=cmd_gen_command_capture)

    gen_command_list = gen_command_sub.add_parser("list", help="Generate JSON, Markdown, and HTML command-library assets from captured history")
    gen_command_list.add_argument("--root-dir", help="Command-library root directory (default: ~/.singine/command-library)")
    gen_command_list.add_argument("--output-dir", help="Output directory for generated artifacts")
    gen_command_list.add_argument("--since-days", type=int, help="Only include commands recorded in the last N days")
    gen_command_list.add_argument("--limit", type=int, help="Maximum number of command assets to emit")
    gen_command_list.add_argument("--json", action="store_true", help="Emit JSON")
    gen_command_list.set_defaults(func=cmd_gen_command_list)

    proof_parser = sub.add_parser(
        "proof",
        help="Generate Persian font specimens, bilingual showcase PDFs, and HarfBuzz previews",
    )
    proof_sub = proof_parser.add_subparsers(dest="proof_subcommand")
    proof_parser.set_defaults(func=lambda a: (proof_parser.print_help(), 1)[1])

    proof_specimen = proof_sub.add_parser(
        "specimen",
        help="Build a multi-font Persian specimen PDF with math, Unicode, and ASCII-art checks",
    )
    proof_specimen.add_argument("--output-dir", default=str(REPO_ROOT / "docs" / "target" / "farsi-proof"))
    proof_specimen.add_argument("--title", default="Singine Persian Font Specimen")
    proof_specimen.add_argument(
        "--fonts",
        nargs="+",
        default=["Amiri", "Geeza Pro", "Al Bayan", "Damascus", "Baghdad", "Tahoma"],
        help="Font families to compare",
    )
    proof_specimen.add_argument("--json", action="store_true")
    proof_specimen.set_defaults(func=cmd_proof_specimen)

    proof_showcase = proof_sub.add_parser(
        "showcase",
        help="Build a compact bilingual showcase PDF for complex analysis, entropy, and Dirac typography",
    )
    proof_showcase.add_argument("--output-dir", default=str(REPO_ROOT / "docs" / "target" / "farsi-proof"))
    proof_showcase.add_argument("--title", default="Propagation, Bubbles, And Complex Analysis")
    proof_showcase.add_argument("--font", default="Amiri", help="Primary body font family")
    proof_showcase.add_argument("--json", action="store_true")
    proof_showcase.set_defaults(func=cmd_proof_showcase)

    proof_hb = proof_sub.add_parser(
        "harfbuzz",
        help="Render a direct HarfBuzz preview PDF for one font family",
    )
    proof_hb.add_argument("--output-dir", default=str(REPO_ROOT / "docs" / "target" / "farsi-proof"))
    proof_hb.add_argument("--font", default="Noto Naskh Arabic")
    proof_hb.add_argument("--text", default="سلام فارسی · Complex phase z = re^{iθ} · ∮ f(z) dz")
    proof_hb.add_argument("--json", action="store_true")
    proof_hb.set_defaults(func=cmd_proof_harfbuzz)

    proof_suite = proof_sub.add_parser(
        "suite",
        help="Build specimen, showcase, and HarfBuzz preview artifacts together",
    )
    proof_suite.add_argument("--output-dir", default=str(REPO_ROOT / "docs" / "target" / "farsi-proof"))
    proof_suite.add_argument(
        "--fonts",
        nargs="+",
        default=["Amiri", "Geeza Pro", "Al Bayan", "Damascus", "Baghdad", "Tahoma"],
        help="Font families for the specimen document",
    )
    proof_suite.add_argument("--showcase-font", default="Amiri")
    proof_suite.add_argument("--hb-font", default="Noto Naskh Arabic")
    proof_suite.add_argument("--json", action="store_true")
    proof_suite.set_defaults(func=cmd_proof_suite)

    archetype_parser = sub.add_parser(
        "archetype",
        help="List and materialize higher-level reusable Singine archetypes",
    )
    archetype_sub = archetype_parser.add_subparsers(dest="archetype_command")
    archetype_parser.set_defaults(func=lambda a: (archetype_parser.print_help(), 1)[1])

    archetype_list = archetype_sub.add_parser("list", help="List registered archetypes")
    archetype_list.add_argument("--json", action="store_true")
    archetype_list.set_defaults(func=cmd_template_list, family="archetype")

    archetype_materialize = archetype_sub.add_parser(
        "materialize",
        help="Materialize one registered archetype into an output directory",
    )
    archetype_materialize.add_argument("name", help="Archetype name, e.g. personal-os-essay")
    archetype_materialize.add_argument("--output-dir", "-o", required=True, help="Destination directory")
    archetype_materialize.add_argument("--title", help="Optional title override when supported")
    archetype_materialize.add_argument("--json", action="store_true")
    archetype_materialize.set_defaults(func=cmd_template_materialize)

    dotfiles_parser = sub.add_parser(
        "dotfiles",
        help="Inspect, dashboard, and capture home dotfiles into a controlled repo",
    )
    dotfiles_sub = dotfiles_parser.add_subparsers(dest="dotfiles_command")
    dotfiles_parser.set_defaults(func=lambda a: (dotfiles_parser.print_help(), 1)[1])

    dotfiles_common = argparse.ArgumentParser(add_help=False)
    dotfiles_common.add_argument("--home-dir", default=str(Path.home()))
    dotfiles_common.add_argument("--dotfiles-repo", default="/Users/skh/ws/git/bitbucket/sindoc/dotfiles")

    dotfiles_inspect = dotfiles_sub.add_parser("inspect", parents=[dotfiles_common], help="Inspect managed and unmanaged dotfile targets")
    dotfiles_inspect.add_argument("--json", action="store_true")
    dotfiles_inspect.set_defaults(func=cmd_dotfiles_inspect)

    dotfiles_dashboard = dotfiles_sub.add_parser(
        "dashboard",
        parents=[dotfiles_common],
        help="Write an HTML dashboard for shell, vimrc, Dropbox, Claude, and Logseq control",
    )
    dotfiles_dashboard.add_argument("--output-dir", default=str(REPO_ROOT / "target" / "sindoc.local" / "dotfiles"))
    dotfiles_dashboard.add_argument("--json", action="store_true")
    dotfiles_dashboard.set_defaults(func=cmd_dotfiles_dashboard)

    dotfiles_capture = dotfiles_sub.add_parser(
        "capture",
        parents=[dotfiles_common],
        help="Copy one file target into the dotfiles repo or capture a directory manifest",
    )
    dotfiles_capture.add_argument(
        "name",
        choices=[
            "profile",
            "bash-profile",
            "bashrc",
            "zprofile",
            "zshrc",
            "vimrc",
            "box-shell",
            "claude-home",
            "claude-ws",
            "logseq-home",
            "dropbox",
        ],
    )
    dotfiles_capture.add_argument("--json", action="store_true")
    dotfiles_capture.set_defaults(func=cmd_dotfiles_capture)

    intranet_parser = sub.add_parser(
        "intranet",
        help="Generate and maintain local sindoc.local intranet control pages",
    )
    intranet_sub = intranet_parser.add_subparsers(dest="intranet_command")
    intranet_parser.set_defaults(func=lambda a: (intranet_parser.print_help(), 1)[1])

    intranet_control = intranet_sub.add_parser(
        "control-center",
        help="Write a unified machine and edge runtime control center under sindoc.local",
    )
    intranet_control.add_argument("--output-dir", default=str(REPO_ROOT / "target" / "sindoc.local" / "control"))
    intranet_control.add_argument("--home-dir", default=str(Path.home()))
    intranet_control.add_argument("--dotfiles-repo", default="/Users/skh/ws/git/bitbucket/sindoc/dotfiles")
    intranet_control.add_argument("--ai-root-dir", default=str(Path.home() / ".singine" / "ai"))
    intranet_control.add_argument("--repo-ai-dir", default=str(REPO_ROOT / "ai"))
    intranet_control.add_argument("--json", action="store_true")
    intranet_control.set_defaults(func=cmd_intranet_control_center)

    intranet_publish = intranet_sub.add_parser(
        "publish",
        help="Publish the local sindoc.local intranet through Silkpage-style deploy roots and TLS metadata",
    )
    intranet_publish.add_argument("--site-root", default=str(REPO_ROOT / "target" / "sindoc.local"))
    intranet_publish.add_argument("--deploy-root", default=str(Path.home() / "var" / "deploy" / "sindoc.local"))
    intranet_publish.add_argument("--silkpage-root", default=str(REPO_ROOT.parent / "silkpage"))
    intranet_publish.add_argument("--ssl-dir", default=str(Path.home() / ".config" / "lutino" / "ssl"))
    intranet_publish.add_argument("--domain", default="sindoc.local")
    intranet_publish.add_argument("--no-sync", action="store_true")
    intranet_publish.add_argument("--json", action="store_true")
    intranet_publish.set_defaults(func=cmd_intranet_publish)

    intranet_cert = intranet_sub.add_parser(
        "cert-bootstrap",
        help="Create a local CA and sindoc.local server certificate for Apache / Firefox testing",
    )
    intranet_cert.add_argument("--ssl-dir", default=str(Path.home() / ".config" / "lutino" / "ssl"))
    intranet_cert.add_argument("--domain", default="sindoc.local")
    intranet_cert.add_argument("--force", action="store_true")
    intranet_cert.add_argument("--json", action="store_true")
    intranet_cert.set_defaults(func=cmd_intranet_cert_bootstrap)

    runtime_parser = sub.add_parser("runtime", help="Runtime envelope and capability inspection")
    runtime_sub = runtime_parser.add_subparsers(dest="runtime_subcommand")

    runtime_inspect = runtime_sub.add_parser("inspect", help="Inspect JVM, Racket, Emacs, and shell context")
    runtime_inspect.set_defaults(func=cmd_runtime_inspect)

    runtime_exec = runtime_sub.add_parser("exec", help="Execute a singine subcommand inside a runtime envelope")
    runtime_exec.add_argument("command_args", nargs=argparse.REMAINDER, help="Singine subcommand to execute")
    runtime_exec.set_defaults(func=cmd_runtime_exec)

    runtime_exec_ext = runtime_sub.add_parser(
        "exec-external",
        help="Execute an external binary (e.g. collibractl) inside the singine runtime envelope"
    )
    runtime_exec_ext.add_argument(
        "command_args", nargs=argparse.REMAINDER,
        help="External binary and its arguments, e.g.: collibractl community create --name Foo"
    )
    runtime_exec_ext.set_defaults(func=cmd_runtime_exec_external)

    runtime_java = runtime_sub.add_parser("java", help="Resolve and manage Java runtime versions via the Singine registry")
    runtime_java_sub = runtime_java.add_subparsers(dest="java_subcommand")
    runtime_java.set_defaults(func=lambda a: (runtime_java.print_help(), 1)[1])

    rj_list = runtime_java_sub.add_parser("list", help="List registered Java aliases, SDKMAN IDs, and status")
    rj_list.add_argument("--json", action="store_true", help="Output as JSON")
    rj_list.set_defaults(func=cmd_runtime_java_list)

    rj_inspect = runtime_java_sub.add_parser("inspect", help="Show which Java version a directory resolves to")
    rj_inspect.add_argument("dir", nargs="?", default=None, help="Directory to inspect (default: cwd)")
    rj_inspect.add_argument("--json", action="store_true", help="Output as JSON")
    rj_inspect.set_defaults(func=cmd_runtime_java_inspect)

    rj_env = runtime_java_sub.add_parser("env", help="Print export statements for JAVA_HOME and PATH (for eval)")
    rj_env.add_argument("alias", nargs="?", default=None, help="Registry alias (default: resolve from cwd)")
    rj_env.add_argument("--json", action="store_true", help="Output as JSON")
    rj_env.set_defaults(func=cmd_runtime_java_env)

    rj_install = runtime_java_sub.add_parser("install", help="Install a Java SDKMAN distribution for a registry alias")
    rj_install.add_argument("alias", help="Registry alias to install (e.g. lts, lts-prev, graal)")
    rj_install.set_defaults(func=cmd_runtime_java_install)

    # ── singine runtime groovy ────────────────────────────────────────────────
    runtime_groovy = runtime_sub.add_parser("groovy", help="Resolve and manage Groovy runtime versions (SDKMAN)")
    runtime_groovy_sub = runtime_groovy.add_subparsers(dest="groovy_subcommand")
    runtime_groovy.set_defaults(func=lambda a: (runtime_groovy.print_help(), 1)[1])

    for _name, _fn in [("list", _groovy_list), ("inspect", _groovy_inspect),
                       ("env", _groovy_env), ("install", _groovy_install)]:
        _p = runtime_groovy_sub.add_parser(_name)
        if _name in ("list", "inspect", "env"):
            _p.add_argument("--json", action="store_true")
        if _name in ("inspect",):
            _p.add_argument("dir", nargs="?", default=None)
        if _name in ("env",):
            _p.add_argument("alias", nargs="?", default=None)
        if _name == "install":
            _p.add_argument("alias")
        _p.set_defaults(func=_fn)

    # ── singine runtime clojure ───────────────────────────────────────────────
    runtime_clojure = runtime_sub.add_parser("clojure", help="Inspect Clojure runtime versions (brew-managed)")
    runtime_clojure_sub = runtime_clojure.add_subparsers(dest="clojure_subcommand")
    runtime_clojure.set_defaults(func=lambda a: (runtime_clojure.print_help(), 1)[1])

    for _name, _fn in [("list", _clojure_list), ("inspect", _clojure_inspect),
                       ("env", _clojure_env), ("install", _clojure_install)]:
        _p = runtime_clojure_sub.add_parser(_name)
        if _name in ("list", "inspect", "env"):
            _p.add_argument("--json", action="store_true")
        if _name in ("inspect",):
            _p.add_argument("dir", nargs="?", default=None)
        if _name in ("env",):
            _p.add_argument("alias", nargs="?", default=None)
        if _name == "install":
            _p.add_argument("alias")
        _p.set_defaults(func=_fn)

    # ── singine runtime jvm ───────────────────────────────────────────────────
    runtime_jvm = runtime_sub.add_parser("jvm", help="Cross-JVM operations: deps, shared library management")
    runtime_jvm_sub = runtime_jvm.add_subparsers(dest="jvm_subcommand")
    runtime_jvm.set_defaults(func=lambda a: (runtime_jvm.print_help(), 1)[1])

    rjvm_deps = runtime_jvm_sub.add_parser("deps", help="List JVM dependencies across singine, silkpage, and collibra")
    rjvm_deps.add_argument("project", nargs="?", default=None, help="Filter to a single project (singine-core | collibra-edge | silkpage-core)")
    rjvm_deps.add_argument("--json", action="store_true", help="Output as JSON")
    rjvm_deps.set_defaults(func=cmd_runtime_jvm_deps)

    server_parser = sub.add_parser("server", help="Inspect or query the local Singine HTTP server surface")
    server_sub = server_parser.add_subparsers(dest="server_subcommand")
    server_parser.set_defaults(func=lambda a: (server_parser.print_help(), 1)[1])

    server_inspect = server_sub.add_parser("inspect", help="Show server defaults, interfaces, docker packaging, and git awareness")
    server_inspect.add_argument("--host", default="127.0.0.1", help="Client host for generated URLs (default: 127.0.0.1)")
    server_inspect.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")
    server_inspect.add_argument("--environment-type", choices=["local", "edge", "docker"], help="Override environment type")
    server_inspect.add_argument("--json", action="store_true", help="Emit JSON")
    server_inspect.set_defaults(func=cmd_server_inspect)

    server_health = server_sub.add_parser("health", help="Call GET /health on the Singine HTTP server")
    server_health.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    server_health.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")
    server_health.add_argument("--timeout", type=int, default=10, help="HTTP timeout in seconds")
    server_health.add_argument("--json", action="store_true", help="Emit JSON")
    server_health.set_defaults(func=cmd_server_health)

    server_bridge = server_sub.add_parser("bridge", help="Call the Singine /bridge HTTP facade")
    server_bridge.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    server_bridge.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")
    server_bridge.add_argument("--action", choices=["sources", "search", "entity", "sparql", "graphql", "latest-changes"], default="sources")
    server_bridge.add_argument("--query", help="Bridge query string for search, sparql, or graphql actions")
    server_bridge.add_argument("--entity", help="Entity IRI for the entity action")
    server_bridge.add_argument("--limit", type=int, default=20, help="Result limit (default: 20)")
    server_bridge.add_argument("--realm", choices=["internal-graph", "external-graph", "filesystem"], help="Realm filter for latest-changes")
    server_bridge.add_argument("--source-kind", help="Exact source kind filter for latest-changes")
    server_bridge.add_argument("--timeout", type=int, default=10, help="HTTP timeout in seconds")
    server_bridge.add_argument("--json", action="store_true", help="Emit JSON")
    server_bridge.set_defaults(func=cmd_server_bridge)

    server_test_case = server_sub.add_parser("test-case", help="Create a runnable server/logseq/snapshot test-case bundle")
    server_test_case.add_argument("case_root", nargs="?", default="/tmp/singine-server-case", help="Output directory for the generated test-case bundle")
    server_test_case.add_argument("--host", default="127.0.0.1", help="Server host recorded in the test case")
    server_test_case.add_argument("--port", type=int, default=8080, help="Server port recorded in the test case")
    server_test_case.add_argument("--logseq-url", default="http://127.0.0.1:12315", help="Logseq API base URL recorded in the test case")
    server_test_case.add_argument("--run", action="store_true", help="Run the mock unittest after generating the bundle")
    server_test_case.add_argument("--json", action="store_true", help="Emit JSON")
    server_test_case.set_defaults(func=cmd_server_test_case)

    logseq_parser = sub.add_parser("logseq", help="Inspect or query the Logseq HTTP API surface")
    logseq_sub = logseq_parser.add_subparsers(dest="logseq_subcommand")
    logseq_parser.set_defaults(func=lambda a: (logseq_parser.print_help(), 1)[1])

    logseq_inspect = logseq_sub.add_parser("inspect", help="Show Logseq API defaults and fallback paths")
    logseq_inspect.add_argument("--base-url", default="http://127.0.0.1:12315", help="Logseq API base URL")
    logseq_inspect.add_argument("--json", action="store_true", help="Emit JSON")
    logseq_inspect.set_defaults(func=cmd_logseq_inspect)

    logseq_ping = logseq_sub.add_parser("ping", help="Call the Logseq HTTP API with logseq.App.getCurrentGraph")
    logseq_ping.add_argument("--base-url", default="http://127.0.0.1:12315", help="Logseq API base URL")
    logseq_ping.add_argument("--token", help="Bearer token; falls back to LOGSEQ_API_TOKEN")
    logseq_ping.add_argument("--timeout", type=int, default=10, help="HTTP timeout in seconds")
    logseq_ping.add_argument("--json", action="store_true", help="Emit JSON")
    logseq_ping.set_defaults(func=cmd_logseq_ping)

    logseq_graphs = logseq_sub.add_parser("graphs", help="Discover local Logseq graph base directories")
    logseq_graphs.add_argument("--root", action="append", help="Additional search root; repeatable")
    logseq_graphs.add_argument("--json", action="store_true", help="Emit JSON")
    logseq_graphs.set_defaults(func=cmd_logseq_graphs)

    logseq_export_org = logseq_sub.add_parser("export-org", help="Render a Logseq graph as a consolidated Org document")
    logseq_export_org.add_argument("--graph", required=True, help="Graph name or path")
    logseq_export_org.add_argument("--root", action="append", help="Additional search root; repeatable")
    logseq_export_org.add_argument("--output", help="Write Org output to this path; defaults to stdout")
    logseq_export_org.add_argument("--limit", type=int, help="Limit exported files")
    logseq_export_org.add_argument("--pages-only", action="store_true", help="Export page files only")
    logseq_export_org.add_argument("--journals-only", action="store_true", help="Export journal files only")
    logseq_export_org.add_argument("--json", action="store_true", help="Emit JSON")
    logseq_export_org.set_defaults(func=cmd_logseq_export_org)

    logseq_export_xml = logseq_sub.add_parser("export-xml", help="Export a Logseq graph to Org and then to XML with Emacs")
    logseq_export_xml.add_argument("--graph", required=True, help="Graph name or path")
    logseq_export_xml.add_argument("--root", action="append", help="Additional search root; repeatable")
    logseq_export_xml.add_argument("--org-output", required=True, help="Generated Org file path")
    logseq_export_xml.add_argument("--xml-output", required=True, help="Generated XML file path")
    logseq_export_xml.add_argument("--om-to-xml-repo", default="/Users/skh/ws/git/codeberg/ndw/org-to-xml", help="Path containing om-to-xml.el")
    logseq_export_xml.add_argument("--elisp-load-path", action="append", default=[], help="Extra Emacs load path for dependencies such as org-ml; repeatable")
    logseq_export_xml.add_argument("--emacs-bin", default="emacs", help="Emacs executable to run in batch mode")
    logseq_export_xml.add_argument("--limit", type=int, help="Limit exported files")
    logseq_export_xml.add_argument("--pages-only", action="store_true", help="Export page files only")
    logseq_export_xml.add_argument("--journals-only", action="store_true", help="Export journal files only")
    logseq_export_xml.add_argument("--json", action="store_true", help="Emit JSON")
    logseq_export_xml.set_defaults(func=cmd_logseq_export_xml)

    snapshot_parser = sub.add_parser("snapshot", help="Persist a full Singine runtime, server, and Logseq context snapshot")
    snapshot_sub = snapshot_parser.add_subparsers(dest="snapshot_subcommand")
    snapshot_parser.set_defaults(func=lambda a: (snapshot_parser.print_help(), 1)[1])

    snapshot_save = snapshot_sub.add_parser("save", help="Save a single JSON snapshot under ~/.singine/context or a chosen path")
    snapshot_save.add_argument("--output", default=str(Path.home() / ".singine" / "context" / "latest.json"), help="Output JSON path")
    snapshot_save.add_argument("--host", default="127.0.0.1", help="Server host to record in the snapshot")
    snapshot_save.add_argument("--port", type=int, default=8080, help="Server port to record in the snapshot")
    snapshot_save.add_argument("--environment-type", choices=["local", "edge", "docker"], help="Override environment type")
    snapshot_save.add_argument("--logseq-url", default="http://127.0.0.1:12315", help="Logseq API base URL")
    snapshot_save.add_argument("--logseq-token", help="Bearer token to mark as present in the snapshot")
    snapshot_save.add_argument("--json", action="store_true", help="Emit JSON")
    snapshot_save.set_defaults(func=cmd_snapshot_save)

    auth_parser = sub.add_parser("auth", help="Authentication and login bootstrap operations")
    auth_sub = auth_parser.add_subparsers(dest="auth_subcommand")

    common_totp = argparse.ArgumentParser(add_help=False)
    common_totp.add_argument("--state", help="Path to a saved TOTP profile JSON file")
    common_totp.add_argument("--secret", help="Base32 TOTP secret")
    common_totp.add_argument("--issuer", default="Singine")
    common_totp.add_argument("--account-name", default="user@singine.local")
    common_totp.add_argument("--digits", type=int, default=6)
    common_totp.add_argument("--period", type=int, default=30)
    common_totp.add_argument("--algorithm", default="SHA1")
    common_totp.add_argument("--provider", default="otp", help="Hint such as 1password, google-authenticator, or microsoft-authenticator")

    totp_parser = auth_sub.add_parser("totp", help="TOTP provisioning operations")
    totp_sub = totp_parser.add_subparsers(dest="totp_subcommand")

    totp_init = totp_sub.add_parser("init", help="Create a TOTP profile and provisioning URI", parents=[common_totp])
    totp_init.set_defaults(func=cmd_auth_totp_init)

    totp_uri = totp_sub.add_parser("uri", help="Print the provisioning URI", parents=[common_totp])
    totp_uri.add_argument("--json", action="store_true")
    totp_uri.set_defaults(func=cmd_auth_totp_uri)

    totp_code = totp_sub.add_parser("code", help="Print the current one-time code", parents=[common_totp])
    totp_code.add_argument("--json", action="store_true")
    totp_code.set_defaults(func=cmd_auth_totp_code)

    totp_verify = totp_sub.add_parser("verify", help="Verify a submitted TOTP code", parents=[common_totp])
    totp_verify.add_argument("code")
    totp_verify.add_argument("--window", type=int, default=1)
    totp_verify.set_defaults(func=cmd_auth_totp_verify)

    login_parser = auth_sub.add_parser("login", help="Verify TOTP and open a local Singine session", parents=[common_totp])
    login_parser.add_argument("--code", required=True)
    login_parser.add_argument("--window", type=int, default=1)
    login_parser.set_defaults(func=cmd_auth_login)

    # ── idp — humble identity provider ───────────────────────────────────
    from .idp import build_idp_parser
    build_idp_parser(sub)

    decide_parser = sub.add_parser("decide", help="Issue a governance decision request for an asset")
    decide_parser.add_argument("id", help="Asset or document ID (e.g. sind0c)")
    decide_parser.add_argument("--decision", default="pending",
                               choices=["approve", "reject", "defer", "escalate", "pending"],
                               help="Decision type (default: pending)")
    decide_parser.add_argument("--reason", help="Optional reason or note")
    decide_parser.add_argument("--server", default="http://localhost:8080",
                               help="Singine server base URL (default: http://localhost:8080)")
    decide_parser.add_argument("--json", action="store_true")
    decide_parser.set_defaults(func=cmd_decide)

    model_parser = sub.add_parser("model", help="Catalog Singine model objects and bridge surfaces")
    model_sub = model_parser.add_subparsers(dest="model_subcommand")

    model_catalog_parser = model_sub.add_parser("catalog", help="List bootstrappers, data objects, and metamodel values")
    model_catalog_parser.add_argument("--json", action="store_true")
    model_catalog_parser.set_defaults(func=cmd_model_catalog)

    model_inspect_parser = model_sub.add_parser("inspect", help="Inspect one named model object or Collibra bridge value")
    model_inspect_parser.add_argument("name")
    model_inspect_parser.set_defaults(func=cmd_model_inspect)

    campaign_parser = sub.add_parser("campaign", help="Generate governed campaign plans from Singine core concepts")
    campaign_sub = campaign_parser.add_subparsers(dest="campaign_subcommand")
    campaign_parser.set_defaults(func=lambda a: (campaign_parser.print_help(), 1)[1])

    campaign_dataset = campaign_sub.add_parser(
        "dataset-plan",
        help="Create a phased dataset collection plan driven by contracts, contacts, vocabulary, and trusted realms",
    )
    campaign_dataset.add_argument("--title", default="Contract-Linked Dataset Campaign")
    campaign_dataset.add_argument("--brief", required=True, help="Plain-language campaign brief")
    campaign_dataset.add_argument("--contract", action="append", help="Active contract identifier or label; repeatable")
    campaign_dataset.add_argument("--contact", action="append", help="Active contact or stakeholder; repeatable")
    campaign_dataset.add_argument("--trusted-realm", action="append", help="Trusted realm or domain; repeatable")
    campaign_dataset.add_argument("--vocabulary-term", action="append", help="Extra vocabulary term to fold into the campaign glossary")
    campaign_dataset.add_argument("--output", help="Write the campaign plan to this JSON file")
    campaign_dataset.add_argument("--json", action="store_true")
    campaign_dataset.set_defaults(func=cmd_campaign_dataset_plan)

    platform_parser = sub.add_parser("platform", help="Generate platform blueprints and scaffolds")
    platform_sub = platform_parser.add_subparsers(dest="platform_subcommand")
    platform_parser.set_defaults(func=lambda a: (platform_parser.print_help(), 1)[1])

    platform_blueprint = platform_sub.add_parser(
        "blueprint",
        help="Write a Singine/Collibra/Flowable/OpenShift platform blueprint and starter scaffold",
    )
    platform_blueprint.add_argument("--title", default="Singine Multi-Model Platform Blueprint")
    platform_blueprint.add_argument("--output-dir", default="/tmp/singine-platform-blueprint")
    platform_blueprint.add_argument("--json", action="store_true")
    platform_blueprint.set_defaults(func=cmd_platform_blueprint)

    essay_parser = sub.add_parser(
        "essay",
        help="Generate essay bundles and reflective publication artefacts",
    )
    essay_sub = essay_parser.add_subparsers(dest="essay_subcommand")
    essay_parser.set_defaults(func=lambda a: (essay_parser.print_help(), 1)[1])

    essay_personal_os = essay_sub.add_parser(
        "personal-os",
        help="Write a personal operating system essay bundle across Markdown, HTML, SVG, LaTeX, XML, SinLisp, Ballerina, C, Rust, Pico, and ixml",
    )
    essay_personal_os.add_argument("--title", default="Singine Personal Operating System")
    essay_personal_os.add_argument("--output-dir", default="/tmp/singine-personal-os")
    essay_personal_os.add_argument("--onepager", default="/Users/skh/ws/today/cleanUp/sindoc42-onepager.pdf")
    essay_personal_os.add_argument(
        "--metamodel-root",
        default="/Users/skh/ws/today/metamodel/reference/current/latest/lutino.collibra.singine.process.C213(1)",
    )
    essay_personal_os.add_argument("--json", action="store_true")
    essay_personal_os.set_defaults(func=cmd_essay_personal_os)

    from .policy import add_policy_parser
    add_policy_parser(sub)

    from .domain import add_domain_parser
    add_domain_parser(sub)

    from .pg import add_pg_parser
    add_pg_parser(sub)

    from .edge import add_edge_parser
    add_edge_parser(sub)

    from .mms import add_mms_parser
    add_mms_parser(sub)

    # ── singe — SINGE Is Not Generally Expansive (template + people) ────────
    singe_parser = sub.add_parser(
        "singe",
        help="SINGE template engine — render @mentions into governed identities",
    )
    singe_sub = singe_parser.add_subparsers(dest="singe_subcommand")

    singe_render_p = singe_sub.add_parser(
        "render",
        help="Render a template, replacing @mentions with display names",
    )
    singe_render_p.add_argument(
        "template", nargs="*",
        help="Template string (use - or omit to read from stdin)",
    )
    singe_render_p.add_argument(
        "--fmt",
        choices=["display", "short", "email", "urn", "key"],
        default="display",
        help="Output format for each resolved mention (default: display)",
    )
    singe_render_p.set_defaults(func=cmd_singe_render)

    singe_people_p = singe_sub.add_parser("people", help="List all people in the registry")
    singe_people_p.add_argument("--json", action="store_true")
    singe_people_p.set_defaults(func=cmd_singe_people)

    singe_who_p = singe_sub.add_parser("who", help="Resolve a single @mention")
    singe_who_p.add_argument("mention", help="Mention to resolve, e.g. @si or @stal")
    singe_who_p.add_argument("--json", action="store_true")
    singe_who_p.set_defaults(func=cmd_singe_who)

    # ── photo — Apple Photos review export workflows ────────────────────────
    from .photo import (
        DEFAULT_DB_PATH as PHOTO_DEFAULT_DB_PATH,
        DEFAULT_PHOTOS_LIBRARY_ROOT as PHOTO_DEFAULT_LIBRARY_ROOT,
        DEFAULT_REVIEW_CITIES as PHOTO_DEFAULT_REVIEW_CITIES,
        cmd_photo_count,
        cmd_photo_export_review,
        cmd_photo_test_case,
    )

    photo_parser = sub.add_parser(
        "photo",
        help="Apple Photos queries and lightweight review exports",
    )
    photo_sub = photo_parser.add_subparsers(dest="photo_subcommand")
    photo_parser.set_defaults(func=lambda a: (photo_parser.print_help(), 1)[1])

    photo_count = photo_sub.add_parser(
        "count-city",
        help="Count still photos whose Apple Photos moment titles match city fragments",
    )
    photo_count.add_argument(
        "--city",
        action="append",
        default=None,
        help="City fragment to match in Apple Photos moment titles/subtitles (repeatable)",
    )
    photo_count.add_argument(
        "--db",
        default=str(PHOTO_DEFAULT_DB_PATH),
        help=f"Photos SQLite database path (default: {PHOTO_DEFAULT_DB_PATH})",
    )
    photo_count.add_argument("--json", action="store_true")
    photo_count.set_defaults(func=cmd_photo_count)

    photo_export = photo_sub.add_parser(
        "export-review",
        help="Export review JPEGs from Apple Photos for matching city moments",
    )
    photo_export.add_argument(
        "out_root",
        nargs="?",
        default=str(Path.home() / "Pictures" / "review-exports" / "beirut-shiraz"),
        help="Output root directory (default: ~/Pictures/review-exports/beirut-shiraz)",
    )
    photo_export.add_argument(
        "--city",
        action="append",
        default=None,
        help="City fragment to match in Apple Photos moment titles/subtitles (repeatable)",
    )
    photo_export.add_argument(
        "--library-root",
        default=str(PHOTO_DEFAULT_LIBRARY_ROOT),
        help=f"Apple Photos library root (default: {PHOTO_DEFAULT_LIBRARY_ROOT})",
    )
    photo_export.add_argument(
        "--db",
        default=str(PHOTO_DEFAULT_DB_PATH),
        help=f"Photos SQLite database path (default: {PHOTO_DEFAULT_DB_PATH})",
    )
    photo_export.add_argument("--max-kb", type=int, default=500, help="Maximum JPEG size in KB (default: 500)")
    photo_export.add_argument("--max-dim", type=int, default=2560, help="Maximum width/height in pixels (default: 2560)")
    photo_export.add_argument("--limit", type=int, default=0, help="Stop after N exported files (default: unlimited)")
    photo_export.add_argument("--json", action="store_true")
    photo_export.set_defaults(func=cmd_photo_export_review)

    photo_test_case = photo_sub.add_parser(
        "test-case",
        help="Create a self-contained Apple Photos fixture for singine photo demos and tests",
    )
    photo_test_case.add_argument(
        "case_root",
        nargs="?",
        default="/tmp/singine-photo-case",
        help="Root directory for the generated fixture and output commands (default: /tmp/singine-photo-case)",
    )
    photo_test_case.add_argument("--json", action="store_true")
    photo_test_case.set_defaults(func=cmd_photo_test_case)

    # ── transfer — sync, ssh, sftp, queue, stack, structure, XML processing ─
    from .transfer import (
        cmd_transfer_sync, cmd_transfer_ssh, cmd_transfer_sftp,
        cmd_transfer_queue, cmd_transfer_stack, cmd_transfer_structure,
        cmd_transfer_process_request, cmd_transfer_generate_response,
        cmd_transfer_project, cmd_transfer_analyze_result, cmd_transfer_move,
        cmd_transfer_find,
    )

    find_parser = sub.add_parser(
        "find",
        help="Find filesystem paths related to a topic",
    )
    find_parser.add_argument(
        "activity",
        choices=["filesAboutTopic"],
        help="Activity to invoke. Use filesAboutTopic to search path names by topic.",
    )
    find_parser.add_argument("topic", help="Topic fragment to match in file or directory names")
    find_parser.add_argument(
        "--root-dir",
        default=".",
        help="Directory to search from (default: current directory)",
    )
    find_parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="Maximum directory depth to traverse below the root (default: 3)",
    )
    find_parser.add_argument(
        "--type",
        dest="path_type",
        choices=["any", "file", "dir"],
        default="any",
        help="Restrict matches to files, directories, or either (default: any)",
    )
    find_parser.add_argument(
        "-0", "--null",
        action="store_true",
        help="Emit NUL-delimited paths instead of newline-delimited paths",
    )
    find_parser.add_argument("--json", action="store_true", help="Emit JSON")
    find_parser.set_defaults(func=cmd_transfer_find)

    mv_parser = sub.add_parser(
        "mv",
        help="Move filesystem paths from stdin into a destination directory",
    )
    mv_parser.add_argument(
        "activity",
        choices=["fileListTo"],
        help="Activity to invoke. Use fileListTo to move stdin-listed files into a directory.",
    )
    mv_parser.add_argument("dest_dir", help="Destination directory")
    mv_parser.add_argument(
        "-0", "--null",
        action="store_true",
        help="Read NUL-delimited paths from stdin instead of newline-delimited paths",
    )
    mv_parser.add_argument(
        "--mkdir",
        action="store_true",
        help="Create the destination directory if it does not exist",
    )
    mv_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned moves without changing the filesystem",
    )
    mv_parser.add_argument("--json", action="store_true", help="Emit JSON")
    mv_parser.set_defaults(func=cmd_transfer_move)

    find_parser = sub.add_parser(
        "find",
        help="Find filesystem paths related to a topic",
    )
    find_parser.add_argument(
        "activity",
        choices=["filesAboutTopic"],
        help="Activity to invoke. Use filesAboutTopic to search path names by topic.",
    )
    find_parser.add_argument("topic", help="Topic fragment to match in file or directory names")
    find_parser.add_argument(
        "--root-dir",
        default=".",
        help="Directory to search from (default: current directory)",
    )
    find_parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="Maximum directory depth to traverse below the root (default: 3)",
    )
    find_parser.add_argument(
        "--type",
        dest="path_type",
        choices=["any", "file", "dir"],
        default="any",
        help="Restrict matches to files, directories, or either (default: any)",
    )
    find_parser.add_argument(
        "-0", "--null",
        action="store_true",
        help="Emit NUL-delimited paths instead of newline-delimited paths",
    )
    find_parser.add_argument("--json", action="store_true", help="Emit JSON")
    find_parser.set_defaults(func=cmd_transfer_find)

    mv_parser = sub.add_parser(
        "mv",
        help="Move filesystem paths from stdin into a destination directory",
    )
    mv_parser.add_argument(
        "activity",
        choices=["fileListTo"],
        help="Activity to invoke. Use fileListTo to move stdin-listed files into a directory.",
    )
    mv_parser.add_argument("dest_dir", help="Destination directory")
    mv_parser.add_argument(
        "-0", "--null",
        action="store_true",
        help="Read NUL-delimited paths from stdin instead of newline-delimited paths",
    )
    mv_parser.add_argument(
        "--mkdir",
        action="store_true",
        help="Create the destination directory if it does not exist",
    )
    mv_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned moves without changing the filesystem",
    )
    mv_parser.add_argument("--json", action="store_true", help="Emit JSON")
    mv_parser.set_defaults(func=cmd_transfer_move)

    transfer_parser = sub.add_parser(
        "transfer",
        help="File transfer, queues, stacks, and XML request/response processing",
    )
    tsub = transfer_parser.add_subparsers(dest="transfer_subcommand")

    # sync
    t_sync = tsub.add_parser("sync", help="Sync files via rsync or scp")
    t_sync.add_argument("src", help="Source path or host:path")
    t_sync.add_argument("dest", help="Destination path or host:path")
    t_sync.add_argument("--scp", action="store_true", help="Use scp instead of rsync")
    t_sync.add_argument("--json", action="store_true")
    t_sync.set_defaults(func=cmd_transfer_sync)

    # ssh
    t_ssh = tsub.add_parser("ssh", help="Run a command over SSH")
    t_ssh.add_argument("host")
    t_ssh.add_argument("--cmd", required=True, help="Remote command to run")
    t_ssh.add_argument("--user", help="SSH username")
    t_ssh.add_argument("--port", type=int)
    t_ssh.add_argument("--json", action="store_true")
    t_ssh.set_defaults(func=cmd_transfer_ssh)

    # sftp
    t_sftp = tsub.add_parser("sftp", help="Get or put a file over SFTP")
    t_sftp.add_argument("host")
    t_sftp.add_argument("local", help="Local file path")
    t_sftp.add_argument("--remote", help="Remote file path (default: same as local)")
    t_sftp.add_argument("--get", action="store_true", help="Download from remote (default: upload)")
    t_sftp.add_argument("--user", help="SFTP username")
    t_sftp.add_argument("--port", type=int)
    t_sftp.add_argument("--json", action="store_true")
    t_sftp.set_defaults(func=cmd_transfer_sftp)

    # queue
    t_queue = tsub.add_parser("queue", help="Persistent FIFO queue")
    t_queue.add_argument("queue_op", choices=["push", "pop", "peek", "list", "clear"])
    t_queue.add_argument("item", nargs="?", help="Item to push")
    t_queue.add_argument("--state", default="/tmp/singine-queue.json")
    t_queue.set_defaults(func=cmd_transfer_queue)

    # stack
    t_stack = tsub.add_parser("stack", help="Persistent LIFO stack")
    t_stack.add_argument("stack_op", choices=["push", "pop", "peek", "list", "clear"])
    t_stack.add_argument("item", nargs="?", help="Item to push")
    t_stack.add_argument("--state", default="/tmp/singine-stack.json")
    t_stack.set_defaults(func=cmd_transfer_stack)

    # structure
    t_struct = tsub.add_parser("structure", help="Introspect a queue, stack, or JSON structure")
    t_struct.add_argument("--state", default="/tmp/singine-queue.json")
    t_struct.add_argument("--type", choices=["queue", "stack"], default="queue")
    t_struct.set_defaults(func=cmd_transfer_structure)

    # process-request
    t_proc = tsub.add_parser("process-request", help="Parse an XML request into a structured envelope")
    t_proc.add_argument("--xml", help="Path to XML file (default: stdin)")
    t_proc.set_defaults(func=cmd_transfer_process_request)

    # generate-response
    t_gen = tsub.add_parser("generate-response", help="Generate N response variants from input (default ×4)")
    t_gen.add_argument("--input", help="Path to JSON/text input (default: stdin)")
    t_gen.add_argument("--times", type=int, default=4, help="Number of variants (default: 4)")
    t_gen.set_defaults(func=cmd_transfer_generate_response)

    # project
    t_proj = tsub.add_parser("project", help="Project (select) fields from a JSON structure")
    t_proj.add_argument("--input", help="Path to JSON input (default: stdin)")
    t_proj.add_argument("--fields", required=True, help="Comma-separated field names to project")
    t_proj.set_defaults(func=cmd_transfer_project)

    # analyze-result
    t_anal = tsub.add_parser("analyze-result", help="Compute statistics and shape summary for a JSON result")
    t_anal.add_argument("--input", help="Path to JSON input (default: stdin)")
    t_anal.set_defaults(func=cmd_transfer_analyze_result)

    # ── smtp — test and send ──────────────────────────────────────────────
    _smtp_common = argparse.ArgumentParser(add_help=False)
    _smtp_common.add_argument("--host", help="SMTP host (default: from idp.properties)")
    _smtp_common.add_argument("--port", type=int, help="SMTP port (default: from idp.properties, fallback 587)")
    _smtp_common.add_argument("--user", help="SMTP username")
    _smtp_common.add_argument("--password", help="SMTP password (or set SMTP_PASSWORD env var)")

    smtp_parser = sub.add_parser("smtp", help="SMTP operations — test connectivity and send mail")
    smtp_sub = smtp_parser.add_subparsers(dest="smtp_subcommand")

    smtp_test = smtp_sub.add_parser("test", help="Test SMTP connectivity and optional auth", parents=[_smtp_common])
    smtp_test.set_defaults(func=cmd_smtp_test)

    smtp_send = smtp_sub.add_parser("send", help="Send a test email (defaults to self)", parents=[_smtp_common])
    smtp_send.add_argument("--to", dest="to", help="Recipient address (default: same as --from or smtp_from)")
    smtp_send.add_argument("--from", dest="from_addr", help="Sender address (default: idp.smtp_from)")
    smtp_send.add_argument("--subject", help="Subject line (default: 'singine smtp test')")
    smtp_send.add_argument("--body", help="Message body")
    smtp_send.set_defaults(func=cmd_smtp_send)

    # ── ai ─────────────────────────────────────────────────────────────────────
    ai_parser = sub.add_parser(
        "ai",
        help="AI provider passthrough and governance layer",
        description=(
            "Every interaction is mediated by the singine governance layer: "
            "commands are recorded, permissions are checked and logged, "
            "and sessions are serialised to git-managed EDN files for audit."
        ),
    )
    ai_sub = ai_parser.add_subparsers(dest="ai_subcommand")
    ai_parser.set_defaults(func=lambda a: (ai_parser.print_help(), 1)[1])

    from .ai import (
        cmd_ai_provider as cmd_ai_provider_shell,
        cmd_ai_session_list as cmd_ai_session_list_json,
        cmd_ai_session_show as cmd_ai_session_show_json,
        cmd_ai_last_session_data as cmd_ai_last_session_data_json,
    )

    provider_parent = argparse.ArgumentParser(add_help=False)
    provider_parent.add_argument("--model", default="default")
    provider_parent.add_argument("--session", help="Reuse or pin a session id.")
    provider_parent.add_argument("--mandate", help="Mandate file reference.")
    provider_parent.add_argument("--root-dir", default=str(Path.home() / ".singine" / "ai"))
    provider_parent.add_argument("--db", help="Optional SQLite path to sync on session close.")

    for provider in ["claude", "codex", "openai"]:
        provider_parser = ai_sub.add_parser(
            provider,
            parents=[provider_parent],
            help=f"Open a governed {provider} session shell",
        )
        provider_parser.set_defaults(func=cmd_ai_provider_shell, provider=provider)

    # ai session
    ai_sess = ai_sub.add_parser("session", help="Manage recorded AI sessions")
    sess_sub = ai_sess.add_subparsers(dest="session_subcommand")
    ai_sess.set_defaults(func=lambda a: (ai_sess.print_help(), 1)[1])

    sess_list = sess_sub.add_parser("list", help="List all recorded sessions")
    sess_list.add_argument("--json", action="store_true", help="Machine-readable output")
    sess_list.add_argument("--root-dir", default=str(Path.home() / ".singine" / "ai"))
    sess_list.set_defaults(func=cmd_ai_session_list_json)

    sess_show = sess_sub.add_parser("show", help="Show manifest, commands, and permissions")
    sess_show.add_argument("session_id", help="Session ID")
    sess_show.add_argument("--root-dir", default=str(Path.home() / ".singine" / "ai"))
    sess_show.set_defaults(func=cmd_ai_session_show_json)

    sess_dashboard = sess_sub.add_parser(
        "dashboard",
        help="Build an HTML dashboard that combines governed JSON sessions and repo-backed EDN command sessions",
    )
    sess_dashboard.add_argument("--root-dir", default=str(Path.home() / ".singine" / "ai"))
    sess_dashboard.add_argument("--repo-ai-dir", default=str(REPO_ROOT / "ai"))
    sess_dashboard.add_argument("--output-dir", default=str(REPO_ROOT / "target" / "sindoc.local" / "sessions"))
    sess_dashboard.add_argument("--provider", action="append", help="Filter to one provider; repeatable")
    sess_dashboard.add_argument("--title", default="Singine AI Session Dashboard")
    sess_dashboard.add_argument("--site-url", default="http://sindoc.local:8080/")
    sess_dashboard.add_argument("--json", action="store_true")
    sess_dashboard.set_defaults(func=cmd_ai_session_dashboard)

    sess_export = sess_sub.add_parser("export", help="Export session in requested format")
    sess_export.add_argument("id", help="Session ID")
    fmt_grp = sess_export.add_mutually_exclusive_group()
    fmt_grp.add_argument("--json", dest="fmt", action="store_const", const="json",
                         default="json", help="Export as JSON (default)")
    fmt_grp.add_argument("--edn",  dest="fmt", action="store_const", const="edn",
                         help="Export raw EDN files")
    sess_export.add_argument("--raw", action="store_true",
                             help="Include raw EDN text in JSON export")
    sess_export.set_defaults(func=cmd_ai_session_export)

    # ai mandate
    ai_mand = ai_sub.add_parser("mandate", help="Manage governance mandates")
    mand_sub = ai_mand.add_subparsers(dest="mandate_subcommand")
    ai_mand.set_defaults(func=lambda a: (ai_mand.print_help(), 1)[1])

    mand_list = mand_sub.add_parser("list", help="List stored mandates")
    mand_list.add_argument("--json", action="store_true")
    mand_list.set_defaults(func=cmd_ai_mandate_list)

    mand_show = mand_sub.add_parser("show", help="Print mandate permissions and status")
    mand_show.add_argument("id", help="Mandate ID or filename stem (e.g. collibra-20260315)")
    mand_show.add_argument("--json", action="store_true")
    mand_show.set_defaults(func=cmd_ai_mandate_show)

    # ai status
    ai_status_p = ai_sub.add_parser("status", help="Check provider configuration")
    ai_status_p.add_argument("--json", action="store_true")
    ai_status_p.set_defaults(func=cmd_ai_status)

    # ai flush
    ai_flush_p = ai_sub.add_parser(
        "flush", help="Flush session EDN files to disk; optionally git-commit"
    )
    ai_flush_p.add_argument("--session", metavar="ID",
                            help="Session ID to flush (default: all sessions)")
    ai_flush_p.add_argument("--commit", action="store_true",
                            help="git-add and git-commit the session EDN files")
    ai_flush_p.set_defaults(func=cmd_ai_flush)

    # ai last session data
    ai_last = ai_sub.add_parser("last", help="Commands for the latest recorded AI session")
    last_sub = ai_last.add_subparsers(dest="last_subcommand")
    ai_last.set_defaults(func=lambda a: (ai_last.print_help(), 1)[1])

    ai_last_session = last_sub.add_parser("session", help="Inspect or sync the latest session")
    ai_last_session_sub = ai_last_session.add_subparsers(dest="last_session_subcommand")
    ai_last_session.set_defaults(func=lambda a: (ai_last_session.print_help(), 1)[1])

    ai_last_session_data = ai_last_session_sub.add_parser(
        "data",
        help="Sync the latest recorded session into sqlite.db and print it",
    )
    ai_last_session_data.add_argument("--root-dir", default=str(Path.home() / ".singine" / "ai"))
    ai_last_session_data.add_argument("--db", help="SQLite path (default: <root-dir>/sqlite.db)")
    ai_last_session_data.set_defaults(func=cmd_ai_last_session_data_json)

    # ── demo — zip-code community notebook demo ───────────────────────────────
    demo_parser = sub.add_parser(
        "demo",
        help="Zip-code community demo: life phases, multilingual mapping, messaging pipeline",
    )
    demo_sub = demo_parser.add_subparsers(dest="demo_subcommand")
    demo_parser.set_defaults(func=lambda a: (demo_parser.print_help(), 1)[1])

    demo_zip_neighborhood = demo_sub.add_parser(
        "zip-neighborhood",
        help="Write the full zip-neighborhood messaging bundle (RabbitMQ raw/staging, Kafka, publication artefacts)",
    )
    demo_zip_neighborhood.add_argument("--title", default="Zip Neighborhood Messaging Demo")
    demo_zip_neighborhood.add_argument("--output-dir", "-o", default="/tmp/singine-zip-neighborhood-demo")
    demo_zip_neighborhood.add_argument("--db", help="Optional domain SQLite database path for event logging")
    demo_zip_neighborhood.add_argument("--actor-id", default="singine")
    demo_zip_neighborhood.add_argument("--json", action="store_true")
    demo_zip_neighborhood.set_defaults(func=cmd_demo_zip_neighborhood)

    demo_bundle = demo_sub.add_parser(
        "bundle",
        help="Alias for demo zip-neighborhood",
    )
    demo_bundle.add_argument("--title", default="Zip Neighborhood Messaging Demo")
    demo_bundle.add_argument("--output-dir", "-o", default="/tmp/singine-zip-neighborhood-demo")
    demo_bundle.add_argument("--domain-db", dest="db", help="Optional domain SQLite database path for event logging")
    demo_bundle.add_argument("--actor-id", default="singine")
    demo_bundle.add_argument("--json", action="store_true")
    demo_bundle.set_defaults(func=cmd_demo_zip_neighborhood)

    # ── collibra — live Collibra REST operations ──────────────────────────────
    collibra_parser = sub.add_parser(
        "collibra",
        help="Live Collibra REST API operations (requires COLLIBRA_BASE_URL + credentials)",
    )
    collibra_sub = collibra_parser.add_subparsers(dest="collibra_subcommand")
    collibra_parser.set_defaults(func=lambda a: (collibra_parser.print_help(), 1)[1])

    # singine collibra env
    collibra_env = collibra_sub.add_parser("env", help="Validate Collibra environment config")
    collibra_env.set_defaults(func=cmd_collibra_env)

    # singine collibra fetch <resource>
    collibra_fetch = collibra_sub.add_parser("fetch", help="Fetch a Collibra resource")
    fetch_sub = collibra_fetch.add_subparsers(dest="fetch_resource")
    collibra_fetch.set_defaults(func=lambda a: (collibra_fetch.print_help(), 1)[1])

    fetch_community = fetch_sub.add_parser("community", help="Fetch Communities")
    fetch_community.add_argument("--name", help="Filter by name prefix")
    fetch_community.add_argument("--limit", type=int, default=50)
    fetch_community.add_argument("--json", action="store_true", default=True)
    fetch_community.set_defaults(func=cmd_collibra_fetch_community)

    fetch_domain = fetch_sub.add_parser("domain", help="Fetch Domains")
    fetch_domain.add_argument("--community", metavar="COMMUNITY_ID", help="Filter by community UUID")
    fetch_domain.add_argument("--type", metavar="DOMAIN_TYPE", help="Filter by domain type name")
    fetch_domain.add_argument("--limit", type=int, default=50)
    fetch_domain.add_argument("--json", action="store_true", default=True)
    fetch_domain.set_defaults(func=cmd_collibra_fetch_domain)

    fetch_asset_type = fetch_sub.add_parser("asset-type", help="Fetch AssetTypes")
    fetch_asset_type.add_argument("--json", action="store_true", default=True)
    fetch_asset_type.set_defaults(func=cmd_collibra_fetch_asset_type)

    fetch_view = fetch_sub.add_parser("view", help="Fetch Views (tableViewConfig)")
    fetch_view.add_argument("--location", help="Filter by view location (e.g. catalog|reports)")
    fetch_view.add_argument("--limit", type=int, default=100)
    fetch_view.add_argument("--json", action="store_true", default=True)
    fetch_view.set_defaults(func=cmd_collibra_fetch_view)

    fetch_workflow = fetch_sub.add_parser("workflow", help="Fetch Workflow definitions")
    fetch_workflow.add_argument("--limit", type=int, default=50)
    fetch_workflow.add_argument("--json", action="store_true", default=True)
    fetch_workflow.set_defaults(func=cmd_collibra_fetch_workflow)

    # singine collibra search
    collibra_search_p = collibra_sub.add_parser("search", help="Search Assets by name")
    collibra_search_p.add_argument("query", help="Name search string")
    collibra_search_p.add_argument("--type", metavar="ASSET_TYPE", help="AssetType publicId filter")
    collibra_search_p.add_argument("--domain", metavar="DOMAIN_ID", help="Restrict to Domain UUID")
    collibra_search_p.add_argument("--limit", type=int, default=25)
    collibra_search_p.add_argument("--json", action="store_true", default=True)
    collibra_search_p.set_defaults(func=cmd_collibra_search)

    # singine collibra edge — full edge stack (reuses singine.edge handlers)
    add_edge_parser(collibra_sub)

    # singine collibra id / contract / server — loaded from collibra repo
    from .collibra_idgen import add_collibra_subcommands
    add_collibra_subcommands(collibra_sub)

    # ------------------------------------------------------------------ web
    web_parser = sub.add_parser(
        "web",
        help="Serve a static HTML directory over HTTP",
    )
    web_parser.add_argument(
        "directory",
        help="Directory to serve (e.g. markupware.com/html/)",
    )
    web_parser.add_argument(
        "--port", "-p",
        type=int,
        default=8080,
        help="HTTP port (default: 8080)",
    )
    web_parser.set_defaults(func=cmd_web)

    # ── www — web asset lifecycle ─────────────────────────────────────────────
    www_parser = sub.add_parser("www", help="Web asset lifecycle: deploy, sync, status, diff")
    www_sub = www_parser.add_subparsers(dest="www_subcommand")

    def _s(p): p.add_argument("--site", required=True, help="markupware.com | lutino.io")
    def _j(p): p.add_argument("--json", action="store_true")
    def _d(p): p.add_argument("--dry-run", action="store_true")

    p = www_sub.add_parser("deploy", help="git pull → build → Dropbox → rsync/scp")
    _s(p); _j(p); _d(p)
    p.add_argument("--method", default="rsync", choices=["rsync", "scp", "dropbox", "all"])
    p.add_argument("--skip-git",     action="store_true")
    p.add_argument("--skip-build",   action="store_true")
    p.add_argument("--skip-dropbox", action="store_true")
    p.set_defaults(func=cmd_www_deploy)

    p = www_sub.add_parser("sync", help="Sync via specified method only")
    _s(p); _d(p)
    p.add_argument("--method", default="rsync", choices=["rsync", "scp", "dropbox", "git", "all"])
    p.set_defaults(func=cmd_www_sync)

    p = www_sub.add_parser("status", help="Show deployment status"); _s(p); _j(p)
    p.set_defaults(func=cmd_www_status)

    p = www_sub.add_parser("diff",   help="Local changes not yet deployed"); _s(p); _j(p)
    p.set_defaults(func=cmd_www_diff)

    p = www_sub.add_parser("pull",   help="git pull only"); _s(p); _d(p)
    p.set_defaults(func=cmd_www_pull)

    www_parser.set_defaults(func=lambda args: www_parser.print_help() or 0)

    # ── vww — validate www ────────────────────────────────────────────────────
    vww_parser = sub.add_parser("vww", help="Validate www: cert, scan, assets, audit")
    vww_sub = vww_parser.add_subparsers(dest="vww_subcommand")

    p = vww_sub.add_parser("cert",   help="TLS certificate check"); _s(p); _j(p)
    p.set_defaults(func=cmd_vww_cert)

    p = vww_sub.add_parser("scan",   help="HTTP security header scan"); _s(p); _j(p)
    p.set_defaults(func=cmd_vww_scan)

    p = vww_sub.add_parser("assets", help="List tracked web assets"); _s(p); _j(p)
    p.set_defaults(func=cmd_vww_assets)

    p = vww_sub.add_parser("check",  help="Quick health check"); _s(p); _j(p)
    p.add_argument("--all", action="store_true", help="Full check (cert + scan + assets)")
    p.set_defaults(func=cmd_vww_check)

    p = vww_sub.add_parser("audit",  help="Full security audit report"); _s(p); _j(p)
    p.set_defaults(func=cmd_vww_audit)

    vww_parser.set_defaults(func=lambda args: vww_parser.print_help() or 0)

    # ── wingine — web engine (build pipeline) ─────────────────────────────────
    wingine_parser = sub.add_parser("wingine", help="Web engine: build and serve sites")
    wingine_sub = wingine_parser.add_subparsers(dest="wingine_subcommand")

    p = wingine_sub.add_parser("build",  help="Build site (cortex / maven)"); _s(p); _j(p); _d(p)
    p.add_argument("--clean", action="store_true")
    p.set_defaults(func=cmd_wingine_build)

    p = wingine_sub.add_parser("serve",  help="Serve built site locally"); _s(p); _d(p)
    p.add_argument("--port", type=int, default=None)
    p.set_defaults(func=cmd_wingine_serve)

    p = wingine_sub.add_parser("status", help="Show build status"); _s(p); _j(p)
    p.set_defaults(func=cmd_wingine_status)

    wingine_parser.set_defaults(func=lambda args: wingine_parser.print_help() or 0)

    # ── wsec — web security (TLS, SSH keys, IDP tokens) ───────────────────────
    wsec_parser = sub.add_parser("wsec", help="Web security: TLS certs, SSH keys, IDP tokens")
    wsec_sub = wsec_parser.add_subparsers(dest="wsec_subcommand")

    p = wsec_sub.add_parser("cert",   help="TLS certificate ops"); _s(p); _j(p); _d(p)
    p.add_argument("--renew",    action="store_true")
    p.add_argument("--fix-san",  action="store_true")
    p.add_argument("--method",   default="certbot", choices=["certbot", "acme.sh", "manual"])
    p.set_defaults(func=cmd_wsec_cert)

    p = wsec_sub.add_parser("keys",   help="SSH deploy key management"); _s(p); _j(p); _d(p)
    p.add_argument("--add",    action="store_true")
    p.add_argument("--rotate", action="store_true")
    p.set_defaults(func=cmd_wsec_keys)

    p = wsec_sub.add_parser("token",  help="IDP deploy token (JWT)"); _s(p); _j(p); _d(p)
    p.add_argument("--ttl", type=int, default=3600)
    p.set_defaults(func=cmd_wsec_token)

    p = wsec_sub.add_parser("status", help="Full security status"); _s(p); _j(p)
    p.set_defaults(func=cmd_wsec_status)

    wsec_parser.set_defaults(func=lambda args: wsec_parser.print_help() or 0)

    # ── net — intranet service registry and port management ───────────────────
    net_parser = sub.add_parser(
        "net",
        help="Intranet network control: service registry, ports, routing, dispatch",
    )
    net_sub = net_parser.add_subparsers(dest="net_subcommand")

    def _j(p): p.add_argument("--json", action="store_true", help="JSON output")

    p = net_sub.add_parser("status", help="Full service and port status")
    _j(p); p.set_defaults(func=cmd_net_status)

    p = net_sub.add_parser("ports", help="List all intranet ports")
    _j(p); p.set_defaults(func=cmd_net_ports)

    p = net_sub.add_parser("probe", help="TCP probe a specific service")
    p.add_argument("--service", required=True, help="Service ID (e.g. edge-site)")
    _j(p); p.set_defaults(func=cmd_net_probe)

    p = net_sub.add_parser("route", help="Show routing for a URL path")
    p.add_argument("--from", dest="from_path", default="/", help="URL path to match")
    _j(p); p.set_defaults(func=cmd_net_route)

    net_parser.set_defaults(func=lambda args: net_parser.print_help() or 0)

    # ── panel — live intranet control panel (Tornado) ─────────────────────────
    panel_parser = sub.add_parser(
        "panel",
        help="Live intranet control panel web UI (Tornado, port 9090)",
    )
    panel_sub = panel_parser.add_subparsers(dest="panel_subcommand")

    p = panel_sub.add_parser("serve", help="Start the live control panel")
    p.add_argument("--port", type=int, default=9090, help="Port (default 9090)")
    p.add_argument("--bind", default="127.0.0.1", help="Bind address (default 127.0.0.1)")
    p.set_defaults(func=cmd_panel_serve)

    panel_parser.set_defaults(func=lambda args: panel_parser.print_help() or 0)

    # ── presence — human presence attestation ─────────────────────────────────
    presence_parser = sub.add_parser(
        "presence",
        help="Human presence attestation (Touch ID / 1Password / TOTP)",
    )
    presence_sub = presence_parser.add_subparsers(dest="presence_subcommand")

    p = presence_sub.add_parser("verify", help="Verify human presence")
    p.add_argument("--force", action="store_true", help="Force re-verification")
    _j(p); p.set_defaults(func=cmd_presence_verify)

    p = presence_sub.add_parser("status", help="Show current presence status")
    _j(p); p.set_defaults(func=cmd_presence_status)

    presence_parser.set_defaults(func=lambda args: presence_parser.print_help() or 0)

    # ── feeds — Atom/RSS 1.0 feed generation ──────────────────────────────────
    feeds_parser = sub.add_parser(
        "feeds",
        help="Generate Atom 1.0 and RSS 1.0 (RDF-aligned) activity feeds",
    )
    feeds_sub = feeds_parser.add_subparsers(dest="feeds_subcommand")

    p = feeds_sub.add_parser("generate", help="Write all feeds to output directory")
    p.add_argument("--output-dir", default="/tmp/singine-feeds")
    p.add_argument("--db", default="/tmp/humble-idp.db")
    p.set_defaults(func=cmd_feeds_generate)

    p = feeds_sub.add_parser("atom", help="Print Atom feed to stdout")
    p.add_argument("--kind", default="activity", choices=["activity", "decisions"])
    p.add_argument("--db", default="/tmp/humble-idp.db")
    p.set_defaults(func=cmd_feeds_atom)

    p = feeds_sub.add_parser("rss", help="Print RSS 1.0 feed to stdout")
    p.add_argument("--kind", default="activity", choices=["activity", "decisions"])
    p.add_argument("--db", default="/tmp/humble-idp.db")
    p.set_defaults(func=cmd_feeds_rss)

    feeds_parser.set_defaults(func=lambda args: feeds_parser.print_help() or 0)

    # ── mcp ────────────────────────────────────────────────────────────────────
    mcp_parser = sub.add_parser(
        "mcp",
        help="Singine MCP server: expose domain, AI, and governance data to Claude",
    )
    mcp_sub = mcp_parser.add_subparsers(dest="mcp_subcommand")

    p = mcp_sub.add_parser(
        "seed",
        help="Seed a test SQLite database with representative Collibra domain data",
    )
    p.add_argument(
        "--db", default="/tmp/singine-mcp-test.db",
        help="Path to the SQLite database (default: /tmp/singine-mcp-test.db)",
    )
    p.set_defaults(func=cmd_mcp_seed)

    p = mcp_sub.add_parser(
        "serve",
        help="Start the Singine Collibra MCP server (stdio or SSE transport)",
    )
    p.add_argument(
        "--db", default="/tmp/singine-mcp-test.db",
        help="Path to the SQLite database (default: /tmp/singine-mcp-test.db)",
    )
    p.add_argument(
        "--transport", choices=["stdio", "sse"], default="stdio",
        help="Transport: 'stdio' for MCP clients (default) or 'sse' for HTTP",
    )
    p.add_argument(
        "--port", type=int, default=8765,
        help="HTTP port when using --transport sse (default: 8765)",
    )
    p.set_defaults(func=cmd_mcp_serve)

    p = mcp_sub.add_parser(
        "tools",
        help="List all registered MCP tool names",
    )
    p.set_defaults(func=cmd_mcp_tools)

    p = mcp_sub.add_parser(
        "call",
        help="Call a single MCP tool by name and print the JSON result",
    )
    p.add_argument("tool", help="Tool name (see: singine mcp tools)")
    p.add_argument(
        "--params", default="{}",
        metavar="JSON",
        help="Tool parameters as a JSON object (default: '{}')",
    )
    p.add_argument(
        "--db", default="/tmp/singine-mcp-test.db",
        help="Path to the SQLite database (default: /tmp/singine-mcp-test.db)",
    )
    p.set_defaults(func=cmd_mcp_call)

    mcp_parser.set_defaults(func=lambda args: mcp_parser.print_help() or 0)

    return parser


def cmd_web(args) -> int:
    """Serve a static HTML directory using Python's built-in HTTP server."""
    import functools
    import http.server

    directory = Path(args.directory).resolve()
    if not directory.exists():
        print(f"Error: directory not found: {directory}", file=sys.stderr)
        return 1

    port = args.port

    # Collect local IPs for display
    ips: list[str] = []
    try:
        hostname = __import__("socket").gethostname()
        ips = [__import__("socket").gethostbyname(hostname)]
    except Exception:
        pass

    print(f"Serving {directory}")
    print(f"  http://localhost:{port}/")
    for ip in ips:
        print(f"  http://{ip}:{port}/")
    print("Ctrl-C to stop.")
    print()

    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=str(directory),
    )
    with http.server.HTTPServer(("", port), handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
    return 0


# ── www handlers ─────────────────────────────────────────────────────────────

def cmd_www_deploy(args) -> int:
    from .www import deploy
    deploy(args.site, method=args.method,
           skip_git=getattr(args, "skip_git", False),
           skip_build=getattr(args, "skip_build", False),
           skip_dropbox=getattr(args, "skip_dropbox", False),
           dry_run=getattr(args, "dry_run", False),
           json_out=getattr(args, "json", False))
    return 0

def cmd_www_sync(args) -> int:
    from .www import resolve_site, git_pull, dropbox_stage, rsync_deploy, scp_deploy
    site = resolve_site(args.site)
    dry = getattr(args, "dry_run", False)
    m = args.method
    if m in ("git", "all"):    git_pull(site, dry_run=dry)
    if m in ("dropbox", "all"): dropbox_stage(site, dry_run=dry)
    if m in ("rsync", "all"):  rsync_deploy(site, dry_run=dry)
    if m == "scp":             scp_deploy(site, dry_run=dry)
    return 0

def cmd_www_status(args) -> int:
    from .www import status
    status(args.site, json_out=getattr(args, "json", False))
    return 0

def cmd_www_diff(args) -> int:
    from .www import diff
    diff(args.site, json_out=getattr(args, "json", False))
    return 0

def cmd_www_pull(args) -> int:
    from .www import git_pull, resolve_site
    git_pull(resolve_site(args.site), dry_run=getattr(args, "dry_run", False))
    return 0


# ── vww handlers ──────────────────────────────────────────────────────────────

def cmd_vww_cert(args) -> int:
    from .wsec import cert_check
    cert_check(args.site, json_out=getattr(args, "json", False))
    return 0

def cmd_vww_scan(args) -> int:
    from .vww import scan
    scan(args.site, json_out=getattr(args, "json", False))
    return 0

def cmd_vww_assets(args) -> int:
    from .vww import assets
    assets(args.site, json_out=getattr(args, "json", False))
    return 0

def cmd_vww_check(args) -> int:
    from .vww import check
    check(args.site, full=getattr(args, "all", False),
          json_out=getattr(args, "json", False))
    return 0

def cmd_vww_audit(args) -> int:
    from .vww import audit
    audit(args.site, json_out=getattr(args, "json", False))
    return 0


# ── wingine handlers ──────────────────────────────────────────────────────────

def cmd_wingine_build(args) -> int:
    from .wingine import build
    build(args.site, clean=getattr(args, "clean", False),
          dry_run=getattr(args, "dry_run", False),
          json_out=getattr(args, "json", False))
    return 0

def cmd_wingine_serve(args) -> int:
    from .wingine import serve
    serve(args.site, port=getattr(args, "port", None),
          dry_run=getattr(args, "dry_run", False))
    return 0

def cmd_wingine_status(args) -> int:
    from .wingine import wingine_status
    wingine_status(args.site, json_out=getattr(args, "json", False))
    return 0


# ── wsec handlers ─────────────────────────────────────────────────────────────

def cmd_wsec_cert(args) -> int:
    from .wsec import cert_check, cert_renew
    if getattr(args, "renew", False) or getattr(args, "fix_san", False):
        cert_renew(args.site, method=args.method,
                   dry_run=getattr(args, "dry_run", False))
    else:
        cert_check(args.site, json_out=getattr(args, "json", False))
    return 0

def cmd_wsec_keys(args) -> int:
    from .wsec import keys_list, keys_add, keys_rotate
    if getattr(args, "add", False):
        keys_add(args.site, dry_run=getattr(args, "dry_run", False),
                 json_out=getattr(args, "json", False))
    elif getattr(args, "rotate", False):
        keys_rotate(args.site, dry_run=getattr(args, "dry_run", False))
    else:
        keys_list(args.site, json_out=getattr(args, "json", False))
    return 0

def cmd_wsec_token(args) -> int:
    from .wsec import token_mint
    token_mint(args.site, ttl=getattr(args, "ttl", 3600),
               dry_run=getattr(args, "dry_run", False),
               json_out=getattr(args, "json", False))
    return 0

def cmd_wsec_status(args) -> int:
    from .wsec import wsec_status
    wsec_status(args.site, json_out=getattr(args, "json", False))
    return 0


# ── net handlers ──────────────────────────────────────────────────────────────

def cmd_net_status(args) -> int:
    from .net import cmd_status
    return cmd_status(args)

def cmd_net_ports(args) -> int:
    from .net import cmd_ports
    return cmd_ports(args)

def cmd_net_probe(args) -> int:
    from .net import cmd_probe
    return cmd_probe(args)

def cmd_net_route(args) -> int:
    from .net import cmd_route
    return cmd_route(args)


# ── panel handlers ────────────────────────────────────────────────────────────

def cmd_panel_serve(args) -> int:
    from .panel_server import cmd_serve
    return cmd_serve(args)


# ── presence handlers ─────────────────────────────────────────────────────────

def cmd_presence_verify(args) -> int:
    from .presence import cmd_verify
    return cmd_verify(args)

def cmd_presence_status(args) -> int:
    from .presence import cmd_status
    return cmd_status(args)


# ── feeds handlers ────────────────────────────────────────────────────────────

def cmd_feeds_generate(args) -> int:
    from .feeds import cmd_generate
    return cmd_generate(args)

def cmd_feeds_atom(args) -> int:
    from .feeds import cmd_atom
    return cmd_atom(args)

def cmd_feeds_rss(args) -> int:
    from .feeds import cmd_rss
    return cmd_rss(args)


# ── mcp handlers ──────────────────────────────────────────────────────────────

def cmd_mcp_seed(args) -> int:
    from .mcp.seed import run
    run(args.db)
    return 0


def cmd_mcp_serve(args) -> int:
    from .mcp.server import serve
    serve(args.db, transport=getattr(args, "transport", "stdio"),
          port=getattr(args, "port", 8765))
    return 0


def cmd_mcp_tools(args) -> int:
    import json as _json
    from .mcp.server import list_tool_names
    for name in list_tool_names():
        print(name)
    return 0


def cmd_mcp_call(args) -> int:
    import json as _json
    from .mcp.server import call_tool
    try:
        params = _json.loads(args.params)
    except _json.JSONDecodeError as exc:
        print(f"error: --params is not valid JSON: {exc}", file=sys.stderr)
        return 1
    call_tool(args.db, args.tool, params)
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
