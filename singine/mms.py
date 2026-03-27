"""Multimedia Server (MMS) commands for Singine.

Manages the full lifecycle of the CDN-backed multimedia streaming server
used to serve live TV channels (persiangulf.org, IRIB3, etc.).

The MMS is the nginx CDN stack at
``~/ws/git/github/sindoc/collibra/edge/``
running in ``docker-compose.cloud.yml`` mode.  Channel metadata is
tracked in a ``mms-channels.json`` file alongside the stack ``.env``.

Command families
----------------
``singine mms start``
    Bring the CDN stack up (docker compose up -d).

``singine mms stop``
    Bring the CDN stack down (docker compose down).

``singine mms restart``
    Stop then start.  Pass ``--service cdn`` to restart only the CDN
    container without touching edge-site.

``singine mms reload``
    Send ``nginx -s reload`` to the running CDN container — picks up
    conf changes without a full restart.

``singine mms status``
    Show container health, active channels, and nginx config validity.

``singine mms logs``
    Stream CDN and/or edge-site logs.

``singine mms channels list``
    List all registered channels from ``mms-channels.json``.

``singine mms channels add``
    Register a new channel and write it to the channel catalogue.

``singine mms channels remove``
    Remove a channel from the catalogue.

``singine mms channels probe``
    Test whether a channel's HLS origin is reachable from the running
    CDN container.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Default paths ─────────────────────────────────────────────────────────────

_DEFAULT_MMS_DIR = Path.home() / "ws/git/github/sindoc/collibra/edge"
_CHANNELS_FILE = "mms-channels.json"
_CDN_CONTAINER = "edge-cdn-1"
_CLOUD_COMPOSE = "docker-compose.cloud.yml"


def _mms_dir() -> Path:
    return Path(os.environ.get("MMS_DIR", str(_DEFAULT_MMS_DIR)))


def _channels_path() -> Path:
    return _mms_dir() / _CHANNELS_FILE


# ── Envelope helpers ──────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _envelope(ok: bool, command: str, **kwargs: Any) -> Dict[str, Any]:
    return {"ok": ok, "command": command, "ts": _now_iso(), **kwargs}


def _run(cmd: List[str], cwd: Optional[Path] = None,
         capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=capture,
        text=True,
    )


def _compose(args: List[str], profile: str = "cloud",
             cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    """Run docker compose with the appropriate compose file."""
    compose_file = {
        "cloud": _CLOUD_COMPOSE,
        "dev":   "docker-compose.dev.yml",
        "prod":  "docker-compose.yml",
    }.get(profile, _CLOUD_COMPOSE)
    cmd = ["docker", "compose", "-f", compose_file, "--env-file", ".env"] + args
    return _run(cmd, cwd=cwd or _mms_dir())


# ── Channel catalogue helpers ──────────────────────────────────────────────────

def _load_channels() -> List[Dict[str, Any]]:
    p = _channels_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _save_channels(channels: List[Dict[str, Any]]) -> None:
    _channels_path().write_text(
        json.dumps(channels, indent=2, ensure_ascii=False) + "\n"
    )


# ── start ─────────────────────────────────────────────────────────────────────

def cmd_mms_start(args: argparse.Namespace) -> int:
    use_json = args.json
    profile = args.profile
    mms = _mms_dir()

    if not mms.exists():
        msg = f"MMS directory not found: {mms}"
        if use_json:
            print(json.dumps(_envelope(False, "mms start", error=msg)))
        else:
            print(f"[mms start] ERROR: {msg}", file=sys.stderr)
        return 1

    print(f"[mms start] profile={profile}  dir={mms}")
    result = _compose(["up", "-d"], profile=profile)
    ok = result.returncode == 0
    if use_json:
        print(json.dumps(_envelope(ok, "mms start",
                                   profile=profile,
                                   exit_code=result.returncode)))
    elif ok:
        print("[mms start] stack is up")
    else:
        print(f"[mms start] FAILED (exit {result.returncode})", file=sys.stderr)
    return result.returncode


# ── stop ──────────────────────────────────────────────────────────────────────

def cmd_mms_stop(args: argparse.Namespace) -> int:
    use_json = args.json
    profile = args.profile
    mms = _mms_dir()

    print(f"[mms stop] profile={profile}")
    result = _compose(["down"], profile=profile)
    ok = result.returncode == 0
    if use_json:
        print(json.dumps(_envelope(ok, "mms stop",
                                   profile=profile,
                                   exit_code=result.returncode)))
    elif ok:
        print("[mms stop] stack is down")
    else:
        print(f"[mms stop] FAILED (exit {result.returncode})", file=sys.stderr)
    return result.returncode


# ── restart ───────────────────────────────────────────────────────────────────

def cmd_mms_restart(args: argparse.Namespace) -> int:
    use_json = args.json
    profile = args.profile
    service = args.service  # None = whole stack, or "cdn" / "edge-site"
    mms = _mms_dir()

    if service:
        print(f"[mms restart] service={service}  profile={profile}")
        result = _compose(["restart", service], profile=profile)
    else:
        print(f"[mms restart] full stack  profile={profile}")
        down = _compose(["down"], profile=profile)
        if down.returncode != 0:
            if use_json:
                print(json.dumps(_envelope(False, "mms restart",
                                           error="stop failed",
                                           exit_code=down.returncode)))
            else:
                print(f"[mms restart] stop FAILED (exit {down.returncode})", file=sys.stderr)
            return down.returncode
        result = _compose(["up", "-d"], profile=profile)

    ok = result.returncode == 0
    if use_json:
        print(json.dumps(_envelope(ok, "mms restart",
                                   profile=profile,
                                   service=service,
                                   exit_code=result.returncode)))
    elif ok:
        print("[mms restart] done")
    else:
        print(f"[mms restart] FAILED (exit {result.returncode})", file=sys.stderr)
    return result.returncode


# ── reload ────────────────────────────────────────────────────────────────────

def cmd_mms_reload(args: argparse.Namespace) -> int:
    """Send nginx -s reload to the running CDN container."""
    use_json = args.json
    container = args.container

    print(f"[mms reload] container={container}")
    result = _run(["docker", "exec", container, "nginx", "-s", "reload"])
    ok = result.returncode == 0
    if use_json:
        print(json.dumps(_envelope(ok, "mms reload",
                                   container=container,
                                   exit_code=result.returncode)))
    elif ok:
        print("[mms reload] nginx reloaded")
    else:
        print(f"[mms reload] FAILED (exit {result.returncode})", file=sys.stderr)
    return result.returncode


# ── status ────────────────────────────────────────────────────────────────────

def cmd_mms_status(args: argparse.Namespace) -> int:
    use_json = args.json

    # Container health
    ps_r = _run(
        ["docker", "ps",
         "--filter", "name=edge-cdn",
         "--filter", "name=edge-edge-site",
         "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}"],
        capture=True,
    )
    containers = []
    for line in ps_r.stdout.strip().splitlines():
        parts = line.split("\t")
        containers.append({
            "name":   parts[0] if len(parts) > 0 else "",
            "status": parts[1] if len(parts) > 1 else "",
            "ports":  parts[2] if len(parts) > 2 else "",
        })

    # nginx config test
    nginx_r = _run(
        ["docker", "exec", _CDN_CONTAINER, "nginx", "-t"],
        capture=True,
    )
    nginx_ok = nginx_r.returncode == 0
    nginx_msg = (nginx_r.stderr or nginx_r.stdout).strip()

    # Active channels
    channels = _load_channels()

    if use_json:
        print(json.dumps(_envelope(
            nginx_ok and len(containers) > 0,
            "mms status",
            containers=containers,
            nginx_config_ok=nginx_ok,
            nginx_message=nginx_msg,
            channels=channels,
        )))
        return 0

    print("── MMS Status ───────────────────────────────────────────────")
    if containers:
        for c in containers:
            print(f"  {c['name']:30s}  {c['status']}")
    else:
        print("  (no containers running)")

    print()
    print(f"  nginx config: {'OK' if nginx_ok else 'INVALID'}")
    if not nginx_ok:
        for line in nginx_msg.splitlines():
            if "emerg" in line or "error" in line:
                print(f"    {line}")

    print()
    print(f"  channels: {len(channels)}")
    for ch in channels:
        probe = ch.get("last_probe", "—")
        print(f"    {ch.get('name','?'):20s}  {ch.get('origin','?'):30s}  probe={probe}")
    print("─────────────────────────────────────────────────────────────")
    return 0


# ── logs ──────────────────────────────────────────────────────────────────────

def cmd_mms_logs(args: argparse.Namespace) -> int:
    use_json = args.json
    profile = args.profile
    service = args.service
    follow = args.follow
    tail = args.tail

    compose_args = ["logs"]
    if follow:
        compose_args.append("--follow")
    if tail:
        compose_args += ["--tail", str(tail)]
    if service:
        compose_args.append(service)

    if use_json:
        result = _compose(compose_args + ["--no-color"], profile=profile)
        ok = result.returncode == 0
        print(json.dumps(_envelope(ok, "mms logs",
                                   profile=profile,
                                   service=service,
                                   exit_code=result.returncode)))
        return result.returncode

    result = _compose(compose_args, profile=profile)
    return result.returncode


# ── channels list ─────────────────────────────────────────────────────────────

def cmd_mms_channels_list(args: argparse.Namespace) -> int:
    use_json = args.json
    channels = _load_channels()

    if use_json:
        print(json.dumps(_envelope(True, "mms channels list", channels=channels)))
        return 0

    if not channels:
        print("[mms channels] no channels registered  (see mms-channels.json)")
        return 0

    print(f"{'NAME':<20}  {'ORIGIN':<35}  {'PATH'}")
    print("─" * 90)
    for ch in channels:
        print(f"{ch.get('name','?'):<20}  {ch.get('origin','?'):<35}  {ch.get('path','?')}")
    return 0


# ── channels add ──────────────────────────────────────────────────────────────

def cmd_mms_channels_add(args: argparse.Namespace) -> int:
    use_json = args.json
    name = args.name
    origin = args.origin
    path = args.path
    cdn_host = args.cdn_host
    group = args.group

    channels = _load_channels()
    if any(ch.get("name") == name for ch in channels):
        msg = f"channel '{name}' already exists — use remove first"
        if use_json:
            print(json.dumps(_envelope(False, "mms channels add", error=msg, name=name)))
        else:
            print(f"[mms channels add] ERROR: {msg}", file=sys.stderr)
        return 1

    entry: Dict[str, Any] = {
        "name":     name,
        "origin":   origin,
        "path":     path,
        "cdn_host": cdn_host or f"{name}.persiangulf.org",
        "group":    group or "General",
        "added_at": _now_iso(),
    }
    channels.append(entry)
    _save_channels(channels)

    if use_json:
        print(json.dumps(_envelope(True, "mms channels add", channel=entry)))
    else:
        print(f"[mms channels add] registered: {name}")
        print(f"  origin:   {origin}{path}")
        print(f"  cdn_host: {entry['cdn_host']}")
        print(f"  group:    {entry['group']}")
        print(f"  Saved → {_channels_path()}")
    return 0


# ── channels remove ───────────────────────────────────────────────────────────

def cmd_mms_channels_remove(args: argparse.Namespace) -> int:
    use_json = args.json
    name = args.name

    channels = _load_channels()
    before = len(channels)
    channels = [ch for ch in channels if ch.get("name") != name]

    if len(channels) == before:
        msg = f"channel '{name}' not found"
        if use_json:
            print(json.dumps(_envelope(False, "mms channels remove", error=msg, name=name)))
        else:
            print(f"[mms channels remove] ERROR: {msg}", file=sys.stderr)
        return 1

    _save_channels(channels)
    if use_json:
        print(json.dumps(_envelope(True, "mms channels remove", name=name,
                                   remaining=len(channels))))
    else:
        print(f"[mms channels remove] removed: {name}  ({len(channels)} channels remaining)")
    return 0


# ── channels probe ────────────────────────────────────────────────────────────

def cmd_mms_channels_probe(args: argparse.Namespace) -> int:
    """Test if a channel's HLS origin is reachable from the CDN container."""
    use_json = args.json
    name = args.name

    channels = _load_channels()
    channel = next((ch for ch in channels if ch.get("name") == name), None)

    if channel is None:
        msg = f"channel '{name}' not found in catalogue"
        if use_json:
            print(json.dumps(_envelope(False, "mms channels probe", error=msg, name=name)))
        else:
            print(f"[mms channels probe] ERROR: {msg}", file=sys.stderr)
        return 1

    url = f"https://{channel['origin']}{channel['path']}"
    if not use_json:
        print(f"[mms channels probe] {name} → {url}")

    result = _run(
        ["docker", "exec", _CDN_CONTAINER,
         "curl", "-sk", "-o", "/dev/null", "-w", "%{http_code}",
         "--max-time", "8", url],
        capture=True,
    )
    http_code = result.stdout.strip()
    ok = http_code in ("200", "206")
    probe_result = {
        "name":      name,
        "url":       url,
        "http_code": http_code,
        "reachable": ok,
        "probed_at": _now_iso(),
    }

    # Update last_probe in catalogue
    for ch in channels:
        if ch.get("name") == name:
            ch["last_probe"] = http_code
            ch["last_probed_at"] = probe_result["probed_at"]
    _save_channels(channels)

    if use_json:
        print(json.dumps(_envelope(ok, "mms channels probe", **probe_result)))
    else:
        status = "REACHABLE" if ok else f"UNREACHABLE (HTTP {http_code or 'timeout'})"
        print(f"[mms channels probe] {name}: {status}")
    return 0 if ok else 1


