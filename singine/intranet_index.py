"""Shared sindoc.local index for generated local intranet pages."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, List


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_registry(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _write_registry(path: Path, items: List[Dict[str, Any]]) -> None:
    path.write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")


def render_index(items: List[Dict[str, Any]]) -> str:
    cards = []
    for item in items:
        cards.append(
            f"""
            <article class="card">
              <p class="eyebrow">{escape(item.get('kind', 'page'))}</p>
              <h2><a href="{escape(item['href'])}">{escape(item['title'])}</a></h2>
              <p>{escape(item.get('description', ''))}</p>
              <code>{escape(item.get('href', ''))}</code>
            </article>
            """
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sindoc Local</title>
  <style>
    :root {{ --bg:#f5efe5; --ink:#13212b; --muted:#5d675d; --accent:#9a3d20; --panel:#fffaf3; --line:#e2d3bf; }}
    body {{ margin:0; font-family:"Iowan Old Style", Georgia, serif; color:var(--ink); background:radial-gradient(circle at top,#fff8ee, #f5efe5 58%, #efe2cf); }}
    main {{ max-width:1180px; margin:0 auto; padding:40px 18px 72px; }}
    h1 {{ margin:0; font-size:clamp(2.6rem,6vw,4.8rem); line-height:.94; max-width:9ch; }}
    p.lede {{ max-width:70ch; color:var(--muted); }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:18px; margin-top:28px; }}
    .card {{ background:var(--panel); border:1px solid var(--line); padding:18px; box-shadow:0 18px 40px rgba(0,0,0,.08); }}
    .eyebrow {{ margin:0 0 6px; color:var(--accent); text-transform:uppercase; letter-spacing:.08em; font-size:.74rem; }}
    a {{ color:var(--ink); text-decoration:none; }}
    code {{ display:block; background:#f3e8d8; padding:6px 8px; white-space:pre-wrap; word-break:break-word; }}
  </style>
</head>
<body>
  <main>
    <p>Singine local intranet</p>
    <h1>Sindoc Local</h1>
    <p class="lede">Generated local control surfaces, observatories, and operational pages. New pages should always register here.</p>
    <section class="grid">{''.join(cards) if cards else '<article class="card"><p>No pages registered yet.</p></article>'}</section>
  </main>
</body>
</html>
"""


def register_page(*, site_root: Path, title: str, href: str, description: str, kind: str = "page") -> Dict[str, Any]:
    site_root.mkdir(parents=True, exist_ok=True)
    registry_path = site_root / "pages.json"
    items = _load_registry(registry_path)
    entry = {
        "title": title,
        "href": href,
        "description": description,
        "kind": kind,
        "updated_at": _now(),
    }
    items = [item for item in items if item.get("href") != href]
    items.append(entry)
    items.sort(key=lambda item: (item.get("kind", ""), item.get("title", "")))
    _write_registry(registry_path, items)
    (site_root / "index.html").write_text(render_index(items), encoding="utf-8")
    return entry
