"""Edge server commands for Singine.

Provides full lifecycle management of the Collibra edge stack that lives in
``~/ws/git/github/sindoc/collibra/edge/``.  All heavy lifting delegates to
the stack's own Makefile and docker compose file; singine acts as the
sanctioned execution gate and wraps results in a structured envelope.

Command families
----------------
``singine edge build``
    Build one or all container images (base, collibra-edge, cdn).

``singine edge push``
    Tag and push images to a registry.

``singine edge up / down / logs / status``
    docker compose lifecycle operations.

``singine edge install``
    Full install: build all images + prepare agent venv + register governance
    decision.  Idempotent — safe to run repeatedly.

``singine edge deploy``
    install + up — bring the full stack to a running state.

``singine edge agent``
    Run, validate, or install the Claude API edge-agent that generates
    Kubernetes/OpenShift/Collibra configuration artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# ── Default paths ─────────────────────────────────────────────────────────────

_DEFAULT_EDGE_DIR = Path.home() / "ws/git/github/sindoc/collibra/edge"


def _edge_dir() -> Path:
    """Return the edge stack root, overridable via COLLIBRA_EDGE_DIR."""
    return Path(os.environ.get("COLLIBRA_EDGE_DIR", str(_DEFAULT_EDGE_DIR)))


def _agent_dir() -> Path:
    return _edge_dir() / "agent"


def _image_dir() -> Path:
    return _edge_dir() / "image"


# ── Envelope helpers ──────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _envelope(ok: bool, command: str, **kwargs: Any) -> Dict[str, Any]:
    return {"ok": ok, "command": command, "ts": _now_iso(), **kwargs}


def _run(
    cmd: List[str],
    cwd: Optional[Path] = None,
    capture: bool = False,
) -> subprocess.CompletedProcess:
    """Run a subprocess, streaming output unless capture=True."""
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=capture,
        text=True,
    )


def _make(targets: List[str], cwd: Path, extra_vars: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
    cmd = ["make", "-C", str(cwd)] + targets
    if extra_vars:
        cmd += [f"{k}={v}" for k, v in extra_vars.items()]
    return subprocess.run(cmd, text=True)


# ── Build ─────────────────────────────────────────────────────────────────────

VALID_TARGETS = ("base", "collibra-edge", "cdn", "all")


def cmd_edge_build(args: argparse.Namespace) -> int:
    target = args.target
    tag = args.tag
    no_cache = args.no_cache
    use_json = args.json

    edge = _edge_dir()
    if not edge.exists():
        msg = f"Edge directory not found: {edge}"
        if use_json:
            print(json.dumps(_envelope(False, "edge build", error=msg)))
        else:
            print(f"[edge build] ERROR: {msg}", file=sys.stderr)
        return 1

    make_target = f"build-{target}" if target != "all" else "build"
    extra: Dict[str, str] = {"TAG": tag}
    if no_cache:
        extra["DOCKER_BUILDKIT"] = "1"

    print(f"[edge build] target={target}  tag={tag}  no_cache={no_cache}")
    result = _make([make_target] + ([f"DOCKER_BUILD_ARGS=--no-cache"] if no_cache else []), edge, extra)

    ok = result.returncode == 0
    if use_json:
        print(json.dumps(_envelope(ok, "edge build", target=target, tag=tag, exit_code=result.returncode)))
    elif ok:
        print(f"[edge build] done: {make_target}  tag={tag}")
    else:
        print(f"[edge build] FAILED (exit {result.returncode})", file=sys.stderr)
    return result.returncode


# ── Push ──────────────────────────────────────────────────────────────────────

def cmd_edge_push(args: argparse.Namespace) -> int:
    target = args.target
    tag = args.tag
    registry = args.registry
    use_json = args.json

    edge = _edge_dir()
    images = {
        "base":          "sindoc-collibra-edge-base",
        "collibra-edge": "sindoc-collibra-edge",
        "cdn":           "sindoc-collibra-cdn",
    }

    targets = list(images.keys()) if target == "all" else [target]
    results = []
    overall_ok = True

    for t in targets:
        img = images[t]
        src = f"{img}:{tag}"
        dst = f"{registry}/{img}:{tag}"
        print(f"[edge push] {src} → {dst}")
        r_tag = subprocess.run(["docker", "tag", src, dst], text=True)
        r_push = subprocess.run(["docker", "push", dst], text=True) if r_tag.returncode == 0 else None
        rc = (r_push.returncode if r_push else r_tag.returncode)
        ok = rc == 0
        if not ok:
            overall_ok = False
        results.append({"target": t, "image": dst, "ok": ok, "exit_code": rc})

    if use_json:
        print(json.dumps(_envelope(overall_ok, "edge push", registry=registry, tag=tag, results=results)))
    elif overall_ok:
        print(f"[edge push] done — {len(results)} image(s) pushed to {registry}")
    else:
        print(f"[edge push] one or more pushes FAILED", file=sys.stderr)
    return 0 if overall_ok else 1


# ── Stack: up / down / logs / status ─────────────────────────────────────────

def _compose_cmd(edge: Path) -> List[str]:
    return ["docker", "compose", "-f", str(edge / "docker-compose.yml")]


def cmd_edge_up(args: argparse.Namespace) -> int:
    edge = _edge_dir()
    cmd = _compose_cmd(edge) + ["up"]
    if args.detach:
        cmd.append("-d")
    print(f"[edge up] starting stack (detach={args.detach})")
    result = subprocess.run(cmd, text=True)
    if args.json:
        print(json.dumps(_envelope(result.returncode == 0, "edge up", detach=args.detach, exit_code=result.returncode)))
    return result.returncode


def cmd_edge_down(args: argparse.Namespace) -> int:
    edge = _edge_dir()
    cmd = _compose_cmd(edge) + ["down"]
    print("[edge down] stopping stack")
    result = subprocess.run(cmd, text=True)
    if args.json:
        print(json.dumps(_envelope(result.returncode == 0, "edge down", exit_code=result.returncode)))
    return result.returncode


def cmd_edge_logs(args: argparse.Namespace) -> int:
    edge = _edge_dir()
    cmd = _compose_cmd(edge) + ["logs"]
    if args.follow:
        cmd.append("-f")
    if args.service:
        cmd.append(args.service)
    return subprocess.run(cmd, text=True).returncode


def cmd_edge_status(args: argparse.Namespace) -> int:
    edge = _edge_dir()
    use_json = args.json

    # docker compose ps
    r = subprocess.run(
        _compose_cmd(edge) + ["ps", "--format", "json"],
        capture_output=True, text=True,
    )
    compose_ok = r.returncode == 0
    try:
        services = json.loads(r.stdout) if r.stdout.strip() else []
    except json.JSONDecodeError:
        services = r.stdout.strip()

    # docker images
    images_r = subprocess.run(
        ["docker", "images",
         "--filter", "reference=sindoc-collibra*",
         "--format", "{{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}"],
        capture_output=True, text=True,
    )
    image_lines = [l for l in images_r.stdout.strip().splitlines() if l]

    # agent decision
    decision_path = Path.home() / ".singine/decisions/edge-agent.json"
    decision: Any = "(not registered)"
    if decision_path.exists():
        try:
            decision = json.loads(decision_path.read_text()).get("urn", "(missing urn)")
        except Exception:
            pass

    if use_json:
        print(json.dumps(_envelope(
            compose_ok, "edge status",
            services=services,
            images=image_lines,
            agent_decision=decision,
            edge_dir=str(edge),
        )))
    else:
        print(f"[edge status] edge_dir  : {edge}")
        print(f"[edge status] decision  : {decision}")
        print(f"[edge status] images    :")
        for line in image_lines:
            print(f"               {line}")
        print(f"[edge status] services  :")
        if isinstance(services, list):
            for svc in services:
                if isinstance(svc, dict):
                    name = svc.get("Name") or svc.get("Service", "?")
                    state = svc.get("State", "?")
                    health = svc.get("Health", "")
                    print(f"               {name:<30} {state}  {health}")
        else:
            print(f"               {services}")
    return 0


# ── Install ───────────────────────────────────────────────────────────────────

def cmd_edge_install(args: argparse.Namespace) -> int:
    """Full install: build all images + prepare agent + register governance decision."""
    use_json = args.json
    edge = _edge_dir()
    agent = _agent_dir()
    steps: List[Dict[str, Any]] = []

    def step(name: str, cmd: List[str], cwd: Optional[Path] = None) -> bool:
        print(f"[edge install] → {name}")
        r = subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True)
        ok = r.returncode == 0
        steps.append({"step": name, "ok": ok, "exit_code": r.returncode})
        if not ok:
            print(f"[edge install]   FAILED (exit {r.returncode})", file=sys.stderr)
        return ok

    # 1. Build all images
    if not step("build images", ["make", "build", f"TAG={args.tag}"], edge):
        if use_json:
            print(json.dumps(_envelope(False, "edge install", steps=steps)))
        return 1

    # 2. Prepare agent venv
    if not step("agent prepare", ["make", "-C", str(agent), "prepare"]):
        if use_json:
            print(json.dumps(_envelope(False, "edge install", steps=steps)))
        return 1

    # 3. Register governance decision
    if not step("governance decision", ["make", "-C", str(agent), "install"]):
        if use_json:
            print(json.dumps(_envelope(False, "edge install", steps=steps)))
        return 1

    ok = all(s["ok"] for s in steps)
    if use_json:
        print(json.dumps(_envelope(ok, "edge install", tag=args.tag, steps=steps)))
    else:
        print(f"[edge install] complete — {len(steps)} steps, all ok={ok}")
    return 0 if ok else 1


# ── Deploy ────────────────────────────────────────────────────────────────────

def cmd_edge_deploy(args: argparse.Namespace) -> int:
    """install + up — bring the full stack to a running state."""
    rc = cmd_edge_install(args)
    if rc != 0:
        return rc
    # re-use up with detach=True
    up_ns = argparse.Namespace(detach=True, json=args.json)
    return cmd_edge_up(up_ns)


# ── Agent subcommands ─────────────────────────────────────────────────────────

def cmd_edge_agent_validate(args: argparse.Namespace) -> int:
    agent = _agent_dir()
    print("[edge agent validate] running tool smoke-test …")
    result = subprocess.run(["make", "-C", str(agent), "validate"], text=True)
    ok = result.returncode == 0
    if args.json:
        print(json.dumps(_envelope(ok, "edge agent validate", exit_code=result.returncode)))
    return result.returncode


def cmd_edge_agent_run(args: argparse.Namespace) -> int:
    agent = _agent_dir()
    task = args.task
    output_dir = args.output_dir or str(agent / "output")
    print(f"[edge agent run] task: {task}")
    result = subprocess.run(
        ["make", "-C", str(agent), "run-task", f"TASK={task}", f"OUTPUT_DIR={output_dir}"],
        text=True,
    )
    ok = result.returncode == 0
    if args.json:
        print(json.dumps(_envelope(ok, "edge agent run", task=task, output_dir=output_dir, exit_code=result.returncode)))
    return result.returncode


def cmd_edge_agent_install(args: argparse.Namespace) -> int:
    agent = _agent_dir()
    print("[edge agent install] preparing venv and registering governance decision …")
    result = subprocess.run(["make", "-C", str(agent), "install"], text=True)
    ok = result.returncode == 0
    if args.json:
        print(json.dumps(_envelope(ok, "edge agent install", exit_code=result.returncode)))
    return result.returncode


def cmd_edge_agent_status(args: argparse.Namespace) -> int:
    agent = _agent_dir()
    result = subprocess.run(["make", "-C", str(agent), "status"], text=True)
    ok = result.returncode == 0
    if args.json:
        print(json.dumps(_envelope(ok, "edge agent status", exit_code=result.returncode)))
    return result.returncode


# ── Parser registration ───────────────────────────────────────────────────────

def add_edge_parser(sub: argparse._SubParsersAction) -> None:
    """Register ``singine edge`` and all its subcommand families."""

    edge_parser = sub.add_parser(
        "edge",
        help="Collibra edge server lifecycle — build, deploy, and manage the CDN + DGC edge stack",
    )
    edge_parser.set_defaults(func=lambda a: (edge_parser.print_help(), 1)[1])

    edge_sub = edge_parser.add_subparsers(dest="edge_family")

    # ── build ─────────────────────────────────────────────────────────────────
    p = edge_sub.add_parser("build", help="Build edge container image(s)")
    p.add_argument(
        "--target",
        choices=list(VALID_TARGETS),
        default="all",
        help="Image to build: base | collibra-edge | cdn | all  (default: all)",
    )
    p.add_argument("--tag", default="local", help="Image tag (default: local)")
    p.add_argument("--no-cache", action="store_true", help="Pass --no-cache to docker build")
    p.add_argument("--json", action="store_true", help="Emit JSON envelope")
    p.set_defaults(func=cmd_edge_build)

    # ── push ──────────────────────────────────────────────────────────────────
    p = edge_sub.add_parser("push", help="Tag and push image(s) to a registry")
    p.add_argument("--target", choices=list(VALID_TARGETS), default="all")
    p.add_argument("--registry", required=True, help="Registry hostname (e.g. registry.example.com)")
    p.add_argument("--tag", default="local", help="Image tag (default: local)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_push)

    # ── up ────────────────────────────────────────────────────────────────────
    p = edge_sub.add_parser("up", help="Start the edge stack via docker compose")
    p.add_argument("--detach", "-d", action="store_true", help="Run in background")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_up)

    # ── down ──────────────────────────────────────────────────────────────────
    p = edge_sub.add_parser("down", help="Stop and remove edge stack containers")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_down)

    # ── logs ──────────────────────────────────────────────────────────────────
    p = edge_sub.add_parser("logs", help="Stream or print container logs")
    p.add_argument(
        "--service",
        choices=["collibra-edge", "cdn"],
        default=None,
        help="Limit to a specific service (default: all)",
    )
    p.add_argument("--follow", "-f", action="store_true", help="Follow log output")
    p.set_defaults(func=cmd_edge_logs)

    # ── status ────────────────────────────────────────────────────────────────
    p = edge_sub.add_parser("status", help="Show image, container, and governance decision status")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_status)

    # ── install ───────────────────────────────────────────────────────────────
    p = edge_sub.add_parser(
        "install",
        help="Full install: build all images + agent venv + governance decision",
    )
    p.add_argument("--tag", default="local", help="Image tag (default: local)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_install)

    # ── deploy ────────────────────────────────────────────────────────────────
    p = edge_sub.add_parser(
        "deploy",
        help="Install + start stack (full bring-up from scratch)",
    )
    p.add_argument("--tag", default="local", help="Image tag (default: local)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_deploy)

    # ── agent ─────────────────────────────────────────────────────────────────
    agent_parser = edge_sub.add_parser(
        "agent",
        help="Claude API edge-agent — generate K8s/OpenShift/Collibra configuration artifacts",
    )
    agent_parser.set_defaults(func=lambda a: (agent_parser.print_help(), 1)[1])
    agent_sub = agent_parser.add_subparsers(dest="edge_agent_action")

    p = agent_sub.add_parser("validate", help="Smoke-test all agent tools (no API call)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_agent_validate)

    p = agent_sub.add_parser("run", help="Run the agent with a natural-language task")
    p.add_argument("--task", required=True, help="Natural-language task description")
    p.add_argument(
        "--output-dir",
        metavar="DIR",
        default=None,
        help="Directory to write generated artifacts (default: agent/output/)",
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_agent_run)

    p = agent_sub.add_parser("install", help="Prepare agent venv and register governance decision")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_agent_install)

    p = agent_sub.add_parser("status", help="Show agent venv, package, and decision status")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_agent_status)
