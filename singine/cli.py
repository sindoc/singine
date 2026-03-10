"""Command-line interface for singine."""

import sys
import os
import subprocess
import socket
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .config import Config
from .logseq import LogseqParser, Todo, TodoStatus
from .query import filter_todos
from .eisenhower import format_eisenhower_matrix
from .knowledge_graph import KnowledgeGraph
from .logseq_url import get_page_metadata
from .operating_model import get_operating_model
from .context_enrichment import enrich_entity_with_context
from .scenario_codex import (
    SCENARIO_REGISTRY, ScenarioId, list_codes, describe_code
)
from .conversation_log import (
    ConversationLog, make_default_turn, LogseqPageRenderer,
    PrincipleOfLeastAction
)


def format_todo_table(todos: List[Todo], show_done: bool = False) -> str:
    """Format todos as a table."""
    if not todos:
        return "No todos found."

    # Filter out DONE/CANCELED unless explicitly requested
    if not show_done:
        todos = [t for t in todos if t.status not in [TodoStatus.DONE, TodoStatus.CANCELED]]

    if not todos:
        return "No active todos found."

    # Sort by status priority, then by priority, then alphabetically
    status_order = {
        TodoStatus.NOW: 0,
        TodoStatus.DOING: 1,
        TodoStatus.TODO: 2,
        TodoStatus.WAITING: 3,
        TodoStatus.LATER: 4,
        TodoStatus.DONE: 5,
        TodoStatus.CANCELED: 6,
    }

    todos.sort(key=lambda t: (
        status_order.get(t.status, 99),
        t.priority if t.priority else 'Z',
        t.content.lower()
    ))

    output = []
    for todo in todos:
        output.append(str(todo))

    return "\n".join(output)


def cmd_ls_tasks(args):
    """List tasks from Logseq."""
    try:
        config = Config()
        graph_path = config.get_logseq_path()

        parser = LogseqParser(graph_path)
        todos = parser.find_all_todos()

        # Apply WHERE filter if provided
        if args.where:
            try:
                todos = filter_todos(todos, args.where)
            except ValueError as e:
                print(f"Error in WHERE clause: {e}", file=sys.stderr)
                return 1

        # Choose output format
        if args.eisenhower:
            output = format_eisenhower_matrix(todos, use_color=not args.no_color)
        else:
            output = format_todo_table(todos, show_done=args.all)

        print(output)

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


