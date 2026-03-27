"""Silkpage-backed deployment helpers for the local sindoc.local intranet."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, List


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_cacert_path(ssl_dir: Path) -> Path:
    dotfile = ssl_dir / ".cacert_path"
    if dotfile.exists():
        text = dotfile.read_text(encoding="utf-8").strip()
        if text:
            return Path(text).expanduser()
    return ssl_dir / "cacert.pem"


def certificate_status(*, domain: str, ssl_dir: Path) -> Dict[str, Any]:
    cert_path = ssl_dir / f"{domain}.crt"
    key_path = ssl_dir / f"{domain}.key"
    ca_path = _load_cacert_path(ssl_dir)
    return {
        "domain": domain,
        "ssl_dir": str(ssl_dir),
        "cert_path": str(cert_path),
        "key_path": str(key_path),
        "ca_path": str(ca_path),
        "cert_exists": cert_path.exists(),
        "key_exists": key_path.exists(),
        "ca_exists": ca_path.exists(),
        "ready": cert_path.exists() and key_path.exists() and ca_path.exists(),
        "firefox": {
            "enterprise_roots_pref": "security.enterprise_roots.enabled",
            "policy": {"policies": {"Certificates": {"ImportEnterpriseRoots": True}}},
            "advice": [
                "Firefox does not always trust local certificates from the system keychain automatically.",
                "Set security.enterprise_roots.enabled=true in about:config, or install the local CA into Firefox Authorities.",
                "On managed Firefox installs, distribution/policies.json can enable ImportEnterpriseRoots.",
            ],
        },
    }


def bootstrap_local_tls(*, ssl_dir: Path, domain: str = "sindoc.local", force: bool = False) -> Dict[str, Any]:
    ssl_dir = ssl_dir.expanduser()
    openssl = shutil.which("openssl")
    if not openssl:
        raise FileNotFoundError("openssl is not available on PATH")

    ssl_dir.mkdir(parents=True, exist_ok=True)
    ca_key = ssl_dir / "local-root-ca.key"
    ca_cert = ssl_dir / "cacert.pem"
    server_key = ssl_dir / f"{domain}.key"
    server_csr = ssl_dir / f"{domain}.csr"
    server_cert = ssl_dir / f"{domain}.crt"
    ext_file = ssl_dir / f"{domain}.ext"
    cacert_path_file = ssl_dir / ".cacert_path"
    commands_run: List[List[str]] = []

    def run(parts: List[str]) -> None:
        commands_run.append(parts)
        subprocess.run(parts, check=True, capture_output=True, text=True)

    if force or not ca_cert.exists():
        if ca_key.exists() and force:
            ca_key.unlink()
        run([openssl, "genrsa", "-out", str(ca_key), "2048"])
        run(
            [
                openssl,
                "req",
                "-x509",
                "-new",
                "-nodes",
                "-key",
                str(ca_key),
                "-sha256",
                "-days",
                "825",
                "-out",
                str(ca_cert),
                "-subj",
                "/CN=Sindoc Local Root CA",
            ]
        )
    elif not ca_key.exists():
        raise FileNotFoundError(f"missing CA private key required for signing: {ca_key}")

    if force or not server_key.exists():
        run([openssl, "genrsa", "-out", str(server_key), "2048"])

    ext_file.write_text(
        "\n".join(
            [
                "authorityKeyIdentifier=keyid,issuer",
                "basicConstraints=CA:FALSE",
                "keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment",
                "extendedKeyUsage = serverAuth",
                f"subjectAltName = DNS:{domain}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    run([openssl, "req", "-new", "-key", str(server_key), "-out", str(server_csr), "-subj", f"/CN={domain}"])
    run(
        [
            openssl,
            "x509",
            "-req",
            "-in",
            str(server_csr),
            "-CA",
            str(ca_cert),
            "-CAkey",
            str(ca_key),
            "-CAcreateserial",
            "-out",
            str(server_cert),
            "-days",
            "825",
            "-sha256",
            "-extfile",
            str(ext_file),
        ]
    )
    cacert_path_file.write_text(f"{ca_cert}\n", encoding="utf-8")
    os.chmod(cacert_path_file, 0o600)
    return {
        "ok": True,
        "domain": domain,
        "ssl_dir": str(ssl_dir),
        "ca_key": str(ca_key),
        "ca_cert": str(ca_cert),
        "server_key": str(server_key),
        "server_cert": str(server_cert),
        "server_csr": str(server_csr),
        "ext_file": str(ext_file),
        "commands_run": [" ".join(parts) for parts in commands_run],
        "firefox": {
            "enterprise_roots_pref": "security.enterprise_roots.enabled",
            "policy": {"policies": {"Certificates": {"ImportEnterpriseRoots": True}}},
        },
    }


def _firefox_policy_json() -> str:
    return json.dumps(
        {"policies": {"Certificates": {"ImportEnterpriseRoots": True}}},
        indent=2,
    ) + "\n"


def _commands(*, silkpage_root: Path, deploy_root: Path, site_root: Path) -> List[str]:
    hosts_fragment = silkpage_root / "dev" / "infra" / "hosts.sindoc.local.fragment"
    vhost = silkpage_root / "dev" / "infra" / "vhosts" / "sindoc.local.conf"
    cert_script = silkpage_root / "dev" / "infra" / "ssl" / "cacert-setup.sh"
    return [
        (
            "LUTINO_SSL_DOMAINS=\"lutino.io app.lutino.io cdn.lutino.io sindoc.local\" "
            f"LUTINO_SSL_SKIP_MISSING=true {cert_script}"
        ),
        f"sudo sh -c 'cat {hosts_fragment} >> /etc/hosts'",
        f"sudo cp {vhost} /etc/apache2/other/",
        "sudo apachectl graceful",
        (
            "python3 -m singine.command intranet publish "
            f"--site-root {site_root} --deploy-root {deploy_root} "
            f"--silkpage-root {silkpage_root} --json"
        ),
    ]


def render_dashboard(payload: Dict[str, Any]) -> str:
    cert = payload["certificate"]
    commands = "".join(
        f"<li><code>{escape(command)}</code></li>"
        for command in payload["commands"]
    )
    status_items = "".join(
        f"<li><strong>{escape(label)}</strong>: {escape(value)}</li>"
        for label, value in [
            ("Site root", payload["site_root"]),
            ("Deploy root", payload["deploy_root"]),
            ("Silkpage root", payload["silkpage_root"]),
            ("Certificate", cert["cert_path"]),
            ("Private key", cert["key_path"]),
            ("CA certificate", cert["ca_path"]),
        ]
    )
    checks = "".join(
        f"<li>{escape(name)}: <strong>{'ready' if ok else 'missing'}</strong></li>"
        for name, ok in [
            ("Server certificate", cert["cert_exists"]),
            ("Server key", cert["key_exists"]),
            ("Local CA", cert["ca_exists"]),
        ]
    )
    firefox_advice = "".join(
        f"<li>{escape(item)}</li>" for item in cert["firefox"]["advice"]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sindoc Local Deploy</title>
  <style>
    :root {{ --bg:#f3efe7; --ink:#16222d; --muted:#5d6770; --accent:#a73f1d; --panel:#fffdfa; --line:#dfd5c4; --ok:#245f32; --warn:#8f6114; }}
    body {{ margin:0; background:linear-gradient(180deg,#fcf7ef,#efe6d8); color:var(--ink); font-family:"Iowan Old Style", Georgia, serif; }}
    main {{ max-width:1100px; margin:0 auto; padding:32px 18px 72px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(2.5rem,6vw,4.4rem); line-height:.95; }}
    p.lede {{ max-width:72ch; color:var(--muted); }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:18px; margin-top:24px; }}
    .card {{ background:var(--panel); border:1px solid var(--line); padding:18px; box-shadow:0 16px 34px rgba(0,0,0,.08); }}
    .eyebrow {{ margin:0 0 6px; color:var(--accent); text-transform:uppercase; letter-spacing:.08em; font-size:.74rem; }}
    ul {{ padding-left:20px; }}
    code, pre {{ background:#f4ebdf; padding:8px 10px; white-space:pre-wrap; word-break:break-word; }}
    .badge-ok {{ color:var(--ok); }}
    .badge-warn {{ color:var(--warn); }}
  </style>
</head>
<body>
  <main>
    <p>Silkpage-backed intranet deployment</p>
    <h1>Sindoc Local Deploy</h1>
    <p class="lede">This page shows where the generated intranet is published, which Silkpage files govern the local vhost, and what Firefox needs before it will trust the HTTPS endpoint cleanly.</p>
    <section class="grid">
      <article class="card">
        <p class="eyebrow">publish</p>
        <h2>Deployment roots</h2>
        <ul>{status_items}</ul>
      </article>
      <article class="card">
        <p class="eyebrow">tls</p>
        <h2>Certificate readiness</h2>
        <p class="{ 'badge-ok' if cert['ready'] else 'badge-warn' }">{'TLS material ready' if cert['ready'] else 'TLS material incomplete'}</p>
        <ul>{checks}</ul>
      </article>
      <article class="card">
        <p class="eyebrow">firefox</p>
        <h2>Trust path</h2>
        <ul>{firefox_advice}</ul>
        <pre>{escape(json.dumps(cert["firefox"]["policy"], indent=2))}</pre>
      </article>
      <article class="card">
        <p class="eyebrow">ops</p>
        <h2>Exact commands</h2>
        <ol>{commands}</ol>
      </article>
    </section>
  </main>
</body>
</html>
"""


