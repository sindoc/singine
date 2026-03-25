"""Central command history capture and publication for Singine."""

from __future__ import annotations

import html
import json
import os
import re
import shlex
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_COMMAND_LIBRARY_ROOT = Path(
    os.environ.get("SINGINE_COMMAND_LIBRARY_ROOT", str(Path.home() / ".singine" / "command-library"))
).expanduser()

VARIABLE_PATTERN = re.compile(r"(~(?=/|$)|\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$[A-Za-z_][A-Za-z0-9_]*)")


@dataclass
class CommandEvent:
    recorded_at: str
    shell: str
    pwd: str
    raw_command: str
    abstract_command: str
    exit_code: int
    history_id: Optional[int]
    pid: Optional[int]
    session: Optional[str]
    variables: List[str]
    argv: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recorded_at": self.recorded_at,
            "shell": self.shell,
            "pwd": self.pwd,
            "raw_command": self.raw_command,
            "abstract_command": self.abstract_command,
            "exit_code": self.exit_code,
            "history_id": self.history_id,
            "pid": self.pid,
            "session": self.session,
            "variables": self.variables,
            "argv": self.argv,
        }


def command_library_root(root_dir: Optional[Path] = None) -> Path:
    return Path(root_dir).expanduser() if root_dir else DEFAULT_COMMAND_LIBRARY_ROOT


def command_history_path(root_dir: Optional[Path] = None) -> Path:
    return command_library_root(root_dir) / "commands.jsonl"


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def extract_variables(raw_command: str) -> List[str]:
    seen: List[str] = []
    for match in VARIABLE_PATTERN.findall(raw_command):
        if match not in seen:
            seen.append(match)
    return seen


def split_argv(raw_command: str) -> List[str]:
    try:
        return shlex.split(raw_command, posix=True)
    except ValueError:
        return [raw_command]


def normalize_command(raw_command: str, *, pwd: Optional[str] = None, home: Optional[str] = None) -> str:
    normalized = raw_command.strip()
    home_value = home or str(Path.home())
    pwd_value = pwd or ""
    if home_value:
        normalized = normalized.replace(home_value, "$HOME")
    if pwd_value:
        normalized = normalized.replace(pwd_value, "$PWD")
    return normalized


def record_command(
    *,
    raw_command: str,
    shell: str,
    pwd: str,
    exit_code: int,
    history_id: Optional[int] = None,
    pid: Optional[int] = None,
    session: Optional[str] = None,
    root_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    root = command_library_root(root_dir)
    root.mkdir(parents=True, exist_ok=True)
    history_path = command_history_path(root)
    raw = raw_command.strip()
    event = CommandEvent(
        recorded_at=iso_now(),
        shell=shell,
        pwd=pwd,
        raw_command=raw,
        abstract_command=normalize_command(raw, pwd=pwd),
        exit_code=int(exit_code),
        history_id=int(history_id) if history_id is not None else None,
        pid=int(pid) if pid is not None else None,
        session=session,
        variables=extract_variables(raw),
        argv=split_argv(raw),
    )
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.to_dict(), ensure_ascii=True) + "\n")
    return {
        "ok": True,
        "root_dir": str(root),
        "history_path": str(history_path),
        "event": event.to_dict(),
    }


