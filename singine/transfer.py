"""singine.transfer — file transfer, queues, stacks, and XML request/response processing.

Subcommands:
  sync            rsync or scp wrapper
  ssh             run a command over SSH
  sftp            get/put files over SFTP
  queue           persistent FIFO queue (push/pop/peek/list/clear)
  stack           persistent LIFO stack (push/pop/peek/list/clear)
  structure       introspect a queue, stack, or JSON structure
  process-request parse an XML request into a structured envelope
  generate-response generate N response variants from an input (default ×4)
  project         project (select) fields from a JSON structure
  analyze-result  compute statistics and shape summary for a JSON result
"""

from __future__ import annotations

import json
import os
import pwd
import subprocess
import sys
import xml.etree.ElementTree as ET
from itertools import count
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2))


def _run(cmd: List[str]) -> Dict[str, Any]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "cmd": cmd,
        }
    except Exception as exc:
        return {"ok": False, "exit_code": None, "stdout": "", "stderr": str(exc), "cmd": cmd}


def _read_stdin_or_file(path: Optional[str]) -> str:
    if not path or path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _run_jvm_filesystem_activity(argv: List[str], stdin_bytes: Optional[bytes] = None) -> Optional[subprocess.CompletedProcess[bytes]]:
    repo_root = Path(__file__).resolve().parent.parent
    classes_dir = Path(os.environ.get("SINGINE_CORE_CLASSES", str(repo_root / "core" / "classes")))
    main_class = classes_dir / "singine" / "activity" / "fs" / "FilesystemActivityMain.class"
    if not main_class.exists():
        return None
    cmd = ["java", "-cp", str(classes_dir), "singine.activity.fs.FilesystemActivityMain"] + argv
    return subprocess.run(cmd, input=stdin_bytes, capture_output=True, timeout=60)


# ---------------------------------------------------------------------------
# sync — rsync / scp
# ---------------------------------------------------------------------------

def do_sync(src: str, dest: str, method: str = "rsync",
            extra: Optional[List[str]] = None) -> Dict[str, Any]:
    extra = extra or []
    if method == "scp":
        cmd = ["scp", "-r"] + extra + [src, dest]
    else:
        cmd = ["rsync", "-avz", "--progress"] + extra + [src, dest]
    result = _run(cmd)
    result["method"] = method
    result["src"] = src
    result["dest"] = dest
    return result


# ---------------------------------------------------------------------------
# ssh
# ---------------------------------------------------------------------------

def do_ssh(host: str, command: str, user: Optional[str] = None,
           port: Optional[int] = None, extra: Optional[List[str]] = None) -> Dict[str, Any]:
    extra = extra or []
    target = f"{user}@{host}" if user else host
    cmd = ["ssh"]
    if port:
        cmd += ["-p", str(port)]
    cmd += extra + [target, command]
    result = _run(cmd)
    result["host"] = host
    result["command"] = command
    return result


# ---------------------------------------------------------------------------
# sftp
# ---------------------------------------------------------------------------

def do_sftp(host: str, direction: str, local: str, remote: str,
            user: Optional[str] = None, port: Optional[int] = None) -> Dict[str, Any]:
    target = f"{user}@{host}" if user else host
    if direction == "get":
        batch = f"get {remote} {local}\nbye\n"
    else:
        batch = f"put {local} {remote}\nbye\n"
    cmd = ["sftp"]
    if port:
        cmd += ["-P", str(port)]
    cmd.append(target)
    try:
        proc = subprocess.run(
            cmd, input=batch, capture_output=True, text=True, timeout=60
        )
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "direction": direction,
            "local": local,
            "remote": remote,
            "host": host,
        }
    except Exception as exc:
        return {"ok": False, "stderr": str(exc), "direction": direction}


# ---------------------------------------------------------------------------
# persistent queue / stack
# ---------------------------------------------------------------------------

def _load_store(path: str) -> List[Any]:
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return []


def _save_store(path: str, items: List[Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items, indent=2), encoding="utf-8")


