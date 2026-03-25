"""Inspect and capture user dotfiles into a controlled repo."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_DOTFILES_REPO = Path("/Users/skh/ws/git/bitbucket/sindoc/dotfiles")


@dataclass(frozen=True)
class DotfileTarget:
    name: str
    home_relative: str
    repo_relative: Optional[str]
    kind: str
    description: str
    manifest_relative: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dir_excerpt(path: Path) -> List[str]:
    items: List[str] = []
    if not path.exists() or not path.is_dir():
        return items
    for child in sorted(path.iterdir(), key=lambda item: item.name)[:12]:
        suffix = "/" if child.is_dir() else ""
        items.append(f"{child.name}{suffix}")
    return items


def target_registry() -> List[DotfileTarget]:
    return [
        DotfileTarget("profile", ".profile", "dot/.profile", "file", "POSIX shell startup profile"),
        DotfileTarget("bash-profile", ".bash_profile", "dot/.bash_profile", "file", "Bash login shell profile"),
        DotfileTarget("bashrc", ".bashrc", "dot/.bashrc", "file", "Interactive Bash shell config"),
        DotfileTarget("zprofile", ".zprofile", "dot/.zprofile", "file", "Zsh login profile"),
        DotfileTarget("zshrc", ".zshrc", "dot/.zshrc", "file", "Interactive Zsh shell config"),
        DotfileTarget("vimrc", ".vimrc", "dot/.vimrc", "file", "Vim configuration"),
        DotfileTarget("box-shell", ".box-shell", "dot/.box-shell", "dir", "Shared shell helper scripts", "state/box-shell/manifest.json"),
        DotfileTarget("claude-home", ".claude", None, "dir", "Claude local state and config", "state/claude-home/manifest.json"),
        DotfileTarget("claude-ws", "ws/.claude", None, "dir", "Workspace Claude state", "state/claude-ws/manifest.json"),
        DotfileTarget("logseq-home", ".logseq", None, "dir", "Logseq desktop state", "state/logseq-home/manifest.json"),
        DotfileTarget("dropbox", "Dropbox", None, "dir", "Dropbox root folder", "state/dropbox/manifest.json"),
    ]


def inspect_targets(*, home_dir: Path, dotfiles_repo: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for target in target_registry():
        home_path = home_dir / target.home_relative
        repo_path = dotfiles_repo / target.repo_relative if target.repo_relative else None
        item: Dict[str, Any] = {
            "name": target.name,
            "description": target.description,
            "kind": target.kind,
            "home_path": str(home_path),
            "home_exists": home_path.exists(),
            "repo_path": str(repo_path) if repo_path else None,
            "repo_exists": bool(repo_path and repo_path.exists()),
            "manifest_path": str(dotfiles_repo / target.manifest_relative) if target.manifest_relative else None,
        }
        if home_path.exists():
            stat = home_path.stat()
            item["home_modified_at"] = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
            if home_path.is_file():
                item["home_size"] = stat.st_size
                item["home_sha256"] = _sha256(home_path)
            else:
                item["home_children_excerpt"] = _dir_excerpt(home_path)
                item["home_child_count"] = sum(1 for _ in home_path.iterdir())
        if repo_path and repo_path.exists():
            if repo_path.is_file():
                item["repo_sha256"] = _sha256(repo_path)
                item["in_sync"] = item.get("home_sha256") == item.get("repo_sha256")
            else:
                item["repo_children_excerpt"] = _dir_excerpt(repo_path)
        rows.append(item)
    return rows


def build_payload(*, home_dir: Path, dotfiles_repo: Path) -> Dict[str, Any]:
    items = inspect_targets(home_dir=home_dir, dotfiles_repo=dotfiles_repo)
    managed = sum(1 for item in items if item.get("repo_exists"))
    unmanaged = sum(1 for item in items if item.get("home_exists") and not item.get("repo_exists"))
    return {
        "generated_at": _now(),
        "home_dir": str(home_dir),
        "dotfiles_repo": str(dotfiles_repo),
        "summary": {
            "target_count": len(items),
            "managed_count": managed,
            "unmanaged_count": unmanaged,
        },
        "items": items,
    }


def render_html(payload: Dict[str, Any]) -> str:
    cards = []
    for item in payload["items"]:
        home_state = "present" if item["home_exists"] else "missing"
        repo_state = "tracked" if item["repo_exists"] else "untracked"
        excerpt = item.get("home_children_excerpt") or item.get("repo_children_excerpt") or []
        excerpt_html = "".join(f"<li>{escape(entry)}</li>" for entry in excerpt) or "<li>No preview available.</li>"
        sync_badge = ""
        if "in_sync" in item:
            sync_badge = f"<span class='badge'>{'in-sync' if item['in_sync'] else 'drift'}</span>"
        cards.append(
            f"""
            <article class="card">
              <header>
                <div>
                  <p class="eyebrow">{escape(item['kind'])}</p>
                  <h2>{escape(item['name'])}</h2>
                </div>
                {sync_badge}
              </header>
              <p>{escape(item['description'])}</p>
              <dl>
                <div><dt>Home</dt><dd>{escape(home_state)}</dd></div>
                <div><dt>Repo</dt><dd>{escape(repo_state)}</dd></div>
              </dl>
              <p><code>{escape(item['home_path'])}</code></p>
              <p><code>{escape(item.get('repo_path') or item.get('manifest_path') or '')}</code></p>
              <ul>{excerpt_html}</ul>
            </article>
            """
        )
    summary = payload["summary"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Singine Dotfiles Control</title>
  <style>
    :root {{ --bg:#f3efe7; --ink:#16212b; --muted:#55616b; --accent:#8a3a18; --panel:#fffaf3; --line:#e2d7c8; }}
    body {{ margin:0; font-family:"Iowan Old Style", Georgia, serif; background:linear-gradient(180deg,#faf6ef,#f3efe7); color:var(--ink); }}
    main {{ max-width:1180px; margin:0 auto; padding:40px 18px 72px; }}
    h1 {{ margin:0; font-size:clamp(2.6rem,6vw,4.8rem); line-height:.94; max-width:11ch; }}
    .summary {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:14px; margin:24px 0 32px; }}
    .metric, .card {{ background:var(--panel); border:1px solid var(--line); box-shadow:0 18px 40px rgba(0,0,0,.08); }}
    .metric {{ padding:18px; }}
    .metric strong {{ display:block; color:var(--accent); font-size:2rem; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:18px; }}
    .card {{ padding:18px; }}
    .card header {{ display:flex; justify-content:space-between; gap:10px; align-items:flex-start; }}
    .eyebrow {{ margin:0 0 6px; color:var(--accent); text-transform:uppercase; font-size:.74rem; letter-spacing:.08em; }}
    .badge {{ border:1px solid var(--line); padding:6px 10px; font-size:.78rem; }}
    dl {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }}
    dt {{ color:var(--muted); font-size:.72rem; text-transform:uppercase; }}
    dd {{ margin:4px 0 0; }}
    code {{ display:block; white-space:pre-wrap; word-break:break-word; background:#f4eadc; padding:6px 8px; }}
  </style>
</head>
<body>
  <main>
    <p>Singine dotfiles control surface</p>
    <h1>Dotfiles under control</h1>
    <p>Home: <code>{escape(payload['home_dir'])}</code><br>Repo: <code>{escape(payload['dotfiles_repo'])}</code></p>
    <section class="summary">
      <div class="metric"><small>Targets</small><strong>{summary['target_count']}</strong></div>
      <div class="metric"><small>Managed</small><strong>{summary['managed_count']}</strong></div>
      <div class="metric"><small>Unmanaged</small><strong>{summary['unmanaged_count']}</strong></div>
    </section>
    <section class="grid">{''.join(cards)}</section>
  </main>
</body>
</html>
"""


