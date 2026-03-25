"""Personal operating system essay and artifact bundle generation."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_ONEPAGER = Path("/Users/skh/ws/today/cleanUp/sindoc42-onepager.pdf")
DEFAULT_METAMODEL_ROOT = Path("/Users/skh/ws/today/metamodel/reference/current/latest/lutino.collibra.singine.process.C213(1)")
DEFAULT_LOGSEQ_PDF = Path("/Users/skh/ws/logseq/singine/sindoc/Logseq.pdf")
DEFAULT_NOTEBOOK_FRAGMENTS = Path("/Users/skh/ws/today/singine-notebook/output/fragments")
DEFAULT_PUBLISH_REQUEST_XML = Path("/Users/skh/ws/today/singine-mail/xml/publish-request.xml")
DEFAULT_PUBLISH_RESPONSE_XML = Path("/Users/skh/ws/today/singine-mail/xml/publish-response.xml")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_personal_os_manifest(
    *,
    title: str = "Singine Personal Operating System",
    onepager: Path = DEFAULT_ONEPAGER,
    metamodel_root: Path = DEFAULT_METAMODEL_ROOT,
) -> Dict[str, Any]:
    rules = [
        {
            "domain": "legal-entity",
            "actor": "lutino.io",
            "mandate": "business dimension and legal anchor under the Collibra-aligned metamodel",
        },
        {
            "domain": "workflow",
            "actor": "xml-request-response",
            "mandate": "signed request, response, and certificate-backed approval flow",
        },
        {
            "domain": "runtime",
            "actor": "singine",
            "mandate": "coordinate Logseq, Collibra, SQLite, XML, text, and publication artefacts",
        },
        {
            "domain": "adapter",
            "actor": "ballerina-c-rust-pico",
            "mandate": "retain inheritable code contracts across interface boundaries",
        },
    ]
    references = [
        {"label": "sindoc42 onepager", "path": str(onepager), "exists": onepager.exists()},
        {"label": "lutino Collibra metamodel root", "path": str(metamodel_root), "exists": metamodel_root.exists()},
        {"label": "logseq pdf", "path": str(DEFAULT_LOGSEQ_PDF), "exists": DEFAULT_LOGSEQ_PDF.exists()},
        {"label": "singine notebook fragments", "path": str(DEFAULT_NOTEBOOK_FRAGMENTS), "exists": DEFAULT_NOTEBOOK_FRAGMENTS.exists()},
        {"label": "publish request xml", "path": str(DEFAULT_PUBLISH_REQUEST_XML), "exists": DEFAULT_PUBLISH_REQUEST_XML.exists()},
        {"label": "publish response xml", "path": str(DEFAULT_PUBLISH_RESPONSE_XML), "exists": DEFAULT_PUBLISH_RESPONSE_XML.exists()},
    ]
    return {
        "title": title,
        "generated_at": _now(),
        "domains_of_influence": [
            "legal entity",
            "collibra metamodel",
            "workflow and signed certificates",
            "publication and notebook surfaces",
            "temporal and experimental reflection",
        ],
        "references": references,
        "rules": rules,
        "topics": [
            "personal operating system",
            "temporal awareness",
            "relativation",
            "general relativity as coordination metaphor",
            "quantum mechanics as uncertainty metaphor",
            "fractal growth",
            "complex plane projection",
            "invisible XML and ixml",
            "Babel2 and language games",
            "pico and lisp inheritance",
        ],
    }


def render_markdown(manifest: Dict[str, Any]) -> str:
    refs = "\n".join(f"- `{ref['label']}`: {ref['path']}" for ref in manifest["references"])
    rules = "\n".join(
        f"- `{rule['domain']}`: {rule['actor']} -> {rule['mandate']}"
        for rule in manifest["rules"]
    )
    topics = ", ".join(manifest["topics"])
    return f"""# {manifest['title']}

## Thesis

Software can be represented as a personal operating system when its mandates,
interfaces, memories, and execution surfaces remain explicitly linked across
time. In this view, Logseq, Collibra, SQLite, XML request/response workflows,
and publication artefacts are not separate tools but adjacent memory organs.

`lutino.io` acts here as the legal and business dimension, while the
`lutino.collibra` metamodel acts as a semantic operating model. Singine becomes
the coordinating shell that keeps those domains distinct while still allowing
their mandates to travel through signed certificates, request/response
workflows, and inheritable interface contracts.

## Best Practices

1. Keep each domain of influence explicit: legal entity, workflow, catalog,
   notebook, runtime, and publication.
2. Treat XML request/response pairs as signed boundary objects rather than as
   incidental serializations.
3. Use SQLite for local memory, Logseq for reflective graph structure, and
   Collibra for governed operating-model expression.