def queue_op(op: str, item: Optional[str], state: str) -> Dict[str, Any]:
    """FIFO queue operations."""
    items = _load_store(state)
    if op == "push":
        items.append(item)
        _save_store(state, items)
        return {"ok": True, "op": "push", "item": item, "size": len(items)}
    elif op == "pop":
        if not items:
            return {"ok": False, "op": "pop", "error": "queue is empty"}
        popped = items.pop(0)
        _save_store(state, items)
        return {"ok": True, "op": "pop", "item": popped, "size": len(items)}
    elif op == "peek":
        if not items:
            return {"ok": False, "op": "peek", "error": "queue is empty"}
        return {"ok": True, "op": "peek", "item": items[0], "size": len(items)}
    elif op == "list":
        return {"ok": True, "op": "list", "items": items, "size": len(items)}
    elif op == "clear":
        _save_store(state, [])
        return {"ok": True, "op": "clear", "cleared": len(items)}
    return {"ok": False, "error": f"unknown queue op: {op}"}


def stack_op(op: str, item: Optional[str], state: str) -> Dict[str, Any]:
    """LIFO stack operations."""
    items = _load_store(state)
    if op == "push":
        items.append(item)
        _save_store(state, items)
        return {"ok": True, "op": "push", "item": item, "size": len(items)}
    elif op == "pop":
        if not items:
            return {"ok": False, "op": "pop", "error": "stack is empty"}
        popped = items.pop()
        _save_store(state, items)
        return {"ok": True, "op": "pop", "item": popped, "size": len(items)}
    elif op == "peek":
        if not items:
            return {"ok": False, "op": "peek", "error": "stack is empty"}
        return {"ok": True, "op": "peek", "item": items[-1], "size": len(items)}
    elif op == "list":
        return {"ok": True, "op": "list", "items": list(reversed(items)), "size": len(items)}
    elif op == "clear":
        _save_store(state, [])
        return {"ok": True, "op": "clear", "cleared": len(items)}
    return {"ok": False, "error": f"unknown stack op: {op}"}


# ---------------------------------------------------------------------------
# structure — introspect a queue, stack, or JSON blob
# ---------------------------------------------------------------------------

def structure_inspect(source: str, structure_type: str) -> Dict[str, Any]:
    items = _load_store(source)
    return {
        "type": structure_type,
        "state_path": source,
        "size": len(items),
        "head": items[0] if items else None,
        "tail": items[-1] if items else None,
        "items": items,
    }


# ---------------------------------------------------------------------------
# processRequest(xml)
# ---------------------------------------------------------------------------

def _xml_element_to_dict(el: ET.Element, depth: int = 0) -> Dict[str, Any]:
    node: Dict[str, Any] = {"tag": el.tag}
    if el.attrib:
        node["attributes"] = dict(el.attrib)
    text = (el.text or "").strip()
    if text:
        node["text"] = text
    children = [_xml_element_to_dict(c, depth + 1) for c in el]
    if children:
        node["children"] = children
    return node


def process_request(xml_source: str) -> Dict[str, Any]:
    """Parse an XML request into a structured singine envelope."""
    try:
        root = ET.fromstring(xml_source)
    except ET.ParseError as exc:
        return {
            "ok": False,
            "well_formed": False,
            "error": str(exc),
            "request": None,
        }
    return {
        "ok": True,
        "well_formed": True,
        "root_tag": root.tag,
        "attributes": dict(root.attrib),
        "request": _xml_element_to_dict(root),
        "element_count": sum(1 for _ in root.iter()),
    }


# ---------------------------------------------------------------------------
# generateResponseTimesFour
# ---------------------------------------------------------------------------

def generate_response_times(input_data: Any, times: int = 4) -> Dict[str, Any]:
    """Generate N response variants from an input object."""
    def _variant_xml(data: Any) -> str:
        if isinstance(data, dict):
            inner = "".join(f"<{k}>{v}</{k}>" for k, v in data.items())
            return f"<response>{inner}</response>"
        return f"<response><value>{data}</value></response>"

    def _variant_summary(data: Any) -> str:
        if isinstance(data, dict):
            return "; ".join(f"{k}={v}" for k, v in data.items())
        return str(data)

    def _variant_table(data: Any) -> List[Dict[str, str]]:
        if isinstance(data, dict):
            return [{"key": k, "value": str(v)} for k, v in data.items()]
        return [{"key": "value", "value": str(data)}]

    variants = [
        {"format": "json",    "content": data if isinstance(data := input_data, dict) else {"value": data}},
        {"format": "xml",     "content": _variant_xml(input_data)},
        {"format": "summary", "content": _variant_summary(input_data)},
        {"format": "table",   "content": _variant_table(input_data)},
    ]
    return {
        "ok": True,
        "times": times,
        "variants": variants[:times],
    }


