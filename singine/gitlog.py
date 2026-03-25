"""Git-backed operation log for singine.

Every significant operation — pipeline sends, notebook queries, demo runs,
Collibra registrations — produces a markdown fragment that can be committed
with git. This gives full auditability across XML, JSON, API, and MediaWiki
publication artefacts.

Usage:
    from singine.gitlog import GitLog
    log = GitLog()
    log.record("ZIP_LOOKUP", {"zip": "10001", "result": ...})
    log.commit("notebook session: zip community analysis")

Protocol:
    Each fragment is a dated Markdown file:
        {log_dir}/{YYYY-MM-DD}/{HHMMSS}-{slug}.md

    The markdown contains:
    - YAML-style frontmatter (logseq-compatible)
    - JSON block of the payload
    - XML projection of key fields
    - API call representation
    - MediaWiki snippet

    Running `singine gitlog commit` stages and commits all pending fragments.
    Running `singine gitlog push` pushes to remote.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_LOG_DIR = Path.home() / ".singine" / "gitlog"
REPO_ROOT = Path(__file__).resolve().parent.parent


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]


def _git_run(args: List[str], cwd: Path) -> str:
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=15, check=False)
        return (r.stdout or r.stderr).strip()
    except Exception:
        return ""


def _to_xml(event_type: str, payload: Dict[str, Any]) -> str:
    root = ET.Element("singine-event", {"type": event_type})
    for key, val in payload.items():
        child = ET.SubElement(root, _slug(str(key)))
        if isinstance(val, (dict, list)):
            child.text = json.dumps(val)
        else:
            child.text = str(val) if val is not None else ""
    return ET.tostring(root, encoding="unicode")


def _to_mediawiki(event_type: str, payload: Dict[str, Any]) -> str:
    lines = [f"== {event_type} ==", ""]
    for key, val in payload.items():
        if isinstance(val, (dict, list)):
            lines.append(f"; {key}: <code>{json.dumps(val)}</code>")
        else:
            lines.append(f"; {key}: {val}")
    return "\n".join(lines)


def _to_api_call(event_type: str, payload: Dict[str, Any]) -> str:
    """Represent the event as a curl-style API call."""
    body = json.dumps({"event": event_type, **payload}, separators=(",", ":"))
    return f"curl -X POST http://localhost:8090/invoke -H 'Content-Type: application/json' -d '{body}'"


class GitLog:
    """Write, stage, and commit markdown log fragments with git provenance."""

    def __init__(
        self,
        log_dir: Optional[Path] = None,
        repo_root: Optional[Path] = None,
        actor: str = "singine",
    ) -> None:
        self.log_dir = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
        self.repo_root = Path(repo_root) if repo_root else REPO_ROOT
        self.actor = actor
        self._pending: List[Path] = []

    def _ensure_dir(self) -> Path:
        date_dir = self.log_dir / _now().strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        return date_dir

    def record(
        self,
        event_type: str,
        payload: Dict[str, Any],
        *,
        subject_id: Optional[str] = None,
        note: str = "",
    ) -> Path:
        """Write a markdown fragment for one event. Returns the fragment path."""
        ts = _now()
        slug = _slug(note or event_type)
        fragment_name = f"{ts.strftime('%H%M%S')}-{slug}.md"
        fragment_path = self._ensure_dir() / fragment_name

        event_id = str(uuid.uuid4())
        git_head = _git_run(["git", "rev-parse", "HEAD"], self.repo_root)
        git_branch = _git_run(["git", "rev-parse", "--abbrev-ref", "HEAD"], self.repo_root)

        xml_text = _to_xml(event_type, payload)
        mw_text = _to_mediawiki(event_type, payload)
        api_call = _to_api_call(event_type, payload)

        content = (
            f"---\n"
            f"event-id:: {event_id}\n"
            f"event-type:: {event_type}\n"
            f"actor:: {self.actor}\n"
            f"subject-id:: {subject_id or ''}\n"
            f"occurred-at:: {ts.isoformat()}\n"
            f"git-head:: {git_head}\n"
            f"git-branch:: {git_branch}\n"
            f"---\n\n"
            f"# {event_type}\n\n"
            f"> {note}\n\n" if note else (
                f"---\n"
                f"event-id:: {event_id}\n"
                f"event-type:: {event_type}\n"
                f"actor:: {self.actor}\n"
                f"subject-id:: {subject_id or ''}\n"
                f"occurred-at:: {ts.isoformat()}\n"
                f"git-head:: {git_head}\n"
                f"git-branch:: {git_branch}\n"
                f"---\n\n"
                f"# {event_type}\n\n"
            )
        )

        # Write all projections
        content = (
            f"---\n"
            f"event-id:: {event_id}\n"
            f"event-type:: {event_type}\n"
            f"actor:: {self.actor}\n"
            f"subject-id:: {subject_id or ''}\n"
            f"occurred-at:: {ts.isoformat()}\n"
            f"git-head:: {git_head}\n"
            f"git-branch:: {git_branch}\n"
            f"---\n\n"
            f"# {event_type}\n\n"
            + (f"> {note}\n\n" if note else "")
            + f"## JSON\n\n```json\n{json.dumps(payload, indent=2, ensure_ascii=False)}\n```\n\n"
            f"## XML\n\n```xml\n{xml_text}\n```\n\n"
            f"## API\n\n```bash\n{api_call}\n```\n\n"
            f"## MediaWiki\n\n```mediawiki\n{mw_text}\n```\n"
        )

        fragment_path.write_text(content, encoding="utf-8")
        self._pending.append(fragment_path)
        return fragment_path

    def stage(self, paths: Optional[List[Path]] = None) -> str:
        """Git add the pending fragments. Returns git output."""
        targets = [str(p) for p in (paths or self._pending)]
        if not targets:
            return "nothing to stage"
        return _git_run(["git", "add", "--"] + targets, self.repo_root)

    def commit(self, message: str = "singine gitlog: auto-commit") -> str:
        """Stage pending fragments and create a git commit."""
        self.stage()
        result = _git_run(
            ["git", "commit", "-m", message, "--allow-empty"],
            self.repo_root,
        )
        self._pending.clear()
        return result

    def status(self) -> Dict[str, Any]:
        """Return current git status and pending fragment count."""
        return {
            "pending_fragments": len(self._pending),
            "git_head": _git_run(["git", "rev-parse", "HEAD"], self.repo_root),
            "git_branch": _git_run(["git", "rev-parse", "--abbrev-ref", "HEAD"], self.repo_root),
            "git_status": _git_run(["git", "status", "--short"], self.repo_root),
            "log_dir": str(self.log_dir),
        }

    def tail(self, n: int = 10) -> List[Path]:
        """Return the most recent fragment paths."""
        all_frags = sorted(self.log_dir.rglob("*.md"), reverse=True)
        return all_frags[:n]


# Module-level default instance
_default: Optional[GitLog] = None


def default_log() -> GitLog:
    global _default
    if _default is None:
        _default = GitLog()
    return _default


def record(event_type: str, payload: Dict[str, Any], **kwargs: Any) -> Path:
    return default_log().record(event_type, payload, **kwargs)