def cmd_inspect(args):
    """Inspect an entity and show everything about it."""
    try:
        config = Config()
        graph_path = config.get_logseq_path()

        # Initialize knowledge graph
        kg = KnowledgeGraph(graph_path)

        # Load from specified sources
        if args.csv:
            csv_path = Path(args.csv)
            if csv_path.exists():
                print(f"Loading CSV: {csv_path}")
                kg.load_from_csv(csv_path)

        if args.rdf:
            rdf_path = Path(args.rdf)
            if rdf_path.exists():
                print(f"Loading RDF: {rdf_path}")
                kg.load_from_rdf(rdf_path)

        # Determine what we're inspecting
        entity = None
        query = args.entity

        # Check if it's a Logseq URL
        if query.startswith('logseq://'):
            print(f"Loading Logseq page from URL...\n")
            entity = kg.load_logseq_page(query)
        else:
            # Try to find by name
            entity = kg.query_by_name(query)

        if not entity:
            print(f"Entity not found: {query}", file=sys.stderr)
            print("\nTip: Make sure to load data sources with --csv or --rdf", file=sys.stderr)
            return 1

        # Display everything about this entity
        print("="*70)
        print(f"  ENTITY INSPECTION: {entity.display_name}")
        print("="*70)

        # Basic info
        print(f"\nEntity ID:   {entity.entity_id}")
        print(f"Entity Type: {entity.entity_type}")
        print(f"Display Name: {entity.display_name}")

        # Collibra Asset view
        if entity.collibra_asset:
            print("\n" + "-"*70)
            print("  COLLIBRA ASSET VIEW")
            print("-"*70)

            asset = entity.collibra_asset
            print(f"\nAsset Type:    {asset.asset_type.value}")
            print(f"Community:     {asset.community}")
            print(f"Domain:        {asset.domain}")
            print(f"Domain Type:   {asset.domain_type.value}")
            print(f"Status:        {asset.status.value}")

            # Standard attributes
            if asset.definition:
                print(f"\nDefinition:")
                print(f"  {asset.definition[:200]}{'...' if len(asset.definition) > 200 else ''}")

            if asset.description:
                print(f"\nDescription:")
                print(f"  {asset.description[:200]}{'...' if len(asset.description) > 200 else ''}")

            if asset.note:
                print(f"\nNote:")
                print(f"  {asset.note[:200]}{'...' if len(asset.note) > 200 else ''}")

            # Custom attributes
            if asset.attributes:
                print(f"\nAttributes:")
                for attr in asset.attributes:
                    print(f"  • {attr.attribute_type}: {attr.value}")

            # Relations
            if asset.relations:
                print(f"\nRelations ({len(asset.relations)}):")
                for rel in asset.relations:
                    print(f"  • {rel.relation_type.value}: {rel.tail_asset_name}")
                    print(f"    (target ID: {rel.tail_asset_id})")

            # Metadata
            if asset.metadata:
                print(f"\nMetadata:")
                for key, value in asset.metadata.items():
                    if isinstance(value, (list, dict)):
                        print(f"  • {key}: {json.dumps(value, indent=4)}")
                    else:
                        print(f"  • {key}: {value}")

        # Activity view
        if entity.activity:
            print("\n" + "-"*70)
            print("  ACTIVITY VIEW (PROV-O)")
            print("-"*70)

            activity = entity.activity
            print(f"\nActivity Type:  {activity.activity_type.value}")
            print(f"Status:         {activity.status}")
            print(f"Start Time:     {activity.start_time or 'N/A'}")
            print(f"End Time:       {activity.end_time or 'N/A'}")

            if activity.description:
                print(f"\nDescription:")
                print(f"  {activity.description}")

            # Agents
            if activity.agents:
                print(f"\nAgents ({len(activity.agents)}):")
                for agent in activity.agents:
                    print(f"  • {agent.display_name} ({agent.agent_type.value})")
                    if agent.roles:
                        roles = ", ".join([r.value for r in agent.roles])
                        print(f"    Roles: {roles}")
                    if agent.ai_system_category:
                        print(f"    AI Category: {agent.ai_system_category}")

            # Classification
            print(f"\nActivity Classification:")
            print(f"  • Human-led:      {'Yes' if activity.is_human_led() else 'No'}")
            print(f"  • Machine-led:    {'Yes' if activity.is_machine_led() else 'No'}")
            print(f"  • Collaborative:  {'Yes' if activity.is_collaborative() else 'No'}")

            # Entities
            if activity.used_entities:
                print(f"\nUsed Entities (inputs):")
                for ent_id in activity.used_entities:
                    print(f"  • {ent_id}")

            if activity.generated_entities:
                print(f"\nGenerated Entities (outputs):")
                for ent_id in activity.generated_entities:
                    print(f"  • {ent_id}")

        # Related entities
        related = kg.query_related(entity.entity_id)
        if related:
            print("\n" + "-"*70)
            print(f"  RELATED ENTITIES ({len(related)})")
            print("-"*70)
            for rel_entity in related:
                print(f"\n  • {rel_entity.display_name}")
                print(f"    Type: {rel_entity.entity_type}")
                if rel_entity.collibra_asset:
                    print(f"    Asset Type: {rel_entity.collibra_asset.asset_type.value}")

        # Hierarchy (if applicable)
        tree = kg.query_hierarchy(entity.entity_id)
        if tree.get('children'):
            print("\n" + "-"*70)
            print(f"  HIERARCHY (Children)")
            print("-"*70)
            print_hierarchy_tree(tree, level=0)

        # Context enrichment (location, sentiment, tech_env)
        try:
            context = enrich_entity_with_context(entity)

            print("\n" + "-"*70)
            print("  CONTEXT DIMENSIONS")
            print("-"*70)

            # Location
            if context.locations:
                print(f"\nLocation ({len(context.locations)} dimensions):")
                for loc in context.locations:
                    print(f"  • {loc['name']} ({loc['type']}, {loc['dimension']})")

            # Sentiment
            if context.sentiment:
                print(f"\nSentiment:")
                print(f"  • Type: {context.sentiment.value}")
                if context.sentiment_score is not None:
                    print(f"  • Score: {context.sentiment_score:.2f} (-1.0 to 1.0)")
                if context.mood_indicators:
                    print(f"  • Indicators: {', '.join(context.mood_indicators)}")

            # Tech Environment
            tech_items = []
            if context.tech_platforms:
                tech_items.append(f"Platforms: {', '.join(context.tech_platforms)}")
            if context.tech_standards:
                tech_items.append(f"Standards: {', '.join(context.tech_standards)}")
            if context.tech_protocols:
                tech_items.append(f"Protocols: {', '.join(context.tech_protocols)}")
            if context.tech_tools:
                tech_items.append(f"Tools: {', '.join(context.tech_tools[:5])}")

            if tech_items:
                print(f"\nTechnology Environment:")
                for item in tech_items:
                    print(f"  • {item}")

            # Business & Temporal Context
            if context.temporal_context or context.business_context:
                print(f"\nAdditional Context:")
                if context.temporal_context:
                    print(f"  • Temporal: {context.temporal_context}")
                if context.business_context:
                    print(f"  • Business: {context.business_context}")

        except Exception as e:
            # Don't fail if context enrichment fails
            print(f"\n(Context enrichment skipped: {e})")

        # JSON export option
        if args.json:
            print("\n" + "="*70)
            print("  JSON EXPORT")
            print("="*70)

            export_data = {
                "entity_id": entity.entity_id,
                "entity_type": entity.entity_type,
                "display_name": entity.display_name,
                "collibra_asset": {
                    "asset_type": entity.collibra_asset.asset_type.value,
                    "community": entity.collibra_asset.community,
                    "domain": entity.collibra_asset.domain,
                    "domain_type": entity.collibra_asset.domain_type.value,
                    "status": entity.collibra_asset.status.value,
                    "definition": entity.collibra_asset.definition,
                    "description": entity.collibra_asset.description,
                    "attributes": [
                        {"type": a.attribute_type, "value": a.value}
                        for a in entity.collibra_asset.attributes
                    ],
                    "relations": [
                        {
                            "type": r.relation_type.value,
                            "target_id": r.tail_asset_id,
                            "target_name": r.tail_asset_name
                        }
                        for r in entity.collibra_asset.relations
                    ],
                    "metadata": entity.collibra_asset.metadata
                } if entity.collibra_asset else None,
                "activity": {
                    "activity_type": entity.activity.activity_type.value,
                    "status": entity.activity.status,
                    "start_time": str(entity.activity.start_time) if entity.activity.start_time else None,
                    "end_time": str(entity.activity.end_time) if entity.activity.end_time else None,
                    "agents": [
                        {
                            "name": a.display_name,
                            "type": a.agent_type.value,
                            "roles": [r.value for r in a.roles]
                        }
                        for a in entity.activity.agents
                    ]
                } if entity.activity else None
            }

            print(json.dumps(export_data, indent=2))

        print("\n" + "="*70)
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def print_hierarchy_tree(tree, level=0):
    """Recursively print hierarchy tree."""
    entity = tree.get('entity')
    indent = "  " * level

    if level > 0:
        print(f"{indent}└─ {entity.display_name}")
        if entity.collibra_asset:
            print(f"{indent}   ({entity.collibra_asset.asset_type.value})")

    for child_tree in tree.get('children', []):
        print_hierarchy_tree(child_tree, level + 1)