# ---------------------------------------------------------------------------
# project — select fields from a JSON structure
# ---------------------------------------------------------------------------

def project_fields(data: Any, fields: List[str]) -> Dict[str, Any]:
    """Project (select) named fields from a JSON object or list of objects."""
    def _pick(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: obj[k] for k in fields if k in obj}
        return obj

    if isinstance(data, list):
        projected = [_pick(item) for item in data]
    else:
        projected = _pick(data)

    return {"ok": True, "fields": fields, "result": projected}


# ---------------------------------------------------------------------------
# analyzeResult
# ---------------------------------------------------------------------------

def analyze_result(data: Any) -> Dict[str, Any]:
    """Compute shape, depth, and statistics for a JSON result."""
    def _depth(obj: Any, d: int = 0) -> int:
        if isinstance(obj, dict):
            return max((_depth(v, d + 1) for v in obj.values()), default=d + 1)
        if isinstance(obj, list):
            return max((_depth(v, d + 1) for v in obj), default=d + 1)
        return d

    def _count_leaves(obj: Any) -> int:
        if isinstance(obj, dict):
            return sum(_count_leaves(v) for v in obj.values())
        if isinstance(obj, list):
            return sum(_count_leaves(v) for v in obj)
        return 1

    def _numeric_values(obj: Any) -> List[float]:
        vals: List[float] = []
        if isinstance(obj, dict):
            for v in obj.values():
                vals.extend(_numeric_values(v))
        elif isinstance(obj, list):
            for v in obj:
                vals.extend(_numeric_values(v))
        elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
            vals.append(float(obj))
        return vals

    nums = _numeric_values(data)
    stats: Dict[str, Any] = {}
    if nums:
        stats = {
            "count": len(nums),
            "sum": sum(nums),
            "min": min(nums),
            "max": max(nums),
            "mean": sum(nums) / len(nums),
        }

    return {
        "ok": True,
        "type": type(data).__name__,
        "depth": _depth(data),
        "leaf_count": _count_leaves(data),
        "keys": list(data.keys()) if isinstance(data, dict) else None,
        "length": len(data) if isinstance(data, (dict, list, str)) else None,
        "numeric_stats": stats or None,
    }


# ---------------------------------------------------------------------------
# mv — move filesystem paths received on stdin
# ---------------------------------------------------------------------------

def _iter_stdin_paths(null_delimited: bool) -> Sequence[str]:
    if null_delimited:
        stream = sys.stdin.buffer.read()
        for chunk in stream.split(b"\0"):
            if chunk:
                yield os.fsdecode(chunk)
        return

    for line in sys.stdin:
        path = line.rstrip("\n")
        if path:
            yield path


def _resolve_user_path(raw_path: str) -> Path:
    if not raw_path.startswith("~"):
        return Path(raw_path)

    if raw_path == "~" or raw_path.startswith("~/"):
        home = os.environ.get("HOME")
        if not home:
            home = pwd.getpwuid(os.getuid()).pw_dir
        suffix = raw_path[2:] if raw_path.startswith("~/") else ""
        return Path(home) / suffix

    user_part, _, remainder = raw_path[1:].partition("/")
    try:
        home = pwd.getpwnam(user_part).pw_dir
    except KeyError:
        return Path(raw_path)
    return Path(home) / remainder


