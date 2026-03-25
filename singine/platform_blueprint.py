"""Platform blueprint generation for Singine, Collibra, Flowable, and edge runtimes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_platform_blueprint(title: str = "Singine Multi-Model Platform Blueprint") -> Dict[str, Any]:
    return {
        "title": title,
        "generated_at": _now(),
        "vision": "A multi-model, multi-dimensional web platform where Singine orchestrates Node.js, Python, Spring Boot, Clojure, Groovy, and Flowable across Docker, local CentOS farms, and OpenShift/Collibra Edge deployments.",
        "deployment_targets": [
            "docker-compose local stack",
            "local CentOS or RHEL farm",
            "OpenShift 3.11 / OKD edge deployment",
            "Collibra notebook and Databricks notebook runtime",
        ],
        "runtime_layers": [
            {"layer": "webapp", "implementation": "Node.js static or SSR shell", "purpose": "Visually appealing multi-model UI over datasets, messaging, and publication artefacts."},
            {"layer": "python-service", "implementation": "FastAPI / notebook-facing helpers", "purpose": "Notebook import, data-product transforms, probes, and publication rendering."},
            {"layer": "spring-boot-adapter", "implementation": "Spring Boot abstractions", "purpose": "Metadata protocol adapters, human-vs-machine activity interfaces, and edge-safe orchestration."},
            {"layer": "clojure-core", "implementation": "Singine core", "purpose": "Canonical runtime, bridge, taxonomy, policy, and broker contracts."},
            {"layer": "groovy-embedded", "implementation": "Collibra/Groovy execution", "purpose": "CLI-triggered workflows, script storage, and opmodel-aligned execution."},
            {"layer": "flowable", "implementation": "Execution engine", "purpose": "Order job execution across human-led and machine-led activities."},
        ],
        "exchange_fabrics": [
            {"kind": "rabbitmq", "stages": ["raw", "staging"], "purpose": "File and record intake prior to streaming."},
            {"kind": "kafka", "topic_family": "singine.datastreaming.*", "purpose": "Streaming and edge synchronization."},
            {"kind": "file-exchange", "protocols": ["sftp", "s3", ".m2/repository"], "purpose": "Public/private key governed exchange of jars, artifacts, and data products."},
        ],
        "security_and_keys": {
            "public_private_key_exchange": ["ssh public keys", "TLS root and edge certificates", "JWT RS256 verification keys"],
            "governed_targets": ["sftp", "s3-compatible object storage", "maven repository mirror", "edge node registration"],
        },
        "collibra_alignment": {
            "integration_pattern": "interfaces inheritable through CLI, REST, GraphQL, and opmodel type definitions",
            "plain_text_attributes": [
                {"name": "Script Body", "used_on": "Workflow Definition assets", "content": "BPMN and Groovy script bodies"},
                {"name": "Source Code", "used_on": "Script and Executable assets", "content": "Groovy, Python, shell, or adapter source"},
                {"name": "Authorised Commands", "used_on": "Session and Script assets", "content": "Pipe-separated execution allow-list"},
            ],
        },
        "activity_model": {
            "human_led": ["approval", "stewardship", "policy selection", "information architecture curation"],
            "machine_led": ["probes", "streaming transforms", "edge jobs", "publication rendering", "quicksort/data-structure demos"],
            "contract": "Every activity maps back to explicit interfaces and a governed execution record.",
        },
        "data_products": [
            "zip-neighborhood multilingual community demo",
            "edge execution job manifests",
            "notebook-ready JSON and XML artifacts",
            "mediawiki and markdown publication fragments",
        ],
        "interfaces": [
            "Singine CLI",
            "Collibra CLI through singine runtime exec-external",
            "Flowable process model contract",
            "Spring Boot adapter interfaces",
            "OpenAPI / XML infoset / JSON projection",
        ],
    }


def render_markdown(blueprint: Dict[str, Any]) -> str:
    lines = [
        f"# {blueprint['title']}",
        "",
        f"- generated-at:: {blueprint['generated_at']}",
        "",
        "## Vision",
        blueprint["vision"],
        "",
        "## Deployment Targets",
    ]
    for item in blueprint["deployment_targets"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Runtime Layers"])
    for item in blueprint["runtime_layers"]:
        lines.append(f"- `{item['layer']}`: {item['implementation']} — {item['purpose']}")
    lines.extend(["", "## Collibra Attributes"])
    for item in blueprint["collibra_alignment"]["plain_text_attributes"]:
        lines.append(f"- `{item['name']}` on {item['used_on']}: {item['content']}")
    return "\n".join(lines).strip() + "\n"


def render_openshift_template(blueprint: Dict[str, Any]) -> str:
    name = "singine-platform-webapp"
    return f"""apiVersion: template.openshift.io/v1
kind: Template
metadata:
  name: {name}
objects:
  - apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: {name}
    spec:
      replicas: 1
      selector:
        matchLabels:
          app: {name}
      template:
        metadata:
          labels:
            app: {name}
        spec:
          containers:
            - name: node-web
              image: image-registry.openshift-image-registry.svc:5000/demo/{name}:latest
              ports:
                - containerPort: 3000
            - name: python-api
              image: image-registry.openshift-image-registry.svc:5000/demo/{name}-api:latest
              ports:
                - containerPort: 8090
            - name: spring-adapter
              image: image-registry.openshift-image-registry.svc:5000/demo/{name}-adapter:latest
              ports:
                - containerPort: 8080
  - apiVersion: v1
    kind: Service
    metadata:
      name: {name}
    spec:
      selector:
        app: {name}
      ports:
        - name: web
          port: 3000
          targetPort: 3000
        - name: api
          port: 8090
          targetPort: 8090
        - name: adapter
          port: 8080
          targetPort: 8080