def cmd_kg_stats(args):
    """Show knowledge graph statistics."""
    try:
        config = Config()
        graph_path = config.get_logseq_path()

        kg = KnowledgeGraph(graph_path)

        # Load sources
        if args.csv:
            kg.load_from_csv(Path(args.csv))
        if args.rdf:
            kg.load_from_rdf(Path(args.rdf))
        if args.logseq:
            kg.load_from_logseq()

        stats = kg.stats()

        print("\n" + "="*70)
        print("  KNOWLEDGE GRAPH STATISTICS")
        print("="*70)

        print(f"\nTotal Entities: {stats['total_entities']}")

        print("\nBreakdown by Type:")
        for key, value in sorted(stats.items()):
            if key != 'total_entities' and key.endswith('_count'):
                entity_type = key.replace('_count', '').replace('_', ' ').title()
                print(f"  {entity_type:25s} {value:5d}")

        print("\n" + "="*70)
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _get_local_ips():
    """Return non-loopback IPv4 addresses for this machine."""
    ips = []
    try:
        import socket
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ':' not in ip and not ip.startswith('127.'):
                ips.append(ip)
    except Exception:
        pass
    # Also try connecting to an external address to find primary interface
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return list(dict.fromkeys(ips))  # deduplicate preserving order


def _find_clojure():
    """Find clojure binary: PATH first, then ~/.local/clojure/bin."""
    import shutil
    clj = shutil.which('clojure')
    if clj:
        return clj
    local = Path.home() / '.local' / 'clojure' / 'bin' / 'clojure'
    if local.exists():
        return str(local)
    return None


def _find_singine_core():
    """Find singine core/ directory (parent of this file → ../../core)."""
    here = Path(__file__).resolve().parent
    # singine/singine/cli.py → singine/core/
    candidate = here.parent / 'core'
    if candidate.exists() and (candidate / 'deps.edn').exists():
        return candidate
    return None


def cmd_serve(args):
    """Start singine local network server."""
    port = args.port
    dry_run = args.dry_run

    clj = _find_clojure()
    if not clj:
        print("Error: clojure not found on PATH or ~/.local/clojure/bin/clojure", file=sys.stderr)
        print("Install: https://clojure.org/guides/install_clojure", file=sys.stderr)
        return 1

    core_dir = _find_singine_core()
    if not core_dir:
        print("Error: singine/core/ not found", file=sys.stderr)
        return 1

    ips = _get_local_ips()

    if not args.no_detect:
        print("Detecting machine capabilities...")
        try:
            cap_result = subprocess.run(
                [sys.executable, '-m', 'singine.cli', 'cap', 'detect'],
                capture_output=True, text=True, timeout=30
            )
            if cap_result.returncode == 0:
                print(cap_result.stdout.rstrip())
        except Exception:
            print("  (capability detection skipped)")
        print()

    print(f"Starting singine server on 0.0.0.0:{port}...")
    print()

    if ips:
        print("Connect from your iOS devices (same LAN):")
        for ip in ips:
            print(f"  iPad (iSH):        curl http://{ip}:{port}/health")
            print(f"  iPhone (a-Shell):  curl http://{ip}:{port}/health")
            print(f"  Android (Termux):  curl http://{ip}:{port}/health")
        print()

    print("Routes available:")
    print(f"  GET  /health          — ping")
    print(f"  GET  /cap             — machine capability profile")
    print(f"  GET  /messages        — mail search (?search=<term>)")
    print(f"  GET  /loc/<iata>      — resolve IATA → URN + timezone")
    print(f"  GET  /timez           — timezone query (?cities=BRU,NYC)")
    print()
    if dry_run:
        print("  [DRY-RUN: no real mail/Kafka I/O]")
        print()
    print("Press Ctrl-C to stop.")
    print()

    cmd = [clj, '-M:serve']
    if dry_run:
        cmd.append('--dry-run')
    if port != 8080:
        cmd.extend(['--port', str(port)])

    try:
        proc = subprocess.run(cmd, cwd=str(core_dir))
        return proc.returncode
    except KeyboardInterrupt:
        print("\nsingine server stopped.")
        return 0
    except FileNotFoundError:
        print(f"Error: could not start clojure at {clj}", file=sys.stderr)
        return 1


