"""Command-line interface for singine."""

import sys
import argparse
import json
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

    args = parser.parse_args()

    if not hasattr(args, 'func'):
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