4. Allow Ballerina to own the beautiful request/response choreography, while C
   and Rust keep low-level control points honest and inspectable.
5. Preserve Lisp inheritance and small-language expressiveness through Pico and
   SinLisp-style rule lists.
6. Prefer ixml and invisible XML where grammar should remain close to human
   reading while still generating machine structure.

## Temporal Awareness And Relativation

The personal operating system is not static. It evolves by life phase. Early
phases optimise for collection and vocabulary. Middle phases optimise for
interfaces, contracts, and memory consolidation. Later phases optimise for
relativation: seeing each tool as a frame of reference rather than as the
whole system.

General relativity is useful here as a metaphor for frames of coordination:
meaning changes with the observer's domain. Quantum mechanics is useful as a
metaphor for uncertainty, superposition of possibilities, and experimental
observation. Fractals and the complex plane help visualise how local patterns
repeat across notebook cells, XML workflows, CLI commands, and governance
models.

## References

{refs}

## Rules

{rules}

## Topic Evolution

{topics}
"""


def render_html(manifest: Dict[str, Any]) -> str:
    cards = "\n".join(
        f"<article class='card'><h3>{rule['domain']}</h3><p>{rule['mandate']}</p><small>{rule['actor']}</small></article>"
        for rule in manifest["rules"]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{manifest['title']}</title>
  <style>
    :root {{ --bg:#f7f1e8; --ink:#17212b; --accent:#b14917; --panel:#fff9f1; }}
    body {{ margin:0; font-family:'Iowan Old Style', Georgia, serif; background:linear-gradient(180deg,#fff9ef,#f7f1e8); color:var(--ink); }}
    main {{ max-width:1100px; margin:0 auto; padding:48px 20px 80px; }}
    h1 {{ font-size:clamp(2.8rem,6vw,5.4rem); line-height:.92; margin:0; }}
    p.lede {{ font-size:1.15rem; max-width:760px; color:#5a646c; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:18px; margin-top:28px; }}
    .card {{ background:var(--panel); border:1px solid #eadbc9; padding:18px; box-shadow:0 18px 40px rgba(0,0,0,.08); }}
    small {{ color:var(--accent); }}
  </style>
</head>
<body>
  <main>
    <p>Singine essay bundle</p>
    <h1>{manifest['title']}</h1>
    <p class="lede">A personal operating system linking life phases, mandates, semantic models, signed XML workflows, and notebook-era publication.</p>
    <section class="grid">{cards}</section>
  </main>
</body>
</html>
"""


def render_svg() -> str:
    points: List[str] = []
    for i in range(180):
        t = i / 15.0
        x = 400 + math.cos(t) * (30 + i * 1.6)
        y = 280 + math.sin(t) * (20 + i * 1.1)
        points.append(f"{x:.2f},{y:.2f}")
    polyline = " ".join(points)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="900" height="560" viewBox="0 0 900 560">
  <rect width="900" height="560" fill="#fbf5eb"/>
  <text x="48" y="72" font-family="Georgia, serif" font-size="34" fill="#16212a">Personal OS Complex Plane</text>
  <text x="48" y="104" font-family="Georgia, serif" font-size="18" fill="#8a3d16">fractal growth / temporal relativation / semantic orbit</text>
  <line x1="120" y1="280" x2="780" y2="280" stroke="#3b4a54" stroke-width="1.5"/>
  <line x1="400" y1="100" x2="400" y2="460" stroke="#3b4a54" stroke-width="1.5"/>
  <polyline fill="none" stroke="#b14917" stroke-width="3" points="{polyline}"/>
</svg>
"""


def render_latex(manifest: Dict[str, Any]) -> str:
    return f"""\\documentclass[11pt]{{article}}
\\usepackage{{geometry}}
\\usepackage{{fontspec}}
\\setmainfont{{TeX Gyre Pagella}}
\\geometry{{margin=2.4cm}}
\\title{{{manifest['title']}}}
\\date{{{manifest['generated_at']}}}
\\begin{{document}}
\\maketitle
\\section*{{Best Practices}}
Represent software as a personal operating system by preserving explicit domain
boundaries, signed XML request/response workflows, catalog-backed semantics, and
publication projections across Markdown, XML, JSON, and vector graphics.
\\end{{document}}
"""


def render_request_xml(manifest: Dict[str, Any]) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<personal-os-request xmlns="urn:singine:personal-os:request" generated-at="{manifest['generated_at']}">
  <title>{manifest['title']}</title>
  <legal-entity>lutino.io</legal-entity>
  <workflow>xml-request-response</workflow>
  <signature-state>expected-signed-certificate</signature-state>
</personal-os-request>
"""


