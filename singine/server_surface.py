"""Simple server, Logseq, and snapshot helpers for the Singine CLI.

This module exposes:
- server defaults for local, edge, and docker-aware Singine deployments
- lightweight HTTP clients for /health, /bridge, and the Logseq /api surface
- a persisted snapshot that captures runtime, git, docker, Java, and taxonomy context
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_CLIENT_HOST = "127.0.0.1"
DEFAULT_BIND_HOST = "0.0.0.0"
DEFAULT_SERVER_PORT = 8080
DEFAULT_LOGSEQ_URL = "http://127.0.0.1:12315"


def _detect_environment_type() -> str:
    env = os.environ.get("SINGINE_ENVIRONMENT_TYPE") or os.environ.get("SINGINE_ENV")
    if env:
        return env
    if os.environ.get("DOCKER_CONTAINER") or os.path.exists("/.dockerenv"):
        return "docker"
    return "local"


def _safe_git(repo_root: Path, *args: str) -> Dict[str, Any]:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return {
        "ok": proc.returncode == 0,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _git_awareness(repo_root: Path) -> Dict[str, Any]:
    branch = _safe_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    status = _safe_git(repo_root, "status", "--short")
    head = _safe_git(repo_root, "rev-parse", "HEAD")
    return {
        "branch": branch["stdout"] if branch["ok"] else None,
        "head": head["stdout"] if head["ok"] else None,
        "status_excerpt": status["stdout"].splitlines()[:12] if status["ok"] else [],
    }


def _docker_awareness(repo_root: Path) -> Dict[str, Any]:
    docker_root = repo_root / "docker"
    return {
        "root": str(docker_root),
        "files": sorted(path.name for path in docker_root.glob("*") if path.is_file()),
        "edge_compose": str(docker_root / "docker-compose.edge.yml"),
        "mail_compose": str(docker_root / "docker-compose.mail.yml"),
        "edge_dockerfile": str(docker_root / "Dockerfile.edge"),
        "mail_dockerfile": str(docker_root / "Dockerfile.mail"),
    }


def _activity_java_interfaces(repo_root: Path) -> Dict[str, Any]:
    activity_root = repo_root / "core" / "java" / "singine" / "activity"
    interfaces = sorted(
        str(path.relative_to(activity_root))
        for path in activity_root.rglob("*.java")
        if path.name != "package-info.java"
    )
    taxonomy_path = repo_root / "core" / "resources" / "singine" / "activity" / "taxonomy.edn"
    activity_ids: List[str] = []
    if taxonomy_path.exists():
        for line in taxonomy_path.read_text(encoding="utf-8").splitlines():
            marker = ':activity/id          "'
            if marker in line:
                activity_ids.append(line.split(marker, 1)[1].split('"', 1)[0])
    return {
        "java_root": str(activity_root),
        "interfaces": interfaces,
        "taxonomy_path": str(taxonomy_path),
        "activity_count": len(activity_ids),
        "activity_ids_excerpt": activity_ids[:12],
    }


def _publication_awareness(repo_root: Path) -> Dict[str, Any]:
    return {
        "core_makefile": str(repo_root / "core" / "Makefile"),
        "docs_makefile": str(repo_root / "docs" / "Makefile"),
        "docs_target_spec": str(repo_root / "docs" / "target" / "spec"),
        "javadoc_xml": str(repo_root / "core" / "target" / "javadoc-xml" / "doclet.xml"),
        "spec_xml": str(repo_root / "docs" / "spec-publication.xml"),
        "silkpage_xsl": str(repo_root.parent / "silkpage" / "docs" / "src" / "xsl" / "html-spec-single.xsl"),
        "ant_targets": ["javadoc-html", "javadoc-xml"],
        "maven_artifact": "com.saxonica:xmldoclet:LATEST",
    }


def _runtime_context(repo_root: Path) -> Dict[str, Any]:
    return {
        "cwd": os.getcwd(),
        "repo_root": str(repo_root),
        "python_executable": sys.executable,
        "shell": Path(os.environ.get("SHELL", "sh")).name,
        "hostname": socket.gethostname(),
        "user": os.environ.get("USER") or os.environ.get("LOGNAME"),
        "virtual_env": os.environ.get("VIRTUAL_ENV"),
        "singine_env": os.environ.get("SINGINE_ENV"),
        "singine_cortex_db": os.environ.get("SINGINE_CORTEX_DB"),
    }


def _migration_paths(repo_root: Path) -> Dict[str, str]:
    return {
        "context_snapshot_dir": str(Path.home() / ".singine" / "context"),
        "bridge_db_default": "/tmp/sqlite.db",
        "xml_matrix_output": "/tmp/singine-xml-matrix",
        "activity_taxonomy": str(repo_root / "core" / "resources" / "singine" / "activity" / "taxonomy.edn"),
        "javadoc_xml": str(repo_root / "core" / "target" / "javadoc-xml" / "doclet.xml"),
        "spec_target": str(repo_root / "docs" / "target" / "spec"),
        "logseq_root_hint": str(Path.home() / "ws" / "logseq"),
    }


def server_descriptor(
    repo_root: Path,
    *,
    host: Optional[str] = None,
    port: Optional[int] = None,
    environment_type: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_host = host or os.environ.get("SINGINE_HOST") or DEFAULT_CLIENT_HOST
    resolved_port = int(port or os.environ.get("SINGINE_PORT") or DEFAULT_SERVER_PORT)
    resolved_env = environment_type or _detect_environment_type()
    base_url = f"http://{resolved_host}:{resolved_port}"
    return {
        "environment_type": resolved_env,
        "server": {
            "bind_host": os.environ.get("SINGINE_BIND_HOST", DEFAULT_BIND_HOST),
            "client_host": resolved_host,
            "port": resolved_port,
            "base_url": base_url,
            "default_routes": {
                "health": f"{base_url}/health",
                "bridge": f"{base_url}/bridge?action=sources",
                "cap": f"{base_url}/cap",
                "messages": f"{base_url}/messages",
                "timez": f"{base_url}/timez?cities=BRU,NYC",
            },
            "profiles": {
                "local": {"base_url": base_url, "note": "developer workstation or laptop runtime"},
                "edge": {"base_url": base_url, "compose_file": str(repo_root / "docker" / "docker-compose.edge.yml")},
                "docker": {"base_url": base_url, "dockerfile": str(repo_root / "docker" / "Dockerfile.edge")},
            },
        },
        "git": _git_awareness(repo_root),
        "docker": _docker_awareness(repo_root),
        "activity_api": _activity_java_interfaces(repo_root),
        "publication": _publication_awareness(repo_root),
        "migration_paths": _migration_paths(repo_root),
        "runtime": _runtime_context(repo_root),
    }


def logseq_descriptor(repo_root: Path, *, base_url: Optional[str] = None) -> Dict[str, Any]:
    resolved = base_url or os.environ.get("LOGSEQ_API_URL") or DEFAULT_LOGSEQ_URL
    return {
        "base_url": resolved,
        "token_env_var": "LOGSEQ_API_TOKEN",
        "token_present": bool(os.environ.get("LOGSEQ_API_TOKEN")),
        "api_endpoint": f"{resolved.rstrip('/')}/api",
        "fallback_mode": "filesystem",
        "filesystem_hint": str(Path.home() / "ws" / "logseq"),
        "publication_alignment": {
            "activity_taxonomy": str(repo_root / "core" / "resources" / "singine" / "activity" / "taxonomy.edn"),
            "silkpage_docs": str(repo_root.parent / "silkpage" / "docs"),
        },
    }


def _decode_response_body(raw: bytes) -> Dict[str, Any]:
    text = raw.decode("utf-8")
    try:
        return {"ok": True, "data": json.loads(text), "raw_text": text}
    except json.JSONDecodeError:
        return {"ok": True, "data": text, "raw_text": text}


def _http_get(url: str, *, timeout: int = 10) -> Dict[str, Any]:
    try:
        with urlopen(url, timeout=timeout) as response:
            payload = _decode_response_body(response.read())
            payload["status"] = getattr(response, "status", 200)
            payload["url"] = url
            return payload
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": exc.code, "url": url, "error": body}
    except URLError as exc:
        return {"ok": False, "status": None, "url": url, "error": str(exc.reason)}


def _http_post_json(url: str, payload: Dict[str, Any], *, headers: Optional[Dict[str, str]] = None, timeout: int = 10) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urlopen(request, timeout=timeout) as response:
            parsed = _decode_response_body(response.read())
            parsed["status"] = getattr(response, "status", 200)
            parsed["url"] = url
            return parsed
    except HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": exc.code, "url": url, "error": body_text}
    except URLError as exc:
        return {"ok": False, "status": None, "url": url, "error": str(exc.reason)}


def ping_server(base_url: str, *, timeout: int = 10) -> Dict[str, Any]:
    result = _http_get(f"{base_url.rstrip('/')}/health", timeout=timeout)
    result["base_url"] = base_url.rstrip("/")
    return result


def query_bridge(
    base_url: str,
    *,
    action: str,
    query: Optional[str] = None,
    entity: Optional[str] = None,
    limit: int = 20,
    realm: Optional[str] = None,
    source_kind: Optional[str] = None,
    timeout: int = 10,
) -> Dict[str, Any]:
    params = {"action": action, "limit": str(limit)}
    if query:
        params["q"] = query
    if entity:
        params["entity"] = entity
    if realm:
        params["realm"] = realm
    if source_kind:
        params["source-kind"] = source_kind
    url = f"{base_url.rstrip('/')}/bridge?{urlencode(params)}"
    result = _http_get(url, timeout=timeout)
    result["action"] = action
    return result


def ping_logseq(base_url: str, *, token: Optional[str], timeout: int = 10) -> Dict[str, Any]:
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    result = _http_post_json(
        f"{base_url.rstrip('/')}/api",
        {"method": "logseq.App.getCurrentGraph", "args": []},
        headers=headers,
        timeout=timeout,
    )
    result["base_url"] = base_url.rstrip("/")
    result["token_present"] = bool(token)
    return result


def snapshot_payload(
    repo_root: Path,
    *,
    host: Optional[str] = None,
    port: Optional[int] = None,
    environment_type: Optional[str] = None,
    logseq_url: Optional[str] = None,
    logseq_token: Optional[str] = None,
) -> Dict[str, Any]:
    server = server_descriptor(repo_root, host=host, port=port, environment_type=environment_type)
    logseq = logseq_descriptor(repo_root, base_url=logseq_url)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "context_type": "singine-runtime-snapshot",
        "server": server,
        "logseq": logseq,
        "commands": {
            "server_inspect": "singine server inspect --json",
            "server_health": "singine server health --json",
            "server_bridge": "singine server bridge --action sources --json",
            "logseq_inspect": "singine logseq inspect --json",
            "logseq_ping": "singine logseq ping --json",
        },
    }
    if logseq_token:
        payload["logseq"]["token_present"] = True
    return payload


def save_snapshot(
    output_path: Path,
    repo_root: Path,
    *,
    host: Optional[str] = None,
    port: Optional[int] = None,
    environment_type: Optional[str] = None,
    logseq_url: Optional[str] = None,
    logseq_token: Optional[str] = None,
) -> Dict[str, Any]:
    payload = snapshot_payload(
        repo_root,
        host=host,
        port=port,
        environment_type=environment_type,
        logseq_url=logseq_url,
        logseq_token=logseq_token,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"ok": True, "output_path": str(output_path), "snapshot": payload}


def create_server_test_case(
    case_root: Path,
    repo_root: Path,
    *,
    host: str = DEFAULT_CLIENT_HOST,
    port: int = DEFAULT_SERVER_PORT,
    logseq_url: str = DEFAULT_LOGSEQ_URL,
) -> Dict[str, Any]:
    if case_root.exists():
        for path in sorted(case_root.rglob("*"), reverse=True):
            if path.is_file() or path.is_symlink():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    case_root.mkdir(parents=True, exist_ok=True)

    readme_path = case_root / "README.txt"
    activity_path = case_root / "activity.json"
    snapshot_path = case_root / "snapshot.json"
    commands = [
        "singine server inspect --json",
        "singine server health --json",
        "singine server bridge --action sources --json",
        "singine logseq inspect --json",
        "singine logseq ping --token \"$LOGSEQ_API_TOKEN\" --json",
        f"singine snapshot save --output {snapshot_path} --json",
        "python3 -m unittest py.tests.test_server_surface_commands -v",
    ]
    activity_payload = {
        "activity_id": "activity-singine-server-surface-01",
        "activity_name": "Validate Singine server/logseq/snapshot surface",
        "activity_interface": "singine server test-case",
        "taxonomy_path": str(repo_root / "core" / "resources" / "singine" / "activity" / "taxonomy.edn"),
        "host": host,
        "port": port,
        "logseq_url": logseq_url,
        "commands": commands,
    }
    activity_path.write_text(json.dumps(activity_payload, indent=2) + "\n", encoding="utf-8")
    readme_path.write_text(
        "\n".join(
            [
                "Singine server surface test case",
                "",
                f"Host: {host}",
                f"Port: {port}",
                f"Logseq URL: {logseq_url}",
                "",
                "Commands:",
                *[f"  {command}" for command in commands],
                "",
                "Notes:",
                "  - server health and bridge expect the local Singine HTTP server surface",
                "  - logseq ping expects LOGSEQ_API_TOKEN when calling a real Logseq API",
                "  - the bundled unittest uses a mock transport and is safe to run offline",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "ok": True,
        "case_root": str(case_root),
        "readme_path": str(readme_path),
        "activity_path": str(activity_path),
        "snapshot_path": str(snapshot_path),
        "commands": commands,
    }
