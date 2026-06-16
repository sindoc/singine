"""singine mime_xml — MIME-aware XML construction from file trees.

Given a file or directory, wraps content in semantic XML based on MIME type,
aligned with SilkPage/Forrest content pipeline capabilities.

SilkPage/Forrest MIME capabilities (from actual core XSLTs and Ant build):
  text/xml          → pass-through or XSLT transform
  application/xhtml+xml → XSLT
  text/html         → serve directly / tidy
  text/x-markdown   → md→html→xslt
  text/plain        → wrap in <source> element
  application/rdf+xml  → rdf-html.xsl (FOAF, Dublin Core, SKOS)
  application/pdf   → serve directly
  text/x-sh / application/x-sh → wrap as <code-block lang="bash">
  text/x-java-source → wrap as <code-block lang="java">
  text/x-python      → wrap as <code-block lang="python">
  application/json   → wrap as <code-block lang="json">
  application/x-clojure → wrap as <code-block lang="clojure">
  application/x-xslt → identity / transform chain
"""
from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from typing import Any

# ── MIME registry (extends stdlib) ────────────────────────────────────────────

_EXTRA_MIMES: dict[str, str] = {
    ".md":    "text/x-markdown",
    ".edn":   "application/x-clojure",
    ".clj":   "application/x-clojure",
    ".cljs":  "application/x-clojurescript",
    ".sh":    "text/x-sh",
    ".bash":  "text/x-sh",
    ".py":    "text/x-python",
    ".java":  "text/x-java-source",
    ".xsl":   "application/xslt+xml",
    ".xslt":  "application/xslt+xml",
    ".xsd":   "application/xml",
    ".rdf":   "application/rdf+xml",
    ".ttl":   "text/turtle",
    ".n3":    "text/n3",
    ".nt":    "application/n-triples",
    ".jsonld": "application/ld+json",
    ".rs":    "text/x-rust",
    ".bal":   "text/x-ballerina",
    ".toml":  "application/toml",
    ".yml":   "application/x-yaml",
    ".yaml":  "application/x-yaml",
    ".makefile": "text/x-makefile",
    ".mk":    "text/x-makefile",
}

# SilkPage/Forrest pipeline handler map
SILKPAGE_HANDLERS: dict[str, dict[str, Any]] = {
    "text/xml":               {"handler": "xslt",         "xsl": "core/src/xsl/butterfly/main.xsl"},
    "application/xhtml+xml":  {"handler": "xslt",         "xsl": "core/src/xsl/butterfly/main.xsl"},
    "application/xslt+xml":   {"handler": "identity",     "xsl": None},
    "application/xml":        {"handler": "xslt",         "xsl": "core/src/xsl/butterfly/main.xsl"},
    "application/rdf+xml":    {"handler": "rdf-html",     "xsl": "site/silkpage.markupware.com/rdf-html.xsl"},
    "text/html":              {"handler": "static",        "xsl": None},
    "text/x-markdown":        {"handler": "md-xslt",      "xsl": None},
    "text/plain":             {"handler": "source-wrap",   "xsl": None},
    "text/x-sh":              {"handler": "code-block",   "lang": "bash"},
    "text/x-python":          {"handler": "code-block",   "lang": "python"},
    "text/x-java-source":     {"handler": "code-block",   "lang": "java"},
    "application/x-clojure":  {"handler": "code-block",   "lang": "clojure"},
    "application/x-clojurescript": {"handler": "code-block", "lang": "clojurescript"},
    "text/x-rust":            {"handler": "code-block",   "lang": "rust"},
    "text/x-ballerina":       {"handler": "code-block",   "lang": "ballerina"},
    "application/json":       {"handler": "code-block",   "lang": "json"},
    "application/ld+json":    {"handler": "code-block",   "lang": "json-ld"},
    "application/toml":       {"handler": "code-block",   "lang": "toml"},
    "application/x-yaml":     {"handler": "code-block",   "lang": "yaml"},
    "text/turtle":            {"handler": "code-block",   "lang": "turtle"},
    "text/x-makefile":        {"handler": "code-block",   "lang": "makefile"},
    "application/pdf":        {"handler": "binary",        "xsl": None},
}


