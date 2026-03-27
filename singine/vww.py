"""
singine vww — validate/verify www: security scanning, asset integrity, audit.

Commands:
    singine vww cert   --site markupware.com        (TLS cert check — delegates to wsec)
    singine vww scan   --site markupware.com         (HTTP headers, HTTPS redirect, CSP)
    singine vww audit  --site markupware.com         (full security + integrity report)
    singine vww check  --site markupware.com [--all] (quick health check)
    singine vww assets --site markupware.com         (list all tracked web assets)

vww = validate www
Purpose: read-only inspection counterpart to www (deploy) and wsec (key/cert ops).
"""

from __future__ import annotations

import json
import socket
import ssl
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .www import now_iso, resolve_site, SITE_REGISTRY
from .wsec import cert_check


# ── HTTP header checks ────────────────────────────────────────────────────────

SECURITY_HEADERS = [
    "Strict-Transport-Security",
    "Content-Security-Policy",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
    "Permissions-Policy",
]


def scan(site_name: str, json_out: bool = False) -> dict:
    """
    HTTP security scan:
    - HTTPS redirect (HTTP → HTTPS)
    - Security response headers present/missing
    - Server header exposure
    - Basic HTTP status
    """
    site = resolve_site(site_name)
    host = site_name
    results: dict = {"site": site_name, "checks": {}, "alerts": [], "timestamp": now_iso()}

    print(f"\n[vww] scan — {site_name}")

    # 1. HTTP → HTTPS redirect
    try:
        req = urllib.request.Request(
            f"http://{host}",
            headers={"User-Agent": "singine-vww/1.0"},
            method="HEAD",
        )
        # Don't follow redirects — we want to see the redirect itself
        opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
        resp = opener.open(req, timeout=10)
        final_url = resp.geturl()
        https_redirect = final_url.startswith("https://")
        results["checks"]["https_redirect"] = {
            "ok": https_redirect,
            "final_url": final_url,
        }
        if not https_redirect:
            results["alerts"].append("HTTP does not redirect to HTTPS")
    except Exception as e:
        results["checks"]["https_redirect"] = {"ok": False, "error": str(e)}
        results["alerts"].append(f"HTTP check failed: {e}")

    # 2. HTTPS response headers
    try:
        req = urllib.request.Request(
            f"https://{host}",
            headers={"User-Agent": "singine-vww/1.0"},
            method="HEAD",
        )
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_OPTIONAL
        resp = urllib.request.urlopen(req, context=ctx, timeout=10)
        headers = dict(resp.headers)

        present = []
        missing = []
        for h in SECURITY_HEADERS:
            if any(k.lower() == h.lower() for k in headers):
                present.append(h)
            else:
                missing.append(h)
                results["alerts"].append(f"Missing security header: {h}")

        server_header = headers.get("Server", headers.get("server", ""))
        if server_header:
            results["alerts"].append(f"Server header exposed: {server_header}")

        results["checks"]["security_headers"] = {
            "present": present,
            "missing": missing,
            "server_exposed": bool(server_header),
            "status": resp.status,
        }

    except ssl.SSLError as e:
        results["checks"]["security_headers"] = {"ok": False, "ssl_error": str(e)}
        results["alerts"].append(f"TLS error: {e}")
    except Exception as e:
        results["checks"]["security_headers"] = {"ok": False, "error": str(e)}
        results["alerts"].append(f"HTTPS check failed: {e}")

    results["ok"] = len(results["alerts"]) == 0

    if json_out:
        print(json.dumps(results, indent=2))
    else:
        ok_sym = "✓" if results["ok"] else "✗"
        print(f"  {ok_sym} {site_name}")
        for check, detail in results["checks"].items():
            c_ok = detail.get("ok", True)
            sym = "✓" if c_ok else "✗"
            print(f"  {sym} {check}")
        for alert in results["alerts"]:
            print(f"  ⚠ {alert}")

    return results


# ── Asset inventory ───────────────────────────────────────────────────────────

