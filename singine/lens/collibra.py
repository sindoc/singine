"""Collibra metamodel lens for transforming entities into Collibra concepts.

This lens maps various source entities to Collibra's metamodel:
- Communities
- Domains (Domain Types)
- Assets (Asset Types: Business Asset, Data Asset, Governance Asset, etc.)
- Attributes
- Relations (head → tail relationships)
- Complex Relations (many-to-many with attributes)
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from .base import Lens, LensEntity


class CollibraAssetType(Enum):
    """Collibra out-of-the-box asset types."""
    # Top-level categories
    BUSINESS_ASSET = "Business Asset"
    DATA_ASSET = "Data Asset"
    GOVERNANCE_ASSET = "Governance Asset"
    TECHNOLOGY_ASSET = "Technology Asset"
    ISSUE = "Issue"

    # Business Assets (specialized)
    BUSINESS_CAPABILITY = "Business Capability"
    BUSINESS_PROCESS = "Business Process"
    BUSINESS_TERM = "Business Term"
    DATA_CATEGORY = "Data Category"

    # Data Assets (specialized)
    DATABASE = "Database"
    SCHEMA = "Schema"
    TABLE = "Table"
    COLUMN = "Column"
    DATA_ELEMENT = "Data Element"

    # Governance Assets (specialized)
    POLICY = "Policy"
    RULE = "Rule"
    STANDARD = "Standard"


class CollibraDomainType(Enum):
    """Collibra domain types for organizing assets."""
    GLOSSARY = "Glossary"
    PHYSICAL_DATA_DICTIONARY = "Physical Data Dictionary"
    LOGICAL_DATA_DICTIONARY = "Logical Data Dictionary"
    HIERARCHIES = "Hierarchies"
    POLICIES = "Policies"
    REFERENCE_DATA = "Reference Data"


class CollibraRelationType(Enum):
    """Collibra relation types (bidirectional)."""
    # Hierarchical relations
    GROUPS = "groups"  # head groups tail
    GROUPED_BY = "grouped by"  # inverse

    # Semantic relations
    MEANS = "means"
    RELATED_TO = "related to"

    # Data lineage
    SOURCES_FROM = "sources from"
    TARGETS_TO = "targets to"

    # Governance
    GOVERNS = "governs"
    GOVERNED_BY = "governed by"


class CollibraStatus(Enum):
    """Collibra asset status values."""
    CANDIDATE = "Candidate"
    UNDER_REVIEW = "Under Review"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    ARCHIVED = "Archived"


@dataclass
class CollibraAttribute:
    """Collibra attribute (key-value metadata on an asset)."""
    attribute_type: str  # e.g., "Definition", "Description", "Effective Start Date"
    value: Any
    attribute_id: Optional[str] = None


@dataclass
class CollibraRelation:
    """Collibra relation between two assets."""
    relation_id: Optional[str]
    relation_type: CollibraRelationType
    head_asset_id: str  # Source asset
    head_asset_name: str
    tail_asset_id: str  # Target asset
    tail_asset_name: str

    def reverse(self) -> 'CollibraRelation':
        """Get the inverse relation (bidirectional)."""
        # Map to inverse relation type
        inverse_map = {
            CollibraRelationType.GROUPS: CollibraRelationType.GROUPED_BY,
            CollibraRelationType.GROUPED_BY: CollibraRelationType.GROUPS,
            CollibraRelationType.GOVERNS: CollibraRelationType.GOVERNED_BY,
            CollibraRelationType.GOVERNED_BY: CollibraRelationType.GOVERNS,
        }

        inverse_type = inverse_map.get(self.relation_type, self.relation_type)

        return CollibraRelation(
            relation_id=self.relation_id,
            relation_type=inverse_type,
            head_asset_id=self.tail_asset_id,
            head_asset_name=self.tail_asset_name,
            tail_asset_id=self.head_asset_id,
            tail_asset_name=self.head_asset_name
        )


@dataclass
class CollibraAsset:
    """Collibra Asset representation."""
    # Required Collibra fields
    entity_id: str
    asset_id: str
    asset_type: CollibraAssetType
    display_name: str
    community: str
    domain: str
    domain_type: CollibraDomainType
    status: CollibraStatus
    source_type: str
    source_id: str

    # Metadata and attributes
    metadata: Dict[str, Any] = field(default_factory=dict)
    attributes: List[CollibraAttribute] = field(default_factory=list)
    relations: List[CollibraRelation] = field(default_factory=list)

    # Standard attributes (common across assets)
    definition: Optional[str] = None
    description: Optional[str] = None
    note: Optional[str] = None
    effective_start_date: Optional[str] = None
    effective_end_date: Optional[str] = None

    # Entity type (for compatibility)
    entity_type: str = ""

    def __post_init__(self):
        """Ensure entity_type is set correctly."""
        if not self.entity_type:
            object.__setattr__(self, 'entity_type', self.asset_type.value)

    def add_attribute(self, attribute_type: str, value: Any) -> None:
        """Add an attribute to this asset."""
        self.attributes.append(CollibraAttribute(
            attribute_type=attribute_type,
            value=value
        ))

    def add_relation(self, relation: CollibraRelation) -> None:
        """Add a relation to this asset."""
        self.relations.append(relation)

    def get_attribute(self, attribute_type: str) -> Optional[Any]:
        """Get attribute value by type."""
        for attr in self.attributes:
            if attr.attribute_type == attribute_type:
                return attr.value
        return None


class CollibraLens(Lens):
    """Lens for transforming entities into Collibra metamodel representations."""

    @property
    def name(self) -> str:
        return "collibra"

    @property
    def description(self) -> str:
        return "Maps entities to Collibra Data Intelligence Cloud metamodel (Assets, Domains, Relations)"

    def supports_source_type(self, source_type: str) -> bool:
        """Check if source type is supported."""
        supported = [
            "logseq_page",
            "logseq_todo",
            "csv_data_category",
            "rdf_concept",
            "rdf_ai_system"
        ]
        return source_type in supported

    def transform(self, source: Any) -> CollibraAsset:
        """Transform source entity to Collibra Asset.

        Args:
            source: Source entity (dict, PageMetadata, Todo, etc.)

        Returns:
            CollibraAsset
        """
        source_type = self._detect_source_type(source)

        if source_type == "csv_data_category":
            return self._transform_data_category(source)
        elif source_type == "rdf_ai_system":
            return self._transform_ai_concept(source)
        elif source_type == "logseq_page":
            return self._transform_logseq_page(source)
        elif source_type == "logseq_todo":
            return self._transform_logseq_todo(source)
        else:
            raise ValueError(f"Unsupported source type: {source_type}")

    def _detect_source_type(self, source: Any) -> str:
        """Detect the type of source entity."""
        if isinstance(source, dict):
            if "Asset Type" in source and source.get("Asset Type") == "Data Category":
                return "csv_data_category"
            elif "skos:prefLabel" in str(source) or "AI" in str(source.get("prefLabel", "")):
                return "rdf_ai_system"

        # Check for Logseq types
        if hasattr(source, 'page_name'):
            return "logseq_page"
        elif hasattr(source, 'status') and hasattr(source, 'content'):
            return "logseq_todo"

        return "unknown"

    def _transform_data_category(self, csv_row: Dict[str, str]) -> CollibraAsset:
        """Transform CSV Data Category row to Collibra Asset.

        Args:
            csv_row: Dictionary from CSV with Collibra export fields

        Returns:
            CollibraAsset representing the Data Category
        """
        asset = CollibraAsset(
            entity_id=csv_row.get("Asset Id", ""),
            asset_id=csv_row.get("Asset Id", ""),
            asset_type=CollibraAssetType.DATA_CATEGORY,
            display_name=csv_row.get("Full Name", csv_row.get("Name", "")),
            community=csv_row.get("Community", ""),
            domain=csv_row.get("Domain", ""),
            domain_type=self._parse_domain_type(csv_row.get("Domain Type", "")),
            status=self._parse_status(csv_row.get("Status", "")),
            source_type="csv_data_category",
            source_id=csv_row.get("Asset Id", ""),
            metadata=csv_row,

            # Standard attributes
            definition=csv_row.get("Definition"),
            description=csv_row.get("Description"),
            note=csv_row.get("Note"),
            effective_start_date=csv_row.get("Effective Start Date"),
            effective_end_date=csv_row.get("Effective End Date")
        )

        # Add hierarchical relation if grouped by another asset
        parent_asset_id = csv_row.get("[Business Asset] grouped by [Business Asset] > Asset Id")
        parent_asset_name = csv_row.get("[Business Asset] grouped by [Business Asset] > Name")

        if parent_asset_id and parent_asset_name:
            relation = CollibraRelation(
                relation_id=None,
                relation_type=CollibraRelationType.GROUPED_BY,
                head_asset_id=asset.asset_id,
                head_asset_name=asset.display_name,
                tail_asset_id=parent_asset_id,
                tail_asset_name=parent_asset_name
            )
            asset.add_relation(relation)

        # Add custom attributes
        if csv_row.get("Descriptive Example"):
            asset.add_attribute("Descriptive Example", csv_row["Descriptive Example"])

        if csv_row.get("Sequence Number"):
            asset.add_attribute("Sequence Number", csv_row["Sequence Number"])

        return asset

    def _transform_ai_concept(self, rdf_concept: Dict[str, Any]) -> CollibraAsset:
        """Transform RDF AI System concept to Collibra Business Asset.

        Maps AI-human relationship concepts to Collibra Business Assets
        representing business capabilities or processes.

        Args:
            rdf_concept: Parsed RDF/SKOS concept

        Returns:
            CollibraAsset representing the AI concept
        """
        concept_uri = rdf_concept.get("uri", "")
        pref_label = rdf_concept.get("prefLabel", "")
        alt_label = rdf_concept.get("altLabel", "")

        asset = CollibraAsset(
            entity_id=concept_uri,
            asset_id=concept_uri,
            asset_type=CollibraAssetType.BUSINESS_CAPABILITY,
            display_name=pref_label,
            community="AI Systems",
            domain="AI-Human Relationships",
            domain_type=CollibraDomainType.GLOSSARY,
            status=CollibraStatus.APPROVED,
            source_type="rdf_ai_system",
            source_id=concept_uri,
            metadata=rdf_concept,

            definition=rdf_concept.get("description", ""),
            description=rdf_concept.get("note", "")
        )

        # Add alternate label as attribute
        if alt_label:
            asset.add_attribute("Alternate Label", alt_label)

        # Add risk profile attributes
        risk_profile = rdf_concept.get("riskProfile", {})
        if risk_profile:
            asset.add_attribute("Risk Likelihood", risk_profile.get("likelihood"))
            asset.add_attribute("Risk Impact", risk_profile.get("impact"))

        # Add roles as attributes
        if rdf_concept.get("humanRole"):
            asset.add_attribute("Human Role", rdf_concept["humanRole"])
        if rdf_concept.get("aiRole"):
            asset.add_attribute("AI Role", rdf_concept["aiRole"])

        # Add hierarchical relation if broader concept exists
        broader_uri = rdf_concept.get("broader")
        if broader_uri:
            relation = CollibraRelation(
                relation_id=None,
                relation_type=CollibraRelationType.GROUPED_BY,
                head_asset_id=asset.asset_id,
                head_asset_name=asset.display_name,
                tail_asset_id=broader_uri,
                tail_asset_name="AI Systems"  # Parent concept
            )
            asset.add_relation(relation)

        return asset

    def _transform_logseq_page(self, page_metadata) -> CollibraAsset:
        """Transform Logseq PageMetadata to Collibra Business Asset.

        Args:
            page_metadata: PageMetadata object

        Returns:
            CollibraAsset
        """
        # Infer asset type from page properties or namespace
        asset_type = self._infer_asset_type_from_page(page_metadata)

        asset = CollibraAsset(
            entity_id=page_metadata.page_name,
            asset_id=page_metadata.page_name,
            asset_type=asset_type,
            display_name=page_metadata.page_title or page_metadata.page_name,
            community="Logseq Knowledge Base",
            domain=page_metadata.namespace or "General",
            domain_type=CollibraDomainType.GLOSSARY,
            status=CollibraStatus.APPROVED,
            source_type="logseq_page",
            source_id=page_metadata.page_name,
            metadata={
                "file_path": str(page_metadata.file_path),
                "tags": page_metadata.tags,
                "properties": page_metadata.properties
            },

            description=page_metadata.content[:500] if page_metadata.content else None
        )

        # Add properties as attributes
        for key, value in page_metadata.properties.items():
            asset.add_attribute(key, value)

        # Add parent page relations
        for parent in page_metadata.parent_pages:
            relation = CollibraRelation(
                relation_id=None,
                relation_type=CollibraRelationType.GROUPED_BY,
                head_asset_id=asset.asset_id,
                head_asset_name=asset.display_name,
                tail_asset_id=parent,
                tail_asset_name=parent
            )
            asset.add_relation(relation)

        # Add outbound link relations
        for link in page_metadata.outbound_links:
            relation = CollibraRelation(
                relation_id=None,
                relation_type=CollibraRelationType.RELATED_TO,
                head_asset_id=asset.asset_id,
                head_asset_name=asset.display_name,
                tail_asset_id=link,
                tail_asset_name=link
            )
            asset.add_relation(relation)

        return asset

    def _transform_logseq_todo(self, todo) -> CollibraAsset:
        """Transform Logseq Todo to Collibra Issue/Governance Asset.

        Args:
            todo: Todo object

        Returns:
            CollibraAsset
        """
        asset = CollibraAsset(
            entity_id=f"{todo.file_path.name}:{todo.line_number}",
            asset_id=f"{todo.file_path.name}:{todo.line_number}",
            asset_type=CollibraAssetType.ISSUE,
            display_name=todo.content[:100],
            community="Logseq Tasks",
            domain=todo.file_path.parent.name,
            domain_type=CollibraDomainType.GLOSSARY,
            status=self._map_todo_status_to_collibra(todo.status.value),
            source_type="logseq_todo",
            source_id=f"{todo.file_path}:{todo.line_number}",
            metadata={
                "file_path": str(todo.file_path),
                "line_number": todo.line_number,
                "priority": todo.priority,
                "todo_status": todo.status.value
            },

            description=todo.content
        )

        # Add priority as attribute
        if todo.priority:
            asset.add_attribute("Priority", todo.priority)

        # Add dates as attributes
        if todo.created_date:
            asset.add_attribute("Created Date", str(todo.created_date))
        if todo.last_updated:
            asset.add_attribute("Last Updated", str(todo.last_updated))

        return asset

    def _parse_domain_type(self, domain_type_str: str) -> CollibraDomainType:
        """Parse domain type string to enum."""
        try:
            return CollibraDomainType(domain_type_str)
        except ValueError:
            return CollibraDomainType.GLOSSARY  # Default

    def _parse_status(self, status_str: str) -> CollibraStatus:
        """Parse status string to enum."""
        try:
            return CollibraStatus(status_str)
        except ValueError:
            return CollibraStatus.CANDIDATE  # Default

    def _infer_asset_type_from_page(self, page_metadata) -> CollibraAssetType:
        """Infer Collibra asset type from Logseq page metadata."""
        # Check properties for type hints
        page_type = page_metadata.properties.get("type", "").lower()

        if "process" in page_type:
            return CollibraAssetType.BUSINESS_PROCESS
        elif "capability" in page_type or "sell" in page_metadata.page_name.lower():
            return CollibraAssetType.BUSINESS_CAPABILITY
        elif "data" in page_type:
            return CollibraAssetType.DATA_ELEMENT
        elif "policy" in page_type:
            return CollibraAssetType.POLICY
        else:
            return CollibraAssetType.BUSINESS_TERM  # Default

    def _map_todo_status_to_collibra(self, todo_status: str) -> CollibraStatus:
        """Map Logseq TODO status to Collibra status."""
        mapping = {
            "TODO": CollibraStatus.CANDIDATE,
            "DOING": CollibraStatus.UNDER_REVIEW,
            "NOW": CollibraStatus.UNDER_REVIEW,
            "DONE": CollibraStatus.APPROVED,
            "CANCELED": CollibraStatus.REJECTED,
            "LATER": CollibraStatus.CANDIDATE,
            "WAITING": CollibraStatus.UNDER_REVIEW
        }
        return mapping.get(todo_status, CollibraStatus.CANDIDATE)