def cmd_cap_detect(args):
    """Detect machine capabilities."""
    import platform
    import shutil

    caps = []
    profile = {
        'hostname': socket.gethostname(),
        'user': os.environ.get('USER', os.environ.get('USERNAME', 'unknown')),
        'os': platform.system(),
        'os-version': platform.release(),
        'python': sys.version.split()[0],
    }

    # Java
    clj = _find_clojure()
    java = shutil.which('java')
    if java:
        try:
            r = subprocess.run(['java', '-version'], capture_output=True, text=True, timeout=5)
            profile['java'] = r.stderr.split('\n')[0] if r.stderr else 'present'
            caps.extend(['java', 'broker', 'kg', 'sec'])
        except Exception:
            profile['java'] = 'not detected'
    else:
        profile['java'] = 'unavailable'

    # Clojure
    profile['clojure'] = clj if clj else 'unavailable'
    if clj:
        caps.append('clojure')

    # Docker
    docker = shutil.which('docker')
    if docker:
        try:
            r = subprocess.run(['docker', 'info'], capture_output=True, timeout=5)
            if r.returncode == 0:
                caps.extend(['docker', 'edge'])
                profile['docker'] = 'running'
            else:
                profile['docker'] = 'installed (daemon not running)'
        except Exception:
            profile['docker'] = 'installed'
    else:
        profile['docker'] = 'unavailable'

    # Git
    git = shutil.which('git')
    if git:
        try:
            r = subprocess.run(['git', '--version'], capture_output=True, text=True, timeout=5)
            profile['git'] = r.stdout.strip()
        except Exception:
            profile['git'] = 'present'
    else:
        profile['git'] = 'unavailable'

    # SSH
    ssh_key = Path.home() / '.ssh' / 'id_rsa.pub'
    if not ssh_key.exists():
        ssh_key = Path.home() / '.ssh' / 'id_ed25519.pub'
    if ssh_key.exists():
        caps.append('ssh')
        profile['ssh'] = str(ssh_key)
    else:
        profile['ssh'] = 'no key found'

    # Always available
    caps = ['mail', 'cli', 'python'] + [c for c in caps if c not in ('mail', 'cli', 'python')]
    profile['capabilities'] = caps

    if hasattr(args, 'json') and args.json:
        print(json.dumps(profile, indent=2))
    else:
        print(f"  hostname:     {profile['hostname']}")
        print(f"  user:         {profile['user']}")
        print(f"  os:           {profile['os']} {profile['os-version']}")
        print(f"  python:       {profile['python']}")
        print(f"  java:         {profile['java']}")
        print(f"  clojure:      {profile['clojure']}")
        print(f"  docker:       {profile['docker']}")
        print(f"  git:          {profile['git']}")
        print(f"  ssh:          {profile['ssh']}")
        print(f"  capabilities: {', '.join(caps)}")
    return 0


def cmd_cap_deploy(args):
    """Show deploy order for this machine."""
    print("Deploy order for this machine:")
    # Basic deploy order based on Python-detectable capabilities
    order = ['mail']
    import shutil
    if shutil.which('java'):
        order.extend(['broker', 'kg'])
    if shutil.which('docker'):
        order.append('edge')
    order.append('checkin')
    for i, step in enumerate(order, 1):
        print(f"  {i}. {step}")
    return 0


# ============================================================================
# Scenario commands
# ============================================================================

def _get_graph_path() -> Optional[Path]:
    """Return the configured Logseq graph path, or None if not configured."""
    try:
        return Config().get_logseq_path()
    except (FileNotFoundError, ValueError):
        return None


def cmd_codex(args):
    """List all four-letter codes or describe a specific one."""
    code = getattr(args, 'code', None)
    if code:
        code = code.upper()
        print(describe_code(code))
    else:
        print("Singine Scenario Codex — Four-Letter Codes\n")
        print(f"  {'CODE':<6}  {'NAME':<45}  {'URN PREFIX'}")
        print("  " + "-" * 80)
        for flc in list_codes():
            urn = f"urn:singine:scenario:{flc.code}:NNNN"
            print(f"  {flc.code:<6}  {flc.name:<45}  {urn}")
        print()
        print(f"  Total codes: {len(SCENARIO_REGISTRY)}")
        print(f"  Collibra parent type: Business Asset (SCEN)")
    return 0


def cmd_scenario_ls(args):
    """List existing scenarios."""
    graph_path = _get_graph_path()
    code = getattr(args, 'code', None)
    if code:
        code = code.upper()

    if graph_path is None:
        print("Warning: Logseq graph path not configured. No scenarios on disk.", file=sys.stderr)
        print("Create ~/.singine/backend.config with [logseq] graph_path = /path/to/graph")
        return 0

    ids = ScenarioId.list_all(graph_path, code=code)

    if not ids:
        label = f" for code {code}" if code else ""
        print(f"No scenarios found{label}.")
        return 0

    print(f"  {'ID':<12}  {'URN':<40}  {'Logseq page'}")
    print("  " + "-" * 80)
    for sid in ids:
        print(f"  {str(sid):<12}  {sid.urn():<40}  {sid.logseq_path()}")
    print(f"\n  Total: {len(ids)}")
    return 0


