"""singine.net — Intranet service registry, port inventory, and dispatch table.

Canonical source of truth for every port, process, and routing rule in the
sindoc.local intranet.  All other modules (panel, feeds, presence) import from
here to avoid duplication.

Usage::

    singine net status
    singine net status --json
    singine net ports
    singine net probe --service edge-site
    singine net route --from / --to edge-site
"""
from __future__ import annotations

import json
import socket
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ── Canonical intranet service registry ───────────────────────────────────────

@dataclass
class Service:
    id: str
    label: str
    port: int
    proto: str          # http | https | tcp
    host: str
    kind: str           # docker | process | external
    container: str = ""
    process: str = ""
    health_path: str = "/health"
    requires_presence: bool = False
    skos_concept: str = ""
    description: str = ""
    # runtime state (populated by probe())
    reachable: Optional[bool] = None
    latency_ms: Optional[float] = None
    probed_at: Optional[str] = None

    def url(self) -> str:
        return f"{self.proto}://{self.host}:{self.port}"

    def health_url(self) -> str:
        return f"{self.proto}://{self.host}:{self.port}{self.health_path}"

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


SERVICES: List[Service] = [
    Service(
        id="cdn-https",
        label="nginx CDN — TLS Proxy",
        port=443, proto="https", host="sindoc.local", kind="docker",
        container="edge-cdn-1",
        health_path="/healthz",
        skos_concept="urn:singine:net:service:cdn",
        description="Terminates TLS, routes /site/, /api/edge/, /rest/, /graphql/.",
    ),
    Service(
        id="cdn-http",
        label="nginx CDN — HTTP redirect",
        port=80, proto="http", host="sindoc.local", kind="docker",
        container="edge-cdn-1",
        health_path="/healthz",
        skos_concept="urn:singine:net:service:cdn",
        description="Redirects all HTTP to HTTPS.",
    ),
    Service(
        id="edge-site",
        label="Collibra Edge Site — Java REST API",
        port=8080, proto="http", host="localhost", kind="docker",
        container="edge-edge-site-1",
        health_path="/health",
        skos_concept="urn:singine:net:service:edge-site",
        description="Custom Java server serving /api/edge/v1/* and static /site/ content.",
    ),
    Service(
        id="collibra-dgc",
        label="Collibra DGC Edge Node",
        port=7080, proto="http", host="localhost", kind="docker",
        container="edge-collibra-edge-1",
        health_path="/health/detailed",
        skos_concept="urn:singine:net:service:collibra-dgc",
        description="Collibra DGC edge: REST /rest/, GraphQL /graphql/, catalog proxy.",
    ),
    Service(
        id="singine-http",
        label="Singine HTTP Surface",
        port=8081, proto="http", host="localhost", kind="process",
        process="python3",
        health_path="/health",
        skos_concept="urn:singine:net:service:singine-http",
        description="singine server bridge — SPARQL/GraphQL/bridge endpoints.",
    ),
    Service(
        id="logseq",
        label="Logseq API",
        port=12315, proto="http", host="localhost", kind="process",
        process="electron",
        health_path="/api",
        skos_concept="urn:singine:net:service:logseq",
        description="Logseq desktop HTTP API — graph queries.",
    ),
    Service(
        id="panel",
        label="Singine Net Panel",
        port=9090, proto="http", host="localhost", kind="process",
        process="python3",
        health_path="/api/health",
        requires_presence=True,
        skos_concept="urn:singine:net:service:panel",
        description="Live intranet control panel — port 9090.",
    ),
]

SERVICE_INDEX: Dict[str, Service] = {s.id: s for s in SERVICES}


# ── Routing table ──────────────────────────────────────────────────────────────

@dataclass
class Route:
    path_pattern: str
    target_service: str
    cacheable: bool = False
    auth_required: bool = False
    requires_presence: bool = False
    description: str = ""


ROUTES: List[Route] = [
    Route("/health",            "edge-site",   cacheable=False, description="Health probe shortcut"),
    Route("/healthz",           "cdn-https",   cacheable=False, description="CDN health"),
    Route("/api/edge/",         "edge-site",   cacheable=False, auth_required=True,  description="Edge Site REST API"),
    Route("/api/net/",          "panel",       cacheable=False, auth_required=True,  description="Net panel REST API"),
    Route("/site/",             "edge-site",   cacheable=True,  description="Static CDN-cached content"),
    Route("/rest/",             "collibra-dgc", cacheable=False, auth_required=True,  description="Collibra REST API"),
    Route("/graphql/",          "collibra-dgc", cacheable=False, auth_required=True,  description="Collibra GraphQL"),
    Route("/feeds/",            "panel",       cacheable=True,  description="Atom/RSS activity feeds"),
    Route("/vocab/",            "panel",       cacheable=True,  description="RDF/SKOS vocabularies"),
    Route("/panel/",            "panel",       cacheable=False, auth_required=True,  requires_presence=True, description="Net control panel UI"),
    Route("/bridge",            "singine-http", cacheable=False, auth_required=True,  description="Singine bridge (SPARQL/search)"),
    Route("/",                  "edge-site",   cacheable=True,  description="Default — edge site root"),
]


