"""HTML dashboard for governed AI sessions across JSON and EDN stores."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _edn_str(text: str, key: str, default: str = "") -> str:
    match = re.search(rf"{re.escape(key)}\s+\"([^\"]*)\"", text, re.MULTILINE)
    return match.group(1) if match else default


def _edn_keyword(text: str, key: str, default: str = "") -> str:
    match = re.search(rf"{re.escape(key)}\s+:(\S+)", text, re.MULTILINE)
    return match.group(1).lower() if match else default


def _edn_int(text: str, key: str, default: int = 0) -> int:
    match = re.search(rf"{re.escape(key)}\s+(\d+)", text, re.MULTILINE)
    return int(match.group(1)) if match else default


def _parse_edn_commands(text: str) -> List[Dict[str, str]]:
    pattern = re.compile(
        r':cmd/id\s+"(?P<id>[^"]+)".*?'
        r':cmd/tool\s+"(?P<tool>[^"]+)".*?'
        r':cmd/seq\s+(?P<seq>\d+).*?'
        r':cmd/resource\s+"(?P<resource>[^"]+)".*?'
        r':cmd/purpose\s+"(?P<purpose>[^"]+)"',
        re.DOTALL,
    )
    commands: List[Dict[str, str]] = []
    for match in pattern.finditer(text):
        commands.append(
            {
                "id": match.group("id"),
                "tool": match.group("tool"),
                "seq": match.group("seq"),
                "resource": match.group("resource"),
                "purpose": match.group("purpose"),
            }
        )
    return commands


def load_json_sessions(root_dir: Path) -> List[Dict[str, Any]]:
    sessions_dir = root_dir / "sessions"
    rows: List[Dict[str, Any]] = []
    if not sessions_dir.exists():
        return rows
    for session_dir in sorted(p for p in sessions_dir.iterdir() if p.is_dir()):
        manifest = _read_json(session_dir / "manifest.json", {})
        interactions = _read_json(session_dir / "interactions.json", [])
        mandates = _read_json(session_dir / "mandates.json", [])
        if not manifest:
            continue
        provider = (manifest.get("provider") or "").lower()
        rows.append(
            {
                "session_id": manifest.get("session_id", session_dir.name),
                "provider": provider,
                "model": manifest.get("model", ""),
                "status": manifest.get("status", ""),
                "started_at": manifest.get("started_at", ""),
                "ended_at": manifest.get("ended_at", ""),
                "source": "json-store",
                "topic": manifest.get("metadata", {}).get("topic", ""),
                "interaction_count": len(interactions),
                "mandate_count": len(mandates),
                "command_count": 0,
                "interactions": interactions,
                "commands": [],
                "session_path": str(session_dir),
            }
        )
    return rows


def load_edn_sessions(repo_ai_dir: Path) -> List[Dict[str, Any]]:
    sessions_dir = repo_ai_dir / "sessions"
    rows: List[Dict[str, Any]] = []
    if not sessions_dir.exists():
        return rows
    for session_dir in sorted(p for p in sessions_dir.iterdir() if p.is_dir()):
        manifest_text = _read_text(session_dir / "manifest.edn")
        commands_text = _read_text(session_dir / "commands.edn")
        if not manifest_text:
            continue
        provider = _edn_keyword(manifest_text, ":session/provider")
        commands = _parse_edn_commands(commands_text)
        rows.append(
            {
                "session_id": session_dir.name,
                "provider": provider,
                "model": _edn_str(manifest_text, ":session/model"),
                "status": _edn_keyword(manifest_text, ":session/status"),
                "started_at": _edn_str(manifest_text, ":session/started-at"),
                "ended_at": _edn_str(manifest_text, ":session/ended-at"),
                "source": "edn-repo",
                "topic": _edn_str(manifest_text, ":session/topic"),
                "interaction_count": 0,
                "mandate_count": 0,
                "command_count": _edn_int(manifest_text, ":session/command-count", len(commands)),
                "interactions": [],
                "commands": commands,
                "session_path": str(session_dir),
            }
        )
    return rows


def collect_sessions(
    *,
    json_root_dir: Path,
    repo_ai_dir: Path,
    providers: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    normalized = {item.lower() for item in (providers or [])}
    sessions = load_json_sessions(json_root_dir) + load_edn_sessions(repo_ai_dir)
    if normalized:
        sessions = [item for item in sessions if item.get("provider", "").lower() in normalized]
    sessions.sort(key=lambda item: item.get("started_at", ""), reverse=True)
    return sessions


def build_dashboard_payload(
    *,
    json_root_dir: Path,
    repo_ai_dir: Path,
    providers: Optional[List[str]] = None,
    title: str = "Singine AI Session Dashboard",
    site_url: str = "http://sindoc.local:8080/",
) -> Dict[str, Any]:
    sessions = collect_sessions(json_root_dir=json_root_dir, repo_ai_dir=repo_ai_dir, providers=providers)
    provider_counts: Dict[str, int] = {}
    total_interactions = 0
    total_commands = 0
    for session in sessions:
        provider = session.get("provider") or "unknown"
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
        total_interactions += int(session.get("interaction_count", 0))
        total_commands += int(session.get("command_count", 0))
    return {
        "title": title,
        "generated_at": _now(),
        "site_url": site_url,
        "stores": {
            "json_root_dir": str(json_root_dir),
            "repo_ai_dir": str(repo_ai_dir),
        },
        "providers": sorted(provider_counts),
        "summary": {
            "session_count": len(sessions),
            "provider_counts": provider_counts,
            "interaction_count": total_interactions,
            "command_count": total_commands,
        },
        "sessions": sessions,
    }


def render_html(payload: Dict[str, Any]) -> str:
    cards: List[str] = []
    for session in payload["sessions"]:
        interactions = "".join(
            f"<li><strong>{escape(item.get('role', ''))}</strong><span>{escape(item.get('created_at', ''))}</span><p>{escape(item.get('content', ''))}</p></li>"
            for item in session.get("interactions", [])[:8]
        ) or "<li><p>No recorded interaction bodies in this session source.</p></li>"
        commands = "".join(
            f"<li><strong>{escape(item.get('tool', ''))}</strong><code>{escape(item.get('resource', ''))}</code><p>{escape(item.get('purpose', ''))}</p></li>"
            for item in session.get("commands", [])[:10]
        ) or "<li><p>No recorded command log in this session source.</p></li>"
        topic = escape((session.get("topic") or "").replace("\n", " ").strip()[:280] or "No topic recorded.")
        cards.append(
            f"""
            <article class="card" data-provider="{escape(session.get('provider', 'unknown'))}">
              <header>
                <div>
                  <p class="eyebrow">{escape(session.get('provider', 'unknown'))} · {escape(session.get('source', ''))}</p>
                  <h2>{escape(session.get('session_id', ''))}</h2>
                </div>
                <span class="status">{escape(session.get('status', ''))}</span>
              </header>
              <p class="topic">{topic}</p>
              <dl class="facts">
                <div><dt>Model</dt><dd>{escape(session.get('model', ''))}</dd></div>
                <div><dt>Started</dt><dd>{escape(session.get('started_at', ''))}</dd></div>
                <div><dt>Interactions</dt><dd>{session.get('interaction_count', 0)}</dd></div>
                <div><dt>Commands</dt><dd>{session.get('command_count', 0)}</dd></div>
              </dl>
              <div class="columns">
                <section>
                  <h3>Interactions</h3>
                  <ol>{interactions}</ol>
                </section>
                <section>
                  <h3>Command Sessions</h3>
                  <ol>{commands}</ol>
                </section>
              </div>
              <footer><code>{escape(session.get('session_path', ''))}</code></footer>
            </article>
            """
        )
    buttons = "".join(
        f'<button type="button" data-provider="{escape(provider)}">{escape(provider)}</button>'
        for provider in payload["providers"]
    )
    summary = payload["summary"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(payload['title'])}</title>
  <style>
    :root {{ --paper:#f5efe5; --ink:#13212b; --muted:#5d675d; --accent:#9a3d20; --panel:#fffaf3; --line:#e2d3bf; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:"Iowan Old Style", Georgia, serif; color:var(--ink); background:radial-gradient(circle at top,#fff8ee, #f5efe5 58%, #efe2cf); }}
    main {{ max-width:1280px; margin:0 auto; padding:40px 18px 72px; }}
    header.hero {{ display:grid; gap:16px; margin-bottom:28px; }}
    h1 {{ margin:0; font-size:clamp(2.8rem,7vw,5.2rem); line-height:.92; max-width:10ch; }}
    p.lede {{ margin:0; max-width:72ch; color:var(--muted); font-size:1.08rem; }}
    .summary {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; margin:24px 0; }}
    .metric {{ background:rgba(255,250,243,.82); backdrop-filter:blur(12px); border:1px solid var(--line); padding:18px; box-shadow:0 20px 50px rgba(18,33,43,.08); }}
    .metric strong {{ display:block; font-size:2rem; color:var(--accent); }}
    .filters {{ display:flex; gap:10px; flex-wrap:wrap; margin:18px 0 28px; }}
    .filters button {{ border:1px solid var(--line); background:var(--panel); color:var(--ink); padding:10px 14px; cursor:pointer; }}
    .grid {{ display:grid; gap:20px; }}
    .card {{ background:var(--panel); border:1px solid var(--line); padding:20px; box-shadow:0 18px 40px rgba(18,33,43,.08); }}
    .card header {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-start; }}
    .eyebrow {{ margin:0 0 6px; color:var(--accent); text-transform:uppercase; letter-spacing:.08em; font-size:.74rem; }}
    h2 {{ margin:0; font-size:1.25rem; overflow-wrap:anywhere; }}
    .status {{ border:1px solid var(--line); padding:6px 10px; font-size:.8rem; }}
    .topic {{ color:var(--muted); }}
    .facts {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px; margin:18px 0; }}
    .facts div {{ border-top:1px solid var(--line); padding-top:10px; }}
    dt {{ font-size:.72rem; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); }}
    dd {{ margin:6px 0 0; }}
    .columns {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:18px; }}
    ol {{ margin:0; padding-left:18px; }}
    li {{ margin-bottom:10px; }}
    li span {{ display:block; color:var(--muted); font-size:.82rem; }}
    li code, footer code {{ display:block; margin-top:4px; white-space:pre-wrap; word-break:break-word; font-size:.84rem; background:#f3e8d8; padding:4px 6px; }}
    footer {{ margin-top:16px; color:var(--muted); }}
  </style>
</head>
<body>
  <main>
    <header class="hero">
      <p>Singine local session observatory</p>
      <h1>{escape(payload['title'])}</h1>
      <p class="lede">This page combines the newer governed JSON session store under <code>{escape(payload['stores']['json_root_dir'])}</code> with the older EDN command-session records under <code>{escape(payload['stores']['repo_ai_dir'])}</code>. It is intended to let you inspect Claude and Codex work side by side, including command-line sessions.</p>
    </header>
    <section class="summary">
      <div class="metric"><small>Sessions</small><strong>{summary['session_count']}</strong></div>
      <div class="metric"><small>Interactions</small><strong>{summary['interaction_count']}</strong></div>
      <div class="metric"><small>Command Events</small><strong>{summary['command_count']}</strong></div>
      <div class="metric"><small>Site URL</small><strong style="font-size:1rem">{escape(payload['site_url'])}</strong></div>
    </section>
    <nav class="filters">
      <button type="button" data-provider="all">all</button>
      {buttons}
    </nav>
    <section class="grid">
      {''.join(cards) if cards else '<article class="card"><p>No matching sessions found.</p></article>'}
    </section>
  </main>
  <script>
    const buttons = Array.from(document.querySelectorAll('.filters button'));
    const cards = Array.from(document.querySelectorAll('.card[data-provider]'));
    for (const button of buttons) {{
      button.addEventListener('click', () => {{
        const provider = button.dataset.provider;
        for (const card of cards) {{
          const show = provider === 'all' || card.dataset.provider === provider;
          card.style.display = show ? '' : 'none';
        }}
      }});
    }}
  </script>
</body>
</html>
"""


def write_dashboard(
    *,
    output_dir: Path,
    json_root_dir: Path,
    repo_ai_dir: Path,
    providers: Optional[List[str]] = None,
    title: str = "Singine AI Session Dashboard",
    site_url: str = "http://sindoc.local:8080/",
) -> Dict[str, Any]:
    from .intranet_index import register_page

    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_dashboard_payload(
        json_root_dir=json_root_dir,
        repo_ai_dir=repo_ai_dir,
        providers=providers,
        title=title,
        site_url=site_url,
    )
    html_path = output_dir / "index.html"
    json_path = output_dir / "sessions.json"
    html_path.write_text(render_html(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    site_root = output_dir.parent
    register_page(
        site_root=site_root,
        title="AI Session Dashboard",
        href=f"/{output_dir.name}/",
        description="Claude and Codex session observatory across JSON and EDN stores.",
        kind="dashboard",
    )
    return {
        "dashboard": payload,
        "artifacts": {
            "html": str(html_path),
            "json": str(json_path),
        },
    }
