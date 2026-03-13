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

    jdbc_parser = sub.add_parser("jdbc-url", help="Print the SQLite JDBC URL")
    jdbc_parser.add_argument("--db", default="/tmp/sqlite.db", help="SQLite database path")
    jdbc_parser.set_defaults(func=cmd_jdbc_url)

    xml_parser = sub.add_parser("xml", help="Generate XML request/response matrices")
    xml_sub = xml_parser.add_subparsers(dest="xml_subcommand")

    xml_matrix = xml_sub.add_parser("matrix", help="Run scenarios across dimensions and data categories")
    xml_matrix.add_argument("--db", default="/tmp/sqlite.db", help="SQLite database path")
    xml_matrix.add_argument("--output-dir", default="/tmp/singine-xml-matrix", help="Directory for request/response/heatmap XML")
    xml_matrix.set_defaults(func=cmd_xml_matrix)

    man_parser = sub.add_parser("man", help="Open or print Singine manpages")
    man_parser.add_argument("topic", nargs="?", default="singine")
    man_parser.add_argument("--raw", action="store_true", help="Print the file path instead of opening man")
    man_parser.set_defaults(func=cmd_man)

    install_parser = sub.add_parser("install", help="Install singine launcher and manpages into a prefix")
    install_parser.add_argument("--prefix", default=str(DEFAULT_PREFIX))
    install_parser.add_argument("--shell", choices=["bash", "sh", "all"], default="all")
    install_parser.add_argument("--json", action="store_true")
    install_parser.set_defaults(func=cmd_install)

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

    # ── transfer — sync, ssh, sftp, queue, stack, structure, XML processing ─
    from .transfer import (
        cmd_transfer_sync, cmd_transfer_ssh, cmd_transfer_sftp,
        cmd_transfer_queue, cmd_transfer_stack, cmd_transfer_structure,
        cmd_transfer_process_request, cmd_transfer_generate_response,
        cmd_transfer_project, cmd_transfer_analyze_result,
    )

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