def _probe_tcp(host: str, port: int, timeout: float = 2.0) -> tuple[bool, float]:
    """Returns (reachable, latency_ms)."""
    import time
    t0 = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, (time.monotonic() - t0) * 1000
    except OSError:
        return False, -1.0


def probe(service: Service) -> Service:
    """Probe a service TCP port and update runtime state in-place."""
    reachable, latency = _probe_tcp(service.host, service.port)
    service.reachable = reachable
    service.latency_ms = round(latency, 1) if latency >= 0 else None
    service.probed_at = datetime.now(timezone.utc).isoformat()
    return service


def probe_all() -> List[Service]:
    for svc in SERVICES:
        probe(svc)
    return SERVICES


def docker_containers() -> List[Dict[str, str]]:
    """Live Docker ps output for all containers."""
    try:
        proc = subprocess.run(
            ["docker", "ps", "--format",
             "{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"],
            capture_output=True, text=True, timeout=10,
        )
        rows = []
        for line in proc.stdout.splitlines():
            parts = line.split("\t")
            rows.append({
                "name":   parts[0] if len(parts) > 0 else "",
                "image":  parts[1] if len(parts) > 1 else "",
                "status": parts[2] if len(parts) > 2 else "",
                "ports":  parts[3] if len(parts) > 3 else "",
            })
        return rows
    except Exception:
        return []


def status_payload() -> Dict[str, Any]:
    services = probe_all()
    containers = docker_containers()
    reachable = [s for s in services if s.reachable]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(services),
            "reachable": len(reachable),
            "unreachable": len(services) - len(reachable),
        },
        "services": [s.as_dict() for s in services],
        "routes": [asdict(r) for r in ROUTES],
        "docker_containers": containers,
    }


def cmd_status(args) -> int:
    payload = status_payload()
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
        return 0
    print(f"singine net — {payload['generated_at']}")
    print(f"  Services: {payload['summary']['total']}  "
          f"reachable: {payload['summary']['reachable']}  "
          f"unreachable: {payload['summary']['unreachable']}")
    print()
    for svc in payload["services"]:
        status = "✓" if svc["reachable"] else "✗"
        ms = f"{svc['latency_ms']}ms" if svc["latency_ms"] else "—"
        print(f"  {status}  [{svc['id']:20s}] {svc['proto']}://{svc['host']}:{svc['port']}"
              f"  ({svc['kind']})  {ms}  — {svc['label']}")
    return 0


def cmd_ports(args) -> int:
    payload = status_payload()
    if getattr(args, "json", False):
        print(json.dumps({"ports": payload["services"]}, indent=2))
        return 0
    print(f"{'PORT':>6}  {'PROTO':8}  {'ID':22}  {'KIND':9}  {'LABEL'}")
    print("-" * 76)
    for svc in payload["services"]:
        print(f"{svc['port']:>6}  {svc['proto']:8}  {svc['id']:22}  "
              f"{svc['kind']:9}  {svc['label']}")
    return 0


def cmd_probe(args) -> int:
    svc_id = args.service
    svc = SERVICE_INDEX.get(svc_id)
    if not svc:
        print(f"Unknown service: {svc_id}")
        return 1
    probe(svc)
    if getattr(args, "json", False):
        print(json.dumps(svc.as_dict(), indent=2))
        return 0
    status = "reachable" if svc.reachable else "unreachable"
    print(f"{svc.id}: {svc.url()} — {status} ({svc.latency_ms}ms)")
    return 0


def cmd_route(args) -> int:
    path = getattr(args, "from_path", "/")
    matched = [r for r in ROUTES if path.startswith(r.path_pattern)]
    matched.sort(key=lambda r: -len(r.path_pattern))  # longest match first
    if getattr(args, "json", False):
        print(json.dumps({"path": path, "routes": [asdict(r) for r in matched]}, indent=2))
        return 0
    if not matched:
        print(f"No route matched: {path}")
        return 1
    best = matched[0]
    target = SERVICE_INDEX.get(best.target_service)
    print(f"{path!r}  →  {best.target_service}  ({target.url() if target else '?'})")
    if best.auth_required:
        print("  auth required")
    if best.cacheable:
        print("  cacheable")
    return 0
