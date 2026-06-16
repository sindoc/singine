"""singine graph — Logseq knowledge graph publisher.

Converts a Logseq graph (pages/ + journals/) into semantic HTML
suitable for serving from SilkPage www/.

Generates:
  www/graph/index.html        — graph landing page
  www/graph/pages/           — individual page files
  www/graph/graph-data.xml   — RDF/XML representation of the graph
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────

_HERE     = Path(__file__).parent
_WS       = _HERE.parent.parent.parent.parent
_SILKPAGE = _WS / "silkpage" / "main" / "silkpage" / "www"
_GRAPH_OUT = _SILKPAGE / "graph"

# ── Markdown to HTML (zero-dep, enough for Logseq) ────────────────────────────

def _md_to_html(text: str, title: str = "") -> str:
    """Convert Logseq Markdown to basic semantic HTML."""
    lines = text.splitlines()
    html: list[str] = []
    in_ul = False

    def close_ul():
        nonlocal in_ul
        if in_ul:
            html.append("</ul>")
            in_ul = False

    for line in lines:
        s = line.strip()
        if not s:
            close_ul()
            continue

        # Logseq properties (key:: value) → skip or render as dl
        if re.match(r'^[a-z_-]+::', s):
            key, _, val = s.partition("::")
            html.append(f'<p class="lg-prop"><span class="lg-key">{_esc(key.strip())}</span> {_inline(val.strip())}</p>')
            continue

        if s.startswith("# "):
            close_ul()
            html.append(f"<h1>{_inline(s[2:])}</h1>")
        elif s.startswith("## "):
            close_ul()
            html.append(f"<h2>{_inline(s[3:])}</h2>")
        elif s.startswith("### "):
            close_ul()
            html.append(f"<h3>{_inline(s[4:])}</h3>")
        elif s.startswith("- "):
            if not in_ul:
                html.append("<ul>")
                in_ul = True
            html.append(f"<li>{_inline(s[2:])}</li>")
        elif s.startswith("  - ") or s.startswith("\t- "):
            if not in_ul:
                html.append("<ul>")
                in_ul = True
            html.append(f"<li class='lg-sub'>{_inline(s.lstrip()[2:])}</li>")
        else:
            close_ul()
            html.append(f"<p>{_inline(s)}</p>")

    close_ul()
    return "\n".join(html)


def _inline(text: str) -> str:
    """Apply Logseq inline markup: [[links]], **bold**, `code`, urls."""
    # [[Page Link]]
    text = re.sub(r'\[\[([^\]]+)\]\]',
                  lambda m: f'<a class="lg-link" href="/graph/pages/{_slug(m.group(1))}.html">'
                            f'{_esc(m.group(1))}</a>', text)
    # [text](url)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)',
                  lambda m: f'<a href="{m.group(2)}" target="_blank" rel="noopener">{_esc(m.group(1))}</a>', text)
    # bare URLs
    text = re.sub(r'(?<![">])(https?://\S+)',
                  lambda m: f'<a href="{m.group(1)}" target="_blank" rel="noopener">{_esc(m.group(1))}</a>', text)
    # **bold**
    text = re.sub(r'\*\*(.+?)\*\*', lambda m: f'<strong>{_esc(m.group(1))}</strong>', text)
    # `code`
    text = re.sub(r'`([^`]+)`', lambda m: f'<code>{_esc(m.group(1))}</code>', text)
    return text


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _slug(name: str) -> str:
    return re.sub(r'[^a-z0-9_-]', '-', name.lower()).strip('-')


def _page_title(filename: str) -> str:
    """Convert Logseq filename to readable title."""
    name = Path(filename).stem
    # Logseq uses ___ for / in namespaced pages
    name = name.replace("___", " / ").replace("_", " ")
    return name.title()


# ── HTML template ──────────────────────────────────────────────────────────────

_NAV = """<nav id="sg-graph-nav">
  <a class="brand" href="/graph/">sg:graph · kern</a>
  <a href="/cv/">CV</a>
  <a href="/snippets/">Snippets</a>
  <a href="/">Home</a>