def cmd_scenario_new(args):
    """Create a new scenario scaffold."""
    code = args.code.upper()
    description = args.description

    if code not in SCENARIO_REGISTRY:
        print(f"Error: unknown code {code!r}. Run 'singine codex' to list valid codes.",
              file=sys.stderr)
        return 1

    graph_path = _get_graph_path()
    if graph_path is None:
        print("Error: Logseq graph path not configured.", file=sys.stderr)
        return 1

    sid = ScenarioId.next(code, graph_path)
    out_path = sid.logseq_abs_path(graph_path)

    # Create scaffold
    out_path.parent.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    scaffold = (
        f"type:: scenario\n"
        f"scenario-code:: {sid}\n"
        f"urn:: {sid.urn()}\n"
        f"collibra-asset:: {sid.collibra_id()}\n"
        f"description:: {description}\n"
        f"status:: pending\n"
        f"created-at:: {created_at}\n"
        f"tags:: scenario, {code}\n"
        f"\n"
        f"# {sid}: {SCENARIO_REGISTRY[code].name}\n"
        f"\n"
        f"> {description}\n"
        f"\n"
        f"<!-- Run: singine scenario run {sid} -->\n"
    )
    out_path.write_text(scaffold, encoding="utf-8")

    print(f"Created: {sid}")
    print(f"URN:     {sid.urn()}")
    print(f"Path:    {out_path}")
    return 0


def cmd_scenario_show(args):
    """Display scenario metadata."""
    try:
        sid = ScenarioId.parse(args.scenario_id)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    graph_path = _get_graph_path()
    if graph_path is None:
        print("Error: Logseq graph path not configured.", file=sys.stderr)
        return 1

    page_path = sid.logseq_abs_path(graph_path)
    if not page_path.exists():
        print(f"Error: scenario {sid} not found at {page_path}", file=sys.stderr)
        return 1

    info = sid.code_info()
    print(f"  Scenario ID:  {sid}")
    print(f"  URN:          {sid.urn()}")
    print(f"  Code:         {info.code} — {info.name}")
    print(f"  Collibra:     {sid.collibra_id()}")
    print(f"  Logseq page:  {page_path}")
    print()
    # Print frontmatter lines (leading property lines)
    content = page_path.read_text(encoding="utf-8")
    for line in content.splitlines():
        if '::' in line:
            print(f"  {line}")
        elif line.startswith('#') or not line:
            break
    return 0


def cmd_scenario_run(args):
    """Execute the scenario pipeline: generate 4 responses + PoLA selection."""
    try:
        sid = ScenarioId.parse(args.scenario_id)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    graph_path = _get_graph_path()
    if graph_path is None:
        print("Error: Logseq graph path not configured.", file=sys.stderr)
        return 1

    page_path = sid.logseq_abs_path(graph_path)
    if not page_path.exists():
        print(f"Error: scenario {sid} not found. Run: singine scenario new {sid.code} \"..\"",
              file=sys.stderr)
        return 1

    # Read description from scaffold
    content = page_path.read_text(encoding="utf-8")
    description = ""
    group_a = "Group A"
    group_b = "Group B"
    for line in content.splitlines():
        if line.startswith("description::"):
            description = line.split("::", 1)[1].strip()
        elif line.startswith("group-a::"):
            group_a = line.split("::", 1)[1].strip().strip("[]")
        elif line.startswith("group-b::"):
            group_b = line.split("::", 1)[1].strip().strip("[]")
    if not description:
        description = f"Scenario {sid}"
    if group_a == "Group A":
        group_a = "Engineering Team"
    if group_b == "Group B":
        group_b = "Product Team"

    print(f"Running scenario {sid}…")
    print(f"  Group A: {group_a}")
    print(f"  Group B: {group_b}")
    print(f"  Request: {description}")
    print()

    # Generate turn with 4 responses + PoLA
    turn = make_default_turn(
        scenario_id=sid,
        request=description,
        group_a_name=group_a,
        group_b_name=group_b,
    )

    # Show metrics table
    metrics = turn.metrics_list()
    print("  Response Candidates:")
    print(f"  {'R#':<4}  {'Strategy':<20}  {'S':<8}  {'Δ':<8}  {'η':<8}  {'L':<8}  {'Selected'}")
    print("  " + "-" * 72)
    for m in metrics:
        sel = "✓" if m.selected else ""
        print(
            f"  {m.response_id:<4}  "
            f"{m.strategy.value.replace('_',' ').title():<20}  "
            f"{m.action_score:<8.2f}  "
            f"{m.net_result:<8.2f}  "
            f"{m.efficiency:<8.2f}  "
            f"{m.lagrangian:<8.2f}  "
            f"{sel}"
        )
    print()
    print(PrincipleOfLeastAction.explain(metrics))
    print()

    # Write full Logseq page
    log = ConversationLog(scenario_id=sid)
    log.add_turn(turn)
    renderer = LogseqPageRenderer()
    out_path = renderer.render(log, graph_path)
    print(f"Logseq page written: {out_path}")
    return 0


def cmd_scenario_log(args):
    """Print the Logseq page content for a scenario."""
    try:
        sid = ScenarioId.parse(args.scenario_id)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    graph_path = _get_graph_path()
    if graph_path is None:
        print("Error: Logseq graph path not configured.", file=sys.stderr)
        return 1

    page_path = sid.logseq_abs_path(graph_path)
    if not page_path.exists():
        print(f"Error: no Logseq page for {sid}. Run: singine scenario run {sid}",
              file=sys.stderr)
        return 1

    print(page_path.read_text(encoding="utf-8"))
    return 0


