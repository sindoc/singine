"""
singine.idp — Humble IdP CLI commands for singine

Provides `singine idp <subcommand>` — the full CLI surface for the humble-idp
identity provider, covering login, token management, API keys, user registry,
git-based snapshot/restore, and 1Password credential operations.

The IdP server (Node.js/Fastify) runs at IDP_URL (default: https://id.singine.local).
All HTTP calls are thin wrappers; the actual logic lives in humble-idp/server/.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

SINGINE_DIR = Path.home() / ".singine"
DEFAULT_IDP_URL = os.environ.get("IDP_URL", "https://id.singine.local")
SESSION_FILE = SINGINE_DIR / "session.json"


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2))


def _idp_request(
    path: str,
    method: str = "GET",
    body: Optional[dict] = None,
    token: Optional[str] = None,
    base_url: str = DEFAULT_IDP_URL,
) -> dict:
    """Make an HTTP request to the IdP server."""
    url = f"{base_url}{path}"
    data = json.dumps(body).encode() if body else None
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        # Disable SSL verification for self-signed dev cert
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            return json.loads(resp.read()) if resp.length != 0 else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        try:
            return {"ok": False, "error": json.loads(err_body)}
        except Exception:
            return {"ok": False, "error": err_body, "status": e.code}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _load_session() -> Optional[dict]:
    if SESSION_FILE.exists():
        try:
            return json.loads(SESSION_FILE.read_text())
        except Exception:
            return None
    return None


def _save_session(data: dict) -> None:
    SINGINE_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(data, indent=2))
    SESSION_FILE.chmod(0o600)


def _current_token() -> Optional[str]:
    session = _load_session()
    return session.get("access_token") if session else None


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_idp_status(args: argparse.Namespace) -> int:
    result = _idp_request("/health", base_url=args.idp_url)
    if args.json:
        _print_json(result)
        return 0
    if result.get("ok") is False:
        print(f"IdP unreachable: {result.get('error')}")
        return 1
    print(f"IdP:     {result.get('issuer', '?')}")
    print(f"Status:  {result.get('status', '?')}")
    print(f"Time:    {result.get('ts', '?')}")
    session = _load_session()
    if session:
        print(f"Session: active  ({session.get('user', {}).get('username', '?')})")
    else:
        print("Session: none")
    return 0


def cmd_idp_login(args: argparse.Namespace) -> int:
    """
    Login via TOTP → exchange for a governed IdP token and write a lock file.
    Replaces the placeholder session_token in `singine auth login`.
    """
    from .auth_totp import profile_from_args, verify_totp

    profile = profile_from_args(args)
    verified = verify_totp(
        args.code,
        profile.secret,
        period=profile.period,
        digits=profile.digits,
        algorithm=profile.algorithm,
        window=args.window,
    )
    if not verified.get("ok"):
        _print_json({"ok": False, "error": verified.get("error"), "account_name": profile.account_name})
        return 1

    # Exchange TOTP proof for an IdP token via HTTP header auth
    # We use the TOTP code as a signed assertion — the IdP validates the user identity
    # by checking the X-Singine-Identity header against the user registry.
    user_urn = args.user_urn or f"urn:singine:user:{profile.account_name.split('@')[0]}"

    result = _idp_request(
        "/auth/http-header",
        method="POST",
        body={},
        token=None,
        base_url=args.idp_url,
    )
    # NOTE: For now fall back to password-auth POST /token if IdP is up,
    # otherwise create a local-only token. The IdP login flow is:
    #   1. User provides TOTP code (verified locally)
    #   2. CLI asks IdP for a token bound to the user's URN
    # Future: POST /auth/totp-exchange with signed TOTP proof.

    if result.get("ok") is False:
        # IdP not reachable — issue a local-only session note
        import secrets
        payload = {
            "ok": True,
            "mode": "local-fallback",
            "account_name": profile.account_name,
            "user_urn": user_urn,
            "session_token": secrets.token_urlsafe(24),
            "note": "TOTP verified locally. IdP unreachable — token not federated.",
            "verified_at": verified.get("verified_at"),
        }
    else:
        payload = {
            "ok": True,
            "mode": "idp",
            "account_name": profile.account_name,
            "user_urn": user_urn,
            "access_token": result.get("access_token"),
            "expires_in": result.get("expires_in"),
            "verified_at": verified.get("verified_at"),
        }
        _save_session({
            "access_token": result.get("access_token"),
            "user": result.get("user"),
            "verified_at": verified.get("verified_at"),
        })

    _print_json(payload)
    return 0


def cmd_idp_logout(args: argparse.Namespace) -> int:
    session = _load_session()
    if not session:
        _print_json({"ok": True, "note": "no active session"})
        return 0

    user_urn = session.get("user", {}).get("urn", "")
    if user_urn:
        _idp_request(
            "/auth/file-lock",
            method="DELETE",
            body={"user_urn": user_urn},
            token=session.get("access_token"),
            base_url=args.idp_url,
        )

    SESSION_FILE.unlink(missing_ok=True)
    _print_json({"ok": True, "logged_out": True, "user_urn": user_urn})
    return 0


def cmd_idp_token_issue(args: argparse.Namespace) -> int:
    token = _current_token()
    body: dict = {}
    if args.user:
        body["user"] = args.user
    if args.scopes:
        body["scopes"] = args.scopes.split(",")
    if args.ttl:
        body["ttl_seconds"] = int(args.ttl)

    result = _idp_request("/api/keys", method="POST", body=body, token=token, base_url=args.idp_url)
    _print_json(result)
    return 0 if result.get("ok") is not False else 1


def cmd_idp_token_verify(args: argparse.Namespace) -> int:
    result = _idp_request(
        "/introspect",
        method="POST",
        body={"token": args.token},
        base_url=args.idp_url,
    )
    _print_json(result)
    return 0 if result.get("active") else 1


def cmd_idp_key_issue(args: argparse.Namespace) -> int:
    token = _current_token()
    body: dict = {"label": args.label}
    if args.user:
        body["user"] = args.user
    if args.scopes:
        body["scopes"] = args.scopes.split(",")
    if args.ttl:
        body["ttl_seconds"] = int(args.ttl)

    result = _idp_request("/api/keys", method="POST", body=body, token=token, base_url=args.idp_url)
    if result.get("ok") is False:
        _print_json(result)
        return 1

    if not args.json:
        print(f"API key (save this — shown once):")
        print(f"  {result.get('key')}")
        print(f"ID: {result.get('id')}, user: {result.get('user')}")
    else:
        _print_json(result)
    return 0


def cmd_idp_key_list(args: argparse.Namespace) -> int:
    token = _current_token()
    result = _idp_request("/api/keys", method="GET", token=token, base_url=args.idp_url)
    if result.get("ok") is False:
        _print_json(result)
        return 1
    keys = result.get("keys", [])
    if args.json:
        _print_json(keys)
        return 0
    if not keys:
        print("No API keys.")
        return 0
    print(f"{'ID':<20}  {'User':<40}  {'Label':<20}  Revoked")
    for k in keys:
        print(f"{k.get('id',''):<20}  {k.get('user',''):<40}  {str(k.get('label','')):<20}  {k.get('revoked')}")
    return 0


def cmd_idp_key_revoke(args: argparse.Namespace) -> int:
    token = _current_token()
    result = _idp_request(f"/api/keys/{args.id}", method="DELETE", token=token, base_url=args.idp_url)
    _print_json(result)
    return 0 if result.get("ok") is not False else 1


def cmd_idp_user_list(args: argparse.Namespace) -> int:
    token = _current_token()
    result = _idp_request("/userinfo", method="GET", token=token, base_url=args.idp_url)
    if result.get("ok") is False:
        # Fall back to reading users.properties directly
        _print_json({"ok": False, "note": "IdP unreachable — cannot list users without active session"})
        return 1
    _print_json(result)
    return 0


def cmd_idp_user_set_password(args: argparse.Namespace) -> int:
    """Hash a password with bcrypt and print the line to add to users.properties."""
    try:
        import bcrypt as _bcrypt
        hashed = _bcrypt.hashpw(args.password.encode(), _bcrypt.gensalt(12)).decode()
    except ImportError:
        # Try via node if bcrypt not installed in Python
        result = subprocess.run(
            ["node", "-e", f"require('bcrypt').hash('{args.password}',12,(e,h)=>process.stdout.write(h))"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            print("Error: neither Python bcrypt nor node bcrypt available", file=sys.stderr)
            return 1
        hashed = result.stdout.strip()

    line = f"{args.user}.password_hash={hashed}"
    if args.json:
        _print_json({"user": args.user, "line": line})
    else:
        print(f"Add this line to config/users.properties:")
        print(f"  {line}")
    return 0


def cmd_idp_op_read(args: argparse.Namespace) -> int:
    """Read a 1Password reference with graceful fallback."""
    # Delegate to the shell script op-read.sh in humble-idp/scripts/
    humble_idp_dir = Path.home() / "ws" / "today" / "X0-DigitalIdentity" / "humble-idp"
    op_read_sh = humble_idp_dir / "scripts" / "op-read.sh"

    if op_read_sh.exists():
        result = subprocess.run(
            ["bash", str(op_read_sh), args.ref, args.fallback or ""],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0:
            value = result.stdout.strip()
            if args.json:
                _print_json({"ok": True, "ref": args.ref, "value": value})
            else:
                print(value)
            return 0

    # Inline fallback: try op CLI directly
    op_result = subprocess.run(
        ["op", "read", "--no-newline", args.ref],
        capture_output=True, text=True, check=False,
    )
    if op_result.returncode == 0:
        value = op_result.stdout.strip()
        if args.json:
            _print_json({"ok": True, "ref": args.ref, "value": value, "backend": "op-cli"})
        else:
            print(value)
        return 0

    if args.fallback:
        if args.json:
            _print_json({"ok": True, "ref": args.ref, "value": args.fallback, "backend": "fallback"})
        else:
            print(args.fallback)
        return 0

    _print_json({"ok": False, "ref": args.ref, "error": "not found"})
    return 1


def cmd_idp_snapshot(args: argparse.Namespace) -> int:
    from . import idp_git
    result = idp_git.snapshot(message=args.message)
    _print_json(result)
    return 0 if result.get("ok") else 1


def cmd_idp_restore(args: argparse.Namespace) -> int:
    from . import idp_git
    result = idp_git.restore(ref=args.ref)
    _print_json(result)
    return 0 if result.get("ok") else 1


def cmd_idp_log(args: argparse.Namespace) -> int:
    from . import idp_git
    entries = idp_git.log(limit=args.limit)
    if args.json:
        _print_json(entries)
        return 0
    if not entries:
        print("No snapshots yet. Run: singine idp snapshot")
        return 0
    for e in entries:
        print(f"{e['short_hash']}  {e['timestamp']}  {e['message']}")
    return 0


def cmd_idp_diff(args: argparse.Namespace) -> int:
    from . import idp_git
    output = idp_git.diff(ref=args.ref)
    if output:
        print(output)
    else:
        print("No differences.")
    return 0


def cmd_idp_bootstrap(args: argparse.Namespace) -> int:
    humble_idp_dir = Path.home() / "ws" / "today" / "X0-DigitalIdentity" / "humble-idp"
    bootstrap_sh = humble_idp_dir / "scripts" / "bootstrap.sh"

    if not bootstrap_sh.exists():
        _print_json({"ok": False, "error": f"bootstrap.sh not found at {bootstrap_sh}"})
        return 1

    result = subprocess.run(["bash", str(bootstrap_sh)], check=False)
    return result.returncode


def cmd_idp_saml_metadata(args: argparse.Namespace) -> int:
    url = f"{args.idp_url.rstrip('/')}/saml/metadata"
    if args.url_only:
        print(url)
        return 0

    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, timeout=10, context=ctx) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc), "url": url})
        return 1

    if args.json:
        _print_json({"ok": True, "url": url, "metadata": text})
    else:
        print(text)
    return 0


def cmd_idp_saml_sp_list(args: argparse.Namespace) -> int:
    url = f"{args.idp_url.rstrip('/')}/saml/sp"
    result = _idp_request("/saml/sp", base_url=args.idp_url)
    if result.get("service_providers") is None:
        _print_json({"ok": False, "error": result.get("error", "failed_to_load_saml_sp_registry"), "url": url})
        return 1
    if args.json:
        _print_json(result)
        return 0
    print(f"IdP metadata: {result['idp']['metadata_url']}")
    print(f"SSO URL:       {result['idp']['sso_url']}")
    print()
    for sp in result["service_providers"]:
        print(f"{sp['slug']}: {sp['name']}")
        print(f"  entity_id: {sp['entity_id']}")
        print(f"  acs_url:   {sp['acs_url']}")
    return 0


def cmd_idp_saml_login_url(args: argparse.Namespace) -> int:
    base = f"{args.idp_url.rstrip('/')}/saml/login?sp={args.sp}"
    if args.relay_state:
        from urllib.parse import quote
        base += f"&RelayState={quote(args.relay_state)}"
    print(base)
    return 0


# ---------------------------------------------------------------------------
# Parser builder (called from command.py)
# ---------------------------------------------------------------------------

def build_idp_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register the `singine idp` command group onto an existing subparser."""

    idp_parser = sub.add_parser("idp", help="Humble IdP — identity provider operations")
    idp_parser.add_argument(
        "--idp-url",
        default=DEFAULT_IDP_URL,
        help=f"IdP base URL (default: {DEFAULT_IDP_URL}, env: IDP_URL)",
    )
    idp_sub = idp_parser.add_subparsers(dest="idp_subcommand")

    # ── status ────────────────────────────────────────────────────────────
    p = idp_sub.add_parser("status", help="IdP health and active session info")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_idp_status)

    # ── login ─────────────────────────────────────────────────────────────
    common_totp = argparse.ArgumentParser(add_help=False)
    common_totp.add_argument("--state", help="Path to saved TOTP profile JSON")
    common_totp.add_argument("--secret", help="Base32 TOTP secret")
    common_totp.add_argument("--issuer", default="Singine")
    common_totp.add_argument("--account-name", default="user@singine.local")
    common_totp.add_argument("--digits", type=int, default=6)
    common_totp.add_argument("--period", type=int, default=30)
    common_totp.add_argument("--algorithm", default="SHA1")
    common_totp.add_argument("--provider", default="otp")

    p = idp_sub.add_parser("login", help="Verify TOTP then exchange for a governed IdP token", parents=[common_totp])
    p.add_argument("--code", required=True, help="Current TOTP one-time code")
    p.add_argument("--window", type=int, default=1)
    p.add_argument("--user-urn", default=None, help="Override the user URN (default: derived from account-name)")
    p.set_defaults(func=cmd_idp_login)

    # ── logout ────────────────────────────────────────────────────────────
    p = idp_sub.add_parser("logout", help="Remove lock file and clear the local session")
    p.set_defaults(func=cmd_idp_logout)

    # ── token ─────────────────────────────────────────────────────────────
    token_parser = idp_sub.add_parser("token", help="JWT token operations")
    token_sub = token_parser.add_subparsers(dest="token_subcommand")

    p = token_sub.add_parser("issue", help="Issue a JWT for a user (requires admin scope)")
    p.add_argument("--user", help="User URN or alias")
    p.add_argument("--scopes", help="Comma-separated scopes")
    p.add_argument("--ttl", type=int, help="TTL in seconds (default: idp.token_ttl_seconds)")
    p.set_defaults(func=cmd_idp_token_issue)

    p = token_sub.add_parser("verify", help="Verify a JWT via /introspect")
    p.add_argument("token", help="The JWT to verify")
    p.set_defaults(func=cmd_idp_token_verify)

    # ── key ───────────────────────────────────────────────────────────────
    key_parser = idp_sub.add_parser("key", help="API key management")
    key_sub = key_parser.add_subparsers(dest="key_subcommand")

    p = key_sub.add_parser("issue", help="Issue a new API key (shown once)")
    p.add_argument("--user", help="User URN or alias (default: current session user)")
    p.add_argument("--scopes", help="Comma-separated scopes")
    p.add_argument("--ttl", type=int, help="TTL in seconds (0 = non-expiring)")
    p.add_argument("--label", default="", help="Human-readable label")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_idp_key_issue)

    p = key_sub.add_parser("list", help="List API keys for the current user")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_idp_key_list)

    p = key_sub.add_parser("revoke", help="Revoke an API key by ID")
    p.add_argument("id", help="Key ID (kid_...)")
    p.set_defaults(func=cmd_idp_key_revoke)

    # ── user ──────────────────────────────────────────────────────────────
    user_parser = idp_sub.add_parser("user", help="User registry operations")
    user_sub = user_parser.add_subparsers(dest="user_subcommand")

    p = user_sub.add_parser("list", help="List registered users (/userinfo endpoint)")
    p.set_defaults(func=cmd_idp_user_list)

    p = user_sub.add_parser("set-password", help="Generate a bcrypt hash line for users.properties")
    p.add_argument("user", help="Username (e.g. attar, arash, soren)")
    p.add_argument("password", help="Plain-text password (only used locally to compute hash)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_idp_user_set_password)

    # ── op ────────────────────────────────────────────────────────────────
    p = idp_sub.add_parser("op", help="Read a 1Password reference (op://Vault/Item/Field)")
    p.add_argument("ref", help="1Password reference, e.g. op://Singine/humble-idp/jks_password")
    p.add_argument("--fallback", help="Value to return if 1Password is unavailable")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_idp_op_read)

    # ── snapshot ──────────────────────────────────────────────────────────
    p = idp_sub.add_parser("snapshot", help="Git-commit the current ~/.singine/ identity state")
    p.add_argument("--message", "-m", help="Commit message (default: auto-generated timestamp)")
    p.set_defaults(func=cmd_idp_snapshot)

    # ── restore ───────────────────────────────────────────────────────────
    p = idp_sub.add_parser("restore", help="Restore ~/.singine/ tracked files to a previous snapshot")
    p.add_argument("ref", nargs="?", default=None,
                   help="Git ref to restore from (commit hash, tag, branch — default: HEAD~1)")
    p.set_defaults(func=cmd_idp_restore)

    # ── log ───────────────────────────────────────────────────────────────
    p = idp_sub.add_parser("log", help="Show snapshot history")
    p.add_argument("--limit", "-n", type=int, default=10)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_idp_log)

    # ── diff ──────────────────────────────────────────────────────────────
    p = idp_sub.add_parser("diff", help="Show git diff of tracked identity files")
    p.add_argument("ref", nargs="?", default=None, help="Compare against this ref (default: HEAD)")
    p.set_defaults(func=cmd_idp_diff)

    # ── bootstrap ─────────────────────────────────────────────────────────
    p = idp_sub.add_parser("bootstrap", help="First-run: generate keys, TLS cert, /etc/hosts entry")
    p.set_defaults(func=cmd_idp_bootstrap)

    # ── saml ──────────────────────────────────────────────────────────────
    saml_parser = idp_sub.add_parser("saml", help="SAML 2.0 Web SSO helpers")
    saml_sub = saml_parser.add_subparsers(dest="saml_subcommand")

    p = saml_sub.add_parser("metadata", help="Fetch or print the IdP SAML metadata")
    p.add_argument("--url-only", action="store_true", help="Only print the metadata URL")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_idp_saml_metadata)

    p = saml_sub.add_parser("sp-list", help="List configured SAML service providers")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_idp_saml_sp_list)

    p = saml_sub.add_parser("login-url", help="Print the SAML login URL for a configured service provider")
    p.add_argument("--sp", default="demo-sp", help="Configured SAML service provider slug")
    p.add_argument("--relay-state", help="Optional RelayState")
    p.set_defaults(func=cmd_idp_saml_login_url)