def _vhost_text(*, domain: str, deploy_root: Path, ssl_dir: Path) -> str:
    return f"""# ── {domain} — Apache virtual host (local dev) ──────────────────────────────
#
# Install:
#   sudo cp dev/infra/vhosts/{domain}.conf /etc/apache2/other/
#   sudo apachectl graceful
#
# The SSL cert + key paths below are expected under {ssl_dir}
#
<VirtualHost *:80>
    ServerName {domain}

    RewriteEngine On
    RewriteRule ^ https://%{{SERVER_NAME}}%{{REQUEST_URI}} [END,NE,R=permanent]
</VirtualHost>

<VirtualHost *:443>
    ServerName {domain}

    DocumentRoot "{deploy_root}"

    <Directory "{deploy_root}">
        Options Indexes FollowSymLinks
        AllowOverride None
        Require all granted
    </Directory>

    SSLEngine on
    SSLCertificateFile "{ssl_dir / f'{domain}.crt'}"
    SSLCertificateKeyFile "{ssl_dir / f'{domain}.key'}"
    SSLCACertificateFile "{_load_cacert_path(ssl_dir)}"

    SSLProtocol all -SSLv3 -TLSv1 -TLSv1.1
    SSLCipherSuite HIGH:!aNULL:!MD5:!3DES
    SSLHonorCipherOrder on

    ErrorLog "{Path.home() / 'var/log' / f'{domain}-error.log'}"
    CustomLog "{Path.home() / 'var/log' / f'{domain}-access.log'}" combined

    Header always set Strict-Transport-Security "max-age=63072000; includeSubDomains"
    Header always set X-Content-Type-Options "nosniff"
</VirtualHost>
"""