def move_paths_to_destination(
    dest_dir: str,
    *,
    null_delimited: bool = False,
    create_dest: bool = False,
    dry_run: bool = False,
    paths: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    destination = _resolve_user_path(dest_dir)
    if create_dest:
        destination.mkdir(parents=True, exist_ok=True)
    if not destination.is_dir():
        return {
            "ok": False,
            "error": f"destination is not a directory: {destination}",
            "dest_dir": str(destination),
        }

    moved: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []
    errors: List[Dict[str, str]] = []

    source_paths = list(paths) if paths is not None else list(_iter_stdin_paths(null_delimited))

    for ordinal, raw_path in zip(count(1), source_paths):
        source = _resolve_user_path(raw_path)
        if not source.exists():
            skipped.append({
                "index": str(ordinal),
                "source": str(source),
                "reason": "missing",
            })
            continue
        target = destination / source.name
        if dry_run:
            moved.append({
                "index": str(ordinal),
                "source": str(source),
                "target": str(target),
                "status": "planned",
            })
            continue
        try:
            source.rename(target)
            moved.append({
                "index": str(ordinal),
                "source": str(source),
                "target": str(target),
                "status": "moved",
            })
        except OSError as exc:
            errors.append({
                "index": str(ordinal),
                "source": str(source),
                "target": str(target),
                "error": str(exc),
            })

    return {
        "ok": not errors,
        "activity": "fileListTo",
        "dest_dir": str(destination),
        "null_delimited": null_delimited,
        "dry_run": dry_run,
        "moved_count": len(moved),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "moved": moved,
        "skipped": skipped,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# find — filesystem topic search
# ---------------------------------------------------------------------------

def find_files_about_topic(
    topic: str,
    *,
    root_dir: str = ".",
    max_depth: int = 3,
    path_type: str = "any",
) -> Dict[str, Any]:
    root = _resolve_user_path(root_dir).resolve()
    if not root.exists():
        return {
            "ok": False,
            "activity": "filesAboutTopic",
            "error": f"root does not exist: {root}",
            "root_dir": str(root),
        }
    if not root.is_dir():
        return {
            "ok": False,
            "activity": "filesAboutTopic",
            "error": f"root is not a directory: {root}",
            "root_dir": str(root),
        }

    topic_lc = topic.casefold()
    matches: List[Dict[str, str]] = []

    for current_root, dirnames, filenames in os.walk(root):
        current_path = Path(current_root)
        rel_parts = current_path.relative_to(root).parts
        depth = len(rel_parts)
        if depth >= max_depth:
            dirnames[:] = []

        if path_type in {"any", "dir"}:
            for dirname in sorted(dirnames):
                if topic_lc in dirname.casefold():
                    matches.append({
                        "type": "dir",
                        "path": str(current_path / dirname),
                    })

        if path_type in {"any", "file"}:
            for filename in sorted(filenames):
                if topic_lc in filename.casefold():
                    matches.append({
                        "type": "file",
                        "path": str(current_path / filename),
                    })

    return {
        "ok": True,
        "activity": "filesAboutTopic",
        "topic": topic,
        "root_dir": str(root),
        "max_depth": max_depth,
        "path_type": path_type,
        "count": len(matches),
        "matches": matches,
    }


# ---------------------------------------------------------------------------
# CLI handlers
# ---------------------------------------------------------------------------

def cmd_transfer_sync(args: "argparse.Namespace") -> int:
    method = "scp" if getattr(args, "scp", False) else "rsync"
    result = do_sync(args.src, args.dest, method=method)
    if getattr(args, "json", False):
        _print_json(result)
    else:
        print(result["stdout"] or result["stderr"])
    return 0 if result["ok"] else 1


def cmd_transfer_ssh(args: "argparse.Namespace") -> int:
    result = do_ssh(
        args.host, args.cmd,
        user=getattr(args, "user", None),
        port=getattr(args, "port", None),
    )
    if getattr(args, "json", False):
        _print_json(result)
    else:
        sys.stdout.write(result["stdout"])
        if result["stderr"]:
            sys.stderr.write(result["stderr"])
    return 0 if result["ok"] else 1


def cmd_transfer_sftp(args: "argparse.Namespace") -> int:
    direction = "get" if getattr(args, "get", False) else "put"
    local = args.local
    remote = getattr(args, "remote", local)
    result = do_sftp(
        args.host, direction, local, remote,
        user=getattr(args, "user", None),
        port=getattr(args, "port", None),
    )
    if getattr(args, "json", False):
        _print_json(result)
    else:
        print(result["stdout"] or result["stderr"])
    return 0 if result["ok"] else 1


def cmd_transfer_queue(args: "argparse.Namespace") -> int:
    result = queue_op(
        args.queue_op,
        getattr(args, "item", None),
        getattr(args, "state", "/tmp/singine-queue.json"),
    )
    _print_json(result)
    return 0 if result["ok"] else 1


def cmd_transfer_stack(args: "argparse.Namespace") -> int:
    result = stack_op(
        args.stack_op,
        getattr(args, "item", None),
        getattr(args, "state", "/tmp/singine-stack.json"),
    )
    _print_json(result)
    return 0 if result["ok"] else 1


def cmd_transfer_structure(args: "argparse.Namespace") -> int:
    result = structure_inspect(
        getattr(args, "state", "/tmp/singine-queue.json"),
        getattr(args, "type", "queue"),
    )
    _print_json(result)
    return 0


def cmd_transfer_process_request(args: "argparse.Namespace") -> int:
    xml_source = _read_stdin_or_file(getattr(args, "xml", None))
    result = process_request(xml_source)
    _print_json(result)
    return 0 if result["ok"] else 1


def cmd_transfer_generate_response(args: "argparse.Namespace") -> int:
    raw = _read_stdin_or_file(getattr(args, "input", None))
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError:
        data = raw.strip()
    times = getattr(args, "times", 4)
    result = generate_response_times(data, times=times)
    _print_json(result)
    return 0


def cmd_transfer_project(args: "argparse.Namespace") -> int:
    raw = _read_stdin_or_file(getattr(args, "input", None))
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError:
        _print_json({"ok": False, "error": "input is not valid JSON"})
        return 1
    fields = [f.strip() for f in args.fields.split(",")]
    result = project_fields(data, fields)
    _print_json(result)
    return 0


def cmd_transfer_analyze_result(args: "argparse.Namespace") -> int:
    raw = _read_stdin_or_file(getattr(args, "input", None))
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError:
        data = raw.strip()
    result = analyze_result(data)
    _print_json(result)
    return 0


def cmd_transfer_move(args: "argparse.Namespace") -> int:
    stdin_bytes = sys.stdin.buffer.read()
    jvm_argv = ["mv", "fileListTo", args.dest_dir]
    if getattr(args, "null", False):
        jvm_argv.append("--null")
    if getattr(args, "mkdir", False):
        jvm_argv.append("--mkdir")
    if getattr(args, "dry_run", False):
        jvm_argv.append("--dry-run")
    if getattr(args, "json", False):
        jvm_argv.append("--json")
    jvm_result = _run_jvm_filesystem_activity(jvm_argv, stdin_bytes=stdin_bytes)
    if jvm_result is not None:
        sys.stdout.buffer.write(jvm_result.stdout)
        sys.stderr.buffer.write(jvm_result.stderr)
        return jvm_result.returncode

    if getattr(args, "null", False):
        decoded_paths = [os.fsdecode(chunk) for chunk in stdin_bytes.split(b"\0") if chunk]
    else:
        decoded_paths = [chunk.decode("utf-8") for chunk in stdin_bytes.splitlines() if chunk]

    result = move_paths_to_destination(
        args.dest_dir,
        null_delimited=getattr(args, "null", False),
        create_dest=getattr(args, "mkdir", False),
        dry_run=getattr(args, "dry_run", False),
        paths=decoded_paths,
    )
    if getattr(args, "json", False):
        _print_json(result)
    else:
        for item in result["moved"]:
            print(f"{item['status']}: {item['source']} -> {item['target']}")
        for item in result["skipped"]:
            print(f"skipped: {item['source']} ({item['reason']})", file=sys.stderr)
        for item in result["errors"]:
            print(f"error: {item['source']} -> {item['target']} ({item['error']})", file=sys.stderr)
        print(
            f"activity={result['activity']} moved={result['moved_count']} "
            f"skipped={result['skipped_count']} errors={result['error_count']}"
        )
    return 0 if result["ok"] else 1


def cmd_transfer_find(args: "argparse.Namespace") -> int:
    jvm_argv = ["find", "filesAboutTopic", args.topic, "--root-dir", getattr(args, "root_dir", "."),
                "--max-depth", str(getattr(args, "max_depth", 3)), "--type", getattr(args, "path_type", "any")]
    if getattr(args, "null", False):
        jvm_argv.append("--null")
    if getattr(args, "json", False):
        jvm_argv.append("--json")
    jvm_result = _run_jvm_filesystem_activity(jvm_argv)
    if jvm_result is not None:
        sys.stdout.buffer.write(jvm_result.stdout)
        sys.stderr.buffer.write(jvm_result.stderr)
        return jvm_result.returncode

    result = find_files_about_topic(
        args.topic,
        root_dir=getattr(args, "root_dir", "."),
        max_depth=getattr(args, "max_depth", 3),
        path_type=getattr(args, "path_type", "any"),
    )
    if getattr(args, "json", False):
        _print_json(result)
    elif getattr(args, "null", False):
        for item in result.get("matches", []):
            sys.stdout.buffer.write(os.fsencode(item["path"]))
            sys.stdout.buffer.write(b"\0")
    else:
        for item in result.get("matches", []):
            print(item["path"])
    return 0 if result.get("ok") else 1
