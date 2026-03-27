"""
singine.idp_git — Git-backed snapshot and restore for ~/.singine/

Tracks identity state (public keys, API key metadata, lock file index,
magic-link state) in a local git repo at ~/.singine/ so any configuration
change can be rolled back with a single command.

Sensitive files (.key, idp_private.pem, singine.jks, password hashes) are
always excluded via .gitignore — they are never committed.
"""

from __future__ import annotations

import subprocess
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SINGINE_DIR = Path.home() / ".singine"

GITIGNORE_CONTENT = """\
# humble-idp git snapshot — sensitive files excluded
idp_private.pem
singine.jks
*.key
*.p12
*.pfx
backend.config
sessions/*.lock
magic-links/pending.json
"""

TRACKED_PATHS = [
    "idp_public.pem",
    "api-keys.json",
    "trust.snapshot.json",
]


def _run(args: list[str], cwd: Path = SINGINE_DIR, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return _run(["git", *args], check=check)


def is_git_repo() -> bool:
    result = _git("rev-parse", "--git-dir", check=False)
    return result.returncode == 0


def init_repo() -> dict:
    """Initialise ~/.singine/ as a git repo if not already done."""
    SINGINE_DIR.mkdir(parents=True, exist_ok=True)

    if not is_git_repo():
        _git("init", "-b", "main")
        _git("config", "user.name", "singine-idp")
        _git("config", "user.email", "idp@singine.local")

    gitignore = SINGINE_DIR / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(GITIGNORE_CONTENT)

    # Stage .gitignore and commit if nothing staged yet
    _git("add", ".gitignore", check=False)
    result = _git("diff", "--cached", "--quiet", check=False)
    if result.returncode != 0:
        _git("commit", "-m", "chore: initialise singine identity snapshot repo")

    return {"ok": True, "path": str(SINGINE_DIR), "git_repo": True}


def snapshot(message: Optional[str] = None) -> dict:
    """
    Commit the current tracked state of ~/.singine/ to git.
    Returns a dict with ok, commit_hash, and message.
    """
    if not is_git_repo():
        init_repo()

    # Write a trust.snapshot.json — non-sensitive summary of current state
    _write_trust_snapshot()

    # Stage only tracked paths (never stage private keys)
    for p in TRACKED_PATHS:
        _git("add", "--force", p, check=False)
    _git("add", ".gitignore", check=False)

    # Check if there's anything to commit
    diff = _git("diff", "--cached", "--quiet", check=False)
    if diff.returncode == 0:
        return {"ok": True, "committed": False, "reason": "nothing to commit — state unchanged"}

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    msg = message or f"snapshot: {ts}"
    _git("commit", "-m", msg)

    log = _git("log", "-1", "--format=%H %s")
    parts = log.stdout.strip().split(" ", 1)
    return {
        "ok": True,
        "committed": True,
        "commit_hash": parts[0],
        "message": parts[1] if len(parts) > 1 else msg,
        "timestamp": ts,
    }


def restore(ref: Optional[str] = None) -> dict:
    """
    Restore ~/.singine/ tracked files to a previous snapshot.
    ref can be a commit hash, branch, or tag (default: HEAD~1).
    """
    if not is_git_repo():
        return {"ok": False, "error": "no snapshot repo — run `singine idp snapshot` first"}

    target = ref or "HEAD~1"

    # Verify ref exists
    verify = _git("rev-parse", "--verify", target, check=False)
    if verify.returncode != 0:
        return {"ok": False, "error": f"unknown ref: {target}"}

    # Checkout only tracked paths from the target ref
    for p in TRACKED_PATHS:
        _git("checkout", target, "--", p, check=False)

    hash_result = _git("rev-parse", "--short", target)
    return {
        "ok": True,
        "restored_from": target,
        "commit_hash": hash_result.stdout.strip(),
        "note": "Restored public keys and API key metadata. Secrets (private key, JKS) unchanged.",
    }


def log(limit: int = 10) -> list[dict]:
    """Return the last N snapshot commits."""
    if not is_git_repo():
        return []
    result = _git(
        "log",
        f"-{limit}",
        "--format=%H|%h|%ai|%s",
        check=False,
    )
    entries = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        parts = line.split("|", 3)
        if len(parts) == 4:
            entries.append({
                "hash": parts[0],
                "short_hash": parts[1],
                "timestamp": parts[2],
                "message": parts[3],
            })
    return entries


def diff(ref: Optional[str] = None) -> str:
    """Show git diff from ref (default HEAD) to working tree for tracked paths."""
    if not is_git_repo():
        return ""
    target = ref or "HEAD"
    result = _git("diff", target, "--", *TRACKED_PATHS, check=False)
    return result.stdout


def _write_trust_snapshot() -> None:
    """Write a non-sensitive snapshot of current identity state to trust.snapshot.json."""
    snapshot_data: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "public_key_exists": (SINGINE_DIR / "idp_public.pem").exists(),
        "jks_exists": (SINGINE_DIR / "singine.jks").exists(),
    }

    # API key metadata (no hashes)
    api_keys_path = SINGINE_DIR / "api-keys.json"
    if api_keys_path.exists():
        try:
            raw = json.loads(api_keys_path.read_text())
            snapshot_data["api_keys"] = [
                {"id": k.get("id"), "user": k.get("user"), "revoked": k.get("revoked"),
                 "created_at": k.get("createdAt"), "expires_at": k.get("expiresAt")}
                for k in raw
            ]
        except Exception:
            snapshot_data["api_keys"] = []

    # Lock file inventory (just filenames, no JWT content)
    sessions_dir = SINGINE_DIR / "sessions"
    if sessions_dir.exists():
        snapshot_data["active_sessions"] = [
            f.stem for f in sessions_dir.glob("*.lock")
        ]

    (SINGINE_DIR / "trust.snapshot.json").write_text(
        json.dumps(snapshot_data, indent=2)
    )