def cmd_scenario_diff(args):
    """Show a diff between two scenario Logseq pages."""
    try:
        sid_a = ScenarioId.parse(args.scenario_id_a)
        sid_b = ScenarioId.parse(args.scenario_id_b)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    graph_path = _get_graph_path()
    if graph_path is None:
        print("Error: Logseq graph path not configured.", file=sys.stderr)
        return 1

    path_a = sid_a.logseq_abs_path(graph_path)
    path_b = sid_b.logseq_abs_path(graph_path)

    for p, sid in [(path_a, sid_a), (path_b, sid_b)]:
        if not p.exists():
            print(f"Error: {sid} not found at {p}", file=sys.stderr)
            return 1

    import difflib
    lines_a = path_a.read_text(encoding="utf-8").splitlines(keepends=True)
    lines_b = path_b.read_text(encoding="utf-8").splitlines(keepends=True)
    diff = difflib.unified_diff(
        lines_a, lines_b,
        fromfile=str(sid_a),
        tofile=str(sid_b),
    )
    sys.stdout.writelines(diff)
    return 0


def cmd_push(args):
    """Publish a scenario event to Kafka (or log to console in dry-run)."""
    try:
        sid = ScenarioId.parse(args.scenario_id)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    graph_path = _get_graph_path()
    page_path = sid.logseq_abs_path(graph_path) if graph_path else None

    event = {
        "scenario-code": sid.code,
        "scenario-id": str(sid),
        "urn": sid.urn(),
        "collibra-id": sid.collibra_id(),
        "event-type": "scenario-published",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dry-run": True,
    }

    if page_path and page_path.exists():
        event["page-path"] = str(page_path)

    print(f"[singine push] {sid}  (dry-run: no Kafka connection)")
    print(json.dumps(event, indent=2))
    return 0


def cmd_pull(args):
    """Consume latest events for a scenario code from Kafka (dry-run: show status)."""
    code = args.code.upper() if hasattr(args, 'code') else None
    if code and code not in SCENARIO_REGISTRY:
        print(f"Error: unknown code {code!r}", file=sys.stderr)
        return 1

    graph_path = _get_graph_path()
    label = f" ({code})" if code else ""
    print(f"[singine pull{label}]  (dry-run: no Kafka connection)")

    if graph_path:
        ids = ScenarioId.list_all(graph_path, code=code)
        print(f"Local scenarios{label}: {len(ids)}")
        for sid in ids:
            print(f"  {sid}")
    else:
        print("No Logseq graph configured; cannot show local scenarios.")
    return 0


def cmd_status(args):
    """Show pending/running scenarios (like git status)."""
    graph_path = _get_graph_path()
    if graph_path is None:
        print("No Logseq graph configured.", file=sys.stderr)
        return 1

    all_ids = ScenarioId.list_all(graph_path)
    pending = []
    published = []

    for sid in all_ids:
        page_path = sid.logseq_abs_path(graph_path)
        content = page_path.read_text(encoding="utf-8") if page_path.exists() else ""
        if "status:: pending" in content:
            pending.append(sid)
        else:
            published.append(sid)

    print("Singine scenario status")
    print()
    if pending:
        print(f"Pending ({len(pending)}):")
        for sid in pending:
            print(f"  {sid}  [pending]")
    if published:
        print(f"\nPublished ({len(published)}):")
        for sid in published:
            print(f"  {sid}  [ok]")
    if not all_ids:
        print("  (no scenarios yet — run: singine scenario new DIAC \"...\")")
    return 0


# ============================================================================
# make command
# ============================================================================

def cmd_make_list(args):
    """
    Create a list from Logseq pages via Virtual SQL.

    Usage: singine make list <page1.md> [<page2.md> ...]

    Queries the Virtual SQL logseq_pages table for each named page and renders
    the result as a Logseq markdown list to stdout. Results are also persisted
    to ~/.singine/singine.db.

    If the Go binary is available on PATH it delegates to it; otherwise
    falls back to a pure-Python implementation backed by SQLite.
    """
    import shutil

    pages: list[str] = args.pages
    if not pages:
        print("Error: at least one page name required.", file=sys.stderr)
        print("Usage: singine make list TLN.md Home.md")
        return 1

    # Attempt to delegate to Go binary (singine-go or ./singine built from cmd/singine)
    go_bin = shutil.which("singine-go") or shutil.which("./singine-go")
    if go_bin:
        result = subprocess.run([go_bin, "make", "list"] + pages)
        return result.returncode

    # Pure-Python fallback via Virtual SQL (sqlite3 backend)
    graph_path = _get_graph_path()
    if graph_path is None:
        print("Error: Logseq graph path not configured.", file=sys.stderr)
        return 1

    rows = _vsql_pages_for_names(graph_path, pages)

    if not rows:
        print("(no matching pages found)")
        return 0

    for row in rows:
        name = row.get("page_name", "")
        props = row.get("properties", {})
        prop_str = "  ".join(f"{k}:: {v}" for k, v in props.items()) if props else ""
        label = name.replace(".md", "")
        line = f"- [[{label}]]"
        if prop_str:
            line += f"  {prop_str}"
        print(line)

    return 0


