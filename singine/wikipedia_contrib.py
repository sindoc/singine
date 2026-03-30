"""High-level wrappers for repository-backed Wikipedia contribution workflows."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_WIKI_REPO = Path("/Users/skh/ws/git/github/sindoc/datatech-wiki-kg")


def _run(repo_root: Path, args: List[str]) -> Dict[str, Any]:
    proc = subprocess.run(
        args,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": args,
        "cwd": str(repo_root),
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def wikipedia_contrib_collibra(
    *,
    repo_root: Path = DEFAULT_WIKI_REPO,
    action: str = "status",
) -> Dict[str, Any]:
    repo_root = repo_root.expanduser().resolve()
    payload: Dict[str, Any] = {
        "topic": "collibra",
        "repo_root": str(repo_root),
        "action": action,
        "exists": repo_root.exists(),
    }
    if not repo_root.exists():
        payload["ok"] = False
        payload["error"] = f"repository does not exist: {repo_root}"
        return payload

    actions = {
        "status": None,
        "refresh": ["python3", "scripts/refresh_repo.py"],
        "ingest-live": ["python3", "scripts/ingest_wikipedia_changes.py"],
        "kernel-sync": ["python3", "scripts/sync_kernel_views.py"],
        "test-case": ["python3", "scripts/test_case.py"],
        "install-hooks": ["python3", "scripts/install_hooks.py"],
        "preview-mail": ["python3", "scripts/send_opt_in_update.py"],
        "send-mail": ["python3", "scripts/send_opt_in_update.py", "--send"],
    }
    if action not in actions:
        payload["ok"] = False
        payload["error"] = f"unsupported action: {action}"
        return payload

    if actions[action]:
        payload["result"] = _run(repo_root, actions[action])

    payload["pending_notification"] = _read_json(repo_root / "notifications" / "pending-update.json")
    payload["project"] = _read_json(repo_root / "config" / "project.json")
    payload["campaign"] = _read_json(repo_root / "data" / "collibra-campaign.json").get("campaign", {})
    payload["ok"] = True
    return payload
