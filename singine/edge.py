"""Edge server commands for Singine.

Provides full lifecycle management of the Collibra edge stack that lives in
``~/ws/git/github/sindoc/collibra/edge/``.  All heavy lifting delegates to
the stack's own Makefile, docker compose files, and shell scripts; singine
acts as the sanctioned execution gate and wraps results in a structured
envelope.

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

``singine edge site init``
    Bootstrap a real Collibra Edge site from the installer bundle and verify it.

``singine edge k8s``
    Deploy the **real Collibra Edge** onto a Kubernetes cluster using the
    site-specific installer bundle (installer/).  Sub-commands:

    prereqs   — verify helm/kubectl/jq/yq and cluster reachability
    install   — run scripts/install-edge-k8s.sh (Helm chart deployment)
    uninstall — tear down the Helm release and namespace
    status    — show pod health and Helm release in namespace collibra-edge
    logs      — stream pod logs from a named edge component

``singine edge agent``
    Run, validate, or install the Claude API edge-agent that generates
    Kubernetes/OpenShift/Collibra configuration artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ── Default paths ─────────────────────────────────────────────────────────────

_DEFAULT_EDGE_DIR = Path.home() / "ws/git/github/sindoc/collibra/edge"


def _edge_dir(args: Optional[argparse.Namespace] = None) -> Path:
    """Return the edge stack root, overridable via COLLIBRA_EDGE_DIR."""
    if args is not None and getattr(args, "edge_dir", None):
        return Path(args.edge_dir).expanduser()
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

VALID_TARGETS = ("base", "collibra-edge", "edge-site", "cdn", "all")


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
        "edge-site":     "sindoc-collibra-edge-site",
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

def cmd_edge_setup(args: argparse.Namespace) -> int:
    """Run the full automated setup and launch the stack."""
    edge = _edge_dir()
    script = edge / "scripts" / "setup.sh"
    if not script.exists():
        msg = f"Setup script not found: {script}"
        if args.json:
            print(json.dumps(_envelope(False, "edge setup", error=msg)))
        else:
            print(f"[edge setup] ERROR: {msg}", file=sys.stderr)
        return 1

    cmd = ["bash", str(script)]
    if args.dev:
        cmd.append("--dev")
    if args.no_start:
        cmd.append("--no-start")
    if args.tag:
        cmd += ["--tag", args.tag]

    result = subprocess.run(cmd, text=True)
    ok = result.returncode == 0
    if args.json:
        print(json.dumps(_envelope(ok, "edge setup", dev=args.dev, exit_code=result.returncode)))
    return result.returncode


def cmd_edge_javadoc(args: argparse.Namespace) -> int:
    """Build Javadoc for the edge Java interface layer."""
    edge = _edge_dir()
    java_dir = edge / "java"
    if not java_dir.exists():
        msg = f"Java module not found: {java_dir}"
        if args.json:
            print(json.dumps(_envelope(False, "edge javadoc", error=msg)))
        else:
            print(f"[edge javadoc] ERROR: {msg}", file=sys.stderr)
        return 1
    print(f"[edge javadoc] building Javadoc in {java_dir}")
    result = subprocess.run(["./gradlew", "javadoc"], cwd=str(java_dir), text=True)
    ok = result.returncode == 0
    out_dir = java_dir / "build/docs/javadoc"
    if args.json:
        print(json.dumps(_envelope(ok, "edge javadoc", output_dir=str(out_dir), exit_code=result.returncode)))
    elif ok:
        print(f"[edge javadoc] done: {out_dir}")
    else:
        print(f"[edge javadoc] FAILED (exit {result.returncode})", file=sys.stderr)
    return result.returncode


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


# ── k8s ───────────────────────────────────────────────────────────────────────

_K8S_NAMESPACE = "collibra-edge"

_K8S_PREREQS = ("helm", "kubectl", "jq", "yq")


def _installer_dir(args: Optional[argparse.Namespace] = None) -> Path:
    if args is not None and getattr(args, "installer_dir", None):
        return Path(args.installer_dir).expanduser()
    return _edge_dir(args) / "installer"


def _compose_down_if_present(edge: Path, compose_name: str) -> int:
    compose_file = edge / compose_name
    if not compose_file.exists():
        return 0
    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "down"],
        cwd=str(edge),
        text=True,
    )
    return result.returncode


def cmd_edge_k8s_prereqs(args: argparse.Namespace) -> int:
    """Check that all K8s prerequisites are satisfied."""
    use_json = args.json
    results: List[Dict[str, Any]] = []
    ok = True

    # 1. Tool availability
    for tool in _K8S_PREREQS:
        r = subprocess.run(["which", tool], capture_output=True, text=True)
        found = r.returncode == 0
        if not found:
            ok = False
        results.append({"check": f"tool:{tool}", "ok": found,
                         "detail": r.stdout.strip() if found else "not found"})

    # 2. Kubernetes cluster reachable
    r = subprocess.run(["kubectl", "cluster-info"], capture_output=True, text=True)
    k8s_ok = r.returncode == 0
    if not k8s_ok:
        ok = False
    results.append({"check": "kubernetes-cluster", "ok": k8s_ok,
                     "detail": "reachable" if k8s_ok else
                     "not reachable — enable Docker Desktop Kubernetes: Settings → Kubernetes → Enable Kubernetes"})

    # 3. Installer bundle present
    installer = _installer_dir(args)
    bundle_ok = (installer / "site-values.yaml").exists() and \
                (installer / "collibra-edge-helm-chart").exists()
    if not bundle_ok:
        ok = False
    results.append({"check": "installer-bundle", "ok": bundle_ok,
                     "detail": str(installer) if bundle_ok else
                     f"missing — extract installer TGZ to {installer}"})

    if use_json:
        print(json.dumps(_envelope(ok, "edge k8s prereqs", checks=results)))
    else:
        for item in results:
            icon = "✓" if item["ok"] else "✗"
            print(f"[edge k8s prereqs] {icon}  {item['check']:<30} {item['detail']}")
        if not ok:
            print("[edge k8s prereqs] FAILED — resolve the issues above before running install",
                  file=sys.stderr)
    return 0 if ok else 1


def cmd_edge_k8s_install(args: argparse.Namespace) -> int:
    """Deploy the real Collibra Edge onto Kubernetes via Helm."""
    edge = _edge_dir(args)
    script = edge / "scripts" / "install-edge-k8s.sh"
    use_json = args.json

    if not script.exists():
        msg = f"Install script not found: {script}"
        if use_json:
            print(json.dumps(_envelope(False, "edge k8s install", error=msg)))
        else:
            print(f"[edge k8s install] ERROR: {msg}", file=sys.stderr)
        return 1

    cmd = ["bash", str(script)]
    if args.dry_run:
        cmd.append("--dry-run")

    print(f"[edge k8s install] dry_run={args.dry_run}")
    result = subprocess.run(cmd, text=True)
    ok = result.returncode == 0
    if use_json:
        print(json.dumps(_envelope(ok, "edge k8s install",
                                   dry_run=args.dry_run,
                                   exit_code=result.returncode)))
    return result.returncode


def cmd_edge_k8s_uninstall(args: argparse.Namespace) -> int:
    """Helm uninstall + delete namespace."""
    edge = _edge_dir(args)
    script = edge / "scripts" / "install-edge-k8s.sh"
    use_json = args.json

    if not script.exists():
        msg = f"Install script not found: {script}"
        if use_json:
            print(json.dumps(_envelope(False, "edge k8s uninstall", error=msg)))
        else:
            print(f"[edge k8s uninstall] ERROR: {msg}", file=sys.stderr)
        return 1

    print("[edge k8s uninstall] removing Helm release and namespace …")
    result = subprocess.run(["bash", str(script), "--uninstall"], text=True)
    ok = result.returncode == 0
    if use_json:
        print(json.dumps(_envelope(ok, "edge k8s uninstall",
                                   exit_code=result.returncode)))
    return result.returncode


def cmd_edge_k8s_status(args: argparse.Namespace) -> int:
    """Show pod health and Helm release status in the collibra-edge namespace."""
    ns = args.namespace
    use_json = args.json

    # kubectl context
    ctx_r = subprocess.run(
        ["kubectl", "config", "current-context"],
        capture_output=True, text=True,
    )
    context = ctx_r.stdout.strip() if ctx_r.returncode == 0 else "unknown"

    # helm release status
    helm_r = subprocess.run(
        ["helm", "status", "collibra-edge", "-n", ns, "--output", "json"],
        capture_output=True, text=True,
    )
    helm_ok = helm_r.returncode == 0
    try:
        helm_data: Any = json.loads(helm_r.stdout) if helm_ok else {}
    except json.JSONDecodeError:
        helm_data = {}
    helm_status = helm_data.get("info", {}).get("status", "not installed") if isinstance(helm_data, dict) else "not installed"
    helm_version = helm_data.get("chart", {}).get("metadata", {}).get("version", "") if isinstance(helm_data, dict) else ""

    # kubectl get pods
    pods_r = subprocess.run(
        ["kubectl", "get", "pods", "-n", ns,
         "--no-headers",
         "-o", "custom-columns=NAME:.metadata.name,READY:.status.containerStatuses[*].ready,STATUS:.status.phase,RESTARTS:.status.containerStatuses[*].restartCount,AGE:.metadata.creationTimestamp"],
        capture_output=True, text=True,
    )
    pod_lines = [l for l in pods_r.stdout.strip().splitlines() if l]

    if use_json:
        print(json.dumps(_envelope(
            helm_ok or pods_r.returncode == 0,
            "edge k8s status",
            context=context,
            namespace=ns,
            helm_status=helm_status,
            helm_version=helm_version,
            pods=pod_lines,
        )))
    else:
        print(f"[edge k8s status] context      : {context}")
        print(f"[edge k8s status] namespace    : {ns}")
        print(f"[edge k8s status] helm release : collibra-edge  {helm_status}  {helm_version}")
        print(f"[edge k8s status] pods:")
        if pod_lines:
            for line in pod_lines:
                print(f"                    {line}")
        else:
            print("                    (none — namespace may not exist yet)")
    return 0


def cmd_edge_k8s_logs(args: argparse.Namespace) -> int:
    """Stream pod logs for a named Collibra Edge component."""
    ns = args.namespace
    component = args.component

    # Label selector varies by component
    label_map = {
        "edge-proxy":          "app=edge-proxy",
        "edge-controller":     "app=edge-controller",
        "edge-cd":             "app=edge-cd",
        "edge-session-manager":"app=edge-session-manager",
        "otel-agent":          "app.kubernetes.io/name=opentelemetry-collector",
    }
    selector = label_map.get(component, f"app={component}")

    cmd = ["kubectl", "logs", "-n", ns, "-l", selector,
           "--prefix", "--tail", str(args.tail)]
    if args.follow:
        cmd.append("-f")

    return subprocess.run(cmd, text=True).returncode


# ── K8s test suite ────────────────────────────────────────────────────────────

def _k8s_namespace_exists(ns: str) -> bool:
    r = subprocess.run(
        ["kubectl", "get", "namespace", ns],
        capture_output=True, text=True,
    )
    return r.returncode == 0


def _kubectl_json(args_list: List[str]) -> Any:
    r = subprocess.run(
        ["kubectl"] + args_list + ["-o", "json"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


# Pods that must be Running for the edge site to pulse on lutino.collibra.com
# Labels from the Collibra Edge Helm chart (app.kubernetes.io/name)
_CRITICAL_PODS = {
    "edge-proxy":                   "app.kubernetes.io/name=collibra-edge-proxy",
    "edge-controller":              "app.kubernetes.io/name=collibra-edge-controller",
    "edge-session-manager":         "app.kubernetes.io/name=edge-session-manager",
    "collibra-edge-objects-server": "app.kubernetes.io/name=edge-objects-server",
}
# Pods that are useful but not required for the core pulse
_OPTIONAL_PODS = {
    "collibra-otel-agent": "app.kubernetes.io/name=opentelemetry-collector",
    "collibra-edge-cd":    "app.kubernetes.io/name=edge-cd",
}

_FILE_SYNC_COMPONENTS = {
    **_CRITICAL_PODS,
    **_OPTIONAL_PODS,
}


def _pod_phase(ns: str, label: str) -> str:
    """Return phase string of the first pod matching label, or 'not found'."""
    data = _kubectl_json(["get", "pods", "-n", ns, "-l", label])
    if not data:
        return "not found"
    items = data.get("items", [])
    if not items:
        return "not found"
    return items[0].get("status", {}).get("phase", "Unknown")


def _component_label(component: str) -> Optional[str]:
    return _FILE_SYNC_COMPONENTS.get(component)


def _first_running_pod(ns: str, label: str) -> Optional[str]:
    data = _kubectl_json(["get", "pods", "-n", ns, "-l", label])
    if not data:
        return None
    items = data.get("items", [])
    if not items:
        return None
    running = [
        item["metadata"]["name"]
        for item in items
        if item.get("status", {}).get("phase") == "Running"
    ]
    if running:
        return running[0]
    return items[0].get("metadata", {}).get("name")


def _kubectl_exec(
    ns: str,
    pod: str,
    argv: Sequence[str],
    *,
    capture: bool = False,
    input_bytes: Optional[bytes] = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["kubectl", "exec", "-n", ns, "-i", pod, "--", *argv],
        capture_output=capture,
        text=False,
        input=input_bytes,
    )


def _remote_mkdir(ns: str, pod: str, remote_dir: str) -> subprocess.CompletedProcess:
    return _kubectl_exec(
        ns,
        pod,
        ["sh", "-lc", 'mkdir -p "$1"', "sh", remote_dir],
    )


def _copy_file_to_pod(ns: str, pod: str, local_path: Path, remote_path: str) -> subprocess.CompletedProcess:
    with local_path.open("rb") as handle:
        data = handle.read()
    return _kubectl_exec(
        ns,
        pod,
        ["sh", "-lc", 'cat > "$1"', "sh", remote_path],
        input_bytes=data,
    )


def _remote_file_size(ns: str, pod: str, remote_path: str) -> Optional[int]:
    result = _kubectl_exec(
        ns,
        pod,
        ["sh", "-lc", 'wc -c < "$1"', "sh", remote_path],
        capture=True,
    )
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.decode().strip())
    except ValueError:
        return None


def _sync_manifest(source: Path, dest: str) -> List[Tuple[Path, str]]:
    if source.is_file():
        remote_path = dest
        if dest.endswith("/"):
            remote_path = posixpath.join(dest, source.name)
        return [(source, remote_path)]

    manifest: List[Tuple[Path, str]] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(source).as_posix()
        manifest.append((path, posixpath.join(dest, rel)))
    return manifest


def cmd_edge_files_sync(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser()
    ns = args.namespace
    component = args.component
    dest = args.dest
    use_json = args.json

    if not source.exists():
        msg = f"Local source not found: {source}"
        if use_json:
            print(json.dumps(_envelope(False, "edge files sync", error=msg)))
        else:
            print(f"[edge files sync] ERROR: {msg}", file=sys.stderr)
        return 1

    selector = _component_label(component)
    if not selector:
        msg = f"Unsupported component: {component}"
        if use_json:
            print(json.dumps(_envelope(False, "edge files sync", error=msg)))
        else:
            print(f"[edge files sync] ERROR: {msg}", file=sys.stderr)
        return 1

    pod = args.pod or _first_running_pod(ns, selector)
    if not pod:
        msg = f"No pod found for component {component} in namespace {ns}"
        if use_json:
            print(json.dumps(_envelope(False, "edge files sync", error=msg)))
        else:
            print(f"[edge files sync] ERROR: {msg}", file=sys.stderr)
        return 1

    manifest = _sync_manifest(source, dest)
    total_bytes = sum(path.stat().st_size for path, _ in manifest)

    if not use_json:
        print(
            f"[edge files sync] source={source} pod={pod} component={component} "
            f"dest={dest} files={len(manifest)} bytes={total_bytes}"
        )

    if args.dry_run:
        preview = [{"local": str(path), "remote": remote} for path, remote in manifest]
        if use_json:
            print(json.dumps(_envelope(
                True,
                "edge files sync",
                namespace=ns,
                component=component,
                pod=pod,
                source=str(source),
                dest=dest,
                files=preview,
                dry_run=True,
            )))
        else:
            for item in preview:
                print(f"  {item['local']} -> {item['remote']}")
        return 0

    mkdirs = {posixpath.dirname(remote) or "/" for _, remote in manifest}
    if source.is_dir():
        mkdirs.add(dest)
    for remote_dir in sorted(mkdirs):
        result = _remote_mkdir(ns, pod, remote_dir)
        if result.returncode != 0:
            msg = f"mkdir failed for {remote_dir}"
            if use_json:
                print(json.dumps(_envelope(False, "edge files sync", error=msg, pod=pod, namespace=ns)))
            else:
                print(f"[edge files sync] ERROR: {msg}", file=sys.stderr)
            return result.returncode

    copied: List[Dict[str, Any]] = []
    for local_path, remote_path in manifest:
        result = _copy_file_to_pod(ns, pod, local_path, remote_path)
        if result.returncode != 0:
            msg = f"copy failed for {local_path} -> {remote_path}"
            if use_json:
                print(json.dumps(_envelope(False, "edge files sync", error=msg, pod=pod, namespace=ns)))
            else:
                print(f"[edge files sync] ERROR: {msg}", file=sys.stderr)
            return result.returncode
        remote_size = _remote_file_size(ns, pod, remote_path)
        copied.append({
            "local": str(local_path),
            "remote": remote_path,
            "bytes": local_path.stat().st_size,
            "remote_bytes": remote_size,
        })

    if use_json:
        print(json.dumps(_envelope(
            True,
            "edge files sync",
            namespace=ns,
            component=component,
            pod=pod,
            source=str(source),
            dest=dest,
            file_count=len(copied),
            bytes=total_bytes,
            copied=copied,
        )))
    else:
        print(f"[edge files sync] synced {len(copied)} file(s) into {pod}:{dest}")
    return 0


def cmd_edge_files_ls(args: argparse.Namespace) -> int:
    ns = args.namespace
    component = args.component
    use_json = args.json

    selector = _component_label(component)
    if not selector:
        msg = f"Unsupported component: {component}"
        if use_json:
            print(json.dumps(_envelope(False, "edge files ls", error=msg)))
        else:
            print(f"[edge files ls] ERROR: {msg}", file=sys.stderr)
        return 1

    pod = args.pod or _first_running_pod(ns, selector)
    if not pod:
        msg = f"No pod found for component {component} in namespace {ns}"
        if use_json:
            print(json.dumps(_envelope(False, "edge files ls", error=msg)))
        else:
            print(f"[edge files ls] ERROR: {msg}", file=sys.stderr)
        return 1

    result = _kubectl_exec(
        ns,
        pod,
        ["sh", "-lc", 'ls -la "$1"', "sh", args.path],
        capture=True,
    )
    output = result.stdout.decode(errors="replace")
    if use_json:
        print(json.dumps(_envelope(
            result.returncode == 0,
            "edge files ls",
            namespace=ns,
            component=component,
            pod=pod,
            path=args.path,
            output=output,
        )))
    else:
        print(output, end="" if output.endswith("\n") else "\n")
    return result.returncode


def _pod_logs_recent(ns: str, label: str, lines: int = 200) -> str:
    r = subprocess.run(
        ["kubectl", "logs", "-n", ns, "-l", label,
         "--tail", str(lines), "--container-name-pattern", ".*"],
        capture_output=True, text=True,
    )
    # fallback without container filter
    if r.returncode != 0:
        r = subprocess.run(
            ["kubectl", "logs", "-n", ns, "-l", label, "--tail", str(lines)],
            capture_output=True, text=True,
        )
    return r.stdout


def cmd_edge_k8s_test(args: argparse.Namespace) -> int:
    """Test suite for the real Collibra Edge K8s deployment.

    Checks:
      1. kubectl cluster reachable
      2. Helm release collibra-edge: deployed
      3-6. Critical pods Running: edge-proxy, edge-controller,
           edge-session-manager, collibra-edge-objects-server
      7. edge-proxy: OAuth token refreshed (logs)
      8. edge-controller: heartbeat sent to lutino.collibra.com (logs)
      9. edge-controller: no heartbeat errors (last 5 min)
      10. Optional pods: otel-agent, collibra-edge-cd
    """
    ns = args.namespace
    use_json = args.json

    results: List[Dict[str, Any]] = []
    overall_ok = True

    def _check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal overall_ok
        if not ok:
            overall_ok = False
        results.append({"test": name, "ok": ok, "detail": detail})
        if not use_json:
            icon = "✓" if ok else "✗"
            suffix = f"  {detail}" if detail and not ok else (f"  {detail}" if detail and ok else "")
            print(f"  {icon}  {name}{suffix}")

    if not use_json:
        print(f"\n[edge k8s test] namespace={ns}")
        print(f"[edge k8s test] ── Cluster & release ────────────────────────")

    # 1. Cluster reachable
    r = subprocess.run(["kubectl", "cluster-info"], capture_output=True, text=True)
    _check("kubectl cluster reachable", r.returncode == 0,
           "cluster-info failed" if r.returncode != 0 else "")

    # 2. Namespace exists
    ns_ok = _k8s_namespace_exists(ns)
    _check(f"namespace {ns} exists", ns_ok, "not found" if not ns_ok else "")

    # 3. Helm release deployed
    helm_r = subprocess.run(
        ["helm", "status", "collibra-edge", "-n", ns, "--output", "json"],
        capture_output=True, text=True,
    )
    helm_status = ""
    helm_version = ""
    if helm_r.returncode == 0:
        try:
            hd = json.loads(helm_r.stdout)
            helm_status = hd.get("info", {}).get("status", "")
            helm_version = hd.get("chart", {}).get("metadata", {}).get("version", "")
        except json.JSONDecodeError:
            pass
    helm_deployed = helm_status == "deployed"
    _check("helm release: deployed",
           helm_deployed,
           f"status={helm_status or 'not installed'}  version={helm_version}" if not helm_deployed
           else f"version={helm_version}")

    if not use_json:
        print(f"[edge k8s test] ── Critical pods ─────────────────────────────")

    # 4-7. Critical pods Running
    pod_phases: Dict[str, str] = {}
    for pod_name, label in _CRITICAL_PODS.items():
        phase = _pod_phase(ns, label)
        pod_phases[pod_name] = phase
        _check(f"pod:{pod_name} Running", phase == "Running",
               f"phase={phase}" if phase != "Running" else "")

    if not use_json:
        print(f"[edge k8s test] ── Heartbeat & auth ──────────────────────────")

    # 8. edge-proxy: OAuth token refreshed
    if pod_phases.get("edge-proxy") == "Running":
        proxy_logs = _pod_logs_recent(ns, "app.kubernetes.io/name=collibra-edge-proxy", lines=300)
        oauth_ok = "OAuth Token refreshed successfully" in proxy_logs
        _check("edge-proxy: OAuth token refreshed", oauth_ok,
               "not seen in recent logs" if not oauth_ok else "")

        # Check proxy is polling lutino (not just getting timeout errors)
        polling_started = "Started polling thread on:" in proxy_logs
        _check("edge-proxy: polling lutino.collibra.com", polling_started,
               "polling start message not found" if not polling_started else "")
    else:
        _check("edge-proxy: OAuth token refreshed", False, "pod not Running — skipped")
        _check("edge-proxy: polling lutino.collibra.com", False, "pod not Running — skipped")

    # 9. edge-controller: heartbeat sent
    # 10. edge-controller: no heartbeat errors
    if pod_phases.get("edge-controller") == "Running":
        ctrl_logs = _pod_logs_recent(ns, "app.kubernetes.io/name=collibra-edge-controller", lines=300)
        hb_ok = "Sending a controller heartbeat from siteId:" in ctrl_logs
        _check("edge-controller: heartbeat sent", hb_ok,
               "heartbeat message not found in recent logs" if not hb_ok else "")

        # Count heartbeat lines and look for errors immediately after
        hb_lines = [l for l in ctrl_logs.splitlines() if "heartbeat" in l.lower()]
        hb_error_lines = [l for l in hb_lines if '"level":"ERROR"' in l or '"level":"WARN"' in l]
        no_hb_errors = len(hb_error_lines) == 0
        _check("edge-controller: heartbeat no errors",
               no_hb_errors,
               f"{len(hb_error_lines)} error(s) in heartbeat lines" if not no_hb_errors else
               f"{len(hb_lines)} heartbeat(s) sent")
    else:
        _check("edge-controller: heartbeat sent", False, "pod not Running — skipped")
        _check("edge-controller: heartbeat no errors", False, "pod not Running — skipped")

    if not use_json:
        print(f"[edge k8s test] ── Optional pods ────────────────────────────")

    # 11-12. Optional pods (warn but don't fail)
    for pod_name, label in _OPTIONAL_PODS.items():
        phase = _pod_phase(ns, label)
        running = phase == "Running"
        # Mark optional failures as ok=True with detail note
        _check(f"pod:{pod_name} Running (optional)", running,
               f"phase={phase} (non-blocking)" if not running else "")
        if not running:
            # Don't count optional failures against overall
            results[-1]["optional"] = True
            overall_ok = overall_ok  # unchanged

    # Re-evaluate overall_ok excluding optional checks
    overall_ok = all(r["ok"] for r in results if not r.get("optional"))

    passed = sum(1 for r in results if r["ok"])
    total = len(results)

    if use_json:
        print(json.dumps(_envelope(
            overall_ok, "edge k8s test",
            namespace=ns,
            passed=passed,
            total=total,
            results=results,
        )))
    else:
        print(f"\n[edge k8s test] {'PASSED' if overall_ok else 'FAILED'}  {passed}/{total} checks")
        if not overall_ok:
            failed = [r for r in results if not r["ok"] and not r.get("optional")]
            print(f"[edge k8s test] Failed checks:")
            for r in failed:
                print(f"  ✗  {r['test']}  {r.get('detail', '')}")
        return 0 if overall_ok else 1

    return 0 if overall_ok else 1


# ── Cloud mode up ─────────────────────────────────────────────────────────────

def cmd_edge_cloud(args: argparse.Namespace) -> int:
    """Start the edge stack in cloud mode (docker-compose.cloud.yml → lutino.collibra.com)."""
    edge = _edge_dir()
    compose_file = edge / "docker-compose.cloud.yml"
    env_file = edge / ".env"
    use_json = args.json

    if not compose_file.exists():
        msg = f"Cloud compose file not found: {compose_file}"
        if use_json:
            print(json.dumps(_envelope(False, "edge cloud", error=msg)))
        else:
            print(f"[edge cloud] ERROR: {msg}", file=sys.stderr)
        return 1

    cmd = ["docker", "compose", "-f", str(compose_file)]
    if env_file.exists():
        cmd += ["--env-file", str(env_file)]
    cmd += ["up", "-d"]

    print(f"[edge cloud] starting cloud stack → lutino.collibra.com")
    result = subprocess.run(cmd, cwd=str(edge), text=True)
    ok = result.returncode == 0
    if use_json:
        print(json.dumps(_envelope(ok, "edge cloud", exit_code=result.returncode)))
    elif ok:
        print("[edge cloud] stack up — test with: singine edge test")
    else:
        print(f"[edge cloud] FAILED (exit {result.returncode})", file=sys.stderr)
    return result.returncode


def cmd_edge_site_init(args: argparse.Namespace) -> int:
    """Bootstrap a real Collibra Edge site from the installer bundle."""
    edge = _edge_dir(args)
    installer = _installer_dir(args)
    use_json = getattr(args, "json", False)
    name = getattr(args, "name", "edge-site")
    namespace = getattr(args, "namespace", _K8S_NAMESPACE)
    dry_run = getattr(args, "dry_run", False)
    keep_dev = getattr(args, "keep_dev_stack", False)
    steps: List[Dict[str, Any]] = []

    def _step(step_name: str, func, ns: argparse.Namespace) -> bool:
        rc = func(ns)
        ok = rc == 0
        steps.append({"step": step_name, "ok": ok, "exit_code": rc})
        return ok

    if not edge.exists():
        msg = f"Edge directory not found: {edge}"
        if use_json:
            print(json.dumps(_envelope(False, "edge site init", error=msg)))
        else:
            print(f"[edge site init] ERROR: {msg}", file=sys.stderr)
        return 1

    if not installer.exists():
        msg = f"Installer directory not found: {installer}"
        if use_json:
            print(json.dumps(_envelope(False, "edge site init", error=msg)))
        else:
            print(f"[edge site init] ERROR: {msg}", file=sys.stderr)
        return 1

    if not use_json:
        print(f"[edge site init] site={name}  edge_dir={edge}")
        print(f"[edge site init] installer={installer}  namespace={namespace}  dry_run={dry_run}")

    if not keep_dev:
        for compose_name in ("docker-compose.dev.yml", "docker-compose.cloud.yml", "docker-compose.yml"):
            rc = _compose_down_if_present(edge, compose_name)
            steps.append({
                "step": f"docker down {compose_name}",
                "ok": rc == 0,
                "exit_code": rc,
                "optional": True,
            })
            if rc != 0 and not use_json:
                print(f"[edge site init] WARN: unable to stop {compose_name} cleanly (exit {rc})", file=sys.stderr)

    prereq_args = argparse.Namespace(
        json=use_json,
        edge_dir=str(edge),
        installer_dir=str(installer),
    )
    if not _step("k8s prereqs", cmd_edge_k8s_prereqs, prereq_args):
        if use_json:
            print(json.dumps(_envelope(False, "edge site init", name=name, steps=steps)))
        return 1

    install_args = argparse.Namespace(
        dry_run=dry_run,
        json=use_json,
        edge_dir=str(edge),
        installer_dir=str(installer),
    )
    if not _step("k8s install", cmd_edge_k8s_install, install_args):
        if use_json:
            print(json.dumps(_envelope(False, "edge site init", name=name, steps=steps)))
        return 1

    if not dry_run:
        status_args = argparse.Namespace(namespace=namespace, json=use_json)
        if not _step("k8s status", cmd_edge_k8s_status, status_args):
            if use_json:
                print(json.dumps(_envelope(False, "edge site init", name=name, steps=steps)))
            return 1

        test_args = argparse.Namespace(namespace=namespace, json=use_json)
        if not _step("k8s test", cmd_edge_k8s_test, test_args):
            if use_json:
                print(json.dumps(_envelope(False, "edge site init", name=name, steps=steps)))
            return 1

    ok = all(step["ok"] for step in steps if not step.get("optional"))
    if use_json:
        print(json.dumps(_envelope(ok, "edge site init", name=name, namespace=namespace, steps=steps)))
    else:
        print(f"[edge site init] {'complete' if ok else 'failed'} — namespace={namespace}")
    return 0 if ok else 1


# ── Test suite ────────────────────────────────────────────────────────────────

def cmd_edge_test(args: argparse.Namespace) -> int:
    """Run a full test suite against the running edge stack.

    Checks:
      - Containers healthy (via docker compose ps)
      - GET /health
      - GET /api/edge/v1/status  (validates dgcUrl, siteId, capabilities)
      - GET /api/edge/v1/capabilities  (validates all three are READY)
      - GET /api/edge/v1/pulse  (validates pulse endpoint exists)
      - POST /api/edge/v1/pulse  (manual trigger)
      - POST /api/edge/v1/capabilities/catalog/invoke
      - POST /api/edge/v1/capabilities/connect/invoke
      - POST /api/edge/v1/capabilities/site/invoke
      - GET  /site/  (static content)
    """
    import urllib.request
    import urllib.error
    import ssl

    base_url = args.url.rstrip("/")
    use_json = args.json
    skip_tls = args.skip_tls_verify
    edge = _edge_dir()

    results: List[Dict[str, Any]] = []
    overall_ok = True

    # TLS context (skip verify for self-signed dev certs)
    ctx = ssl.create_default_context()
    if skip_tls:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    def _http(method: str, path: str, body: Optional[bytes] = None) -> tuple:
        """Return (status_code, parsed_json_or_None, error_str_or_None)."""
        url = base_url + path
        try:
            req = urllib.request.Request(
                url,
                data=body,
                method=method,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
                try:
                    return resp.status, json.loads(raw), None
                except json.JSONDecodeError:
                    return resp.status, raw, None
        except urllib.error.HTTPError as e:
            return e.code, None, str(e)
        except Exception as exc:
            return 0, None, str(exc)

    def _check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal overall_ok
        if not ok:
            overall_ok = False
        results.append({"test": name, "ok": ok, "detail": detail})
        if not use_json:
            icon = "✓" if ok else "✗"
            suffix = f"  {detail}" if detail and not ok else ""
            print(f"  {icon}  {name}{suffix}")

    # ── 0. Containers running ─────────────────────────────────────────────────
    if not use_json:
        print(f"\n[edge test] base_url={base_url}  skip_tls={skip_tls}")
        print(f"[edge test] ── Container health ──────────────────────────")

    for compose_file in ["docker-compose.cloud.yml", "docker-compose.dev.yml", "docker-compose.yml"]:
        cf = edge / compose_file
        if not cf.exists():
            continue
        r = subprocess.run(
            ["docker", "compose", "-f", str(cf), "ps", "--format", "json"],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and r.stdout.strip():
            try:
                raw_services = r.stdout.strip().splitlines()
                services = []
                for line in raw_services:
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, list):
                            services.extend(obj)
                        else:
                            services.append(obj)
                    except json.JSONDecodeError:
                        pass
                for svc in services:
                    name = svc.get("Service") or svc.get("Name", "?")
                    health = svc.get("Health", "")
                    state = svc.get("State", "?")
                    is_ok = health == "healthy" or (state == "running" and health == "")
                    _check(f"container:{name}", is_ok, f"state={state} health={health}")
            except Exception:
                pass
            break

    # ── 1. Health ─────────────────────────────────────────────────────────────
    if not use_json:
        print(f"[edge test] ── API endpoints ─────────────────────────────")

    status, body, err = _http("GET", "/health")
    health_ok = status == 200 and isinstance(body, dict) and body.get("status") == "UP"
    _check("GET /health → UP", health_ok, err or (str(status) if not health_ok else ""))

    # ── 2. Status ─────────────────────────────────────────────────────────────
    status, body, err = _http("GET", "/api/edge/v1/status")
    status_ok = status == 200 and isinstance(body, dict) and body.get("status") == "READY"
    site_id = body.get("siteId", "") if isinstance(body, dict) else ""
    dgc_url = body.get("dgcUrl", "") if isinstance(body, dict) else ""
    _check("GET /api/edge/v1/status → READY", status_ok,
           err or (f"status={body.get('status') if isinstance(body, dict) else 'unknown'}" if not status_ok else ""))
    _check("status.siteId present", bool(site_id), site_id or "missing")
    _check("status.dgcUrl present", bool(dgc_url), dgc_url or "missing")
    _check("status.pulseState present",
           isinstance(body, dict) and "pulseState" in body,
           "pulseState field missing" if not (isinstance(body, dict) and "pulseState" in body) else body.get("pulseState", ""))

    # ── 3. Capabilities ───────────────────────────────────────────────────────
    status, body, err = _http("GET", "/api/edge/v1/capabilities")
    caps_ok = status == 200 and isinstance(body, list) and len(body) > 0
    _check("GET /api/edge/v1/capabilities → list", caps_ok, err or "")
    if caps_ok:
        cap_types = {c.get("type") for c in body if isinstance(c, dict)}
        for expected in ("site", "connect", "catalog"):
            ready = any(
                c.get("type") == expected and c.get("status") == "READY"
                for c in body if isinstance(c, dict)
            )
            _check(f"capability:{expected} → READY", ready, "not found or not READY" if not ready else "")

    # ── 4. Pulse endpoint ─────────────────────────────────────────────────────
    status, body, err = _http("GET", "/api/edge/v1/pulse")
    pulse_ok = status == 200 and isinstance(body, dict) and "pulseState" in body
    _check("GET /api/edge/v1/pulse", pulse_ok, err or "")

    status, body, err = _http(
        "POST", "/api/edge/v1/pulse", body=b"{}"
    )
    pulse_post_ok = status == 200 and isinstance(body, dict) and body.get("pulseState") == "PULSING"
    _check("POST /api/edge/v1/pulse → PULSING", pulse_post_ok, err or "")

    # ── 5. Capability invocations ─────────────────────────────────────────────
    for cap in ("catalog", "connect", "site"):
        payload = json.dumps({"action": "ping", "params": {}}).encode()
        status, body, err = _http(
            "POST", f"/api/edge/v1/capabilities/{cap}/invoke", body=payload
        )
        invoke_ok = (
            status == 200
            and isinstance(body, dict)
            and body.get("success") is True
        )
        _check(f"POST /api/edge/v1/capabilities/{cap}/invoke", invoke_ok, err or "")

    # ── 6. Static site content ────────────────────────────────────────────────
    status, body, err = _http("GET", "/site/")
    site_ok = status == 200
    _check("GET /site/ → 200", site_ok, err or str(status) if not site_ok else "")

    # ── 7. K8s edge stack (auto-detected or --k8s flag) ───────────────────────
    run_k8s = getattr(args, "k8s", False)
    if not run_k8s:
        # auto-detect: check if kubectl is available and namespace exists
        kc = subprocess.run(["which", "kubectl"], capture_output=True, text=True)
        if kc.returncode == 0 and _k8s_namespace_exists(_K8S_NAMESPACE):
            run_k8s = True

    if run_k8s:
        if not use_json:
            print(f"[edge test] ── K8s edge stack ({_K8S_NAMESPACE}) ─────────────────")
        # Run k8s checks and merge results
        k8s_ns = argparse.Namespace(namespace=_K8S_NAMESPACE, json=False)
        _orig_print = None
        # Collect k8s results without re-printing header
        k8s_results: List[Dict[str, Any]] = []
        k8s_ok = True

        def _k8s_check(name: str, ok: bool, detail: str = "") -> None:
            nonlocal k8s_ok
            if not ok and not name.startswith("pod:collibra-otel") and not name.startswith("pod:collibra-edge-cd"):
                k8s_ok = False
            k8s_results.append({"test": f"k8s/{name}", "ok": ok, "detail": detail,
                                 "optional": name.endswith("(optional)")})
            if not use_json:
                icon = "✓" if ok else "✗"
                suffix = f"  {detail}" if detail else ""
                print(f"  {icon}  k8s/{name}{suffix}")

        # cluster
        r = subprocess.run(["kubectl", "cluster-info"], capture_output=True, text=True)
        _k8s_check("cluster reachable", r.returncode == 0)

        # helm release
        helm_r = subprocess.run(
            ["helm", "status", "collibra-edge", "-n", _K8S_NAMESPACE, "--output", "json"],
            capture_output=True, text=True,
        )
        helm_status_str = ""
        if helm_r.returncode == 0:
            try:
                hd = json.loads(helm_r.stdout)
                helm_status_str = hd.get("info", {}).get("status", "")
            except json.JSONDecodeError:
                pass
        _k8s_check("helm:collibra-edge deployed", helm_status_str == "deployed",
                   f"status={helm_status_str or 'not installed'}")

        # critical pods
        for pod_name, label in _CRITICAL_PODS.items():
            phase = _pod_phase(_K8S_NAMESPACE, label)
            _k8s_check(f"pod:{pod_name} Running", phase == "Running",
                       f"phase={phase}" if phase != "Running" else "")

        # heartbeat
        ctrl_logs = _pod_logs_recent(_K8S_NAMESPACE, "app.kubernetes.io/name=collibra-edge-controller", lines=300)
        hb_sent = "Sending a controller heartbeat from siteId:" in ctrl_logs
        _k8s_check("edge-controller heartbeat sent", hb_sent,
                   "not seen in recent logs" if not hb_sent else "")
        hb_err_lines = [l for l in ctrl_logs.splitlines()
                        if "heartbeat" in l.lower() and '"level":"ERROR"' in l]
        _k8s_check("edge-controller heartbeat no errors", len(hb_err_lines) == 0,
                   f"{len(hb_err_lines)} error(s)" if hb_err_lines else "")

        # oauth
        proxy_logs = _pod_logs_recent(_K8S_NAMESPACE, "app.kubernetes.io/name=collibra-edge-proxy", lines=300)
        oauth_ok = "OAuth Token refreshed successfully" in proxy_logs
        _k8s_check("edge-proxy OAuth token refreshed", oauth_ok,
                   "not seen in recent logs" if not oauth_ok else "")

        results.extend(k8s_results)
        if not k8s_ok:
            overall_ok = False

    # ── Summary ───────────────────────────────────────────────────────────────
    passed = sum(1 for r in results if r["ok"])
    total = len(results)

    if use_json:
        print(json.dumps(_envelope(
            overall_ok, "edge test",
            base_url=base_url,
            passed=passed,
            total=total,
            results=results,
        )))
    else:
        print(f"\n[edge test] {'PASSED' if overall_ok else 'FAILED'}  {passed}/{total} checks")
        if not overall_ok:
            failed = [r for r in results if not r["ok"] and not r.get("optional")]
            print(f"[edge test] Failed checks:")
            for r in failed:
                print(f"  ✗  {r['test']}  {r.get('detail', '')}")
            return 1

    return 0 if overall_ok else 1


# ── Parser registration ───────────────────────────────────────────────────────

def add_edge_parser(sub: argparse._SubParsersAction, *, name: str = "edge", help: str = None) -> None:
    """Register ``singine edge`` and all its subcommand families.

    Parameters
    ----------
    sub:
        The _SubParsersAction to attach the edge parser to.
    name:
        Parser name (default: ``"edge"``).  Pass ``"edge"`` when registering
        the top-level ``singine edge`` command; pass any other name when
        reusing the parser under a different parent (e.g. ``singine collibra edge``).
    help:
        Help text override.  Defaults to the standard edge lifecycle description.
    """

    edge_parser = sub.add_parser(
        name,
        help=help or "Collibra edge server lifecycle — build, deploy, and manage the CDN + DGC edge stack",
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
        choices=["edge-site", "collibra-edge", "cdn"],
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

    # ── setup ─────────────────────────────────────────────────────────────────
    p = edge_sub.add_parser(
        "setup",
        help="Full automated setup: certs, .env, JAR, images, launch (runs scripts/setup.sh)",
    )
    p.add_argument("--dev", action="store_true",
                   help="Use mock DGC edge (auto-enabled when collibra-edge.jar is absent)")
    p.add_argument("--no-start", action="store_true", dest="no_start",
                   help="Build and prepare but do not start the stack")
    p.add_argument("--tag", default="local", help="Image tag (default: local)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_setup)

    # ── javadoc ───────────────────────────────────────────────────────────────
    p = edge_sub.add_parser(
        "javadoc",
        help="Build Javadoc for the edge Java interface layer (edge/java/)",
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_javadoc)

    # ── deploy ────────────────────────────────────────────────────────────────
    p = edge_sub.add_parser(
        "deploy",
        help="Install + start stack (full bring-up from scratch)",
    )
    p.add_argument("--tag", default="local", help="Image tag (default: local)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_deploy)

    # ── cloud ─────────────────────────────────────────────────────────────────
    p = edge_sub.add_parser(
        "cloud",
        help="Start the edge stack in cloud mode (docker-compose.cloud.yml → lutino.collibra.com)",
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_cloud)

    # ── site init ─────────────────────────────────────────────────────────────
    site_parser = edge_sub.add_parser(
        "site",
        help="Installer-backed Edge site bootstrap and verification",
    )
    site_parser.set_defaults(func=lambda a: (site_parser.print_help(), 1)[1])
    site_sub = site_parser.add_subparsers(dest="edge_site_command")

    p = site_sub.add_parser(
        "init",
        help="Deploy the official Collibra Edge site from installer/ and verify it",
    )
    p.add_argument("name", help="Local site label for this bootstrap run")
    p.add_argument("--edge-dir", default=str(_DEFAULT_EDGE_DIR),
                   help=f"Edge project root (default: {_DEFAULT_EDGE_DIR})")
    p.add_argument("--installer-dir", help="Installer bundle directory (default: <edge-dir>/installer)")
    p.add_argument("--namespace", default=_K8S_NAMESPACE,
                   help=f"Kubernetes namespace (default: {_K8S_NAMESPACE})")
    p.add_argument("--keep-dev-stack", action="store_true",
                   help="Do not stop existing docker-compose edge stacks before bootstrap")
    p.add_argument("--dry-run", action="store_true", help="Render/install without mutating the cluster")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_site_init)

    # ── files ────────────────────────────────────────────────────────────────
    files_parser = edge_sub.add_parser(
        "files",
        help="Copy local files into a live Collibra Edge Kubernetes pod",
    )
    files_parser.set_defaults(func=lambda a: (files_parser.print_help(), 1)[1])
    files_sub = files_parser.add_subparsers(dest="edge_files_action")

    p = files_sub.add_parser(
        "sync",
        help="Sync a local file or directory into a running edge pod",
    )
    p.add_argument("source", help="Local file or directory to copy")
    p.add_argument("--component", default="collibra-edge-objects-server",
                   choices=sorted(_FILE_SYNC_COMPONENTS),
                   help="Target edge component (default: collibra-edge-objects-server)")
    p.add_argument("--namespace", default=_K8S_NAMESPACE,
                   help=f"Kubernetes namespace (default: {_K8S_NAMESPACE})")
    p.add_argument("--pod", help="Specific pod name override")
    p.add_argument("--dest", default="/tmp/singine",
                   help="Remote destination path inside the pod (default: /tmp/singine)")
    p.add_argument("--dry-run", action="store_true", help="Print the copy plan without writing to the pod")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_files_sync)

    p = files_sub.add_parser(
        "ls",
        help="List files inside a running edge pod",
    )
    p.add_argument("path", nargs="?", default="/tmp/singine",
                   help="Remote path to inspect (default: /tmp/singine)")
    p.add_argument("--component", default="collibra-edge-objects-server",
                   choices=sorted(_FILE_SYNC_COMPONENTS),
                   help="Target edge component (default: collibra-edge-objects-server)")
    p.add_argument("--namespace", default=_K8S_NAMESPACE,
                   help=f"Kubernetes namespace (default: {_K8S_NAMESPACE})")
    p.add_argument("--pod", help="Specific pod name override")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_files_ls)

    # ── test ──────────────────────────────────────────────────────────────────
    p = edge_sub.add_parser(
        "test",
        help="Run the full edge API test suite against the running stack",
    )
    p.add_argument(
        "--url",
        default="https://localhost",
        metavar="URL",
        help="Base URL of the edge CDN (default: https://localhost)",
    )
    p.add_argument(
        "--skip-tls-verify", "-k",
        action="store_true",
        dest="skip_tls_verify",
        help="Skip TLS certificate verification (for self-signed certs, default: True)",
        default=True,
    )
    k8s_group = p.add_mutually_exclusive_group()
    k8s_group.add_argument(
        "--k8s",
        action="store_true",
        dest="k8s",
        default=False,
        help="Force-include K8s edge pod checks (auto-detected when namespace exists)",
    )
    k8s_group.add_argument(
        "--no-k8s",
        action="store_false",
        dest="k8s",
        help="Skip K8s edge pod checks",
    )
    p.add_argument("--json", action="store_true", help="Emit JSON envelope with full test results")
    p.set_defaults(func=cmd_edge_test)

    # ── k8s ───────────────────────────────────────────────────────────────────
    k8s_parser = edge_sub.add_parser(
        "k8s",
        help="Deploy the real Collibra Edge onto Kubernetes (Docker Desktop, EKS, GKE, AKS)",
    )
    k8s_parser.set_defaults(func=lambda a: (k8s_parser.print_help(), 1)[1])
    k8s_sub = k8s_parser.add_subparsers(dest="edge_k8s_action")

    p = k8s_sub.add_parser(
        "prereqs",
        help="Verify helm/kubectl/jq/yq are installed and the K8s cluster is reachable",
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_k8s_prereqs)

    p = k8s_sub.add_parser(
        "install",
        help="Deploy Collibra Edge via Helm into the collibra-edge namespace",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Validate charts and print what would be installed without making changes",
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_k8s_install)

    p = k8s_sub.add_parser(
        "uninstall",
        help="Helm uninstall collibra-edge and delete the namespace",
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_k8s_uninstall)

    p = k8s_sub.add_parser(
        "status",
        help="Show Helm release status and pod health in the collibra-edge namespace",
    )
    p.add_argument(
        "--namespace", "-n",
        default=_K8S_NAMESPACE,
        help=f"Kubernetes namespace (default: {_K8S_NAMESPACE})",
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_k8s_status)

    p = k8s_sub.add_parser(
        "test",
        help="Run the K8s edge test suite: pod health, heartbeat, OAuth token",
    )
    p.add_argument(
        "--namespace", "-n",
        default=_K8S_NAMESPACE,
        help=f"Kubernetes namespace (default: {_K8S_NAMESPACE})",
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_edge_k8s_test)

    p = k8s_sub.add_parser(
        "logs",
        help="Stream logs from a Collibra Edge pod component",
    )
    p.add_argument(
        "component",
        choices=["edge-proxy", "edge-controller", "edge-cd",
                 "edge-session-manager", "otel-agent"],
        help="Which edge component to stream logs from",
    )
    p.add_argument(
        "--namespace", "-n",
        default=_K8S_NAMESPACE,
        help=f"Kubernetes namespace (default: {_K8S_NAMESPACE})",
    )
    p.add_argument("--follow", "-f", action="store_true", help="Follow log output")
    p.add_argument("--tail", type=int, default=100, metavar="N",
                   help="Number of lines to show from end (default: 100)")
    p.set_defaults(func=cmd_edge_k8s_logs)

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
