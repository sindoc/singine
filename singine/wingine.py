"""
singine wingine — web engine: build and local-serve pipeline.

Commands:
    singine wingine build  --site markupware.com [--clean]
    singine wingine serve  --site markupware.com [--port 8080]
    singine wingine status --site markupware.com

markupware.com:  Python cortex/build.py (XML → HTML via xsltproc + DocBook XSL)
lutino.io:       Maven WAR build  (mvn package -DskipTests)

The wingine is the build stage in the www deploy pipeline.
It knows about each site's native build system and invokes it correctly.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .www import now_iso, SITE_REGISTRY, resolve_site


# ── Build backends ────────────────────────────────────────────────────────────

WINGINE_BACKENDS: dict[str, dict] = {
    "markupware.com": {
        "type":        "python-cortex",
        "build_script": Path.home() / "ws/git/markupware.com/cortex/build.py",
        "source_dir":  Path.home() / "ws/git/markupware.com",
        "output_dir":  Path.home() / "ws/git/markupware.com/html",
        "clean_flag":  "--clean",
        "serve_port":  8080,
    },
    "lutino.io": {
        "type":        "maven-war",
        "source_dir":  Path.home() / "ws/git/lutino.io/lutino",
        "output_dir":  Path.home() / "ws/git/lutino.io/lutino/target/lutino_webapp",
        "maven_args":  "package -DskipTests",
        "serve_port":  8081,
    },
}


def _run(cmd: str, cwd: Optional[Path] = None, dry_run: bool = False) -> subprocess.CompletedProcess:
    parts = shlex.split(cmd)
    prefix = "[DRY]" if dry_run else "[RUN]"
    print(f"  {prefix} {cmd}")
    if dry_run:
        return subprocess.CompletedProcess(parts, returncode=0)
    kwargs: dict = {}
    if cwd:
        kwargs["cwd"] = str(cwd)
    return subprocess.run(parts, **kwargs)


# ── Build ─────────────────────────────────────────────────────────────────────

def build(site_name: str, clean: bool = False, dry_run: bool = False, json_out: bool = False) -> dict:
    """
    Build the site using its native pipeline.

    markupware.com → python3 cortex/build.py --output html/ [--clean]
    lutino.io      → mvn package -DskipTests
    """
    if site_name not in WINGINE_BACKENDS:
        raise ValueError(f"No wingine backend for '{site_name}'")

    backend = WINGINE_BACKENDS[site_name]
    btype = backend["type"]
    print(f"\n[wingine] build {site_name} ({btype}) — {now_iso()}")

    ok = False

    if btype == "python-cortex":
        script = backend["build_script"]
        output = backend["output_dir"]
        cmd = f"python3 {script} --output {output}"
        if clean:
            cmd += f" {backend['clean_flag']}"
        r = _run(cmd, cwd=backend["source_dir"], dry_run=dry_run)
        ok = r.returncode == 0

    elif btype == "maven-war":
        cmd = f"mvn {backend['maven_args']}"
        r = _run(cmd, cwd=backend["source_dir"], dry_run=dry_run)
        ok = r.returncode == 0

    else:
        print(f"[wingine] unknown backend type: {btype}", file=sys.stderr)

    result = {
        "site":    site_name,
        "backend": btype,
        "clean":   clean,
        "dry_run": dry_run,
        "ok":      ok,
        "output":  str(backend.get("output_dir", "")),
        "timestamp": now_iso(),
    }

    if json_out:
        print(json.dumps(result, indent=2))
    else:
        status = "✓ build ok" if ok else "✗ build failed"
        print(f"[wingine] {status} — {site_name}")

    return result


# ── Serve (local preview) ─────────────────────────────────────────────────────

def serve(site_name: str, port: Optional[int] = None, dry_run: bool = False) -> None:
    """
    Serve the built site locally for preview.

    markupware.com → python3 -m http.server <port> in html/
    lutino.io      → mvn tomcat7:run  (or python server for static preview)
    """
    if site_name not in WINGINE_BACKENDS:
        raise ValueError(f"No wingine backend for '{site_name}'")

    backend = WINGINE_BACKENDS[site_name]
    serve_port = port or backend.get("serve_port", 8080)

    print(f"\n[wingine] serve {site_name} on http://localhost:{serve_port}/")

    output_dir = backend.get("output_dir", backend["source_dir"])
    cmd = f"python3 -m http.server {serve_port}"
    print(f"  [RUN] {cmd}  (cwd: {output_dir})")

    if not dry_run:
        subprocess.run(shlex.split(cmd), cwd=str(output_dir))


# ── Status ────────────────────────────────────────────────────────────────────

def wingine_status(site_name: str, json_out: bool = False) -> dict:
    """Show build status: output dir exists, last modified, size."""
    if site_name not in WINGINE_BACKENDS:
        raise ValueError(f"No wingine backend for '{site_name}'")

    backend = WINGINE_BACKENDS[site_name]
    output_dir = Path(backend.get("output_dir", backend["source_dir"]))

    built = output_dir.exists()
    file_count = sum(1 for _ in output_dir.rglob("*") if _.is_file()) if built else 0

    result = {
        "site":        site_name,
        "backend":     backend["type"],
        "output_dir":  str(output_dir),
        "built":       built,
        "file_count":  file_count,
        "timestamp":   now_iso(),
    }

    if json_out:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n[wingine] status — {site_name}")
        print(f"  backend   : {result['backend']}")
        print(f"  output    : {result['output_dir']}")
        print(f"  built     : {'yes' if built else 'NO — run: singine wingine build --site ' + site_name}")
        if built:
            print(f"  files     : {file_count}")

    return result
