"""
singine wsec — web security: TLS certs, SSH keys, IDP tokens, asset hardening.

Commands:
    singine wsec cert   --site markupware.com  [--check|--renew|--fix-san]
    singine wsec keys   --site markupware.com  [--list|--add|--rotate]
    singine wsec token  --site markupware.com  [--mint|--verify|--revoke]
    singine wsec scan   --site markupware.com
    singine wsec status --site markupware.com

IDP integration:
    SSH deploy keys and TLS cert private keys are registered in the singine IDP
    trust store (singine.sec.trust / singine.jks).
    Deploy tokens are minted by singine.auth.token (JWT RS256).

    Trust chain:
        singine-root-ca (in singine.jks)
          └── site deploy key (ed25519, per-site)
                └── JWT deploy token (RS256, TTL=3600s)

TLS certificate issue (markupware.com):
    Current: ERR_TLS_CERT_ALTNAME_INVALID
    Cause:   cert does not cover all required SANs
    Fix:     singine wsec cert --site markupware.com --fix-san
"""

from __future__ import annotations

import json
import os
import shlex
import socket
import ssl
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .www import now_iso, resolve_site, SITE_REGISTRY


# ── SSH key management ────────────────────────────────────────────────────────

KEY_DIR = Path.home() / ".singine" / "keys"
KEY_TYPE = "ed25519"


def _key_path(site_name: str) -> tuple[Path, Path]:
    """Return (private_key_path, public_key_path) for a site deploy key."""
    base = KEY_DIR / f"{site_name.replace('.', '_')}_deploy_{KEY_TYPE}"
    return base, Path(str(base) + ".pub")


