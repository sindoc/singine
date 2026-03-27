"""Atom-backed realm operations for DNS, TLS, trust, and vault audits."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


ATOM_NS = "http://www.w3.org/2005/Atom"
SINGINE_NS = "http://singine.io/ontology#"

ET.register_namespace("", ATOM_NS)
ET.register_namespace("singine", SINGINE_NS)

DEFAULT_REALMS = [
    "local.realm",
    "ext.realm",
    "neighbour.realm",
    "dmz.realm",
    "mode1.realm",
    "mode2.realm",
]

DEFAULT_DOMAINS = [
    "lutino.io",
    "www.markupware.com",
    "app.lutino.io",
    "collibra.lutino.io",
]

DEFAULT_SERVICES = ["dns", "tls", "trust", "vault"]
DEFAULT_TOPIC_TARGETS = [
    "singine",
    "silkpage",
    "collibra",
    "lutino.io",
    "www.markupware.com",
    "app.lutino.io",
    "collibra.lutino.io",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atom_tag(local: str) -> str:
    return f"{{{ATOM_NS}}}{local}"


def singine_tag(local: str) -> str:
    return f"{{{SINGINE_NS}}}{local}"


def _indent_xml(element: ET.Element, level: int = 0) -> None:
    indent = "\n" + level * "  "
    if len(element):
        if not element.text or not element.text.strip():
            element.text = indent + "  "
        for child in element:
            _indent_xml(child, level + 1)
        if not element[-1].tail or not element[-1].tail.strip():
            element[-1].tail = indent
    if level and (not element.tail or not element.tail.strip()):
        element.tail = indent


def write_xml(path: Path, root: ET.Element) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _indent_xml(root)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path


def _run_command(command: Sequence[str], timeout: int = 20) -> Dict[str, Any]:
    binary = command[0]
    resolved = shutil.which(binary)
    if resolved is None:
        return {
            "ok": False,
            "command": list(command),
            "error": f"{binary}-not-found",
        }
    try:
        proc = subprocess.run(
            [resolved, *command[1:]],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return {
            "ok": False,
            "command": list(command),
            "error": str(exc),
        }
    return {
        "ok": proc.returncode == 0,
        "command": list(command),
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _normalize_realms(realms: Optional[Sequence[str]], domains: Sequence[str]) -> List[str]:
    values = list(realms or [])
    if not values:
        values.extend(DEFAULT_REALMS)
    for domain in domains:
        if domain not in values:
            values.append(domain)
    return values


def _normalize_domains(domains: Optional[Sequence[str]]) -> List[str]:
    values = list(domains or [])
    return values if values else list(DEFAULT_DOMAINS)


def _normalize_services(services: Optional[Sequence[str]]) -> List[str]:
    values = list(services or [])
    return values if values else list(DEFAULT_SERVICES)


def _request_payload(
    *,
    request_kind: str,
    realms: Sequence[str],
    domains: Sequence[str],
    services: Sequence[str],
    cron_expression: Optional[str] = None,
    output_dir: Optional[str] = None,
    topic: Optional[str] = None,
    targets: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "request_kind": request_kind,
        "realms": list(realms),
        "domains": list(domains),
        "services": list(services),
    }
    if cron_expression:
        payload["cron_expression"] = cron_expression
    if output_dir:
        payload["output_dir"] = output_dir
    if topic:
        payload["topic"] = topic
    if targets:
        payload["targets"] = list(targets)
    return payload


def build_request_feed(
    *,
    request_kind: str,
    realms: Sequence[str],
    domains: Sequence[str],
    services: Sequence[str],
    cron_expression: Optional[str] = None,
    output_dir: Optional[str] = None,
    topic: Optional[str] = None,
    targets: Optional[Sequence[str]] = None,
) -> ET.Element:
    feed = ET.Element(atom_tag("feed"))
    ET.SubElement(feed, atom_tag("id")).text = f"urn:singine:realm-request:{uuid.uuid4()}"
    ET.SubElement(feed, atom_tag("title")).text = f"Singine realm request: {request_kind}"
    ET.SubElement(feed, atom_tag("updated")).text = utc_now()
    author = ET.SubElement(feed, atom_tag("author"))
    ET.SubElement(author, atom_tag("name")).text = "singine"
    for realm in realms:
        ET.SubElement(feed, atom_tag("category"), {"term": realm, "label": "realm"})
    for domain in domains:
        ET.SubElement(feed, atom_tag("category"), {"term": domain, "label": "domain"})
    entry = ET.SubElement(feed, atom_tag("entry"))
    ET.SubElement(entry, atom_tag("id")).text = f"urn:singine:realm-request-entry:{uuid.uuid4()}"
    ET.SubElement(entry, atom_tag("title")).text = request_kind
    ET.SubElement(entry, atom_tag("updated")).text = utc_now()
    content = ET.SubElement(entry, atom_tag("content"), {"type": "application/json"})
    content.text = json.dumps(
        _request_payload(
            request_kind=request_kind,
            realms=realms,
            domains=domains,
            services=services,
            cron_expression=cron_expression,
            output_dir=output_dir,
            topic=topic,
            targets=targets,
        ),
        sort_keys=True,
    )
    return feed


def parse_feed(path: Path) -> Dict[str, Any]:
    root = ET.parse(path).getroot()
    content = root.find(f".//{atom_tag('content')}")
    if content is None or not (content.text or "").strip():
        raise ValueError(f"Atom feed has no JSON payload: {path}")
    payload = json.loads(content.text)
    payload["path"] = str(path)
    return payload


def _check_dns(domain: str) -> Dict[str, Any]:
    nslookup = _run_command(["nslookup", domain], timeout=15)
    whois = _run_command(["whois", domain], timeout=25)
    return {
        "service": "dns",
        "domain": domain,
        "nslookup": nslookup,
        "whois": whois,
        "xwalkCode": f"dns:{domain}",
        "causalityKey": f"dns|{domain}",
    }


def _check_tls(domain: str) -> Dict[str, Any]:
    openssl = _run_command(
        [
            "openssl",
            "s_client",
            "-connect",
            f"{domain}:443",
            "-servername",
            domain,
            "-brief",
        ],
        timeout=25,
    )
    return {
        "service": "tls",
        "domain": domain,
        "openssl": openssl,
        "ca_bundle_candidates": [
            str(Path.home() / ".config" / "lutino" / "ssl" / "cacert.pem"),
            "/etc/ssl/cert.pem",
            "/usr/local/etc/openssl@3/cert.pem",
        ],
        "ca_authorities": ["cacert.org", "controlled-cacert"],
        "xwalkCode": f"tls:{domain}",
        "causalityKey": f"tls|{domain}",
    }


def _check_trust() -> Dict[str, Any]:
    trust_edn = Path.home() / ".singine" / "trust.edn"
    singine_keystore = Path.home() / ".singine" / "singine.jks"
    lutino_cacert = Path.home() / ".config" / "lutino" / "ssl" / "cacert.pem"
    java_home = os.environ.get("JAVA_HOME")
    jvm_cacerts = Path(java_home) / "lib" / "security" / "cacerts" if java_home else None
    return {
        "service": "trust",
        "trust_store": {
            "trust_edn": str(trust_edn),
            "trust_edn_exists": trust_edn.exists(),
            "singine_keystore": str(singine_keystore),
            "singine_keystore_exists": singine_keystore.exists(),
            "lutino_cacert": str(lutino_cacert),
            "lutino_cacert_exists": lutino_cacert.exists(),
            "java_home": java_home,
            "jvm_cacerts": str(jvm_cacerts) if jvm_cacerts else None,
            "jvm_cacerts_exists": bool(jvm_cacerts and jvm_cacerts.exists()),
        },
        "aliases": ["trust.store", "keystore", "cacert.org", "controlled-cacert"],
        "xwalkCode": "trust:keystore",
        "causalityKey": "trust|keystore",
    }


def _check_vault() -> Dict[str, Any]:
    candidates = [
        os.environ.get("VAULT_ADDR"),
        os.environ.get("SINGINE_VAULT_ADDR"),
        os.environ.get("SINGINE_VALULT_ADDR"),
    ]
    vault_token = Path.home() / ".vault-token"
    return {
        "service": "vault",
        "topic_aliases": ["hashicorp", "singine-vault", "valult"],
        "vault": {
            "vault_addr": next((value for value in candidates if value), None),
            "vault_token_path": str(vault_token),
            "vault_token_exists": vault_token.exists(),
            "hashicorp_binary": shutil.which("vault"),
            "singine_vault_env": {key: os.environ.get(key) for key in ["VAULT_ADDR", "VAULT_NAMESPACE", "SINGINE_VAULT_ADDR", "SINGINE_VALULT_ADDR"] if os.environ.get(key)},
        },
        "xwalkCode": "vault:secret-store",
        "causalityKey": "vault|secret-store",
    }


def audit_realm(
    *,
    realm: str,
    domains: Sequence[str],
    services: Sequence[str],
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for service in services:
        if service in {"dns", "tls"}:
            for domain in domains:
                payload = _check_dns(domain) if service == "dns" else _check_tls(domain)
                payload["realm"] = realm
                payload["entity_type"] = "RealmDomainCheck"
                payload["source_kind"] = service
                payload["source_name"] = domain
                payload["label"] = f"{realm} {service} {domain}"
                entries.append(payload)
        elif service == "trust":
            payload = _check_trust()
            payload["realm"] = realm
            payload["entity_type"] = "RealmTrustCheck"
            payload["source_kind"] = service
            payload["source_name"] = realm
            payload["label"] = f"{realm} trust inventory"
            entries.append(payload)
        elif service == "vault":
            payload = _check_vault()
            payload["realm"] = realm
            payload["entity_type"] = "RealmVaultCheck"
            payload["source_kind"] = service
            payload["source_name"] = realm
            payload["label"] = f"{realm} vault inventory"
            entries.append(payload)
    return entries


def run_audit(*, realms: Sequence[str], domains: Sequence[str], services: Sequence[str]) -> Dict[str, List[Dict[str, Any]]]:
    results: Dict[str, List[Dict[str, Any]]] = {}
    for realm in realms:
        results[realm] = audit_realm(realm=realm, domains=domains, services=services)
    return results


def build_audit_response_feed(
    *,
    request_payload: Dict[str, Any],
    results: Dict[str, List[Dict[str, Any]]],
) -> ET.Element:
    feed = ET.Element(atom_tag("feed"))
    ET.SubElement(feed, atom_tag("id")).text = f"urn:singine:realm-response:{uuid.uuid4()}"
    ET.SubElement(feed, atom_tag("title")).text = "Singine realm audit response"
    ET.SubElement(feed, atom_tag("updated")).text = utc_now()
    author = ET.SubElement(feed, atom_tag("author"))
    ET.SubElement(author, atom_tag("name")).text = "singine"
    ET.SubElement(feed, singine_tag("causalityPolicy")).text = "realm-domain-service-crosswalk"
    for realm, rows in results.items():
        ET.SubElement(feed, atom_tag("category"), {"term": realm, "label": "realm"})
        for row in rows:
            entry = ET.SubElement(feed, atom_tag("entry"))
            ET.SubElement(entry, atom_tag("id")).text = f"urn:singine:realm-audit:{uuid.uuid4()}"
            ET.SubElement(entry, atom_tag("title")).text = row["label"]
            ET.SubElement(entry, atom_tag("updated")).text = utc_now()
            ET.SubElement(entry, atom_tag("category"), {"term": realm, "label": "realm"})
            ET.SubElement(entry, atom_tag("category"), {"term": row["source_kind"], "label": "service"})
            ET.SubElement(entry, singine_tag("realm")).text = realm
            ET.SubElement(entry, singine_tag("sourceKind")).text = row["source_kind"]
            ET.SubElement(entry, singine_tag("sourceName")).text = row["source_name"]
            ET.SubElement(entry, singine_tag("xwalkCode")).text = row["xwalkCode"]
            ET.SubElement(entry, singine_tag("causalityKey")).text = row["causalityKey"]
            summary = ET.SubElement(entry, atom_tag("summary"))
            summary.text = f"{row['source_kind']} audit for {row['source_name']} in {realm}"
            content = ET.SubElement(entry, atom_tag("content"), {"type": "application/json"})
            content.text = json.dumps(row, sort_keys=True)
    request_entry = ET.SubElement(feed, atom_tag("entry"))
    ET.SubElement(request_entry, atom_tag("id")).text = f"urn:singine:realm-request-echo:{uuid.uuid4()}"
    ET.SubElement(request_entry, atom_tag("title")).text = "request-echo"
    ET.SubElement(request_entry, atom_tag("updated")).text = utc_now()
    request_content = ET.SubElement(request_entry, atom_tag("content"), {"type": "application/json"})
    request_content.text = json.dumps(request_payload, sort_keys=True)
    return feed


def build_cron_response_feed(
    *,
    request_payload: Dict[str, Any],
    command: str,
) -> ET.Element:
    feed = ET.Element(atom_tag("feed"))
    ET.SubElement(feed, atom_tag("id")).text = f"urn:singine:realm-cron:{uuid.uuid4()}"
    ET.SubElement(feed, atom_tag("title")).text = "Singine realm cron specification"
    ET.SubElement(feed, atom_tag("updated")).text = utc_now()
    entry = ET.SubElement(feed, atom_tag("entry"))
    ET.SubElement(entry, atom_tag("id")).text = f"urn:singine:realm-cron-entry:{uuid.uuid4()}"
    ET.SubElement(entry, atom_tag("title")).text = "cron-spec"
    ET.SubElement(entry, atom_tag("updated")).text = utc_now()
    ET.SubElement(entry, singine_tag("cronExpression")).text = request_payload["cron_expression"]
    ET.SubElement(entry, singine_tag("xwalkCode")).text = "cron:realm-audit"
    ET.SubElement(entry, singine_tag("causalityKey")).text = "|".join(
        [
            "cron",
            request_payload["cron_expression"],
            ",".join(request_payload["realms"]),
            ",".join(request_payload["services"]),
        ]
    )
    summary = ET.SubElement(entry, atom_tag("summary"))
    summary.text = command
    content = ET.SubElement(entry, atom_tag("content"), {"type": "application/json"})
    content.text = json.dumps(
        {
            "cron_expression": request_payload["cron_expression"],
            "command": command,
            "realms": request_payload["realms"],
            "domains": request_payload["domains"],
            "services": request_payload["services"],
        },
        sort_keys=True,
    )
    return feed


def build_broadcast_feed(*, topic: str, targets: Sequence[str], domains: Sequence[str], realms: Sequence[str]) -> ET.Element:
    feed = ET.Element(atom_tag("feed"))
    ET.SubElement(feed, atom_tag("id")).text = f"urn:singine:realm-broadcast:{uuid.uuid4()}"
    ET.SubElement(feed, atom_tag("title")).text = f"Singine topic interest broadcast: {topic}"
    ET.SubElement(feed, atom_tag("updated")).text = utc_now()
    ET.SubElement(feed, singine_tag("topic")).text = topic
    ET.SubElement(feed, singine_tag("causalityPolicy")).text = "topic-to-target-crosswalk"
    for target in targets:
        entry = ET.SubElement(feed, atom_tag("entry"))
        ET.SubElement(entry, atom_tag("id")).text = f"urn:singine:realm-broadcast-entry:{uuid.uuid4()}"
        ET.SubElement(entry, atom_tag("title")).text = f"broadcast target: {target}"
        ET.SubElement(entry, atom_tag("updated")).text = utc_now()
        ET.SubElement(entry, singine_tag("target")).text = target
        ET.SubElement(entry, singine_tag("xwalkCode")).text = f"topic:{target}"
        ET.SubElement(entry, singine_tag("causalityKey")).text = f"topic|{topic}|{target}"
        summary = ET.SubElement(entry, atom_tag("summary"))
        summary.text = f"Topic '{topic}' is aligned for {target} across {', '.join(realms)}"
        content = ET.SubElement(entry, atom_tag("content"), {"type": "application/json"})
        content.text = json.dumps(
            {
                "topic": topic,
                "target": target,
                "domains": list(domains),
                "realms": list(realms),
            },
            sort_keys=True,
        )
    return feed


def summarize_feed(path: Path) -> Dict[str, Any]:
    root = ET.parse(path).getroot()
    entries = root.findall(atom_tag("entry"))
    service_counts: Dict[str, int] = {}
    realm_counts: Dict[str, int] = {}
    for entry in entries:
        realm = entry.findtext(singine_tag("realm"))
        service = entry.findtext(singine_tag("sourceKind"))
        if realm:
            realm_counts[realm] = realm_counts.get(realm, 0) + 1
        if service:
            service_counts[service] = service_counts.get(service, 0) + 1
    return {
        "path": str(path),
        "title": root.findtext(atom_tag("title")),
        "updated": root.findtext(atom_tag("updated")),
        "entry_count": len(entries),
        "realms": realm_counts,
        "services": service_counts,
    }


def write_cron_file(path: Path, cron_expression: str, command: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        "# singine realm cron schedule\n"
        f"{cron_expression} {command}\n"
    )
    path.write_text(payload, encoding="utf-8")
    return path


def default_audit_command(
    *,
    request_path: Path,
    response_path: Path,
    realms: Sequence[str],
    domains: Sequence[str],
    services: Sequence[str],
) -> str:
    parts: List[str] = [
        "singine",
        "realm",
        "check",
        "--request",
        str(request_path),
        "--response",
        str(response_path),
        "--read-request",
    ]
    for realm in realms:
        parts.extend(["--realm", realm])
    for domain in domains:
        parts.extend(["--domain", domain])
    for service in services:
        parts.extend(["--service", service])
    return " ".join(parts)


def resolve_schedule_inputs(
    *,
    realms: Optional[Sequence[str]],
    domains: Optional[Sequence[str]],
    services: Optional[Sequence[str]],
) -> Dict[str, List[str]]:
    resolved_domains = _normalize_domains(domains)
    return {
        "realms": _normalize_realms(realms, resolved_domains),
        "domains": resolved_domains,
        "services": _normalize_services(services),
    }


def local_realm_descriptor(realms: Sequence[str], domains: Sequence[str]) -> Dict[str, Any]:
    return {
        "hostname": socket.gethostname(),
        "realms": list(realms),
        "domains": list(domains),
        "default_services": list(DEFAULT_SERVICES),
        "trust_paths": {
            "keystore": str(Path.home() / ".singine" / "singine.jks"),
            "trust_edn": str(Path.home() / ".singine" / "trust.edn"),
            "lutino_ssl": str(Path.home() / ".config" / "lutino" / "ssl"),
        },
    }