def render_response_xml(manifest: Dict[str, Any]) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<personal-os-response xmlns="urn:singine:personal-os:response" generated-at="{manifest['generated_at']}">
  <title>{manifest['title']}</title>
  <status>accepted-for-reflective-experiment</status>
  <projection>complex-plane-fractal</projection>
  <publication>markdown html svg latex sinlisp ixml</publication>
</personal-os-response>
"""


def render_sinlisp(manifest: Dict[str, Any]) -> str:
    rules = "\n".join(
        f'  (rule "{rule["domain"]}" "{rule["actor"]}" "{rule["mandate"]}")'
        for rule in manifest["rules"]
    )
    refs = "\n".join(
        f'  (path "{ref["label"]}" "{ref["path"]}")'
        for ref in manifest["references"]
    )
    return f"""; Distinct domains of influence for the personal operating system.
(personal-os "{manifest['title']}"
{rules}
  (topics
    "temporal-awareness"
    "relativation"
    "complex-plane"
    "fractal-growth"
    "ixml"
    "babel2"
    "pico"
    "ballerina")
{refs})
"""


def render_ballerina() -> str:
    return """import ballerina/http;

service /personalOs on new http:Listener(8091) {
    resource function get manifest() returns json {
        return {"service":"personal-os", "protocol":"xml-request-response", "adapter":"ballerina"};
    }
}
"""


def render_c_header() -> str:
    return """#ifndef PERSONAL_OS_BRIDGE_H
#define PERSONAL_OS_BRIDGE_H

const char* personal_os_request_xml(void);
const char* personal_os_response_xml(void);

#endif
"""


def render_rust_trait() -> str:
    return """pub trait PersonalOsBridge {
    fn request_xml(&self) -> String;
    fn response_xml(&self) -> String;
}
"""


def render_pico() -> str:
    return """(define personal-os
  (lambda (domain actor mandate)
    (list 'rule domain actor mandate)))
"""


def render_ixml() -> str:
    return """personal-os: title, rules, references.
title: '\"', ~['\"']+, '\"'.
rules: rule+.
rule: '(', 'rule', s, title, s, title, s, title, ')'.
references: reference+.
reference: '(', 'path', s, title, s, title, ')'.
s: ' '+.
"""


def write_personal_os_bundle(
    *,
    output_dir: Path,
    title: str = "Singine Personal Operating System",
    onepager: Path = DEFAULT_ONEPAGER,
    metamodel_root: Path = DEFAULT_METAMODEL_ROOT,
) -> Dict[str, Any]:
    manifest = build_personal_os_manifest(title=title, onepager=onepager, metamodel_root=metamodel_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "essay.md").write_text(render_markdown(manifest), encoding="utf-8")
    (output_dir / "essay.html").write_text(render_html(manifest), encoding="utf-8")
    (output_dir / "visual.svg").write_text(render_svg(), encoding="utf-8")
    (output_dir / "essay.tex").write_text(render_latex(manifest), encoding="utf-8")
    workflow_dir = output_dir / "workflow"
    rules_dir = output_dir / "rules"
    interfaces_dir = output_dir / "interfaces"
    workflow_dir.mkdir(exist_ok=True)
    rules_dir.mkdir(exist_ok=True)
    interfaces_dir.mkdir(exist_ok=True)
    (workflow_dir / "request.xml").write_text(render_request_xml(manifest), encoding="utf-8")
    (workflow_dir / "response.xml").write_text(render_response_xml(manifest), encoding="utf-8")
    (rules_dir / "personal_os_rules.sinlisp").write_text(render_sinlisp(manifest), encoding="utf-8")
    (interfaces_dir / "adapter.bal").write_text(render_ballerina(), encoding="utf-8")
    (interfaces_dir / "bridge.h").write_text(render_c_header(), encoding="utf-8")
    (interfaces_dir / "bridge.rs").write_text(render_rust_trait(), encoding="utf-8")
    (interfaces_dir / "bridge.pico").write_text(render_pico(), encoding="utf-8")
    (interfaces_dir / "grammar.ixml").write_text(render_ixml(), encoding="utf-8")
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {
        "manifest": manifest,
        "artifacts": {
            "markdown": str(output_dir / "essay.md"),
            "html": str(output_dir / "essay.html"),
            "svg": str(output_dir / "visual.svg"),
            "latex": str(output_dir / "essay.tex"),
            "request_xml": str(workflow_dir / "request.xml"),
            "response_xml": str(workflow_dir / "response.xml"),
            "sinlisp": str(rules_dir / "personal_os_rules.sinlisp"),
            "ballerina": str(interfaces_dir / "adapter.bal"),
            "c_header": str(interfaces_dir / "bridge.h"),
            "rust": str(interfaces_dir / "bridge.rs"),
            "pico": str(interfaces_dir / "bridge.pico"),
            "ixml": str(interfaces_dir / "grammar.ixml"),
            "json": str(output_dir / "manifest.json"),
        },
    }