def assets(site_name: str, json_out: bool = False) -> dict:
    """List all tracked web assets (HTML, CSS, JS, images) in the local build."""
    site = resolve_site(site_name)

    from .wingine import WINGINE_BACKENDS
    backend = WINGINE_BACKENDS.get(site_name, {})
    output_dir = Path(backend.get("output_dir", site.get("local_html", "")))

    asset_list = []
    if output_dir.exists():
        for f in sorted(output_dir.rglob("*")):
            if f.is_file():
                suffix = f.suffix.lower()
                asset_type = {
                    ".html": "html", ".htm": "html",
                    ".css": "css", ".js": "js",
                    ".png": "image", ".jpg": "image", ".jpeg": "image",
                    ".gif": "image", ".svg": "image", ".ico": "image",
                    ".xml": "xml", ".rdf": "rdf", ".json": "json",
                    ".pdf": "pdf", ".woff": "font", ".woff2": "font",
                }.get(suffix, "other")
                asset_list.append({
                    "path": str(f.relative_to(output_dir)),
                    "type": asset_type,
                    "size": f.stat().st_size,
                })

    by_type: dict = {}
    for a in asset_list:
        by_type.setdefault(a["type"], 0)
        by_type[a["type"]] += 1

    result = {
        "site":       site_name,
        "output_dir": str(output_dir),
        "total":      len(asset_list),
        "by_type":    by_type,
        "assets":     asset_list,
        "timestamp":  now_iso(),
    }

    if json_out:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n[vww] assets — {site_name}")
        print(f"  output  : {output_dir}")
        print(f"  total   : {len(asset_list)} files")
        for t, n in sorted(by_type.items()):
            print(f"  {t:8s}: {n}")

    return result


# ── Quick health check ────────────────────────────────────────────────────────

def check(site_name: str, full: bool = False, json_out: bool = False) -> dict:
    """
    Quick health check combining cert, scan, and asset inventory.
    --all / full=True runs all checks.
    """
    print(f"\n[vww] check — {site_name}")

    cert = cert_check(site_name, json_out=False)
    results = {"site": site_name, "cert": cert, "timestamp": now_iso()}

    if full:
        scan_result = scan(site_name, json_out=False)
        asset_result = assets(site_name, json_out=False)
        results["scan"] = scan_result
        results["assets"] = asset_result
        results["ok"] = cert.get("ok", False) and scan_result.get("ok", False)
    else:
        results["ok"] = cert.get("ok", False)

    if json_out:
        print(json.dumps(results, indent=2))
    else:
        overall = "✓ healthy" if results["ok"] else "✗ issues found"
        print(f"\n[vww] {overall} — {site_name}")

    return results


# ── Audit report ──────────────────────────────────────────────────────────────

def audit(site_name: str, json_out: bool = False) -> dict:
    """Full audit: cert + scan + assets + git log + wsec keys."""
    from .wsec import keys_list
    from .www import resolve_site

    print(f"\n[vww] audit — {site_name} — {now_iso()}")

    cert   = cert_check(site_name, json_out=False)
    scan_r = scan(site_name, json_out=False)
    asset_r = assets(site_name, json_out=False)
    keys_r  = keys_list(site_name, json_out=False)

    site = resolve_site(site_name)
    git_r = subprocess.run(
        ["git", "-C", str(site["local_src"]), "log", "--oneline", "-10"],
        capture_output=True, text=True,
    )

    all_alerts = (
        cert.get("alerts", []) +
        scan_r.get("alerts", [])
    )

    result = {
        "site":       site_name,
        "cert":       cert,
        "scan":       scan_r,
        "assets":     {k: v for k, v in asset_r.items() if k != "assets"},
        "keys":       keys_r,
        "git_recent": git_r.stdout.strip() if git_r.returncode == 0 else "",
        "alerts":     all_alerts,
        "ok":         len(all_alerts) == 0,
        "timestamp":  now_iso(),
    }

    if json_out:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n[vww] audit complete — {len(all_alerts)} alert(s)")
        for alert in all_alerts:
            print(f"  ⚠ {alert}")
        if not all_alerts:
            print(f"  ✓ no issues found")

    return result
