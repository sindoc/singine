"""Governed AI session recording for Singine.

This module provides a local session abstraction for provider families such as
Claude and Codex/OpenAI. The current implementation records the full session
shape, mandates, and interaction log without calling the external APIs yet.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_ai_root() -> Path:
    return Path.home() / ".singine" / "ai"


def default_db_path(root_dir: Path) -> Path:
    return root_dir / "sqlite.db"


def provider_object_ref(provider: str, session_id: str) -> str:
    if provider == "claude":
        return f"anthropic:session:{session_id}"
    if provider in {"codex", "openai"}:
        return f"openai:session:{session_id}"
    return f"{provider}:session:{session_id}"


def session_urn(provider: str, session_id: str) -> str:
    return f"urn:singine:ai:session:{provider}:{session_id}"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


class AiSessionStore:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.sessions_dir = root_dir / "sessions"
        ensure_dir(self.sessions_dir)

    def session_dir(self, session_id: str) -> Path:
        return self.sessions_dir / session_id

    def manifest_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "manifest.json"

    def interactions_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "interactions.json"

    def mandates_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "mandates.json"

    def create_session(
        self,
        *,
        provider: str,
        model: str,
        session_id: Optional[str] = None,
        mandate_file: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        session_id = session_id or str(uuid.uuid4())
        session_dir = self.session_dir(session_id)
        ensure_dir(session_dir)
        manifest = {
            "session_id": session_id,
            "provider": provider,
            "model": model,
            "started_at": now_iso(),
            "ended_at": None,
            "status": "active",
            "session_urn": session_urn(provider, session_id),
            "provider_object_ref": provider_object_ref(provider, session_id),
            "mandate_source": mandate_file or "",
            "metadata": metadata or {},
        }
        write_json(self.manifest_path(session_id), manifest)
        write_json(self.interactions_path(session_id), [])
        write_json(self.mandates_path(session_id), [])
        return manifest

    def load_manifest(self, session_id: str) -> Dict[str, Any]:
        return read_json(self.manifest_path(session_id), {})

    def save_manifest(self, session_id: str, manifest: Dict[str, Any]) -> None:
        write_json(self.manifest_path(session_id), manifest)

    def append_interaction(self, session_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        interactions = read_json(self.interactions_path(session_id), [])
        item = {
            "interaction_id": str(uuid.uuid4()),
            "created_at": now_iso(),
            "role": role,
            "content": content,
            "metadata": metadata or {},
        }
        interactions.append(item)
        write_json(self.interactions_path(session_id), interactions)
        return item

    def append_mandate(self, session_id: str, action: str, resource: str, note: str = "") -> Dict[str, Any]:
        mandates = read_json(self.mandates_path(session_id), [])
        item = {
            "mandate_id": str(uuid.uuid4()),
            "created_at": now_iso(),
            "action": action,
            "resource": resource,
            "decision": "granted",
            "note": note,
        }
        mandates.append(item)
        write_json(self.mandates_path(session_id), mandates)
        return item

    def list_sessions(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for path in sorted(self.sessions_dir.iterdir(), key=lambda item: item.name):
            manifest = read_json(path / "manifest.json", {})
            if manifest:
                rows.append(manifest)
        return rows

    def latest_session_id(self) -> Optional[str]:
        sessions = self.list_sessions()
        if not sessions:
            return None
        sessions.sort(key=lambda item: item.get("started_at", ""))
        return sessions[-1].get("session_id")

    def load_session_bundle(self, session_id: str) -> Dict[str, Any]:
        manifest = self.load_manifest(session_id)
        interactions = read_json(self.interactions_path(session_id), [])
        mandates = read_json(self.mandates_path(session_id), [])
        return {
            "manifest": manifest,
            "interactions": interactions,
            "mandates": mandates,
        }


def ensure_db(db_path: Path) -> sqlite3.Connection:
    ensure_dir(db_path.parent)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_sessions (
          session_id TEXT PRIMARY KEY,
          provider TEXT NOT NULL,
          model TEXT NOT NULL,
          session_urn TEXT NOT NULL,
          provider_object_ref TEXT NOT NULL,
          started_at TEXT NOT NULL,
          ended_at TEXT,
          status TEXT NOT NULL,
          metadata_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_interactions (
          interaction_id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          role TEXT NOT NULL,
          content TEXT NOT NULL,
          metadata_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_mandates (
          mandate_id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          action_name TEXT NOT NULL,
          resource TEXT NOT NULL,
          decision TEXT NOT NULL,
          note TEXT NOT NULL
        )
        """
    )
    return conn