# ── Parser registration ───────────────────────────────────────────────────────

def add_mms_parser(sub: argparse._SubParsersAction) -> None:
    """Register `singine mms` and all sub-commands."""

    mms_p = sub.add_parser(
        "mms",
        help="Multimedia Server — lifecycle and channel management for the CDN streaming stack",
    )
    mms_sub = mms_p.add_subparsers(dest="mms_subcommand")

    # ── start ──────────────────────────────────────────────────────────────────
    start_p = mms_sub.add_parser("start", help="Bring the CDN stack up (docker compose up -d)")
    start_p.add_argument("--profile", choices=["cloud", "dev", "prod"], default="cloud",
                         help="Compose profile (default: cloud)")
    start_p.add_argument("--json", action="store_true", help="JSON envelope output")
    start_p.set_defaults(func=cmd_mms_start)

    # ── stop ───────────────────────────────────────────────────────────────────
    stop_p = mms_sub.add_parser("stop", help="Bring the CDN stack down")
    stop_p.add_argument("--profile", choices=["cloud", "dev", "prod"], default="cloud")
    stop_p.add_argument("--json", action="store_true")
    stop_p.set_defaults(func=cmd_mms_stop)

    # ── restart ────────────────────────────────────────────────────────────────
    restart_p = mms_sub.add_parser("restart", help="Restart stack or a single service")
    restart_p.add_argument("--service", choices=["cdn", "edge-site"],
                           default=None,
                           help="Restart only this service (default: full stack)")
    restart_p.add_argument("--profile", choices=["cloud", "dev", "prod"], default="cloud")
    restart_p.add_argument("--json", action="store_true")
    restart_p.set_defaults(func=cmd_mms_restart)

    # ── reload ─────────────────────────────────────────────────────────────────
    reload_p = mms_sub.add_parser("reload",
                                  help="Reload nginx config without restart (nginx -s reload)")
    reload_p.add_argument("--container", default=_CDN_CONTAINER,
                          help=f"CDN container name (default: {_CDN_CONTAINER})")
    reload_p.add_argument("--json", action="store_true")
    reload_p.set_defaults(func=cmd_mms_reload)

    # ── status ─────────────────────────────────────────────────────────────────
    status_p = mms_sub.add_parser("status", help="Show container health, nginx validity, channels")
    status_p.add_argument("--json", action="store_true")
    status_p.set_defaults(func=cmd_mms_status)

    # ── logs ───────────────────────────────────────────────────────────────────
    logs_p = mms_sub.add_parser("logs", help="Tail CDN / edge-site logs")
    logs_p.add_argument("--service", choices=["cdn", "edge-site"],
                        default=None, help="Stream logs from this service only")
    logs_p.add_argument("--follow", "-f", action="store_true", help="Follow log output")
    logs_p.add_argument("--tail", type=int, default=50,
                        help="Number of lines to show (default: 50)")
    logs_p.add_argument("--profile", choices=["cloud", "dev", "prod"], default="cloud")
    logs_p.add_argument("--json", action="store_true")
    logs_p.set_defaults(func=cmd_mms_logs)

    # ── channels ───────────────────────────────────────────────────────────────
    channels_p = mms_sub.add_parser("channels", help="Channel catalogue management")
    channels_sub = channels_p.add_subparsers(dest="channels_subcommand")

    # channels list
    ch_list = channels_sub.add_parser("list", help="List registered channels")
    ch_list.add_argument("--json", action="store_true")
    ch_list.set_defaults(func=cmd_mms_channels_list)

    # channels add
    ch_add = channels_sub.add_parser("add", help="Register a new channel")
    ch_add.add_argument("--name", required=True,
                        help="Short slug (e.g. irib3, gem, manoto)")
    ch_add.add_argument("--origin", required=True,
                        help="HLS origin hostname (e.g. lenz.splus.ir)")
    ch_add.add_argument("--path", required=True,
                        help="Path to m3u8 on origin (e.g. /PLTV/88888888/224/3221226868/index.m3u8)")
    ch_add.add_argument("--cdn-host", dest="cdn_host", default=None,
                        help="CDN vhost for this channel (default: <name>.persiangulf.org)")
    ch_add.add_argument("--group", default="General",
                        help="Channel group/category (default: General)")
    ch_add.add_argument("--json", action="store_true")
    ch_add.set_defaults(func=cmd_mms_channels_add)

    # channels remove
    ch_rm = channels_sub.add_parser("remove", help="Remove a channel from the catalogue")
    ch_rm.add_argument("--name", required=True)
    ch_rm.add_argument("--json", action="store_true")
    ch_rm.set_defaults(func=cmd_mms_channels_remove)

    # channels probe
    ch_probe = channels_sub.add_parser(
        "probe",
        help="Test if a channel's HLS origin is reachable from the CDN container",
    )
    ch_probe.add_argument("--name", required=True)
    ch_probe.add_argument("--json", action="store_true")
    ch_probe.set_defaults(func=cmd_mms_channels_probe)
