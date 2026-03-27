"""singine lutino — Lutino.io application lifecycle and test commands.

Provides:
  singine lutino test login --social   Test social OAuth login endpoint connectivity
  singine lutino test gh               Run GitHub JUnit tests (GitHubRequestWrapperTest + social)
  singine lutino test apple            Run Apple JUnit tests  (AppleRequestWrapperTest + social)
  singine lutino test all              Run all social login JUnit tests
  singine lutino status                Check if Lutino is running locally
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List


# ── Constants ─────────────────────────────────────────────────────────────────

GITHUB_AUTH_URL   = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL  = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL   = "https://api.github.com/user"
APPLE_JWKS_URL    = "https://appleid.apple.com/auth/keys"
APPLE_AUTH_URL    = "https://appleid.apple.com/auth/authorize"

DEFAULT_LUTINO_URL = "http://localhost:8080"
DEFAULT_LUTINO_DIR = os.path.expanduser("~/ws/git/lutino.io/lutino")

PROVIDERS = ["github", "apple"]

# ── JUnit test class mapping by shortname ─────────────────────────────────────

_JUNIT_CLASSES: Dict[str, List[str]] = {
    "gh": [
        "io.lutino.ui.servlet.login.GitHubRequestWrapperTest",
        "io.lutino.ui.servlet.login.SocialLoginUserLoginTest",
    ],
    "apple": [
        "io.lutino.ui.servlet.login.AppleRequestWrapperTest",
        "io.lutino.ui.servlet.login.SocialLoginUserLoginTest",
    ],
    "all": [
        "io.lutino.ui.servlet.login.GitHubRequestWrapperTest",
        "io.lutino.ui.servlet.login.AppleRequestWrapperTest",
        "io.lutino.ui.servlet.login.SocialLoginUserLoginTest",
    ],
}


# ── Command handlers ───────────────────────────────────────────────────────────

def _cmd_lutino_status(args: argparse.Namespace) -> int:
    url = getattr(args, "url", DEFAULT_LUTINO_URL).rstrip("/")
    result = _probe_url(url + "/login.jsp", label="Lutino login page")
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_probe(result)
    return 0 if result["reachable"] else 1


def _cmd_lutino_test_login_social(args: argparse.Namespace) -> int:
    """
    singine lutino test login --social [--provider github|apple|all] [--url URL] [--json]

    Tests:
      1. Lutino app is reachable (GET /login.jsp)
      2. Lutino GitHub OAuth initiation endpoint is reachable (GET /GitHubOAuthServlet)
      3. GitHub OAuth authorization URL is reachable
      4. GitHub user API is reachable
      5. Apple JWKS endpoint is reachable
      6. Apple auth URL is reachable
    """
    base_url = getattr(args, "url", DEFAULT_LUTINO_URL).rstrip("/")
    providers = _resolve_providers(args.provider)

    probes: List[Dict[str, Any]] = []

    # --- Lutino app health -----------------------------------------------
    probes.append(_probe_url(base_url + "/login.jsp",
                             label="lutino:login-page"))

    if "github" in providers:
        probes.append(_probe_url(
            base_url + "/GitHubOAuthServlet",
            label="lutino:github-oauth-init",
            expected_status=302,          # redirects to GitHub — that is correct
            accept_redirect=True,
        ))
        probes.append(_probe_url(GITHUB_AUTH_URL,
                                 label="github:authorize-url",
                                 accept_redirect=True))
        probes.append(_probe_url(GITHUB_USER_URL,
                                 label="github:user-api",
                                 expected_status=401))  # 401 without token = reachable

    if "apple" in providers:
        probes.append(_probe_url(APPLE_JWKS_URL,
                                 label="apple:jwks-endpoint"))
        probes.append(_probe_url(APPLE_AUTH_URL,
                                 label="apple:auth-url"))

    passed  = [p for p in probes if p["reachable"]]
    failed  = [p for p in probes if not p["reachable"]]
    overall = len(failed) == 0

    summary = {
        "ok":       overall,
        "base_url": base_url,
        "providers": providers,
        "passed":   len(passed),
        "failed":   len(failed),
        "probes":   probes,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        _print_summary(summary)

    return 0 if overall else 1


# ── JUnit runner ──────────────────────────────────────────────────────────────

def _cmd_lutino_test_junit(args: argparse.Namespace) -> int:
    """
    singine lutino test gh | apple | all [--dir DIR] [--json]

    Runs the Lutino social login JUnit tests via ``mvn test`` using the
    shortname-to-class mapping defined in _JUNIT_CLASSES.
    """
    shortname = args.shortname
    classes   = _JUNIT_CLASSES.get(shortname)
    if not classes:
        msg = f"Unknown shortname '{shortname}'. Choose: {', '.join(_JUNIT_CLASSES)}"
        if args.json:
            print(json.dumps({"ok": False, "error": msg}))
        else:
            print(f"error: {msg}")
        return 1

    lutino_dir = getattr(args, "dir", DEFAULT_LUTINO_DIR)
    if not os.path.isdir(lutino_dir):
        msg = f"Lutino source directory not found: {lutino_dir}"
        if args.json:
            print(json.dumps({"ok": False, "error": msg}))
        else:
            print(f"error: {msg}")
        return 1

    test_filter = ",".join(classes)
    cmd = ["mvn", "test", f"-Dtest={test_filter}", "-Dsurefire.failIfNoSpecifiedTests=false"]

    if not args.json:
        print(f"\nsingine lutino test {shortname}")
        print(f"  dir      : {lutino_dir}")
        print(f"  classes  : {len(classes)}")
        for c in classes:
            print(f"    {c.rsplit('.', 1)[-1]}")
        print()

    result = subprocess.run(cmd, cwd=lutino_dir, capture_output=True, text=True)
    stdout = result.stdout

    # Parse surefire summary line: "Tests run: N, Failures: F, Errors: E, Skipped: S"
    summary = _parse_surefire_summary(stdout)
    ok = result.returncode == 0

    if args.json:
        print(json.dumps({
            "ok":       ok,
            "shortname": shortname,
            "classes":  classes,
            "returncode": result.returncode,
            **summary,
        }, indent=2))
    else:
        overall = "PASS" if ok else "FAIL"
        print(f"  result   : [{overall}]")
        if summary:
            print(f"  run      : {summary.get('tests_run', '?')}")
            print(f"  failures : {summary.get('failures', '?')}")
            print(f"  errors   : {summary.get('errors', '?')}")
        if not ok:
            # Print the surefire failure block only
            in_failures = False
            for line in stdout.splitlines():
                if "FAILED" in line or "ERROR" in line or in_failures:
                    in_failures = True
                    print(f"  {line}")
                    if line.strip() == "":
                        in_failures = False
        print()

    return 0 if ok else 1


def _parse_surefire_summary(stdout: str) -> Dict[str, Any]:
    """Extract the aggregated surefire counters from mvn test output."""
    import re
    totals: Dict[str, int] = {"tests_run": 0, "failures": 0, "errors": 0, "skipped": 0}
    pattern = re.compile(
        r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)"
    )
    for m in pattern.finditer(stdout):
        totals["tests_run"] += int(m.group(1))
        totals["failures"]  += int(m.group(2))
        totals["errors"]    += int(m.group(3))
        totals["skipped"]   += int(m.group(4))
    return totals


# ── Probe helpers ──────────────────────────────────────────────────────────────

def _probe_url(
    url: str,
    *,
    label: str = "",
    expected_status: int = 200,
    accept_redirect: bool = False,
    timeout: int = 8,
) -> Dict[str, Any]:
    """Perform a HEAD (then GET) probe and return a structured result dict."""
    start = time.monotonic()
    result: Dict[str, Any] = {
        "label":    label or url,
        "url":      url,
        "reachable": False,
        "status":   None,
        "error":    None,
        "latency_ms": None,
    }

    # Disable automatic redirect following so we can inspect 302s
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(_NoRedirect)

    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "singine/lutino-test")
        with opener.open(req, timeout=timeout) as resp:
            status = resp.getcode()
            result["status"] = status
            if status == expected_status:
                result["reachable"] = True
            elif accept_redirect and status in (301, 302, 303, 307, 308):
                result["reachable"] = True
    except urllib.error.HTTPError as e:
        result["status"] = e.code
        if e.code == expected_status:
            result["reachable"] = True
        elif accept_redirect and e.code in (301, 302, 303, 307, 308):
            result["reachable"] = True
        else:
            result["error"] = f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        result["error"] = str(e.reason)
    except Exception as e:
        result["error"] = str(e)
    finally:
        result["latency_ms"] = round((time.monotonic() - start) * 1000)

    return result


def _resolve_providers(provider_arg: str) -> List[str]:
    if not provider_arg or provider_arg.lower() == "all":
        return list(PROVIDERS)
    p = provider_arg.lower()
    if p not in PROVIDERS:
        return list(PROVIDERS)
    return [p]


# ── Formatting ─────────────────────────────────────────────────────────────────

def _print_probe(probe: Dict[str, Any]) -> None:
    ok = "OK" if probe["reachable"] else "FAIL"
    status = probe.get("status") or "-"
    latency = probe.get("latency_ms", "-")
    error = ("  -> " + probe["error"]) if probe.get("error") else ""
    print(f"  [{ok:4s}] {probe['label']:<40s} HTTP {status} ({latency}ms){error}")


def _print_summary(summary: Dict[str, Any]) -> None:
    overall = "PASS" if summary["ok"] else "FAIL"
    print(f"\nsingine lutino test login --social  [{overall}]")
    print(f"  base_url  : {summary['base_url']}")
    print(f"  providers : {', '.join(summary['providers'])}")
    print(f"  passed    : {summary['passed']}")
    print(f"  failed    : {summary['failed']}")
    print()
    for probe in summary["probes"]:
        _print_probe(probe)
    print()


# ── argparse registration ──────────────────────────────────────────────────────

def add_lutino_parser(sub: argparse._SubParsersAction) -> None:
    """Register the ``singine lutino`` command family."""

    lutino_parser = sub.add_parser(
        "lutino",
        help="Lutino.io application lifecycle and integration tests",
    )
    lutino_parser.set_defaults(func=lambda a: (lutino_parser.print_help(), 1)[1])
    lutino_sub = lutino_parser.add_subparsers(dest="lutino_subcommand")

    # ── singine lutino status ─────────────────────────────────────────────────
    status_p = lutino_sub.add_parser(
        "status",
        help="Check if Lutino is running locally",
    )
    status_p.add_argument("--url", default=DEFAULT_LUTINO_URL,
                          help=f"Lutino base URL (default: {DEFAULT_LUTINO_URL})")
    status_p.add_argument("--json", action="store_true", help="Emit JSON")
    status_p.set_defaults(func=_cmd_lutino_status)

    # ── singine lutino test ───────────────────────────────────────────────────
    test_p = lutino_sub.add_parser(
        "test",
        help="Run Lutino integration tests",
    )
    test_p.set_defaults(func=lambda a: (test_p.print_help(), 1)[1])
    test_sub = test_p.add_subparsers(dest="lutino_test_subcommand")

    # singine lutino test login --social
    login_p = test_sub.add_parser(
        "login",
        help="Test login endpoint connectivity and social OAuth provider reachability",
    )
    login_p.add_argument(
        "--social",
        action="store_true",
        required=True,
        help="Test social OAuth providers (GitHub, Apple)",
    )
    login_p.add_argument(
        "--provider",
        default="all",
        metavar="PROVIDER",
        help="Provider to test: github | apple | all  (default: all)",
    )
    login_p.add_argument(
        "--url",
        default=DEFAULT_LUTINO_URL,
        help=f"Lutino base URL (default: {DEFAULT_LUTINO_URL})",
    )
    login_p.add_argument("--json", action="store_true", help="Emit JSON")
    login_p.set_defaults(func=_cmd_lutino_test_login_social)

    # singine lutino test gh | apple | all
    for shortname, description in [
        ("gh",    "Run GitHub JUnit tests (GitHubRequestWrapperTest + SocialLoginUserLoginTest)"),
        ("apple", "Run Apple JUnit tests  (AppleRequestWrapperTest  + SocialLoginUserLoginTest)"),
        ("all",   "Run all social login JUnit tests"),
    ]:
        p = test_sub.add_parser(shortname, help=description)
        p.add_argument(
            "--dir",
            default=DEFAULT_LUTINO_DIR,
            metavar="DIR",
            help=f"Lutino source root (default: {DEFAULT_LUTINO_DIR})",
        )
        p.add_argument("--json", action="store_true", help="Emit JSON")
        p.set_defaults(func=_cmd_lutino_test_junit, shortname=shortname)