</nav>"""

_STYLE = """
  :root { --ink:#1a1a2e; --mid:#3a3a5c; --accent:#4a6fa5; --bg:#e8ecf0; --rule:#c8d0dc; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--ink); font-family: Georgia,'Times New Roman',serif; }
  nav#sg-graph-nav { background: var(--ink); color:#fff; padding:8px 20px; display:flex; gap:16px; align-items:center; font-family:'Helvetica Neue',Arial,sans-serif; font-size:12px; position:sticky; top:0; z-index:10; }
  nav#sg-graph-nav a { color:#ccc; text-decoration:none; }
  nav#sg-graph-nav a:hover { color:#fff; }
  nav#sg-graph-nav .brand { color: var(--accent); font-weight:700; margin-right:8px; }
  main { max-width: 860px; margin: 24px auto; padding: 0 20px 60px; }
  h1 { font-size:22pt; color:var(--ink); margin-bottom:8px; }
  h2 { font-size:13pt; color:var(--accent); margin:18px 0 6px; border-bottom:1px solid var(--rule); padding-bottom:3px; }
  h3 { font-size:11pt; color:var(--ink); margin:12px 0 4px; }
  p { font-size:10pt; line-height:1.6; color:var(--mid); margin:4px 0; }
  ul { padding-left:20px; margin:4px 0; }
  li { font-size:10pt; line-height:1.55; color:var(--mid); }
  li.lg-sub { list-style:circle; }
  code { font-family:'Courier New',monospace; font-size:9pt; background:#dde0e8; padding:1px 4px; border-radius:2px; }
  a { color:var(--accent); }
  a.lg-link { color:var(--accent); text-decoration:none; border-bottom:1px dashed var(--rule); }
  .lg-prop { font-family:'Helvetica Neue',Arial,sans-serif; font-size:8.5pt; color:#888; margin:2px 0; }
  .lg-key { font-weight:700; color:var(--accent); }
  .page-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:12px; margin-top:16px; }
  .page-card { background:#fff; border-radius:6px; padding:14px 16px; box-shadow:0 1px 6px rgba(26,26,46,.1); transition:box-shadow .15s; }
  .page-card:hover { box-shadow:0 3px 14px rgba(26,26,46,.18); }
  .page-card h3 { font-size:10.5pt; margin:0 0 4px; }
  .page-card p { font-size:8.5pt; }
  .page-card a { text-decoration:none; color:inherit; }
  .meta-tag { display:inline-block; background:var(--accent); color:#fff; font-family:'Helvetica Neue',Arial,sans-serif; font-size:7pt; padding:2px 6px; border-radius:3px; margin-right:4px; text-transform:uppercase; letter-spacing:.06em; }
"""


def _page_html(title: str, body: str, breadcrumb: str = "") -> str:
    bc = f'<p style="font-family:Helvetica Neue,Arial,sans-serif;font-size:8pt;color:#999;margin-bottom:12px">{breadcrumb}</p>' if breadcrumb else ""
    return f"""<!DOCTYPE html>
<html lang="en" vocab="http://schema.org/">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{_esc(title)} — sg:graph kern</title>
<style>{_STYLE}</style>
</head>
<body>
{_NAV}
<main>
{bc}
{body}
</main>
</body>
</html>"""


# ── Publisher ──────────────────────────────────────────────────────────────────

def publish(
    graph_root: str | None = None,
    out_dir: str | None = None,
    graph_name: str = "kern",
) -> dict[str, Any]:
    """Convert Logseq graph to HTML and write to www/graph/."""
    src   = Path(graph_root).expanduser() if graph_root else _WS / "ls" / "kern"
    dest  = Path(out_dir).expanduser()   if out_dir   else _GRAPH_OUT

    if not src.exists():
        print(f"error: graph root not found: {src}", file=sys.stderr)
        sys.exit(1)

    pages_src    = src / "pages"
    journals_src = src / "journals"
    pages_dest   = dest / "pages"
    pages_dest.mkdir(parents=True, exist_ok=True)

    published_pages: list[dict] = []

    # ── Publish individual pages ───────────────────────────────────────────
    for md_file in sorted(pages_src.glob("*.md")):
        title   = _page_title(md_file.name)
        text    = md_file.read_text(encoding="utf-8")
        body    = _md_to_html(text, title)
        slug    = _slug(md_file.stem)
        out     = pages_dest / f"{slug}.html"
        snippet = re.sub(r'<[^>]+>', '', body).strip()[:160]

        html = _page_html(
            title,
            f"<h1>{_esc(title)}</h1>\n{body}",
            breadcrumb=f'<a href="/graph/">kern</a> › {_esc(title)}',
        )
        out.write_text(html, encoding="utf-8")
        published_pages.append({"title": title, "slug": slug, "snippet": snippet, "file": md_file.name})

    # ── Publish journals ───────────────────────────────────────────────────
    journals_dest = dest / "journals"
    journals_dest.mkdir(exist_ok=True)
    for md_file in sorted(journals_src.glob("*.md"), reverse=True)[:30]:
        title = _page_title(md_file.name).replace("-", " ")
        text  = md_file.read_text(encoding="utf-8")
        body  = _md_to_html(text, title)
        slug  = _slug(md_file.stem)
        out   = journals_dest / f"{slug}.html"
        html  = _page_html(
            title, f"<h1>📅 {_esc(title)}</h1>\n{body}",
            breadcrumb=f'<a href="/graph/">kern</a> › journals › {_esc(title)}',
        )
        out.write_text(html, encoding="utf-8")

    # ── Generate graph-data.xml (RDF/XML stub) ─────────────────────────────
    rdf = _graph_rdf(src, graph_name, published_pages)
    (dest / "graph-data.xml").write_text(rdf, encoding="utf-8")

    # ── Index page ─────────────────────────────────────────────────────────
    cards = "\n".join(
        f'<div class="page-card"><a href="/graph/pages/{p["slug"]}.html">'
        f'<h3>{_esc(p["title"])}</h3>'
        f'<p>{_esc(p["snippet"][:100])}</p></a></div>'
        for p in published_pages
    )
    journal_files = sorted(journals_src.glob("*.md"), reverse=True)[:10]
    journal_links = "\n".join(
        f'<li><a href="/graph/journals/{_slug(f.stem)}.html">{_page_title(f.name)}</a></li>'
        for f in journal_files
    )

    index_body = f"""
<h1 style="font-size:18pt">sg:graph — kern</h1>
<p style="color:var(--mid);font-family:Helvetica Neue,Arial,sans-serif;font-size:9pt;margin:6px 0 20px">
  Logseq knowledge base · {len(published_pages)} pages ·
  <a href="/graph/graph-data.xml" style="color:var(--accent)">RDF/XML</a>
</p>

<h2>Pages</h2>
<div class="page-grid">{cards}</div>

<h2 style="margin-top:24px">Recent Journals</h2>
<ul style="margin-top:8px">{journal_links}</ul>
"""
    index_html = _page_html(f"sg:graph · {graph_name}", index_body)
    (dest / "index.html").write_text(index_html, encoding="utf-8")

    result = {
        "src": str(src), "dest": str(dest),
        "pages": len(published_pages),
        "index": str(dest / "index.html"),
    }
    print(f"sg:graph published → {dest}/")
    print(f"  {len(published_pages)} pages")
    print(f"  url  http://localhost:4242/graph/")
    return result


def _graph_rdf(src: Path, name: str, pages: list[dict]) -> str:
    """Generate RDF/XML stub for the graph."""
    subjects = "\n".join(
        f'  <rdf:Description rdf:about="https://ontology.lutino.io/graph/{name}/pages/{p["slug"]}">'
        f'<dcterms:title>{_esc(p["title"])}</dcterms:title>'
        f'<skos:prefLabel>{_esc(p["title"])}</skos:prefLabel>'
        f'</rdf:Description>'
        for p in pages
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF
  xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
  xmlns:dcterms="http://purl.org/dc/terms/"
  xmlns:skos="http://www.w3.org/2004/02/skos/core#"
  xmlns:sg="https://ontology.lutino.io/singine/1.0/"
>
  <skos:ConceptScheme rdf:about="https://ontology.lutino.io/graph/{name}">
    <dcterms:title>Logseq Kern Graph — {name}</dcterms:title>
    <dcterms:source>{_esc(str(src))}</dcterms:source>
    <dcterms:modified>{__import__('datetime').date.today().isoformat()}</dcterms:modified>
  </skos:ConceptScheme>
{subjects}
</rdf:RDF>"""
