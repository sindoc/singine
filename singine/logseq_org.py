"""Logseq graph discovery and Org/XML export helpers."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import unquote


GRAPH_SENTINELS: Tuple[Tuple[str, ...], ...] = (
    ("pages",),
    ("journals",),
)


@dataclass
class LogseqGraph:
    """Resolved Logseq graph directories."""

    name: str
    root: Path
    pages_dir: Path
    journals_dir: Path
    source_kind: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "root": str(self.root),
            "pages_dir": str(self.pages_dir),
            "journals_dir": str(self.journals_dir),
            "source_kind": self.source_kind,
        }


@dataclass
class LogseqSourceFile:
    title: str
    path: Path
    kind: str


def default_search_roots() -> List[Path]:
    home = Path.home()
    return [
        home / "ws" / "logseq",
        home / "ws" / "git" / "github" / "sindoc" / "website" / "logseq",
    ]


def default_elisp_load_paths() -> List[Path]:
    candidates = [
        Path("/Users/skh/ws/git/github/magnars/dash.el"),
        Path("/Users/skh/ws/git/github/magnars/s.el"),
        Path("/Users/skh/ws/git/github/ndwarshuis/org-ml"),
    ]
    sentinels = {
        "dash.el": "dash.el",
        "s.el": "s.el",
        "org-ml": "org-ml.el",
    }
    resolved: List[Path] = []
    for path in candidates:
        sentinel = sentinels.get(path.name)
        if sentinel and (path / sentinel).exists():
            resolved.append(path)
    return resolved


def _looks_like_graph_root(path: Path) -> bool:
    return any((path / part[0]).exists() for part in GRAPH_SENTINELS)


def _resolve_graph(path: Path) -> Optional[LogseqGraph]:
    path = path.expanduser().resolve()
    if _looks_like_graph_root(path):
        name = path.name
        return LogseqGraph(
            name=name,
            root=path,
            pages_dir=path / "pages",
            journals_dir=path / "journals",
            source_kind="direct",
        )
    version_base = path / "version-files" / "base"
    if _looks_like_graph_root(version_base):
        return LogseqGraph(
            name=path.name,
            root=version_base,
            pages_dir=version_base / "pages",
            journals_dir=version_base / "journals",
            source_kind="version-files/base",
        )
    return None


def _iter_candidate_dirs(root: Path, max_depth: int = 3) -> Iterable[Path]:
    yield root
    frontier = [(root, 0)]
    seen = {str(root)}
    while frontier:
        current, depth = frontier.pop(0)
        if depth >= max_depth:
            continue
        for child in sorted(current.iterdir()):
            if not child.is_dir():
                continue
            child_key = str(child)
            if child_key in seen:
                continue
            seen.add(child_key)
            yield child
            frontier.append((child, depth + 1))


def discover_graphs(search_roots: Optional[Sequence[Path]] = None) -> List[LogseqGraph]:
    """Discover local Logseq graphs from known roots."""
    graphs: Dict[str, LogseqGraph] = {}
    for root in search_roots or default_search_roots():
        root = Path(root).expanduser()
        if not root.exists():
            continue
        for child in _iter_candidate_dirs(root):
            candidate = _resolve_graph(child)
            if candidate is not None:
                graphs[str(candidate.root)] = candidate
    return sorted(graphs.values(), key=lambda item: (item.name, str(item.root)))


def resolve_graph(identifier: str, search_roots: Optional[Sequence[Path]] = None) -> LogseqGraph:
    """Resolve a graph by path or discovered graph name."""
    candidate = _resolve_graph(Path(identifier).expanduser())
    if candidate is not None:
        return candidate
    matches = [graph for graph in discover_graphs(search_roots) if graph.name == identifier]
    if not matches:
        raise FileNotFoundError(f"no Logseq graph found for '{identifier}'")
    if len(matches) > 1:
        roots = ", ".join(str(graph.root) for graph in matches)
        raise ValueError(f"multiple Logseq graphs match '{identifier}': {roots}")
    return matches[0]


def _title_from_path(path: Path, kind: str) -> str:
    stem = unquote(path.stem)
    if kind == "journal":
        return stem.replace("_", "-")
    return stem


def _iter_source_files(graph: LogseqGraph, include_pages: bool = True, include_journals: bool = True) -> Iterable[LogseqSourceFile]:
    if include_pages and graph.pages_dir.exists():
        for path in sorted(graph.pages_dir.glob("*.md")):
            yield LogseqSourceFile(title=_title_from_path(path, "page"), path=path, kind="page")
    if include_journals and graph.journals_dir.exists():
        for path in sorted(graph.journals_dir.glob("*.md")):
            yield LogseqSourceFile(title=_title_from_path(path, "journal"), path=path, kind="journal")


PROPERTY_RE = re.compile(r"^\s*([A-Za-z0-9_-]+)::\s*(.*?)\s*$")
HEADING_RE = re.compile(r"^(#+)\s+(.*)$")


def _sanitize_property_key(key: str) -> str:
    return re.sub(r"[^A-Z0-9_]", "_", key.upper())


def _convert_body_line(line: str) -> str:
    heading = HEADING_RE.match(line)
    if heading:
        return f"{'*' * (len(heading.group(1)) + 1)} {heading.group(2)}"
    return line


def _extract_properties_and_body(text: str) -> Tuple[Dict[str, List[str]], List[str]]:
    properties: Dict[str, List[str]] = {}
    body: List[str] = []
    in_example = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_example = not in_example
            body.append("#+begin_example" if in_example else "#+end_example")
            continue
        if not in_example:
            match = PROPERTY_RE.match(line)
            if match:
                key = _sanitize_property_key(match.group(1))
                properties.setdefault(key, []).append(match.group(2))
                continue
        body.append(_convert_body_line(line))
    return properties, body


def render_graph_to_org(graph: LogseqGraph, include_pages: bool = True, include_journals: bool = True, limit: Optional[int] = None) -> str:
    """Render a Logseq graph to a single Org document."""
    lines = [
        f"#+TITLE: Logseq export for {graph.name}",
        f"#+PROPERTY: LOGSEQ_ROOT {graph.root}",
        "#+OPTIONS: toc:nil",
        "",
        f"* Graph {graph.name}",
        ":PROPERTIES:",
        f":LOGSEQ_ROOT: {graph.root}",
        f":LOGSEQ_SOURCE_KIND: {graph.source_kind}",
        ":END:",
        "",
    ]

    count = 0
    for source in _iter_source_files(graph, include_pages=include_pages, include_journals=include_journals):
        if limit is not None and count >= limit:
            break
        text = source.path.read_text(encoding="utf-8")
        properties, body = _extract_properties_and_body(text)
        lines.extend(
            [
                f"** {source.title}",
                ":PROPERTIES:",
                f":LOGSEQ_KIND: {source.kind}",
                f":LOGSEQ_SOURCE: {source.path}",
            ]
        )
        for key in sorted(properties):
            joined = " | ".join(value for value in properties[key] if value)
            lines.append(f":{key}: {joined}")
        lines.extend(
            [
                ":END:",
                "",
            ]
        )
        trimmed_body = "\n".join(body).strip()
        if trimmed_body:
            lines.append(trimmed_body)
            lines.append("")
        count += 1

    return "\n".join(lines).rstrip() + "\n"


def write_graph_org(graph: LogseqGraph, output_path: Path, include_pages: bool = True, include_journals: bool = True, limit: Optional[int] = None) -> Path:
    output_path = output_path.expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_graph_to_org(
            graph,
            include_pages=include_pages,
            include_journals=include_journals,
            limit=limit,
        ),
        encoding="utf-8",
    )
    return output_path


def _elisp_string(value: str) -> str:
    return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""


def export_org_to_xml(
    org_path: Path,
    xml_path: Path,
    om_to_xml_repo: Path,
    emacs_bin: str = "emacs",
    extra_load_paths: Optional[Sequence[Path]] = None,
) -> Dict[str, object]:
    """Run Emacs batch export through Norman Walsh's om-to-xml.el."""
    org_path = org_path.expanduser().resolve()
    xml_path = xml_path.expanduser().resolve()
    om_to_xml_repo = om_to_xml_repo.expanduser().resolve()
    if not org_path.exists():
        raise FileNotFoundError(f"org file not found: {org_path}")
    if not (om_to_xml_repo / "om-to-xml.el").exists():
        raise FileNotFoundError(f"om-to-xml.el not found under {om_to_xml_repo}")
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    load_paths = [om_to_xml_repo, *[Path(path).expanduser().resolve() for path in (extra_load_paths or default_elisp_load_paths())]]
    load_path_expr = "".join(
        f"(add-to-list 'load-path {_elisp_string(str(path))}) "
        for path in load_paths
    )
    expression = (
        "(progn "
        "(require 'org) "
        f"{load_path_expr}"
        "(require 'om-to-xml) "
        f"(find-file {_elisp_string(str(org_path))}) "
        "(org-mode) "
        f"(om-to-xml {_elisp_string(str(xml_path))}))"
    )
    cmd = [emacs_bin, "--batch", "--quick", "--eval", expression]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return {
        "ok": completed.returncode == 0 and xml_path.exists(),
        "command": cmd,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "org_path": str(org_path),
        "xml_path": str(xml_path),
        "om_to_xml_repo": str(om_to_xml_repo),
        "load_paths": [str(path) for path in load_paths],
    }