"""


def render_node_package() -> str:
    return json.dumps(
        {
            "name": "@sindoc/singine-platform-webapp",
            "version": "0.1.0",
            "private": True,
            "description": "Node.js shell for the Singine multi-model platform blueprint",
            "scripts": {
                "start": "node server.js",
                "dev": "node server.js",
            },
        },
        indent=2,
    ) + "\n"


def render_node_server() -> str:
    return """const http = require('http');
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, 'public');
const port = process.env.PORT || 3000;

http.createServer((req, res) => {
  const target = req.url === '/' ? '/index.html' : req.url;
  const file = path.join(root, target);
  fs.readFile(file, (err, data) => {
    if (err) {
      res.writeHead(404, {'Content-Type': 'text/plain'});
      res.end('not found');
      return;
    }
    const type = file.endsWith('.css') ? 'text/css' : file.endsWith('.js') ? 'application/javascript' : 'text/html';
    res.writeHead(200, {'Content-Type': type});
    res.end(data);
  });
}).listen(port, () => {
  console.log(`singine-platform-webapp listening on ${port}`);
});
"""


def render_html(blueprint: Dict[str, Any]) -> str:
    cards = "\n".join(
        f"<article class=\"card\"><h3>{layer['layer']}</h3><p>{layer['purpose']}</p><small>{layer['implementation']}</small></article>"
        for layer in blueprint["runtime_layers"]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{blueprint['title']}</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main class="shell">
    <section class="hero">
      <p class="eyebrow">Singine Platform Blueprint</p>
      <h1>{blueprint['title']}</h1>
      <p class="lede">{blueprint['vision']}</p>
    </section>
    <section class="grid">
      {cards}
    </section>
  </main>
</body>
</html>
"""


def render_css() -> str:
    return """:root {
  --bg: #f4efe6;
  --ink: #1d2a33;
  --panel: #fffaf2;
  --accent: #b54d1a;
  --muted: #6f7b82;
}
body {
  margin: 0;
  font-family: Georgia, 'Iowan Old Style', serif;
  background: radial-gradient(circle at top, #fffaf0, var(--bg));
  color: var(--ink);
}
.shell { max-width: 1100px; margin: 0 auto; padding: 48px 20px 80px; }
.hero { margin-bottom: 32px; }
.eyebrow { text-transform: uppercase; letter-spacing: 0.15em; color: var(--accent); font-size: 12px; }
h1 { font-size: clamp(2.6rem, 5vw, 5rem); line-height: 0.95; margin: 0 0 16px; }
.lede { max-width: 780px; font-size: 1.2rem; color: var(--muted); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 18px; }
.card { background: var(--panel); border: 1px solid #e3d8c8; padding: 20px; box-shadow: 0 12px 30px rgba(34,36,38,.08); }
.card h3 { margin-top: 0; }
.card small { color: var(--accent); }
"""


def render_python_service() -> str:
    return """from fastapi import FastAPI

app = FastAPI(title='singine-platform-api')


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'singine-platform-api'}


@app.get('/blueprint')
def blueprint():
    from singine.platform_blueprint import build_platform_blueprint
    return build_platform_blueprint()
"""


def render_spring_boot_stub() -> str:
    return """package io.sindoc.singine.platform;

public interface MetadataProtocolAdapter {
    String adapterName();
    String infosetFamily();
    String activityMode();
}
"""


def write_platform_blueprint_bundle(output_dir: Path, title: str = "Singine Multi-Model Platform Blueprint") -> Dict[str, Any]:
    blueprint = build_platform_blueprint(title=title)
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "platform-blueprint.json").write_text(json.dumps(blueprint, indent=2) + "\n", encoding="utf-8")
    (output_dir / "platform-blueprint.md").write_text(render_markdown(blueprint), encoding="utf-8")
    deploy_dir = output_dir / "deploy"
    deploy_dir.mkdir(exist_ok=True)
    (deploy_dir / "openshift-template.yaml").write_text(render_openshift_template(blueprint), encoding="utf-8")

    web_dir = output_dir / "webapp"
    public_dir = web_dir / "public"
    api_dir = output_dir / "python-api"
    java_dir = output_dir / "spring-adapter" / "src" / "main" / "java" / "io" / "sindoc" / "singine" / "platform"
    public_dir.mkdir(parents=True, exist_ok=True)
    api_dir.mkdir(parents=True, exist_ok=True)
    java_dir.mkdir(parents=True, exist_ok=True)

    (web_dir / "package.json").write_text(render_node_package(), encoding="utf-8")
    (web_dir / "server.js").write_text(render_node_server(), encoding="utf-8")
    (public_dir / "index.html").write_text(render_html(blueprint), encoding="utf-8")
    (public_dir / "styles.css").write_text(render_css(), encoding="utf-8")
    (api_dir / "service.py").write_text(render_python_service(), encoding="utf-8")
    (java_dir / "MetadataProtocolAdapter.java").write_text(render_spring_boot_stub(), encoding="utf-8")

    return {
        "blueprint": blueprint,
        "artifacts": {
            "json": str(output_dir / "platform-blueprint.json"),
            "markdown": str(output_dir / "platform-blueprint.md"),
            "openshift_template": str(deploy_dir / "openshift-template.yaml"),
            "node_webapp": str(web_dir),
            "python_api": str(api_dir / "service.py"),
            "spring_adapter_interface": str(java_dir / "MetadataProtocolAdapter.java"),
        },
    }
