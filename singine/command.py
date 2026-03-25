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

    prefix = Path(args.prefix).expanduser()
    launcher = install_launcher(prefix)
    install_manpages(prefix)
    shell_updates = ensure_shell_paths(prefix, args.shell)
    payload = {
        "prefix": str(prefix),
        "launcher": str(launcher),
        "manpath": str(installed_man_path(prefix)),
        "shell_init": shell_updates,
        "shell": args.shell,
    }
    if args.json:
        print_json(payload)
    else:
        print(f"installed launcher: {launcher}")
        print(f"installed manpages: {installed_man_path(prefix)}")
        print(f"updated shell init: {shell_updates}")
        print("open a new shell or run:")
        for _, rc in shell_updates.items():
            print(f". {rc}")
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
    install_parser.add_argument("subject", nargs="?", choices=["singine", "ant", "xmldoclet"], default="singine")
    install_parser.add_argument("--prefix", default=str(DEFAULT_PREFIX))
    install_parser.add_argument("--shell", choices=["bash", "sh", "all"], default="all")
    install_parser.add_argument("--json", action="store_true")
    install_parser.set_defaults(func=cmd_install)

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

    from .policy import add_policy_parser
    add_policy_parser(sub)

    from .domain import add_domain_parser
    add_domain_parser(sub)

    from .edge import add_edge_parser
    add_edge_parser(sub)

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

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