def _hosts_fragment(domain: str) -> str:
    return f"""# ── {domain} local development ──────────────────────────────────────────────
#
# Install:
#   sudo sh -c 'cat dev/infra/hosts.sindoc.local.fragment >> /etc/hosts'
#
# ── BEGIN {domain} ───────────────────────────────────────────────────────────
127.0.0.1   {domain}
::1         {domain}
# ── END {domain} ─────────────────────────────────────────────────────────────
"""


def _write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def _copy_source(site_root: Path, deploy_root: Path) -> Dict[str, Any]:
    copied: List[str] = []
    deploy_root.mkdir(parents=True, exist_ok=True)
    for item in site_root.iterdir():
        destination = deploy_root / item.name
        if item.is_dir():
            shutil.copytree(item, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(item, destination)
        copied.append(str(destination))
    return {"target": str(deploy_root), "count": len(copied), "paths": copied}


def write_publish_bundle(
    *,
    site_root: Path,
    deploy_root: Path,
    silkpage_root: Path,
    ssl_dir: Path,
    domain: str = "sindoc.local",
    sync: bool = True,
) -> Dict[str, Any]:
    site_root = site_root.expanduser()
    deploy_root = deploy_root.expanduser()
    silkpage_root = silkpage_root.expanduser()
    ssl_dir = ssl_dir.expanduser()
    site_root.mkdir(parents=True, exist_ok=True)

    cert = certificate_status(domain=domain, ssl_dir=ssl_dir)
    commands = _commands(
        silkpage_root=silkpage_root,
        deploy_root=deploy_root,
        site_root=site_root,
    )

    publish_root = site_root / "deploy"
    publish_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": _now(),
        "domain": domain,
        "site_root": str(site_root),
        "deploy_root": str(deploy_root),
        "silkpage_root": str(silkpage_root),
        "certificate": cert,
        "commands": commands,
        "artifacts": {},
    }

    payload["artifacts"]["firefox_policy"] = _write_text(
        publish_root / "firefox-policies.json",
        _firefox_policy_json(),
    )
    payload["artifacts"]["html"] = _write_text(
        publish_root / "index.html",
        render_dashboard(payload),
    )

    vhost_path = silkpage_root / "dev" / "infra" / "vhosts" / f"{domain}.conf"
    hosts_path = silkpage_root / "dev" / "infra" / f"hosts.{domain}.fragment"
    payload["artifacts"]["vhost"] = _write_text(
        vhost_path,
        _vhost_text(domain=domain, deploy_root=deploy_root, ssl_dir=ssl_dir),
    )
    payload["artifacts"]["hosts_fragment"] = _write_text(
        hosts_path,
        _hosts_fragment(domain),
    )

    from .intranet_index import register_page

    payload["registry"] = register_page(
        site_root=site_root,
        title="Deploy",
        href="/deploy/",
        description="Silkpage publish roots, TLS readiness, Firefox trust path, and exact install commands.",
        kind="ops",
    )
    if sync:
        payload["sync"] = _copy_source(site_root=site_root, deploy_root=deploy_root)
    else:
        payload["sync"] = {"target": str(deploy_root), "count": 0, "paths": []}
    payload["artifacts"]["json"] = _write_text(
        publish_root / "deploy.json",
        json.dumps(payload, indent=2) + "\n",
    )
    if sync:
        shutil.copy2(publish_root / "deploy.json", deploy_root / "deploy" / "deploy.json")
    return payload