def _vsql_pages_for_names(graph_path: Path, names: list[str]) -> list[dict]:
    """
    Pure-Python Virtual SQL: load named Logseq pages into SQLite and query them.

    Creates/updates ~/.singine/singine.db with a logseq_pages table.
    Returns list of row dicts with keys: page_name, title, alias, page_type,
    content, properties (dict), created_at, updated_at.
    """
    import sqlite3
    import hashlib
    import time

    db_path = Path.home() / ".singine" / "singine.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Create table if needed
    cur.execute("""
        CREATE TABLE IF NOT EXISTS logseq_pages (
            page_name   TEXT PRIMARY KEY,
            title       TEXT,
            alias       TEXT,
            page_type   TEXT,
            content     TEXT,
            properties  TEXT,
            created_at  TEXT,
            updated_at  TEXT
        )
    """)
    conn.commit()

    # Upsert pages from disk
    pages_dir = graph_path / "pages"
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for name in names:
        page_file = pages_dir / name
        if not page_file.exists():
            # Try without .md suffix
            page_file = pages_dir / (name if name.endswith(".md") else name + ".md")
        if not page_file.exists():
            continue

        raw = page_file.read_text(encoding="utf-8")
        props: dict = {}
        for line in raw.splitlines():
            if "::" in line:
                k, _, v = line.partition("::")
                props[k.strip()] = v.strip()
            elif line.startswith("#"):
                break

        title = props.get("title", name.replace(".md", ""))
        alias = props.get("alias", "")
        page_type = props.get("type", "")
        props_json = json.dumps(props)

        cur.execute("""
            INSERT INTO logseq_pages
                (page_name, title, alias, page_type, content, properties, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(page_name) DO UPDATE SET
                title=excluded.title, alias=excluded.alias,
                page_type=excluded.page_type, content=excluded.content,
                properties=excluded.properties, updated_at=excluded.updated_at
        """, (name, title, alias, page_type, raw, props_json, now_iso, now_iso))

    conn.commit()

    # Query
    placeholders = ",".join("?" * len(names))
    rows = cur.execute(
        f"SELECT * FROM logseq_pages WHERE page_name IN ({placeholders})",
        names
    ).fetchall()

    conn.close()

    results = []
    for row in rows:
        d = dict(row)
        try:
            d["properties"] = json.loads(d.get("properties") or "{}")
        except (json.JSONDecodeError, TypeError):
            d["properties"] = {}
        results.append(d)

    return results


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog='singine',
        description='Manage Logseq todos and query knowledge graph'
    )
    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s 0.2.0'
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # ls command
    ls_parser = subparsers.add_parser('ls', help='List items')
    ls_subparsers = ls_parser.add_subparsers(dest='subcommand', help='What to list')

    # ls tasks
    tasks_parser = ls_subparsers.add_parser('tasks', help='List all tasks/todos')
    tasks_parser.add_argument(
        '-a', '--all',
        action='store_true',
        help='Show all tasks including completed ones'
    )
    tasks_parser.add_argument(
        '-where', '--where',
        type=str,
        dest='where',
        metavar='CONDITION',
        help='Filter tasks using WHERE clause (e.g., -where "Last Updated Date" >= pastDay#"3 months")'
    )
    tasks_parser.add_argument(
        '-e', '--eisenhower',
        action='store_true',
        help='Display tasks using Eisenhower Matrix (urgent/important quadrants)'
    )
    tasks_parser.add_argument(
        '--no-color',
        action='store_true',
        help='Disable colored output'
    )
    tasks_parser.set_defaults(func=cmd_ls_tasks)

    # inspect command - THE KEY COMMAND
    inspect_parser = subparsers.add_parser(
        'inspect',
        help='Inspect an entity and show EVERYTHING about it'
    )
    inspect_parser.add_argument(
        'entity',
        type=str,
        help='Entity name or Logseq URL (e.g., "Core Data" or "logseq://graph/...")'
    )
    inspect_parser.add_argument(
        '--csv',
        type=str,
        help='Path to CSV file with data categories'
    )
    inspect_parser.add_argument(
        '--rdf',
        type=str,
        help='Path to RDF/SKOS file'
    )
    inspect_parser.add_argument(
        '--json',
        action='store_true',
        help='Also output as JSON'
    )
    inspect_parser.set_defaults(func=cmd_inspect)

    # kg command (knowledge graph)
    kg_parser = subparsers.add_parser('kg', help='Knowledge graph operations')
    kg_subparsers = kg_parser.add_subparsers(dest='kg_subcommand', help='KG operations')

    # kg stats
    stats_parser = kg_subparsers.add_parser('stats', help='Show knowledge graph statistics')
    stats_parser.add_argument('--csv', type=str, help='Load CSV data categories')
    stats_parser.add_argument('--rdf', type=str, help='Load RDF concepts')
    stats_parser.add_argument('--logseq', action='store_true', help='Load Logseq todos')
    stats_parser.set_defaults(func=cmd_kg_stats)

    # serve command — start local network server for iOS/Android devices
    serve_parser = subparsers.add_parser(
        'serve',
        help='Start singine local network server (Apache Camel + Jetty on :8080)'
    )
    serve_parser.add_argument(
        '--port', '-p',
        type=int,
        default=8080,
        help='HTTP port to listen on (default: 8080)'
    )
    serve_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry-run mode: no real mail/Kafka I/O (synthetic responses)'
    )
    serve_parser.add_argument(
        '--no-detect',
        action='store_true',
        help='Skip capability detection (faster startup)'
    )
    serve_parser.set_defaults(func=cmd_serve)

    # cap command — machine capability detection
    cap_parser = subparsers.add_parser(
        'cap',
        help='Machine capability detection and trust store management'
    )
    cap_subparsers = cap_parser.add_subparsers(dest='cap_subcommand', help='Cap operations')

    detect_parser = cap_subparsers.add_parser('detect', help='Detect machine capabilities')
    detect_parser.add_argument('--json', action='store_true', help='Output as JSON')
    detect_parser.set_defaults(func=cmd_cap_detect)

    deploy_parser = cap_subparsers.add_parser('deploy', help='Show deploy order for this machine')
    deploy_parser.set_defaults(func=cmd_cap_deploy)

    cap_parser.set_defaults(func=lambda args: cap_parser.print_help() or 0)

    # ------------------------------------------------------------------ codex
    codex_parser = subparsers.add_parser(
        'codex',
        help='List or describe four-letter scenario codes (Collibra-aligned)'
    )
    codex_parser.add_argument(
        'code',
        nargs='?',
        help='Four-letter code to describe (e.g. DIAC); omit to list all'
    )
    codex_parser.set_defaults(func=cmd_codex)

    # ------------------------------------------------------------------ status
    status_parser = subparsers.add_parser(
        'status',
        help='Show pending/running scenarios (like git status)'
    )
    status_parser.set_defaults(func=cmd_status)

    # ------------------------------------------------------------------ push
    push_parser = subparsers.add_parser(
        'push',
        help='Publish a scenario event to Kafka (or log to console in dry-run)'
    )
    push_parser.add_argument('scenario_id', help='Scenario ID, e.g. DIAC-0001')
    push_parser.set_defaults(func=cmd_push)

    # ------------------------------------------------------------------ pull
    pull_parser = subparsers.add_parser(
        'pull',
        help='Consume latest events for a scenario code from Kafka'
    )
    pull_parser.add_argument('code', help='Four-letter code, e.g. DIAC')
    pull_parser.set_defaults(func=cmd_pull)

    # ------------------------------------------------------------------ scenario
    scenario_parser = subparsers.add_parser(
        'scenario',
        help='Scenario lifecycle management (new, ls, show, run, log, diff)'
    )
    scenario_subparsers = scenario_parser.add_subparsers(
        dest='scenario_subcommand', help='Scenario operations'
    )

    # scenario ls [CODE]
    s_ls = scenario_subparsers.add_parser('ls', help='List scenarios')
    s_ls.add_argument('code', nargs='?', help='Filter by four-letter code (e.g. DIAC)')
    s_ls.set_defaults(func=cmd_scenario_ls)

    # scenario new CODE "description"
    s_new = scenario_subparsers.add_parser('new', help='Create a new scenario scaffold')
    s_new.add_argument('code', help='Four-letter code (e.g. DIAC)')
    s_new.add_argument('description', help='Short description of the scenario')
    s_new.set_defaults(func=cmd_scenario_new)

    # scenario show DIAC-0001
    s_show = scenario_subparsers.add_parser('show', help='Display scenario metadata')
    s_show.add_argument('scenario_id', help='Scenario ID, e.g. DIAC-0001')
    s_show.set_defaults(func=cmd_scenario_show)

    # scenario run DIAC-0001
    s_run = scenario_subparsers.add_parser(
        'run', help='Execute the scenario: generate 4 responses + PoLA selection'
    )
    s_run.add_argument('scenario_id', help='Scenario ID, e.g. DIAC-0001')
    s_run.set_defaults(func=cmd_scenario_run)

    # scenario log DIAC-0001
    s_log = scenario_subparsers.add_parser('log', help='Show the Logseq page content')
    s_log.add_argument('scenario_id', help='Scenario ID, e.g. DIAC-0001')
    s_log.set_defaults(func=cmd_scenario_log)

    # scenario diff DIAC-0001 DIAC-0002
    s_diff = scenario_subparsers.add_parser('diff', help='Diff two scenario Logseq pages')
    s_diff.add_argument('scenario_id_a', help='First scenario ID')
    s_diff.add_argument('scenario_id_b', help='Second scenario ID')
    s_diff.set_defaults(func=cmd_scenario_diff)

    scenario_parser.set_defaults(func=lambda a: scenario_parser.print_help() or 0)

    # ------------------------------------------------------------------ make
    make_parser = subparsers.add_parser(
        'make',
        help='Create lists and artefacts from Logseq data via Virtual SQL'
    )
    make_subparsers = make_parser.add_subparsers(
        dest='make_subcommand', help='make operations'
    )

    # make list <page1> [<page2> ...]
    m_list = make_subparsers.add_parser(
        'list',
        help='Create a list from Logseq pages (queries Virtual SQL logseq_pages)'
    )
    m_list.add_argument(
        'pages',
        nargs='+',
        help='Logseq page names, e.g. TLN.md Home.md'
    )
    m_list.set_defaults(func=cmd_make_list)

    make_parser.set_defaults(func=lambda a: make_parser.print_help() or 0)

    # ------------------------------------------------------------------ dispatch
    args = parser.parse_args()

    if not hasattr(args, 'func'):
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