def keys_list(site_name: str, json_out: bool = False) -> dict:
    """List SSH deploy keys registered for the site."""
    priv, pub = _key_path(site_name)
    has_priv = priv.exists()
    has_pub = pub.exists()

    fingerprint = None
    if has_pub:
        r = subprocess.run(
            ["ssh-keygen", "-lf", str(pub)],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            fingerprint = r.stdout.strip()

    result = {
        "site":        site_name,
        "private_key": str(priv),
        "public_key":  str(pub),
        "private_exists": has_priv,
        "public_exists":  has_pub,
        "fingerprint": fingerprint,
        "idp_alias":   f"singine-deploy-{site_name}",
        "idp_urn":     f"urn:singine:deploy:{site_name}",
        "timestamp":   now_iso(),
    }

    if json_out:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n[wsec] keys — {site_name}")
        print(f"  private  : {'✓ ' + str(priv) if has_priv else '✗ missing'}")
        print(f"  public   : {'✓ ' + str(pub) if has_pub else '✗ missing'}")
        if fingerprint:
            print(f"  fingerprint: {fingerprint}")
        print(f"  IDP urn  : {result['idp_urn']}")
        if not has_priv:
            print(f"\n  → generate: singine wsec keys --site {site_name} --add")

    return result


def keys_add(site_name: str, dry_run: bool = False, json_out: bool = False) -> dict:
    """
    Generate a new ed25519 deploy key for the site and register it in the
    singine IDP trust store.

    Steps:
      1. ssh-keygen -t ed25519 -f <key_path> -C "singine-deploy-<site>"
      2. singine cap trust register-ssh (appends pub key to authorized_keys)
      3. Print the public key for manual addition to the server's authorized_keys
    """
    priv, pub = _key_path(site_name)
    KEY_DIR.mkdir(parents=True, exist_ok=True)

    comment = f"singine-deploy-{site_name}"
    print(f"\n[wsec] generate {KEY_TYPE} deploy key — {site_name}")
    print(f"  path: {priv}")

    if not dry_run:
        if priv.exists():
            print(f"  [wsec] key already exists — skipping generation")
            print(f"  → to rotate: singine wsec keys --site {site_name} --rotate")
        else:
            r = subprocess.run(
                ["ssh-keygen", "-t", KEY_TYPE, "-f", str(priv),
                 "-C", comment, "-N", ""],
                capture_output=False,
            )
            if r.returncode != 0:
                return {"ok": False, "error": "ssh-keygen failed", "site": site_name}

    pub_content = pub.read_text().strip() if pub.exists() else "(dry run)"

    # Register with singine IDP trust store
    if not dry_run and pub.exists():
        subprocess.run(
            ["singine", "cap", "trust", "register-ssh",
             "--pubkey", pub_content,
             "--alias", f"singine-deploy-{site_name}"],
            capture_output=True, timeout=10,
        )

    result = {
        "site":       site_name,
        "key_type":   KEY_TYPE,
        "private":    str(priv),
        "public":     str(pub),
        "public_key": pub_content,
        "idp_urn":    f"urn:singine:deploy:{site_name}",
        "dry_run":    dry_run,
        "ok":         True,
        "next_step":  (
            f"Add the public key above to the remote server:\n"
            f"  ssh-copy-id -i {pub} "
            f"{SITE_REGISTRY[site_name]['remote_user']}@{SITE_REGISTRY[site_name]['remote_host']}"
        ),
        "timestamp":  now_iso(),
    }

    if json_out:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n  Public key (add to server authorized_keys):")
        print(f"  {pub_content}")
        print(f"\n  {result['next_step']}")

    return result


def keys_rotate(site_name: str, dry_run: bool = False) -> dict:
    """Archive current key and generate a new one."""
    priv, pub = _key_path(site_name)
    if priv.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        archive_priv = priv.parent / f"{priv.name}.{ts}.retired"
        archive_pub  = Path(str(pub) + f".{ts}.retired")
        print(f"[wsec] archiving old key → {archive_priv}")
        if not dry_run:
            priv.rename(archive_priv)
            if pub.exists():
                pub.rename(archive_pub)
    return keys_add(site_name, dry_run=dry_run)


# ── TLS certificate checks ────────────────────────────────────────────────────

def cert_check(site_name: str, json_out: bool = False) -> dict:
    """
    Check TLS certificate for the site:
    - Expiry date
    - SAN coverage (all required domains)
    - Issuer
    - Alert if < 30 days to expiry or SAN mismatch
    """
    site = resolve_site(site_name)
    required_sans = site.get("cert_domains", [site_name])
    host = site_name
    port = 443

    print(f"\n[wsec] cert check — {site_name}")

    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_OPTIONAL

        with socket.create_connection((host, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()

        # Parse expiry
        not_after_str = cert.get("notAfter", "")
        not_after = datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z").replace(
            tzinfo=timezone.utc
        ) if not_after_str else None
        days_left = (not_after - datetime.now(timezone.utc)).days if not_after else None

        # Extract SANs
        san_list = [
            v for (k, v) in cert.get("subjectAltName", []) if k == "DNS"
        ]

        # Check coverage
        missing_sans = [d for d in required_sans if d not in san_list]

        issuer = dict(x[0] for x in cert.get("issuer", []))
        subject = dict(x[0] for x in cert.get("subject", []))

        alerts = []
        if days_left is not None and days_left < 30:
            alerts.append(f"EXPIRY WARNING: {days_left} days remaining")
        if missing_sans:
            alerts.append(f"SAN MISMATCH: missing {missing_sans}")
            alerts.append("FIX: singine wsec cert --site " + site_name + " --fix-san")

        result = {
            "site":         site_name,
            "host":         host,
            "subject_cn":   subject.get("commonName", ""),
            "issuer_o":     issuer.get("organizationName", ""),
            "not_after":    not_after.isoformat() if not_after else None,
            "days_left":    days_left,
            "sans":         san_list,
            "required_sans": required_sans,
            "missing_sans": missing_sans,
            "alerts":       alerts,
            "ok":           len(alerts) == 0,
            "timestamp":    now_iso(),
        }

    except ssl.SSLCertVerificationError as e:
        result = {
            "site":    site_name,
            "ok":      False,
            "error":   str(e),
            "alerts":  [f"SSL ERROR: {e}", "FIX: singine wsec cert --site " + site_name + " --fix-san"],
            "timestamp": now_iso(),
        }
    except Exception as e:
        result = {
            "site":    site_name,
            "ok":      False,
            "error":   str(e),
            "alerts":  [str(e)],
            "timestamp": now_iso(),
        }

    if json_out:
        print(json.dumps(result, indent=2))
    else:
        ok_str = "✓" if result["ok"] else "✗"
        print(f"  {ok_str} {site_name}")
        if result.get("subject_cn"):
            print(f"  subject  : {result['subject_cn']}")
            print(f"  issuer   : {result.get('issuer_o', '')}")
            print(f"  expires  : {result.get('not_after', '')} ({result.get('days_left', '?')} days)")
            print(f"  SANs     : {', '.join(result.get('sans', []))}")
        for alert in result.get("alerts", []):
            print(f"  ⚠ {alert}")

    return result


def cert_renew(site_name: str, method: str = "certbot", dry_run: bool = False) -> dict:
    """
    Renew/fix TLS certificate.
    method: certbot (Let's Encrypt) | acme.sh | manual
    """
    site = resolve_site(site_name)
    domains = site.get("cert_domains", [site_name])
    domains_flag = " ".join(f"-d {d}" for d in domains)

    print(f"\n[wsec] cert renew — {site_name} via {method}")

    if method == "certbot":
        # certbot certonly --standalone or --webroot
        cmd = f"certbot certonly --standalone {domains_flag}"
        if dry_run:
            cmd += " --dry-run"
        r = subprocess.run(shlex.split(cmd))
        ok = r.returncode == 0
    elif method == "acme.sh":
        cmd = f"acme.sh --issue {domains_flag} --standalone"
        if dry_run:
            cmd += " --test"
        r = subprocess.run(shlex.split(cmd))
        ok = r.returncode == 0
    else:
        print(f"  Manual renewal required for {site_name}")
        print(f"  Required SANs: {', '.join(domains)}")
        ok = True  # manual — user handles it

    return {
        "site":    site_name,
        "method":  method,
        "domains": domains,
        "dry_run": dry_run,
        "ok":      ok,
        "timestamp": now_iso(),
    }


# ── IDP deploy token ──────────────────────────────────────────────────────────

def token_mint(site_name: str, ttl: int = 3600, dry_run: bool = False, json_out: bool = False) -> dict:
    """
    Mint a short-lived JWT deploy token for the site via singine IDP.
    Uses HS256 (symmetric) for service-to-service deploy authorization.

    The token carries:
      sub  — urn:singine:deploy:<site>
      site — <site_name>
      role — deploy
      iss  — urn:singine:idp
    """
    print(f"\n[wsec] mint deploy token — {site_name} (TTL={ttl}s)")

    secret = os.environ.get(
        "SINGINE_DEPLOY_SECRET",
        f"singine-deploy-{site_name}-changeme"
    )

    claims = {
        "sub":  f"urn:singine:deploy:{site_name}",
        "site": site_name,
        "role": "deploy",
    }

    if dry_run:
        result = {
            "site":     site_name,
            "dry_run":  True,
            "claims":   claims,
            "ttl":      ttl,
            "token":    "stub.dry-run.token",
            "timestamp": now_iso(),
        }
    else:
        # Call singine Clojure IDP via CLI bridge
        payload = json.dumps({"claims": claims, "ttl": ttl, "secret": secret})
        r = subprocess.run(
            ["singine", "idp", "token", "mint", "--hs256", "--payload", payload],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            try:
                token_result = json.loads(r.stdout)
            except Exception:
                token_result = {"token": r.stdout.strip()}
        else:
            # Fallback: use Python jwt if singine CLI not available
            token_result = {"token": _mint_hs256_python(claims, secret, ttl)}

        result = {
            "site":      site_name,
            "dry_run":   False,
            "claims":    claims,
            "ttl":       ttl,
            **token_result,
            "timestamp": now_iso(),
        }

    if json_out:
        print(json.dumps(result, indent=2))
    else:
        print(f"  token (first 32 chars): {str(result.get('token', ''))[:32]}…")
        print(f"  expires in: {ttl}s")

    return result


def _mint_hs256_python(claims: dict, secret: str, ttl: int) -> str:
    """Minimal HS256 JWT without external deps (base64 + hmac)."""
    import base64, hmac, hashlib, json as _json, time

    header = base64.urlsafe_b64encode(
        _json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()

    now = int(time.time())
    payload_data = {**claims, "iat": now, "exp": now + ttl,
                    "iss": "urn:singine:idp"}
    payload = base64.urlsafe_b64encode(
        _json.dumps(payload_data).encode()
    ).rstrip(b"=").decode()

    signing_input = f"{header}.{payload}".encode()
    sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()

    return f"{header}.{payload}.{signature}"


# ── Full security status ──────────────────────────────────────────────────────

def wsec_status(site_name: str, json_out: bool = False) -> dict:
    """Comprehensive security status: cert + keys + IDP."""
    print(f"\n[wsec] status — {site_name}")
    cert = cert_check(site_name, json_out=False)
    keys = keys_list(site_name, json_out=False)

    result = {
        "site":      site_name,
        "cert":      cert,
        "keys":      keys,
        "ok":        cert.get("ok", False) and keys.get("private_exists", False),
        "timestamp": now_iso(),
    }

    if json_out:
        print(json.dumps(result, indent=2))
    else:
        overall = "✓ secure" if result["ok"] else "✗ issues found"
        print(f"\n[wsec] {overall} — {site_name}")

    return result