def write_dashboard(*, output_dir: Path, home_dir: Path, dotfiles_repo: Path) -> Dict[str, Any]:
    from .intranet_index import register_page

    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_payload(home_dir=home_dir, dotfiles_repo=dotfiles_repo)
    html_path = output_dir / "index.html"
    json_path = output_dir / "dotfiles.json"
    html_path.write_text(render_html(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    site_root = output_dir.parent
    register_page(
        site_root=site_root,
        title="Dotfiles Control",
        href=f"/{output_dir.name}/",
        description="Inventory and control surface for shell files, vimrc, Dropbox, Claude, and Logseq state.",
        kind="dashboard",
    )
    return {
        "report": payload,
        "artifacts": {
            "html": str(html_path),
            "json": str(json_path),
        },
    }


def capture_target(*, name: str, home_dir: Path, dotfiles_repo: Path) -> Dict[str, Any]:
    target = next((item for item in target_registry() if item.name == name), None)
    if target is None:
        raise KeyError(name)
    home_path = home_dir / target.home_relative
    if not home_path.exists():
        raise FileNotFoundError(home_path)
    if target.repo_relative:
        repo_path = dotfiles_repo / target.repo_relative
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        if home_path.is_file():
            shutil.copy2(home_path, repo_path)
        else:
            if repo_path.exists():
                shutil.rmtree(repo_path)
            shutil.copytree(home_path, repo_path)
        return {
            "name": target.name,
            "mode": "copy",
            "source": str(home_path),
            "target": str(repo_path),
        }
    manifest_path = dotfiles_repo / (target.manifest_relative or f"state/{target.name}/manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": target.name,
        "captured_at": _now(),
        "source": str(home_path),
        "kind": target.kind,
        "children_excerpt": _dir_excerpt(home_path) if home_path.is_dir() else [],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {
        "name": target.name,
        "mode": "manifest",
        "source": str(home_path),
        "target": str(manifest_path),
    }
