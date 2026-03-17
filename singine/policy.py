"""Policy management commands for Singine.

Current scope:
- AI policy pack canonification
- AI access governance evaluation and approval workflows
- repo-backed policy sync with targeted git commits

This module is intentionally structured around a policy family namespace
(`ai` today) so other governed policy surfaces can be added later without
changing the top-level `singine policy` command shape.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = REPO_ROOT / "bin"
DEFAULT_POLICY_SUBDIR = Path("policy") / "ai" / "current"


def _parse_scalar(text: str) -> Any:
    value = text.strip()
    if value in {"null", "~"}:
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _yaml_tokens(text: str) -> List[Dict[str, Any]]:
    tokens: List[Dict[str, Any]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        tokens.append({"lineno": lineno, "indent": indent, "text": raw.strip()})
    return tokens


def _parse_yaml_block(tokens: List[Dict[str, Any]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(tokens):
        return {}, index
    if tokens[index]["indent"] != indent:
        raise ValueError(f"Unexpected indentation on line {tokens[index]['lineno']}")
    if tokens[index]["text"].startswith("- "):
        return _parse_yaml_list(tokens, index, indent)
    return _parse_yaml_map(tokens, index, indent)


def _parse_yaml_map(tokens: List[Dict[str, Any]], index: int, indent: int) -> tuple[Dict[str, Any], int]:
    result: Dict[str, Any] = {}
    while index < len(tokens):
        token = tokens[index]
        if token["indent"] < indent:
            break
        if token["indent"] > indent:
            raise ValueError(f"Unexpected indentation on line {token['lineno']}")
        if token["text"].startswith("- "):
            break
        if ":" not in token["text"]:
            raise ValueError(f"Expected key/value pair on line {token['lineno']}")
        key, rest = token["text"].split(":", 1)
        key = key.strip()
        rest = rest.strip()
        index += 1
        if rest:
            result[key] = _parse_scalar(rest)
            continue
        if index < len(tokens) and tokens[index]["indent"] > indent:
            value, index = _parse_yaml_block(tokens, index, tokens[index]["indent"])
            result[key] = value
        else:
            result[key] = {}
    return result, index


def _parse_yaml_list(tokens: List[Dict[str, Any]], index: int, indent: int) -> tuple[List[Any], int]:
    result: List[Any] = []
    while index < len(tokens):
        token = tokens[index]
        if token["indent"] < indent:
            break
        if token["indent"] != indent or not token["text"].startswith("- "):
            break
        content = token["text"][2:].strip()
        index += 1
        if not content:
            if index < len(tokens) and tokens[index]["indent"] > indent:
                value, index = _parse_yaml_block(tokens, index, tokens[index]["indent"])
                result.append(value)
            else:
                result.append(None)
            continue
        if ":" in content:
            key, rest = content.split(":", 1)
            item: Dict[str, Any] = {key.strip(): _parse_scalar(rest.strip()) if rest.strip() else {}}
            if index < len(tokens) and tokens[index]["indent"] > indent:
                nested, index = _parse_yaml_block(tokens, index, tokens[index]["indent"])
                if isinstance(nested, dict):
                    if item[key.strip()] == {}:
                        item[key.strip()] = nested
                    else:
                        item.update(nested)
                else:
                    raise ValueError(f"Expected mapping continuation after line {token['lineno']}")
            result.append(item)
            continue
        result.append(_parse_scalar(content))
    return result, index


def _load_yaml_template(path: Path) -> Dict[str, Any]:
    tokens = _yaml_tokens(path.read_text(encoding="utf-8"))
    if not tokens:
        return {}
    value, index = _parse_yaml_block(tokens, 0, tokens[0]["indent"])
    if index != len(tokens):
        raise ValueError(f"Unparsed YAML content remains near line {tokens[index]['lineno']}")
    if not isinstance(value, dict):
        raise ValueError("YAML template root must be a mapping")
    return value


def _normalize_systems(template: Dict[str, Any]) -> List[Dict[str, Any]]:
    systems = template.get("systems", {})
    normalized: List[Dict[str, Any]] = []
    if isinstance(systems, dict):
        for system_id, payload in systems.items():
            item = dict(payload) if isinstance(payload, dict) else {"value": payload}
            item.setdefault("id", system_id)
            normalized.append(item)
        return normalized
    if isinstance(systems, list):
        for payload in systems:
            if isinstance(payload, dict):
                item = dict(payload)
                item.setdefault("id", str(item.get("name", item.get("display_name", "unknown"))).lower())
                normalized.append(item)
        return normalized
    return normalized


def _policy_names(entry: Dict[str, Any]) -> List[str]:
    policies = entry.get("policies", [])
    names: List[str] = []
    if isinstance(policies, list):
        for item in policies:
            if isinstance(item, dict):
                names.append(str(item.get("name", item.get("id", "policy"))))
            else:
                names.append(str(item))
    return names


def _systems_overview(template: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for entry in _normalize_systems(template):
        rows.append(
            {
                "id": entry.get("id", ""),
                "display_name": entry.get("display_name", entry.get("name", entry.get("id", ""))),
                "vendor": entry.get("vendor", ""),
                "policy_count": len(entry.get("policies", [])) if isinstance(entry.get("policies", []), list) else 0,
                "policy_names": _policy_names(entry),
                "environments": entry.get("environments", []),
                "command_prefixes": entry.get("command_prefixes", []),
            }
        )
    return rows


def _normalize_ai_use_cases(template: Dict[str, Any]) -> List[Dict[str, Any]]:
    use_cases = template.get("ai_use_cases", [])
    normalized: List[Dict[str, Any]] = []
    if isinstance(use_cases, list):
        for item in use_cases:
            if isinstance(item, dict):
                normalized.append(dict(item))
    return normalized


def _group_use_cases_by_system(template: Dict[str, Any]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for use_case in _normalize_ai_use_cases(template):
        system_id = str(use_case.get("ai_system", "unknown"))
        group = grouped.setdefault(
            system_id,
            {
                "id": system_id,
                "display_name": system_id,
                "vendor": "",
                "asset_type": template.get("asset_type", "AI Use Case"),
                "use_cases": [],
                "policy_names": set(),
                "risk_profiles": set(),
                "roles_of_ai": set(),
            },
        )
        group["display_name"] = use_case.get("ai_system_display_name", group["display_name"])
        if use_case.get("vendor"):
            group["vendor"] = use_case["vendor"]
        group["use_cases"].append(use_case)
        for policy_name in use_case.get("governed_policies", []):
            group["policy_names"].add(str(policy_name))
        if use_case.get("risk_profile"):
            group["risk_profiles"].add(str(use_case["risk_profile"]))
        if use_case.get("role_of_ai"):
            group["roles_of_ai"].add(str(use_case["role_of_ai"]))

    rows: List[Dict[str, Any]] = []
    for _, group in grouped.items():
        rows.append(
            {
                "id": group["id"],
                "display_name": group["display_name"],
                "vendor": group["vendor"],
                "asset_type": group["asset_type"],
                "use_case_count": len(group["use_cases"]),
                "use_case_names": [str(item.get("name", item.get("id", "AI Use Case"))) for item in group["use_cases"]],
                "policy_names": sorted(group["policy_names"]),
                "risk_profiles": sorted(group["risk_profiles"]),
                "roles_of_ai": sorted(group["roles_of_ai"]),
                "use_cases": group["use_cases"],
            }
        )
    return rows


def _template_view(template: Dict[str, Any], ai_system: Optional[str]) -> Dict[str, Any]:
    groups = _group_use_cases_by_system(template)
    if groups:
        if ai_system:
            match = next((item for item in groups if item["id"] == ai_system), None)
            if match is None:
                raise SystemExit(f"AI system not found in template: {ai_system}")
            return {
                "asset_type": template.get("asset_type", "AI Use Case"),
                "template_name": template.get("template_name", ""),
                "collibra": template.get("collibra", {}),
                "ai_system": match,
            }
        return {
            "asset_type": template.get("asset_type", "AI Use Case"),
            "template_name": template.get("template_name", ""),
            "collibra": template.get("collibra", {}),
            "systems": [
                {
                    "id": item["id"],
                    "display_name": item["display_name"],
                    "vendor": item["vendor"],
                    "asset_type": item["asset_type"],
                    "use_case_count": item["use_case_count"],
                    "use_case_names": item["use_case_names"],
                    "policy_names": item["policy_names"],
                    "risk_profiles": item["risk_profiles"],
                    "roles_of_ai": item["roles_of_ai"],
                }
                for item in groups
            ],
        }

    systems = _systems_overview(template)
    if ai_system:
        match = next((item for item in _normalize_systems(template) if item.get("id") == ai_system), None)
        if match is None:
            raise SystemExit(f"AI system not found in template: {ai_system}")
        return {
            "asset_type": template.get("asset_type", "Policy"),
            "template_name": template.get("template_name", ""),
            "collibra": template.get("collibra", {}),
            "ai_system": match,
        }
    return {
        "asset_type": template.get("asset_type", "Policy"),
        "template_name": template.get("template_name", ""),
        "collibra": template.get("collibra", {}),
        "systems": systems,
    }


def _run(
    cmd: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=check,
    )


def _json_stdout(proc: subprocess.CompletedProcess[str]) -> Dict[str, Any]:
    text = (proc.stdout or "").strip()
    return json.loads(text) if text else {}


def _policy_repo(args: argparse.Namespace) -> Path:
    raw = getattr(args, "policy_repo", None)
    if raw:
        return Path(raw).expanduser().resolve()
    raise SystemExit("policy repo is required for this operation")


def _policy_output_dir(args: argparse.Namespace) -> Path:
    repo = _policy_repo(args)
    return (repo / getattr(args, "output_subdir", str(DEFAULT_POLICY_SUBDIR))).resolve()


def _policy_pack_path(args: argparse.Namespace) -> Path:
    explicit = getattr(args, "policy_pack", None)
    if explicit:
        return Path(explicit).expanduser().resolve()
    return _policy_output_dir(args) / "policy-pack.json"


def _canonify_cmd(args: argparse.Namespace, output_dir: Path) -> List[str]:
    cmd = [
        sys.executable,
        str(BIN_DIR / "singine-canonify-ai-policies"),
        "--output-dir",
        str(output_dir),
        "--pack-id",
        args.pack_id,
    ]
    if getattr(args, "mapping_json", None):
        cmd.extend(["--mapping-json", args.mapping_json])
    if getattr(args, "systems", None):
        cmd.extend(["--systems", *args.systems])
    if getattr(args, "ldap_ldif", None):
        cmd.extend(["--ldap-ldif", args.ldap_ldif])
    if getattr(args, "ldap_uri", None):
        cmd.extend(["--ldap-uri", args.ldap_uri])
    if getattr(args, "base_dn", None):
        cmd.extend(["--base-dn", args.base_dn])
    if getattr(args, "bind_dn", None):
        cmd.extend(["--bind-dn", args.bind_dn])
    if getattr(args, "bind_password_env", None):
        cmd.extend(["--bind-password-env", args.bind_password_env])
    if getattr(args, "group_filter", None):
        cmd.extend(["--group-filter", args.group_filter])
    return cmd


def _govern_cmd(args: argparse.Namespace, action: str) -> List[str]:
    cmd = [
        sys.executable,
        str(BIN_DIR / "singine-govern-ai-access"),
    ]
    if getattr(args, "db", None):
        cmd.extend(["--db", args.db])
    if getattr(args, "state_dir", None):
        cmd.extend(["--state-dir", args.state_dir])
    if getattr(args, "config_json", None):
        cmd.extend(["--config-json", args.config_json])
    cmd.extend([
        action,
    ])
    if action == "evaluate":
        cmd.extend(["--policy-pack", str(_policy_pack_path(args))])
    if getattr(args, "request_json", None):
        cmd.extend(["--request-json", args.request_json])
    if getattr(args, "ai_system", None):
        cmd.extend(["--ai-system", args.ai_system])
    if getattr(args, "trust_level", None):
        cmd.extend(["--trust-level", args.trust_level])
    if getattr(args, "environment", None):
        cmd.extend(["--environment", args.environment])
    if getattr(args, "network_mode", None):
        cmd.extend(["--network-mode", args.network_mode])
    if getattr(args, "execution_env", None):
        cmd.extend(["--execution-env", args.execution_env])
    if getattr(args, "command", None):
        cmd.extend(["--command", *args.command])
    if getattr(args, "command_text", None):
        cmd.extend(["--command-text", args.command_text])
    if getattr(args, "path", None):
        for item in args.path:
            cmd.extend(["--path", item])
    if getattr(args, "operation", None):
        cmd.extend(["--operation", args.operation])
    if getattr(args, "repo_path", None):
        cmd.extend(["--repo-path", args.repo_path])
    if getattr(args, "lambda_name", None):
        cmd.extend(["--lambda-name", args.lambda_name])
    if getattr(args, "activity_id", None):
        cmd.extend(["--activity-id", args.activity_id])
    if getattr(args, "notes", None):
        cmd.extend(["--notes", args.notes])
    if getattr(args, "resource_grant_kind", None):
        cmd.extend(["--resource-grant-kind", args.resource_grant_kind])
    if action == "approve":
        if getattr(args, "granted_by", None):
            cmd.extend(["--granted-by", args.granted_by])
        cmd.extend(["--reason", args.reason])
        if getattr(args, "op_vault", None):
            cmd.extend(["--op-vault", args.op_vault])
    return cmd


def _ensure_git_repo(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"policy repo does not exist: {path}")
    if not (path / ".git").exists():
        raise SystemExit(f"policy repo is not a git repository: {path}")


def _write_kernel_link(policy_repo: Path, output_dir: Path, args: argparse.Namespace) -> Path:
    link_dir = policy_repo / "policy" / "ai"
    link_dir.mkdir(parents=True, exist_ok=True)
    link_path = link_dir / "singine-kernel-link.json"
    payload = {
        "policy_kind": "ai",
        "sync_mode": "repo-backed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kernel_repo": str(REPO_ROOT),
        "policy_repo": str(policy_repo),
        "policy_output_dir": str(output_dir),
        "pack_id": args.pack_id,
        "systems": list(args.systems),
        "integration_contract": {
            "execution": "governed-process-execution",
            "io_generation": "governed-input-output-generation",
            "integration_point": "singine-kernel-policy-repository",
        },
    }
    link_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return link_path


def _git_output(args: argparse.Namespace, payload: Dict[str, Any]) -> int:
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
    else:
        if payload.get("ok"):
            print(json.dumps(payload, indent=2))
        else:
            print(payload.get("stderr") or payload.get("error") or "command failed", file=sys.stderr)
    return payload.get("exit_code", 0) if isinstance(payload.get("exit_code"), int) else 0


def cmd_policy_ai_canonify(args: argparse.Namespace) -> int:
    output_dir = _policy_output_dir(args)
    output_dir.mkdir(parents=True, exist_ok=True)
    proc = _run(_canonify_cmd(args, output_dir))
    payload: Dict[str, Any] = {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "policy_repo": str(_policy_repo(args)),
        "output_dir": str(output_dir),
    }
    if proc.returncode == 0:
        payload["summary"] = _json_stdout(proc)
    return _git_output(args, payload)


def cmd_policy_ai_evaluate(args: argparse.Namespace) -> int:
    proc = _run(_govern_cmd(args, "evaluate"))
    payload = {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    if proc.stdout.strip():
        try:
            payload["result"] = _json_stdout(proc)
        except json.JSONDecodeError:
            pass
    return _git_output(args, payload)


def cmd_policy_ai_approve(args: argparse.Namespace) -> int:
    proc = _run(_govern_cmd(args, "approve"))
    payload = {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    if proc.stdout.strip():
        try:
            payload["result"] = _json_stdout(proc)
        except json.JSONDecodeError:
            pass
    return _git_output(args, payload)


def cmd_policy_ai_report(args: argparse.Namespace) -> int:
    cmd = [
        sys.executable,
        str(BIN_DIR / "singine-govern-ai-access"),
    ]
    if getattr(args, "db", None):
        cmd.extend(["--db", args.db])
    if getattr(args, "state_dir", None):
        cmd.extend(["--state-dir", args.state_dir])
    if getattr(args, "config_json", None):
        cmd.extend(["--config-json", args.config_json])
    cmd.append("report")
    if getattr(args, "ai_system", None):
        cmd.extend(["--ai-system", args.ai_system])
    proc = _run(cmd)
    payload = {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    if proc.stdout.strip():
        try:
            payload["result"] = _json_stdout(proc)
        except json.JSONDecodeError:
            pass
    return _git_output(args, payload)


def cmd_policy_ai_sync(args: argparse.Namespace) -> int:
    policy_repo = _policy_repo(args)
    _ensure_git_repo(policy_repo)
    output_dir = _policy_output_dir(args)
    output_dir.mkdir(parents=True, exist_ok=True)

    canonify = _run(_canonify_cmd(args, output_dir))
    if canonify.returncode != 0:
        return _git_output(
            args,
            {
                "ok": False,
                "exit_code": canonify.returncode,
                "stdout": canonify.stdout,
                "stderr": canonify.stderr,
                "policy_repo": str(policy_repo),
                "output_dir": str(output_dir),
            },
        )

    summary = _json_stdout(canonify)
    link_path = _write_kernel_link(policy_repo, output_dir, args)
    rel_output_dir = output_dir.relative_to(policy_repo)
    rel_link_path = link_path.relative_to(policy_repo)

    add_cmd = [
        "git",
        "-C",
        str(policy_repo),
        "add",
        str(rel_output_dir),
        str(rel_link_path),
    ]
    add_proc = _run(add_cmd)
    if add_proc.returncode != 0:
        return _git_output(
            args,
            {
                "ok": False,
                "exit_code": add_proc.returncode,
                "stdout": add_proc.stdout,
                "stderr": add_proc.stderr,
                "stage": "git-add",
                "policy_repo": str(policy_repo),
            },
        )

    diff_proc = _run(
        [
            "git",
            "-C",
            str(policy_repo),
            "diff",
            "--cached",
            "--quiet",
            "--",
            str(rel_output_dir),
            str(rel_link_path),
        ]
    )
    commit_created = False
    commit_stdout = ""
    if diff_proc.returncode == 1:
        message = args.commit_message or (
            f"singine policy sync ai {args.pack_id} "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )
        commit_proc = _run(
            [
                "git",
                "-C",
                str(policy_repo),
                "commit",
                "-m",
                message,
                "--",
                str(rel_output_dir),
                str(rel_link_path),
            ]
        )
        if commit_proc.returncode != 0:
            return _git_output(
                args,
                {
                    "ok": False,
                    "exit_code": commit_proc.returncode,
                    "stdout": commit_proc.stdout,
                    "stderr": commit_proc.stderr,
                    "stage": "git-commit",
                    "policy_repo": str(policy_repo),
                },
            )
        commit_created = True
        commit_stdout = commit_proc.stdout.strip()

    push_stdout = ""
    if getattr(args, "push", False):
        push_cmd = ["git", "-C", str(policy_repo), "push", args.remote]
        if getattr(args, "branch", None):
            push_cmd.append(args.branch)
        push_proc = _run(push_cmd)
        if push_proc.returncode != 0:
            return _git_output(
                args,
                {
                    "ok": False,
                    "exit_code": push_proc.returncode,
                    "stdout": push_proc.stdout,
                    "stderr": push_proc.stderr,
                    "stage": "git-push",
                    "policy_repo": str(policy_repo),
                },
            )
        push_stdout = push_proc.stdout.strip()

    payload = {
        "ok": True,
        "policy_repo": str(policy_repo),
        "output_dir": str(output_dir),
        "policy_pack": str(output_dir / "policy-pack.json"),
        "kernel_link": str(link_path),
        "summary": summary,
        "git": {
            "commit_created": commit_created,
            "commit_stdout": commit_stdout,
            "push_requested": bool(getattr(args, "push", False)),
            "push_stdout": push_stdout,
        },
    }
    return _git_output(args, payload)


def cmd_policy_ai_template(args: argparse.Namespace) -> int:
    template_path = Path(args.template_yaml).expanduser().resolve()
    template = _load_yaml_template(template_path)
    payload = {
        "ok": True,
        "template_path": str(template_path),
        "result": _template_view(template, getattr(args, "ai_system", None)),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    result = payload["result"]
    print(f"template: {template_path}")
    print(f"asset type: {result.get('asset_type', '')}")
    if result.get("template_name"):
        print(f"template name: {result['template_name']}")
    if "ai_system" in result:
        item = result["ai_system"]
        print(f"ai system: {item.get('display_name', item.get('id', ''))} ({item.get('id', '')})")
        if item.get("vendor"):
            print(f"vendor: {item['vendor']}")
        if item.get("use_case_count") is not None:
            print(f"use cases: {item.get('use_case_count', 0)}")
            print(f"roles of ai: {', '.join(item.get('roles_of_ai', [])) or '(none)'}")
            print(f"risk profiles: {', '.join(item.get('risk_profiles', [])) or '(none)'}")
            print(f"governed policies: {', '.join(item.get('policy_names', [])) or '(none)'}")
        else:
            print(f"policies: {', '.join(_policy_names(item)) or '(none)'}")
    else:
        print("systems:")
        for item in result.get("systems", []):
            if "use_case_count" in item:
                print(
                    f"  - {item['id']}: {item.get('use_case_count', 0)} use cases, "
                    f"{len(item.get('policy_names', []))} governed policies"
                )
            else:
                print(
                    f"  - {item['id']}: {item.get('policy_count', 0)} policies"
                )
    return 0


def add_policy_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    policy_parser = sub.add_parser(
        "policy",
        help="Manage governed policy packs and policy-backed execution surfaces",
    )
    policy_sub = policy_parser.add_subparsers(dest="policy_family")

    ai_parser = policy_sub.add_parser(
        "ai",
        help="Manage AI policy packs, approvals, evaluations, and repo-backed sync",
    )
    ai_sub = ai_parser.add_subparsers(dest="policy_action")

    repo_parent = argparse.ArgumentParser(add_help=False)
    repo_parent.add_argument("--policy-repo", required=True, help="Git repository that stores synced policy artefacts.")
    repo_parent.add_argument(
        "--output-subdir",
        default=str(DEFAULT_POLICY_SUBDIR),
        help="Subdirectory inside the policy repo for generated AI policy files.",
    )
    repo_parent.add_argument("--pack-id", default="ai-agent-permissions", help="Stable identifier for the emitted policy pack.")
    repo_parent.add_argument("--mapping-json", help="Optional JSON file with group_rules overrides.")
    repo_parent.add_argument(
        "--systems",
        nargs="+",
        default=["claude", "codex", "chatgpt", "openai-api"],
        help="AI systems covered by the policy hierarchy.",
    )
    repo_parent.add_argument("--ldap-ldif", help="Read LDAP group export from an LDIF file.")
    repo_parent.add_argument("--ldap-uri", help="LDAP URI for secure runtime-backed ldapsearch.")
    repo_parent.add_argument("--base-dn", help="LDAP base DN for group discovery.")
    repo_parent.add_argument("--bind-dn", help="Optional bind DN for ldapsearch.")
    repo_parent.add_argument("--bind-password-env", help="Environment variable containing the bind password.")
    repo_parent.add_argument(
        "--group-filter",
        default="(|(objectClass=groupOfNames)(objectClass=groupOfUniqueNames)(objectClass=group))",
        help="LDAP filter used when calling ldapsearch.",
    )
    repo_parent.add_argument("--json", action="store_true", help="Emit JSON payloads.")

    canonify = ai_sub.add_parser(
        "canonify",
        parents=[repo_parent],
        help="Generate canonical AI policy artefacts inside a policy repository.",
    )
    canonify.set_defaults(func=cmd_policy_ai_canonify)

    sync = ai_sub.add_parser(
        "sync",
        parents=[repo_parent],
        help="Generate policy artefacts, stage them, and commit them in the policy repository.",
    )
    sync.add_argument("--commit-message", help="Override the generated git commit message.")
    sync.add_argument("--push", action="store_true", help="Push the sync commit after a successful local commit.")
    sync.add_argument("--remote", default="origin", help="Git remote to push to when --push is used.")
    sync.add_argument("--branch", help="Optional branch to push to when --push is used.")
    sync.set_defaults(func=cmd_policy_ai_sync)

    govern_parent = argparse.ArgumentParser(add_help=False)
    govern_parent.add_argument("--policy-repo", help="Policy repository root; used to infer the canonical policy-pack.json path.")
    govern_parent.add_argument(
        "--output-subdir",
        default=str(DEFAULT_POLICY_SUBDIR),
        help="Subdirectory inside the policy repo that contains policy-pack.json.",
    )
    govern_parent.add_argument("--policy-pack", help="Explicit path to policy-pack.json.")
    govern_parent.add_argument("--db", help="SQLite database path for approvals, counters, and decisions.")
    govern_parent.add_argument("--state-dir", help="Directory for decision and approval artefacts.")
    govern_parent.add_argument("--config-json", help="Optional JSON config overriding trusted systems and command rules.")
    govern_parent.add_argument("--request-json", help="Structured request JSON file.")
    govern_parent.add_argument("--ai-system", help="AI system identifier, e.g. claude or codex.")
    govern_parent.add_argument("--trust-level", help="Trust level label.")
    govern_parent.add_argument("--environment", help="Environment name, e.g. dev or prd.")
    govern_parent.add_argument("--network-mode", help="Network mode, e.g. offline, lan, internet.")
    govern_parent.add_argument("--execution-env", help="Execution environment, e.g. local, docker, singine-isolated.")
    govern_parent.add_argument("--command", nargs="+", help="Command tokens.")
    govern_parent.add_argument("--command-text", help="Command as a single shell-like string.")
    govern_parent.add_argument("--path", action="append", help="Path target; may be repeated.")
    govern_parent.add_argument("--operation", help="CRUD-like operation label.")
    govern_parent.add_argument("--repo-path", help="Repository root path.")
    govern_parent.add_argument("--lambda-name", help="Singine lambda or internal execution name.")
    govern_parent.add_argument("--activity-id", help="Override mapped activity id.")
    govern_parent.add_argument("--notes", help="Free-form notes.")
    govern_parent.add_argument("--resource-grant-kind", help="Approval scope kind: path-prefix, command-prefix, repo, lambda.")
    govern_parent.add_argument("--json", action="store_true", help="Emit JSON payloads.")

    evaluate = ai_sub.add_parser(
        "evaluate",
        parents=[govern_parent],
        help="Evaluate a request against the canonical AI policy pack.",
    )
    evaluate.set_defaults(func=cmd_policy_ai_evaluate)

    approve = ai_sub.add_parser(
        "approve",
        parents=[govern_parent],
        help="Persist an approval for a governed AI policy request.",
    )
    approve.add_argument("--granted-by", help="Approver identity.")
    approve.add_argument("--reason", required=True, help="Approval rationale.")
    approve.add_argument("--op-vault", help="Optional 1Password vault for approval logging.")
    approve.set_defaults(func=cmd_policy_ai_approve)

    report = ai_sub.add_parser(
        "report",
        parents=[govern_parent],
        help="Show approvals, recent decisions, and invocation counters.",
    )
    report.set_defaults(func=cmd_policy_ai_report)

    template = ai_sub.add_parser(
        "template",
        help="Read a YAML AI policy template and show per-AI-system policy information.",
    )
    template.add_argument("--template-yaml", required=True, help="YAML template path shaped around Collibra AI Use Case records.")
    template.add_argument("--ai-system", help="Filter to one AI system in the template.")
    template.add_argument("--json", action="store_true", help="Emit JSON payloads.")
    template.set_defaults(func=cmd_policy_ai_template)
