"""Knowledge Graph query interface for Singine.

Provides natural language querying over integrated knowledge from:
- Logseq pages and todos
- CSV Data Categories
- RDF/SKOS AI concepts
- Viewed through Collibra metamodel lens
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .parsers import CSVDataCategoryParser, RDFSKOSParser
from .logseq_url import LogseqMetadataExtractor, LogseqURLParser, PageMetadata
from .logseq import LogseqParser, Todo
from .lens.collibra import CollibraLens, CollibraAsset, CollibraRelationType
from .lens.activity import ActivityLens, Activity
from .config import Config


@dataclass
class KnowledgeGraphEntity:
    """Unified entity in the knowledge graph."""
    entity_id: str
    entity_type: str  # "data_category", "ai_concept", "logseq_page", "todo"
    display_name: str

    # Collibra view
    collibra_asset: Optional[CollibraAsset] = None

    # Activity view (if applicable)
    activity: Optional[Activity] = None

    # Relations
    related_entities: List[str] = None

    def __post_init__(self):
        if self.related_entities is None:
            self.related_entities = []


class KnowledgeGraph:
    """Integrated knowledge graph combining multiple sources."""

    def __init__(self, graph_path: Path):
        """Initialize knowledge graph.

        Args:
            graph_path: Path to Logseq graph directory
        """
        self.graph_path = graph_path
        self.collibra_lens = CollibraLens()
        self.activity_lens = ActivityLens()

        # Storage for entities
        self.entities: Dict[str, KnowledgeGraphEntity] = {}

        # Indexes for fast lookup
        self.by_type: Dict[str, List[str]] = {}
        self.by_name: Dict[str, str] = {}

    def load_from_csv(self, csv_path: Path) -> None:
        """Load Data Categories from CSV.

        Args:
            csv_path: Path to Collibra CSV export
        """
        parser = CSVDataCategoryParser(csv_path)
        rows = parser.parse()

        for row in rows:
            # Transform to Collibra Asset
            collibra_asset = self.collibra_lens._transform_data_category(row)

            entity = KnowledgeGraphEntity(
                entity_id=collibra_asset.asset_id,
                entity_type="data_category",
                display_name=collibra_asset.display_name,
                collibra_asset=collibra_asset
            )

            # Extract relations
            for relation in collibra_asset.relations:
                entity.related_entities.append(relation.tail_asset_id)

            self._index_entity(entity)

    def load_from_rdf(self, rdf_path: Path) -> None:
        """Load AI concepts from RDF/SKOS.

        Args:
            rdf_path: Path to RDF/XML file
        """
        parser = RDFSKOSParser(rdf_path)
        concepts = parser.parse()

        for concept in concepts:
            # Transform to Collibra Asset
            collibra_asset = self.collibra_lens._transform_ai_concept(concept)

            entity = KnowledgeGraphEntity(
                entity_id=collibra_asset.asset_id,
                entity_type="ai_concept",
                display_name=collibra_asset.display_name,
                collibra_asset=collibra_asset
            )

            # Extract relations
            for relation in collibra_asset.relations:
                entity.related_entities.append(relation.tail_asset_id)

            self._index_entity(entity)

    def load_from_logseq(self) -> None:
        """Load Logseq pages and todos."""
        # Load todos
        logseq_parser = LogseqParser(self.graph_path)
        todos = logseq_parser.find_all_todos()

        for todo in todos:
            # Transform to Collibra Asset and Activity
            collibra_asset = self.collibra_lens._transform_logseq_todo(todo)
            activity = self.activity_lens._transform_logseq_todo(todo)

            entity = KnowledgeGraphEntity(
                entity_id=collibra_asset.asset_id,
                entity_type="todo",
                display_name=collibra_asset.display_name,
                collibra_asset=collibra_asset,
                activity=activity
            )

            self._index_entity(entity)

    def load_logseq_page(self, page_name_or_url: str) -> KnowledgeGraphEntity:
        """Load a specific Logseq page into the knowledge graph.

        Args:
            page_name_or_url: Page name or logseq:// URL

        Returns:
            KnowledgeGraphEntity for the page
        """
        extractor = LogseqMetadataExtractor(self.graph_path)

        if page_name_or_url.startswith('logseq://'):
            metadata = extractor.extract_from_url(page_name_or_url)
        else:
            metadata = extractor.extract_from_page(page_name_or_url)

        if not metadata or not metadata.exists:
            raise ValueError(f"Page not found: {page_name_or_url}")

        # Transform to Collibra Asset
        collibra_asset = self.collibra_lens._transform_logseq_page(metadata)

        entity = KnowledgeGraphEntity(
            entity_id=collibra_asset.asset_id,
            entity_type="logseq_page",
            display_name=collibra_asset.display_name,
            collibra_asset=collibra_asset
        )

        # Extract relations
        for relation in collibra_asset.relations:
            entity.related_entities.append(relation.tail_asset_id)

        self._index_entity(entity)
        return entity

    def _index_entity(self, entity: KnowledgeGraphEntity) -> None:
        """Index an entity for fast lookup."""
        self.entities[entity.entity_id] = entity

        # Index by type
        if entity.entity_type not in self.by_type:
            self.by_type[entity.entity_type] = []
        self.by_type[entity.entity_type].append(entity.entity_id)

        # Index by name (lowercase for case-insensitive search)
        self.by_name[entity.display_name.lower()] = entity.entity_id

    def query_by_name(self, name: str) -> Optional[KnowledgeGraphEntity]:
        """Find entity by name (case-insensitive).

        Args:
            name: Entity name to search for

        Returns:
            KnowledgeGraphEntity or None
        """
        entity_id = self.by_name.get(name.lower())
        return self.entities.get(entity_id) if entity_id else None

    def query_by_type(self, entity_type: str) -> List[KnowledgeGraphEntity]:
        """Find all entities of a given type.

        Args:
            entity_type: Type to filter by

        Returns:
            List of matching entities
        """
        entity_ids = self.by_type.get(entity_type, [])
        return [self.entities[eid] for eid in entity_ids]

    def query_related(self, entity_id: str, relation_type: Optional[str] = None) -> List[KnowledgeGraphEntity]:
        """Find entities related to a given entity.

        Args:
            entity_id: Source entity ID
            relation_type: Optional relation type filter

        Returns:
            List of related entities
        """
        entity = self.entities.get(entity_id)
        if not entity:
            return []

        related = []

        # Get related entity IDs
        for related_id in entity.related_entities:
            related_entity = self.entities.get(related_id)
            if related_entity:
                # Filter by relation type if specified
                if relation_type:
                    # Check if relation matches type
                    if entity.collibra_asset:
                        for rel in entity.collibra_asset.relations:
                            if (rel.tail_asset_id == related_id and
                                rel.relation_type.value == relation_type):
                                related.append(related_entity)
                                break
                else:
                    related.append(related_entity)

        return related

    def query_hierarchy(self, root_entity_id: str) -> Dict[str, Any]:
        """Get hierarchical tree starting from root entity.

        Args:
            root_entity_id: Root entity ID

        Returns:
            Nested dictionary representing hierarchy
        """
        root = self.entities.get(root_entity_id)
        if not root:
            return {}

        tree = {
            'entity': root,
            'children': []
        }

        # Find children (entities grouped by this entity)
        for entity_id, entity in self.entities.items():
            if entity.collibra_asset:
                for relation in entity.collibra_asset.relations:
                    if (relation.relation_type == CollibraRelationType.GROUPED_BY and
                        relation.tail_asset_id == root_entity_id):
                        # Recursive call for child
                        child_tree = self.query_hierarchy(entity_id)
                        tree['children'].append(child_tree)

        return tree

    def query_activities_by_agent_type(self, is_human: bool) -> List[Activity]:
        """Find activities by agent type (human-led or machine-led).

        Args:
            is_human: True for human-led, False for machine-led

        Returns:
            List of matching activities
        """
        activities = []

        for entity in self.entities.values():
            if entity.activity:
                if is_human and entity.activity.is_human_led():
                    activities.append(entity.activity)
                elif not is_human and entity.activity.is_machine_led():
                    activities.append(entity.activity)

        return activities

    def query_collaborative_activities(self) -> List[Activity]:
        """Find activities involving both human and machine agents.

        Returns:
            List of collaborative activities
        """
        activities = []

        for entity in self.entities.values():
            if entity.activity and entity.activity.is_collaborative():
                activities.append(entity.activity)

        return activities

    def stats(self) -> Dict[str, int]:
        """Get knowledge graph statistics.

        Returns:
            Dictionary with entity counts by type
        """
        stats = {
            'total_entities': len(self.entities),
        }

        for entity_type, entity_ids in self.by_type.items():
            stats[f'{entity_type}_count'] = len(entity_ids)

        return stats


def build_knowledge_graph(csv_path: Optional[Path] = None,
                          rdf_path: Optional[Path] = None,
                          include_logseq: bool = True) -> KnowledgeGraph:
    """Build knowledge graph from available sources.

    Args:
        csv_path: Optional path to CSV data categories
        rdf_path: Optional path to RDF/SKOS file
        include_logseq: Whether to include Logseq todos

    Returns:
        KnowledgeGraph instance
    """
    config = Config()
    graph_path = config.get_logseq_path()

    kg = KnowledgeGraph(graph_path)

    if csv_path and csv_path.exists():
        kg.load_from_csv(csv_path)

    if rdf_path and rdf_path.exists():
        kg.load_from_rdf(rdf_path)

    if include_logseq:
        kg.load_from_logseq()

    return kg