def iter_events(root_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    history_path = command_history_path(root_dir)
    if not history_path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with history_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def parse_timestamp(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def filter_events(events: Iterable[Dict[str, Any]], *, since_days: Optional[int] = None) -> List[Dict[str, Any]]:
    rows = list(events)
    if since_days is None:
        return rows
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    return [row for row in rows if parse_timestamp(row["recorded_at"]) >= cutoff]


def summarize_command_assets(
    events: Iterable[Dict[str, Any]],
    *,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in events:
        key = row.get("abstract_command") or row.get("raw_command") or ""
        if not key:
            continue
        item = grouped.setdefault(
            key,
            {
                "abstract_command": key,
                "count": 0,
                "last_seen_at": row["recorded_at"],
                "shells": set(),
                "working_dirs": set(),
                "variables": set(),
                "examples": [],
                "exit_codes": defaultdict(int),
            },
        )
        item["count"] += 1
        if row["recorded_at"] > item["last_seen_at"]:
            item["last_seen_at"] = row["recorded_at"]
        item["shells"].add(row.get("shell") or "unknown")
        item["working_dirs"].add(row.get("pwd") or "")
        for variable in row.get("variables") or []:
            item["variables"].add(variable)
        example = row.get("raw_command") or key
        if example not in item["examples"] and len(item["examples"]) < 5:
            item["examples"].append(example)
        item["exit_codes"][str(row.get("exit_code", 0))] += 1

    assets: List[Dict[str, Any]] = []
    for item in grouped.values():
        assets.append(
            {
                "abstract_command": item["abstract_command"],
                "count": item["count"],
                "last_seen_at": item["last_seen_at"],
                "shells": sorted(item["shells"]),
                "working_dirs": sorted(filter(None, item["working_dirs"]))[:10],
                "variables": sorted(item["variables"]),
                "examples": item["examples"],
                "exit_codes": dict(sorted(item["exit_codes"].items())),
            }
        )
    assets.sort(key=lambda row: (-row["count"], row["abstract_command"]))
    if limit is not None:
        assets = assets[:limit]
    return assets


def render_markdown(assets: List[Dict[str, Any]], meta: Dict[str, Any]) -> str:
    lines = [
        "# Command Library",
        "",
        f"Generated at: {meta['generated_at']}",
        f"Events scanned: {meta['event_count']}",
        f"Assets generated: {meta['asset_count']}",
        "",
    ]
    for asset in assets:
        lines.append(f"## `{asset['abstract_command']}`")
        lines.append("")
        lines.append(f"- Count: {asset['count']}")
        lines.append(f"- Last seen: {asset['last_seen_at']}")
        lines.append(f"- Shells: {', '.join(asset['shells']) or '(none)'}")
        lines.append(f"- Variables: {', '.join(asset['variables']) or '(none)'}")
        if asset["examples"]:
            lines.append("- Examples:")
            for example in asset["examples"]:
                lines.append(f"  - `{example}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_html(assets: List[Dict[str, Any]], meta: Dict[str, Any]) -> str:
    rows = []
    for asset in assets:
        examples = "<br/>".join(html.escape(example) for example in asset["examples"])
        variables = ", ".join(html.escape(item) for item in asset["variables"]) or "&nbsp;"
        rows.append(
            "<tr>"
            f"<td><code>{html.escape(asset['abstract_command'])}</code></td>"
            f"<td>{asset['count']}</td>"
            f"<td>{html.escape(asset['last_seen_at'])}</td>"
            f"<td>{html.escape(', '.join(asset['shells']))}</td>"
            f"<td>{variables}</td>"
            f"<td>{examples or '&nbsp;'}</td>"
            "</tr>"
        )
    table_rows = "\n".join(rows)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Singine Command Library</title>
  <style>
    :root {{
      color-scheme: light;
      --card: #fffdf9;
      --ink: #222222;
      --line: #d8cfbf;
      --accent: #8b3a2f;
    }}
    body {{ margin: 0; font-family: Georgia, "Iowan Old Style", serif; background: linear-gradient(180deg, #f7f2e8 0%, #efe6d6 100%); color: var(--ink); }}
    main {{ max-width: 1200px; margin: 0 auto; padding: 32px 24px 48px; }}
    h1 {{ margin-bottom: 8px; font-size: 2.4rem; }}
    p.meta {{ margin-top: 0; color: #5c5448; }}
    .table-wrap {{ background: var(--card); border: 1px solid var(--line); border-radius: 16px; overflow: hidden; box-shadow: 0 14px 40px rgba(70, 48, 24, 0.08); }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; vertical-align: top; padding: 14px 16px; border-bottom: 1px solid var(--line); }}
    th {{ background: #f0e6d6; font-size: 0.92rem; letter-spacing: 0.04em; text-transform: uppercase; }}
    tr:nth-child(even) td {{ background: #fffaf2; }}
    code {{ font-family: "SFMono-Regular", Menlo, monospace; color: var(--accent); }}
  </style>
</head>
<body>
  <main>
    <h1>Singine Command Library</h1>
    <p class="meta">Generated at {html.escape(meta['generated_at'])}. Events scanned: {meta['event_count']}. Assets generated: {meta['asset_count']}.</p>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Abstract Command</th>
            <th>Count</th>
            <th>Last Seen</th>
            <th>Shells</th>
            <th>Variables</th>
            <th>Examples</th>
          </tr>
        </thead>
        <tbody>
          {table_rows}
        </tbody>
      </table>
    </div>
  </main>
</body>
</html>
"""


def write_command_list(
    *,
    root_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    since_days: Optional[int] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    root = command_library_root(root_dir)
    events = filter_events(iter_events(root), since_days=since_days)
    assets = summarize_command_assets(events, limit=limit)
    target = Path(output_dir).expanduser() if output_dir else (root / "generated" / "latest")
    target.mkdir(parents=True, exist_ok=True)
    meta = {
        "generated_at": iso_now(),
        "root_dir": str(root),
        "history_path": str(command_history_path(root)),
        "event_count": len(events),
        "asset_count": len(assets),
        "since_days": since_days,
        "limit": limit,
    }
    json_path = target / "command-library.json"
    md_path = target / "command-library.md"
    html_path = target / "command-library.html"
    json_path.write_text(json.dumps({"meta": meta, "assets": assets}, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(assets, meta), encoding="utf-8")
    html_path.write_text(render_html(assets, meta), encoding="utf-8")
    return {
        "ok": True,
        "root_dir": str(root),
        "history_path": str(command_history_path(root)),
        "output_dir": str(target),
        "artifacts": {
            "json": str(json_path),
            "markdown": str(md_path),
            "html": str(html_path),
        },
        "meta": meta,
        "assets": assets,
    }
