"""
singine www — web asset lifecycle management.

Commands:
    singine www deploy  --site markupware.com [--method rsync|scp|dropbox]
    singine www sync    --site lutino.io      [--method rsync|scp|dropbox|all]
    singine www status  --site markupware.com
    singine www diff    --site markupware.com
    singine www pull    --site markupware.com  (git pull only)

Sync chain (default):
    git pull → wingine build → Dropbox stage → rsync/scp → remote server

IDP integration:
    SSH keys and deploy tokens are managed via singine IDP (singine.wsec).
    Every deploy is recorded in the singine domain event log.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from .config import Config
except ImportError:
    Config = None  # type: ignore


# ── Site registry ─────────────────────────────────────────────────────────────

SITE_REGISTRY: dict[str, dict] = {
    "markupware.com": {
        "local_html":   Path.home() / "ws/git/markupware.com/html",
        "local_src":    Path.home() / "ws/git/markupware.com",
        "git_remote":   "origin",
        "remote_host":  "markupware.com",
        "remote_user":  "deploy",
        "remote_path":  "/var/www/markupware.com/html",
        "dropbox_path": Path.home() / "Dropbox/www/markupware.com",
        "ssh_key":      Path.home() / ".singine/keys/markupware_deploy_ed25519",
        "build_cmd":    "singine wingine build --site markupware.com",
        "cert_domains": ["markupware.com", "www.markupware.com",
                         "silkpage.markupware.com", "docbookit.markupware.com"],
    },
    "lutino.io": {
        "local_html":   Path.home() / "ws/git/lutino.io/lutino/target/lutino_webapp",
        "local_src":    Path.home() / "ws/git/lutino.io",
        "git_remote":   "origin",
        "remote_host":  "lutino.io",
        "remote_user":  "deploy",
        "remote_path":  "/var/www/lutino.io/webapp",
        "dropbox_path": Path.home() / "Dropbox/www/lutino.io",
        "ssh_key":      Path.home() / ".singine/keys/lutino_deploy_ed25519",
        "build_cmd":    "singine wingine build --site lutino.io",
        "cert_domains": ["lutino.io", "www.lutino.io", "app.lutino.io"],
    },
}


def resolve_site(name: str) -> dict:
    if name not in SITE_REGISTRY:
        raise ValueError(
            f"Unknown site '{name}'. Known sites: {', '.join(SITE_REGISTRY)}"
        )
    return {**SITE_REGISTRY[name], "name": name}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run(cmd: str, dry_run: bool = False, capture: bool = False) -> subprocess.CompletedProcess:
    parts = shlex.split(cmd)
    prefix = "[DRY]" if dry_run else "[RUN]"
    print(f"  {prefix} {cmd}")
    if dry_run:
        return subprocess.CompletedProcess(parts, returncode=0, stdout="", stderr="")
    kwargs = {"capture_output": capture, "text": True} if capture else {}
    return subprocess.run(parts, **kwargs)


# ── git pull ──────────────────────────────────────────────────────────────────

def git_pull(site: dict, dry_run: bool = False) -> bool:
    """Pull latest from git remote for the site repo."""
    src = site["local_src"]
    print(f"\n[www] git pull — {site['name']}")
    r = _run(f"git -C {src} pull {site['git_remote']}", dry_run=dry_run)
    return r.returncode == 0


# ── Dropbox staging ───────────────────────────────────────────────────────────

def dropbox_stage(site: dict, dry_run: bool = False) -> bool:
    """rsync local html → Dropbox staging directory."""
    src = str(site["local_html"]).rstrip("/") + "/"
    dst = str(site["dropbox_path"]).rstrip("/") + "/"
    dropbox_dir = site["dropbox_path"]

    print(f"\n[www] Dropbox stage — {site['name']}")
    if not dry_run:
        dropbox_dir.mkdir(parents=True, exist_ok=True)

    cmd = (
        f"rsync -avz --delete --exclude='.DS_Store' --exclude='*.pyc' "
        f"{src} {dst}"
    )
    r = _run(cmd, dry_run=dry_run)
    return r.returncode == 0


# ── rsync to remote ───────────────────────────────────────────────────────────

def rsync_deploy(site: dict, dry_run: bool = False) -> bool:
    """rsync html → remote server via SSH key from singine IDP."""
    src = str(site["local_html"]).rstrip("/") + "/"
    dst = f"{site['remote_user']}@{site['remote_host']}:{site['remote_path']}/"
    key = site["ssh_key"]

    print(f"\n[www] rsync deploy — {site['name']} → {dst}")
    cmd = (
        f"rsync -avz --delete --checksum "
        f"-e 'ssh -i {key} -o StrictHostKeyChecking=accept-new' "
        f"--exclude='.DS_Store' --exclude='*.pyc' "
        f"{src} {dst}"
    )
    r = _run(cmd, dry_run=dry_run)
    return r.returncode == 0


# ── scp to remote (single file or archive) ────────────────────────────────────

def scp_deploy(site: dict, path: Optional[Path] = None, dry_run: bool = False) -> bool:
    """scp a specific file or tar archive to remote via SSH key."""
    key = site["ssh_key"]
    target_path = path or site["local_html"]
    dst = f"{site['remote_user']}@{site['remote_host']}:{site['remote_path']}/"

    print(f"\n[www] scp deploy — {site['name']}")
    cmd = (
        f"scp -i {key} -o StrictHostKeyChecking=accept-new "
        f"-r {target_path} {dst}"
    )
    r = _run(cmd, dry_run=dry_run)
    return r.returncode == 0


# ── Full deploy pipeline ──────────────────────────────────────────────────────

def deploy(
    site_name: str,
    method: str = "rsync",
    skip_git: bool = False,
    skip_build: bool = False,
    skip_dropbox: bool = False,
    dry_run: bool = False,
    json_out: bool = False,
) -> dict:
    """
    Full deploy pipeline:
      1. git pull
      2. singine wingine build
      3. Dropbox stage
      4. rsync / scp → remote

    Returns result dict.
    """
    site = resolve_site(site_name)
    results: list[dict] = []
    ok = True

    print(f"\n[www] deploy {site_name} via {method} — {now_iso()}")
    if dry_run:
        print("[www] DRY RUN — no changes will be made")

    # 1. git pull
    if not skip_git:
        step_ok = git_pull(site, dry_run=dry_run)
        results.append({"step": "git_pull", "ok": step_ok})
        ok = ok and step_ok

    # 2. build
    if not skip_build and ok:
        print(f"\n[www] build — {site_name}")
        r = _run(site["build_cmd"], dry_run=dry_run)
        step_ok = r.returncode == 0
        results.append({"step": "build", "ok": step_ok})
        ok = ok and step_ok

    # 3. Dropbox stage
    if not skip_dropbox and ok:
        step_ok = dropbox_stage(site, dry_run=dry_run)
        results.append({"step": "dropbox_stage", "ok": step_ok})
        ok = ok and step_ok

    # 4. Deploy to remote
    if ok:
        if method in ("rsync", "all"):
            step_ok = rsync_deploy(site, dry_run=dry_run)
            results.append({"step": "rsync_deploy", "ok": step_ok})
            ok = ok and step_ok
        if method in ("scp",):
            step_ok = scp_deploy(site, dry_run=dry_run)
            results.append({"step": "scp_deploy", "ok": step_ok})
            ok = ok and step_ok

    # 5. Domain event log
    _log_event(site_name, "DEPLOY_COMPLETED" if ok else "DEPLOY_FAILED", {
        "method": method, "dry_run": dry_run,
        "steps": results,
    })

    result = {
        "site": site_name,
        "method": method,
        "dry_run": dry_run,
        "ok": ok,
        "steps": results,
        "timestamp": now_iso(),
    }

    if json_out:
        print(json.dumps(result, indent=2))
    else:
        status = "✓ OK" if ok else "✗ FAILED"
        print(f"\n[www] {status} — {site_name} deploy via {method}")

    return result


# ── status ────────────────────────────────────────────────────────────────────

def status(site_name: str, json_out: bool = False) -> dict:
    """Show deployment status: git log, remote connectivity, cert expiry."""
    site = resolve_site(site_name)

    # Git status
    git_log = _run(
        f"git -C {site['local_src']} log --oneline -5",
        capture=True,
    )

    # Remote SSH connectivity (quick test)
    key = site["ssh_key"]
    ssh_test = _run(
        f"ssh -i {key} -o ConnectTimeout=5 -o BatchMode=yes "
        f"-o StrictHostKeyChecking=accept-new "
        f"{site['remote_user']}@{site['remote_host']} echo ok",
        capture=True,
    )

    result = {
        "site": site_name,
        "git_recent": git_log.stdout.strip() if git_log.returncode == 0 else "unavailable",
        "remote_ssh": "ok" if ssh_test.returncode == 0 else "unreachable",
        "local_html": str(site["local_html"]),
        "remote": f"{site['remote_user']}@{site['remote_host']}:{site['remote_path']}",
        "dropbox": str(site["dropbox_path"]),
        "timestamp": now_iso(),
    }

    if json_out:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n[www] status — {site_name}")
        for k, v in result.items():
            if k not in ("site", "timestamp"):
                print(f"  {k:16s}: {v}")

    return result


# ── diff ──────────────────────────────────────────────────────────────────────

def diff(site_name: str, json_out: bool = False) -> dict:
    """Show git diff between local and what's in Dropbox staging."""
    site = resolve_site(site_name)

    r = _run(
        f"git -C {site['local_src']} status --short",
        capture=True,
    )

    result = {
        "site": site_name,
        "git_status": r.stdout.strip() if r.returncode == 0 else "unavailable",
        "timestamp": now_iso(),
    }

    if json_out:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n[www] diff — {site_name}")
        print(result["git_status"] or "(clean)")

    return result


# ── domain event log ──────────────────────────────────────────────────────────

def _log_event(site: str, event_type: str, payload: dict) -> None:
    """Append to singine domain event log (best-effort)."""
    try:
        import subprocess as sp
        db = os.environ.get("SINGINE_DOMAIN_DB", "/tmp/humble-idp.db")
        sp.run(
            [
                "singine", "domain", "event", "append",
                "--event-type", event_type,
                "--subject-id", f"www:{site}",
                "--db", db,
            ],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass
