"""Unified control-center UI for local machine and edge runtime."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, List


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd: List[str]) -> Dict[str, Any]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return {
            "ok": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
        }
    except Exception as exc:
        return {"ok": False, "stdout": "", "stderr": str(exc), "exit_code": 1}


def _docker_ps() -> List[Dict[str, str]]:
    result = _run(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"])
    if not result["ok"]:
        return []
    rows: List[Dict[str, str]] = []
    for line in result["stdout"].splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        rows.append(
            {
                "name": parts[0] if len(parts) > 0 else "",
                "image": parts[1] if len(parts) > 1 else "",
                "status": parts[2] if len(parts) > 2 else "",
            }
        )
    return rows


def _edge_containers() -> List[Dict[str, str]]:
    rows = _docker_ps()
    return [
        row for row in rows
        if row["name"].startswith("edge-")
        or row["name"].startswith("singine-")
        or "collibra-edge" in row["image"]
        or "sindoc-collibra" in row["image"]
    ]


def _read_pages(site_root: Path) -> List[Dict[str, Any]]:
    pages_path = site_root / "pages.json"
    if not pages_path.exists():
        return []
    return json.loads(pages_path.read_text(encoding="utf-8"))


def build_payload(
    *,
    site_root: Path,
    home_dir: Path,
    dotfiles_repo: Path,
    ai_root_dir: Path,
    repo_ai_dir: Path,
    repo_root: Path,
) -> Dict[str, Any]:
    from .dotfiles import build_payload as build_dotfiles_payload
    from .server_surface import server_descriptor
    from .session_dashboard import build_dashboard_payload as build_session_payload

    dotfiles = build_dotfiles_payload(home_dir=home_dir, dotfiles_repo=dotfiles_repo)
    sessions = build_session_payload(
        json_root_dir=ai_root_dir,
        repo_ai_dir=repo_ai_dir,
        providers=["claude", "codex"],
        title="Singine AI Session Dashboard",
        site_url="http://sindoc.local:8080/sessions/",
    )
    server = server_descriptor(repo_root, environment_type="local")
    edge_rows = _edge_containers()
    return {
        "generated_at": _now(),
        "site_root": str(site_root),
        "machine": {
            "home_dir": str(home_dir),
            "repo_root": str(repo_root),
            "hostname": server["runtime"]["hostname"],
            "user": server["runtime"]["user"],
            "shell": server["runtime"]["shell"],
        },
        "dotfiles": {
            "summary": dotfiles["summary"],
            "href": "/dotfiles/",
        },
        "sessions": {
            "summary": sessions["summary"],
            "href": "/sessions/",
        },
        "edge": {
            "compose_file": str(repo_root / "docker" / "docker-compose.edge.yml"),
            "containers": edge_rows,
            "container_count": len(edge_rows),
            "health_url": "http://localhost:8080/health",
            "commands": [
                "python3 -m singine.command edge status --json",
                "python3 -m singine.command edge logs --service edge-site",
                "python3 -m singine.command edge up --json",
                "python3 -m singine.command edge down --json",
            ],
        },
        "intranet_pages": _read_pages(site_root),
    }


def render_html(payload: Dict[str, Any]) -> str:
    page_cards = "".join(
        f"<li><a href=\"{escape(item['href'])}\">{escape(item['title'])}</a></li>"
        for item in payload["intranet_pages"]
        if item.get("href") != "/control/"
    ) or "<li>No other pages registered yet.</li>"
    edge_cards = "".join(
        f"""
        <tr>
          <td>{escape(item['name'])}</td>
          <td>{escape(item['image'])}</td>
          <td>{escape(item['status'])}</td>
        </tr>
        """
        for item in payload["edge"]["containers"]
    ) or "<tr><td colspan='3'>No matching edge containers detected.</td></tr>"
    edge_cmds = "".join(f"<li><code>{escape(cmd)}</code></li>" for cmd in payload["edge"]["commands"])
    dot_summary = payload["dotfiles"]["summary"]
    sess_summary = payload["sessions"]["summary"]
    machine = payload["machine"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sindoc Local Control Center</title>
  <style>
    :root {{ --paper:#f4eee3; --ink:#13212b; --muted:#5d675d; --accent:#9a3d20; --panel:#fffaf3; --line:#e2d3bf; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:"Iowan Old Style", Georgia, serif; color:var(--ink); background:linear-gradient(180deg,#fff7ed,#f4eee3); }}
    main {{ max-width:1280px; margin:0 auto; padding:40px 18px 72px; }}
    h1 {{ margin:0; font-size:clamp(2.8rem,7vw,5.3rem); line-height:.92; max-width:9ch; }}
    p.lede {{ max-width:76ch; color:var(--muted); font-size:1.08rem; }}
    .summary, .grid {{ display:grid; gap:18px; }}
    .summary {{ grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); margin:26px 0 32px; }}
    .grid {{ grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); }}
    .metric, .card {{ background:var(--panel); border:1px solid var(--line); box-shadow:0 18px 40px rgba(0,0,0,.08); }}
    .metric {{ padding:18px; }}
    .metric strong {{ display:block; color:var(--accent); font-size:2rem; }}
    .card {{ padding:20px; }}
    .eyebrow {{ margin:0 0 6px; color:var(--accent); text-transform:uppercase; letter-spacing:.08em; font-size:.74rem; }}
    h2 {{ margin:.1rem 0 .7rem; }}
    a {{ color:var(--ink); text-decoration:none; }}
    ul {{ padding-left:18px; }}
    code {{ display:block; background:#f3e8d8; padding:7px 9px; white-space:pre-wrap; word-break:break-word; }}
    table {{ width:100%; border-collapse:collapse; }}
    th, td {{ text-align:left; padding:8px 0; border-bottom:1px solid var(--line); vertical-align:top; }}
  </style>
</head>
<body>
  <main>
    <p>Singine local intranet</p>
    <h1>Control Center</h1>
    <p class="lede">One place to manage this machine, your governed artifacts, and the live edge Docker runtime. This page is intentionally command-oriented: it shows the current state and the exact Singine entrypoints to act on it.</p>
    <section class="summary">
      <div class="metric"><small>Dotfile targets</small><strong>{dot_summary['target_count']}</strong></div>
      <div class="metric"><small>Managed dotfiles</small><strong>{dot_summary['managed_count']}</strong></div>
      <div class="metric"><small>AI sessions</small><strong>{sess_summary['session_count']}</strong></div>
      <div class="metric"><small>Edge containers</small><strong>{payload['edge']['container_count']}</strong></div>
    </section>
    <section class="grid">
      <article class="card">
        <p class="eyebrow">Machine</p>
        <h2>{escape(machine['hostname'])}</h2>
        <p>User: {escape(str(machine['user']))}<br>Shell: {escape(str(machine['shell']))}</p>
        <code>{escape(machine['home_dir'])}</code>
        <code>{escape(machine['repo_root'])}</code>
      </article>
      <article class="card">
        <p class="eyebrow">Dotfiles</p>
        <h2><a href="{escape(payload['dotfiles']['href'])}">Dotfiles Control</a></h2>
        <p>Managed: {dot_summary['managed_count']}<br>Unmanaged: {dot_summary['unmanaged_count']}</p>
        <ul>
          <li><code>python3 -m singine.command dotfiles inspect --json</code></li>
          <li><code>python3 -m singine.command dotfiles capture bashrc --json</code></li>
          <li><code>python3 -m singine.command dotfiles capture logseq-home --json</code></li>
        </ul>
      </article>
      <article class="card">
        <p class="eyebrow">Sessions</p>
        <h2><a href="{escape(payload['sessions']['href'])}">AI Session Dashboard</a></h2>
        <p>Claude/Codex sessions: {sess_summary['session_count']}<br>Interactions: {sess_summary['interaction_count']}<br>Command events: {sess_summary['command_count']}</p>
        <ul>
          <li><code>python3 -m singine.command ai session list --json</code></li>
          <li><code>python3 -m singine.command ai session overview --provider claude</code></li>
          <li><code>python3 -m singine.command ai session dashboard --output-dir {escape(str(Path(payload['site_root']) / 'sessions'))} --json</code></li>
        </ul>
      </article>
      <article class="card">
        <p class="eyebrow">Edge Runtime</p>
        <h2>Docker Edge</h2>
        <p>Compose file:</p>
        <code>{escape(payload['edge']['compose_file'])}</code>
        <p>Health endpoint:</p>
        <code>{escape(payload['edge']['health_url'])}</code>
        <table>
          <thead><tr><th>Name</th><th>Image</th><th>Status</th></tr></thead>
          <tbody>{edge_cards}</tbody>
        </table>
        <ul>{edge_cmds}</ul>
      </article>
      <article class="card">
        <p class="eyebrow">Intranet</p>
        <h2>Sindoc Local Pages</h2>
        <ul>{page_cards}</ul>
      </article>
      <article class="card">
        <p class="eyebrow">Serve</p>
        <h2>Local UI</h2>
        <ul>
          <li><code>python3 -m singine.command web {escape(payload['site_root'])} --port 8080</code></li>
          <li><code>http://sindoc.local:8080/</code></li>
          <li><code>http://sindoc.local:8080/control/</code></li>
        </ul>
      </article>
    </section>
  </main>
</body>
</html>
"""


def write_control_center(
    *,
    output_dir: Path,
    home_dir: Path,
    dotfiles_repo: Path,
    ai_root_dir: Path,
    repo_ai_dir: Path,
    repo_root: Path,
) -> Dict[str, Any]:
    from .intranet_index import register_page

    output_dir.mkdir(parents=True, exist_ok=True)
    site_root = output_dir.parent
    payload = build_payload(
        site_root=site_root,
        home_dir=home_dir,
        dotfiles_repo=dotfiles_repo,
        ai_root_dir=ai_root_dir,
        repo_ai_dir=repo_ai_dir,
        repo_root=repo_root,
    )
    html_path = output_dir / "index.html"
    json_path = output_dir / "control.json"
    html_path.write_text(render_html(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    register_page(
        site_root=site_root,
        title="Control Center",
        href=f"/{output_dir.name}/",
        description="Machine, dotfiles, sessions, and live Docker edge runtime in one intranet page.",
        kind="dashboard",
    )
    return {
        "control_center": payload,
        "artifacts": {
            "html": str(html_path),
            "json": str(json_path),
        },
    }