def sync_session_to_db(root_dir: Path, db_path: Path, session_id: str) -> Dict[str, Any]:
    store = AiSessionStore(root_dir)
    bundle = store.load_session_bundle(session_id)
    manifest = bundle["manifest"]
    interactions = bundle["interactions"]
    mandates = bundle["mandates"]
    conn = ensure_db(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO ai_sessions (
              session_id, provider, model, session_urn, provider_object_ref,
              started_at, ended_at, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
              provider=excluded.provider,
              model=excluded.model,
              session_urn=excluded.session_urn,
              provider_object_ref=excluded.provider_object_ref,
              started_at=excluded.started_at,
              ended_at=excluded.ended_at,
              status=excluded.status,
              metadata_json=excluded.metadata_json
            """,
            (
                manifest.get("session_id", ""),
                manifest.get("provider", ""),
                manifest.get("model", ""),
                manifest.get("session_urn", ""),
                manifest.get("provider_object_ref", ""),
                manifest.get("started_at", ""),
                manifest.get("ended_at"),
                manifest.get("status", ""),
                json.dumps(manifest.get("metadata", {})),
            ),
        )
        conn.execute("DELETE FROM ai_interactions WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM ai_mandates WHERE session_id = ?", (session_id,))
        for item in interactions:
            conn.execute(
                """
                INSERT INTO ai_interactions (
                  interaction_id, session_id, created_at, role, content, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item.get("interaction_id", ""),
                    session_id,
                    item.get("created_at", ""),
                    item.get("role", ""),
                    item.get("content", ""),
                    json.dumps(item.get("metadata", {})),
                ),
            )
        for item in mandates:
            conn.execute(
                """
                INSERT INTO ai_mandates (
                  mandate_id, session_id, created_at, action_name, resource, decision, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.get("mandate_id", ""),
                    session_id,
                    item.get("created_at", ""),
                    item.get("action", ""),
                    item.get("resource", ""),
                    item.get("decision", ""),
                    item.get("note", ""),
                ),
            )
    return {
        "session_id": session_id,
        "db_path": str(db_path),
        "interaction_count": len(interactions),
        "mandate_count": len(mandates),
    }


def _print_session_banner(manifest: Dict[str, Any], resumed: bool = False) -> None:
    label = "resumed" if resumed else "session_id"
    print(f"{label}:   {manifest['session_id']}")
    print(f"provider:   {manifest['provider']}")
    print(f"model:      {manifest['model']}")
    print(f"urn:        {manifest['session_urn']}")
    print(f"provider-ref:{manifest['provider_object_ref']}")
    print("commands:")
    print("  /mandate ACTION RESOURCE [NOTE]")
    print("  /meta KEY=VALUE")
    print("  /exit")


def _latest_session_for_provider(store: AiSessionStore, provider: str) -> Optional[str]:
    sessions = [s for s in store.list_sessions() if s.get("provider") == provider]
    if not sessions:
        return None
    sessions.sort(key=lambda s: s.get("started_at", ""))
    return sessions[-1].get("session_id")


def _pick_session(store: AiSessionStore, provider: Optional[str] = None) -> Optional[str]:
    sessions = store.list_sessions()
    if provider:
        sessions = [s for s in sessions if s.get("provider") == provider]
    sessions.sort(key=lambda s: s.get("started_at", ""), reverse=True)
    if not sessions:
        print("no recorded sessions", file=sys.stderr)
        return None
    print(f"\n{'#':<4} {'SESSION-ID':<38} {'MODEL':<24} {'STATUS':<8} {'STARTED':<26} {'INT':>4} {'MND':>4}")
    print("-" * 110)
    for i, s in enumerate(sessions, 1):
        sid = s.get("session_id", "")
        interactions = read_json(store.interactions_path(sid), [])
        mandates = read_json(store.mandates_path(sid), [])
        print(
            f"{i:<4} {sid:<38} {s.get('model', '')[:22]:<24} {s.get('status', ''):<8} "
            f"{s.get('started_at', '')[:25]:<26} {len(interactions):>4} {len(mandates):>4}"
        )
    print()
    try:
        choice = input("select [1]: ").strip()
    except EOFError:
        return None
    idx = (int(choice) - 1) if choice.isdigit() else 0
    if 0 <= idx < len(sessions):
        return sessions[idx].get("session_id")
    return None


def cmd_ai_provider(args: argparse.Namespace) -> int:
    root_dir = Path(args.root_dir).expanduser().resolve()
    store = AiSessionStore(root_dir)

    resume_mode = getattr(args, "resume", False)
    continue_mode = getattr(args, "continue_", False)
    session_id = args.session

    resumed = False
    if continue_mode:
        session_id = _latest_session_for_provider(store, args.provider)
        if not session_id:
            print(f"no recorded {args.provider} sessions to continue", file=sys.stderr)
            return 1
        resumed = True
    elif resume_mode:
        session_id = _pick_session(store, args.provider)
        if not session_id:
            return 1
        resumed = True

    if resumed and store.manifest_path(session_id).exists():
        manifest = store.load_manifest(session_id)
        manifest["status"] = "active"
        manifest["resumed_at"] = now_iso()
        store.save_manifest(session_id, manifest)
    else:
        manifest = store.create_session(
            provider=args.provider,
            model=args.model,
            session_id=session_id,
            mandate_file=args.mandate,
            metadata={"api_execution": "deferred", "transport": "abstract-session"},
        )
    _print_session_banner(manifest, resumed=resumed)
    metadata = manifest.get("metadata", {})

    while True:
        try:
            line = input(f"{args.provider}> ")
        except EOFError:
            line = "/exit"
        text = line.strip()
        if not text:
            continue
        if text == "/exit":
            break
        if text.startswith("/mandate "):
            parts = text.split(" ", 3)
            if len(parts) < 3:
                print("usage: /mandate ACTION RESOURCE [NOTE]", file=sys.stderr)
                continue
            note = parts[3] if len(parts) > 3 else ""
            item = store.append_mandate(manifest["session_id"], parts[1], parts[2], note)
            print(f"mandate recorded: {item['mandate_id']}")
            continue
        if text.startswith("/meta "):
            payload = text[len("/meta "):]
            if "=" not in payload:
                print("usage: /meta KEY=VALUE", file=sys.stderr)
                continue
            key, value = payload.split("=", 1)
            metadata[key.strip()] = value.strip()
            manifest["metadata"] = metadata
            store.save_manifest(manifest["session_id"], manifest)
            print(f"metadata updated: {key.strip()}")
            continue
        store.append_interaction(
            manifest["session_id"],
            "user",
            text,
            {
                "provider": args.provider,
                "provider_object_ref": manifest["provider_object_ref"],
                "api_execution": "deferred",
            },
        )
        store.append_interaction(
            manifest["session_id"],
            "assistant",
            f"[deferred:{args.provider}] interaction recorded but provider API not executed",
            {
                "provider": args.provider,
                "provider_object_ref": manifest["provider_object_ref"],
                "execution_state": "not-called",
            },
        )
        print("recorded")

    manifest["ended_at"] = now_iso()
    manifest["status"] = "closed"
    store.save_manifest(manifest["session_id"], manifest)

    if args.db:
        summary = sync_session_to_db(root_dir, Path(args.db).expanduser().resolve(), manifest["session_id"])
        print(json.dumps({"ok": True, "synced": summary}, indent=2))
    else:
        print(json.dumps({"ok": True, "session_id": manifest["session_id"]}, indent=2))
    return 0


def cmd_ai_session_list(args: argparse.Namespace) -> int:
    store = AiSessionStore(Path(args.root_dir).expanduser().resolve())
    payload = store.list_sessions()
    print(json.dumps(payload, indent=2))
    return 0


def cmd_ai_session_overview(args: argparse.Namespace) -> int:
    root_dir = Path(args.root_dir).expanduser().resolve()
    store = AiSessionStore(root_dir)
    sessions = store.list_sessions()
    provider = getattr(args, "provider", None)
    if provider:
        sessions = [s for s in sessions if s.get("provider") == provider]
    sessions.sort(key=lambda s: s.get("started_at", ""), reverse=True)
    if not sessions:
        print("no recorded AI sessions")
        return 0
    print(f"\n{'#':<4} {'SESSION-ID':<38} {'PROVIDER':<10} {'MODEL':<24} {'STATUS':<8} {'STARTED':<26} {'INT':>4} {'MND':>4}")
    print("-" * 120)
    for i, s in enumerate(sessions, 1):
        sid = s.get("session_id", "")
        interactions = read_json(store.interactions_path(sid), [])
        mandates = read_json(store.mandates_path(sid), [])
        print(
            f"{i:<4} {sid:<38} {s.get('provider', ''):<10} {s.get('model', '')[:22]:<24} "
            f"{s.get('status', ''):<8} {s.get('started_at', '')[:25]:<26} "
            f"{len(interactions):>4} {len(mandates):>4}"
        )
    print()
    return 0


def cmd_ai_session_show(args: argparse.Namespace) -> int:
    store = AiSessionStore(Path(args.root_dir).expanduser().resolve())
    payload = store.load_session_bundle(args.session_id)
    print(json.dumps(payload, indent=2))
    return 0


def cmd_ai_last_session_data(args: argparse.Namespace) -> int:
    root_dir = Path(args.root_dir).expanduser().resolve()
    store = AiSessionStore(root_dir)
    session_id = store.latest_session_id()
    if not session_id:
        print("no recorded AI sessions", file=sys.stderr)
        return 1
    db_path = Path(args.db or default_db_path(root_dir)).expanduser().resolve()
    summary = sync_session_to_db(root_dir, db_path, session_id)
    payload = {
        "ok": True,
        "latest_session_id": session_id,
        "summary": summary,
        "bundle": store.load_session_bundle(session_id),
    }
    print(json.dumps(payload, indent=2))
    return 0


def add_ai_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    ai_parser = sub.add_parser(
        "ai",
        help="Governed AI provider sessions and session data synchronization",
    )
    ai_sub = ai_parser.add_subparsers(dest="ai_command")

    provider_parent = argparse.ArgumentParser(add_help=False)
    provider_parent.add_argument("--model", default="default")
    provider_parent.add_argument("--session", help="Reuse or pin a session id.")
    provider_parent.add_argument("--mandate", help="Mandate file reference.")
    provider_parent.add_argument("--root-dir", default=str(default_ai_root()))
    provider_parent.add_argument("--db", help="Optional SQLite path to sync on session close.")
    provider_parent.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help="Show an interactive session picker and reopen the selected session.",
    )
    provider_parent.add_argument(
        "--continue",
        dest="continue_",
        action="store_true",
        default=False,
        help="Reopen the most recent session for this provider.",
    )

    for provider in ["claude", "codex", "openai"]:
        parser = ai_sub.add_parser(provider, parents=[provider_parent], help=f"Open a governed {provider} session shell")
        parser.set_defaults(func=cmd_ai_provider, provider=provider)

    session_parser = ai_sub.add_parser("session", help="Inspect recorded AI sessions")
    session_sub = session_parser.add_subparsers(dest="session_command")

    session_list = session_sub.add_parser("list", help="List recorded sessions (JSON)")
    session_list.add_argument("--root-dir", default=str(default_ai_root()))
    session_list.set_defaults(func=cmd_ai_session_list)

    session_overview = session_sub.add_parser("overview", help="Human-readable session table with interaction and mandate counts")
    session_overview.add_argument("--root-dir", default=str(default_ai_root()))
    session_overview.add_argument("--provider", help="Filter by provider (claude, codex, openai).")
    session_overview.set_defaults(func=cmd_ai_session_overview)

    session_show = session_sub.add_parser("show", help="Show one recorded session bundle")
    session_show.add_argument("session_id")
    session_show.add_argument("--root-dir", default=str(default_ai_root()))
    session_show.set_defaults(func=cmd_ai_session_show)

    last_parser = ai_sub.add_parser("last", help="Commands for the latest recorded AI session")
    last_sub = last_parser.add_subparsers(dest="last_command")

    last_session = last_sub.add_parser("session", help="Inspect or sync the latest session")
    last_session_sub = last_session.add_subparsers(dest="last_session_command")

    last_data = last_session_sub.add_parser("data", help="Sync the latest session bundle into sqlite.db and print it")
    last_data.add_argument("--root-dir", default=str(default_ai_root()))
    last_data.add_argument("--db", help="SQLite path (default: <root-dir>/sqlite.db)")
    last_data.set_defaults(func=cmd_ai_last_session_data)