def mime_of(path: Path) -> str:
    ext = path.suffix.lower()
    if path.name.lower() == "makefile":
        return "text/x-makefile"
    if ext in _EXTRA_MIMES:
        return _EXTRA_MIMES[ext]
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def file_to_xml(path: Path, max_bytes: int = 64 * 1024) -> str:
    """Wrap a single file's content in semantic XML."""
    mime = mime_of(path)
    handler_info = SILKPAGE_HANDLERS.get(mime, {"handler": "unknown"})
    handler = handler_info["handler"]

    rel = str(path)
    attrs = (
        f' path="{_esc(rel)}"'
        f' mime="{_esc(mime)}"'
        f' silkpage:handler="{_esc(handler)}"'
    )
    if "xsl" in handler_info and handler_info["xsl"]:
        attrs += f' silkpage:xsl="{_esc(handler_info["xsl"])}"'
    if "lang" in handler_info:
        attrs += f' lang="{_esc(handler_info["lang"])}"'

    ns = (
        'xmlns:sg="https://ontology.lutino.io/singine/1.0/" '
        'xmlns:silkpage="https://ontology.lutino.io/silkpage/1.0/" '
        'xmlns:dcterms="http://purl.org/dc/terms/"'
    )

    if handler == "binary" or not path.is_file():
        return f'<sg:file {ns}{attrs} dcterms:format="{_esc(mime)}"/>'

    try:
        raw = path.read_bytes()
        if len(raw) > max_bytes:
            content = _esc(raw[:max_bytes].decode("utf-8", errors="replace"))
            truncated = f' truncated="true" original-bytes="{len(raw)}"'
        else:
            content = _esc(raw.decode("utf-8", errors="replace"))
            truncated = ""

        if handler == "code-block":
            lang = handler_info.get("lang", "text")
            return (
                f'<sg:file {ns}{attrs}{truncated}>\n'
                f'  <code-block lang="{lang}"><![CDATA[{raw[:max_bytes].decode("utf-8", errors="replace")}]]></code-block>\n'
                f'</sg:file>'
            )
        elif handler in ("xslt", "rdf-html", "identity"):
            return (
                f'<sg:file {ns}{attrs}{truncated}>\n'
                f'  <sg:content>{content}</sg:content>\n'
                f'</sg:file>'
            )
        else:
            return (
                f'<sg:file {ns}{attrs}{truncated}>\n'
                f'  <sg:content><![CDATA[{raw[:max_bytes].decode("utf-8", errors="replace")}]]></sg:content>\n'
                f'</sg:file>'
            )
    except Exception as exc:
        return f'<sg:file {ns}{attrs} sg:error="{_esc(str(exc))}"/>'


def tree_to_xml(
    root: Path,
    include_exts: set[str] | None = None,
    exclude_dirs: set[str] | None = None,
    max_files: int = 200,
) -> str:
    """Generate XML document representing a file tree with MIME annotations."""
    exclude_dirs = exclude_dirs or {
        ".git", "__pycache__", "node_modules", ".pytest_cache",
        "dist", "build", "target", ".m2",
    }
    ns = (
        'xmlns:sg="https://ontology.lutino.io/singine/1.0/" '
        'xmlns:silkpage="https://ontology.lutino.io/silkpage/1.0/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:skos="http://www.w3.org/2004/02/skos/core#"'
    )

    def walk(p: Path, depth: int = 0) -> list[str]:
        parts: list[str] = []
        if depth > 6:
            return parts
        try:
            entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        except PermissionError:
            return parts

        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                if entry.name in exclude_dirs:
                    continue
                parts.append(f'<sg:dir name="{_esc(entry.name)}" path="{_esc(str(entry))}">')
                parts.extend(walk(entry, depth + 1))
                parts.append("</sg:dir>")
            elif entry.is_file():
                if include_exts and entry.suffix.lower() not in include_exts:
                    continue
                mime = mime_of(entry)
                handler = SILKPAGE_HANDLERS.get(mime, {}).get("handler", "unknown")
                parts.append(
                    f'<sg:file name="{_esc(entry.name)}" '
                    f'path="{_esc(str(entry))}" '
                    f'mime="{_esc(mime)}" '
                    f'silkpage:handler="{_esc(handler)}" '
                    f'size="{entry.stat().st_size}"/>'
                )
                if len(parts) >= max_files * 2:
                    parts.append('<sg:truncated reason="max-files"/>')
                    return parts
        return parts

    children = walk(root)
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<sg:tree {ns}\n'
        f'  root="{_esc(str(root))}"\n'
        f'  dcterms:modified="{__import__("datetime").date.today().isoformat()}">\n'
        + "\n".join(f"  {c}" for c in children)
        + "\n</sg:tree>"
    )


def mime_capabilities_html() -> str:
    """Return HTML table of SilkPage MIME capabilities."""
    rows = "\n".join(
        f'<tr><td><code>{_esc(mime)}</code></td>'
        f'<td><span class="handler">{_esc(info["handler"])}</span></td>'
        f'<td>{_esc(info.get("xsl") or info.get("lang") or "—")}</td></tr>'
        for mime, info in sorted(SILKPAGE_HANDLERS.items())
    )
    return f"""<table class="mime-table">
<thead><tr><th>MIME Type</th><th>Handler</th><th>XSL / Language</th></tr></thead>
<tbody>{rows}</tbody>
</table>"""
