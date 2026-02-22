"""Collibra Operating Model abstraction layer.

The Operating Model is the foundational structure that defines:
- How resources (assets, domains, communities) are organized
- What types exist and their characteristics
- How they relate to each other

This is the FIRST thing that must be available - it's the grammar
of the data governance language.
"""

from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from enum import Enum


class ResourceType(Enum):
    """Core resource types in Collibra Operating Model."""
    COMMUNITY = "Community"
    DOMAIN = "Domain"
    ASSET = "Asset"
    ATTRIBUTE = "Attribute"
    RELATION = "Relation"


@dataclass
class TypeDefinition:
    """Definition of a type in the operating model.

    Types define the 'what' - what kinds of things can exist.
    """
    type_id: str
    type_name: str
    resource_type: ResourceType
    parent_type_id: Optional[str] = None  # For inheritance hierarchy
    description: Optional[str] = None

    # Constraints
    allowed_in_domain_types: Set[str] = field(default_factory=set)
    required_attributes: List[str] = field(default_factory=list)
    allowed_relations: List[str] = field(default_factory=list)

    def inherits_from(self, parent_id: str) -> bool:
        """Check if this type inherits from a parent type."""
        current = self.parent_type_id
        while current:
            if current == parent_id:
                return True
            # Would need registry to walk up hierarchy
            break
        return False


@dataclass
class Scope:
    """Scope configuration for efficient type assignment.

    Scopes assign types (domain types, attribute types, relation types)
    to specific asset types without creating custom types.
    """
    scope_id: str
    scope_name: str
    asset_type_id: str

    # Assigned types
    allowed_domain_types: Set[str] = field(default_factory=set)
    allowed_attribute_types: Set[str] = field(default_factory=set)
    allowed_relation_types: Set[str] = field(default_factory=set)


@dataclass
class OperatingModelConfig:
    """Complete operating model configuration.

    This is the 'grammar' of your data governance language.
    """
    # Type definitions
    community_types: Dict[str, TypeDefinition] = field(default_factory=dict)
    domain_types: Dict[str, TypeDefinition] = field(default_factory=dict)
    asset_types: Dict[str, TypeDefinition] = field(default_factory=dict)
    attribute_types: Dict[str, TypeDefinition] = field(default_factory=dict)
    relation_types: Dict[str, TypeDefinition] = field(default_factory=dict)

    # Scopes
    scopes: Dict[str, Scope] = field(default_factory=dict)

    # Status workflow
    status_workflow: Dict[str, List[str]] = field(default_factory=dict)

    def register_type(self, type_def: TypeDefinition) -> None:
        """Register a type definition."""
        registry = {
            ResourceType.COMMUNITY: self.community_types,
            ResourceType.DOMAIN: self.domain_types,
            ResourceType.ASSET: self.asset_types,
            ResourceType.ATTRIBUTE: self.attribute_types,
            ResourceType.RELATION: self.relation_types,
        }

        target_dict = registry.get(type_def.resource_type)
        if target_dict is not None:
            target_dict[type_def.type_id] = type_def

    def get_type(self, type_id: str) -> Optional[TypeDefinition]:
        """Get type definition by ID."""
        for type_dict in [
            self.community_types,
            self.domain_types,
            self.asset_types,
            self.attribute_types,
            self.relation_types
        ]:
            if type_id in type_dict:
                return type_dict[type_id]
        return None

    def validate_asset_type_in_domain(self, asset_type_id: str, domain_type_id: str) -> bool:
        """Check if an asset type can exist in a domain type."""
        asset_type = self.asset_types.get(asset_type_id)
        if not asset_type:
            return False

        # Check if domain type is allowed
        if domain_type_id in asset_type.allowed_in_domain_types:
            return True

        # If no restrictions, allow
        if not asset_type.allowed_in_domain_types:
            return True

        return False


class CollibraOperatingModel:
    """The Collibra Operating Model - the foundational abstraction.

    This is THE FIRST THING that must be available to everyone.

    The operating model defines:
    1. What types of things can exist (communities, domains, assets)
    2. What characteristics they can have (attributes)
    3. How they can relate to each other (relations)
    4. The rules and constraints (scopes, workflows)

    Without this, there is no shared language for data governance.
    """

    def __init__(self):
        """Initialize with standard Collibra operating model."""
        self.config = OperatingModelConfig()
        self._initialize_standard_model()

    def _initialize_standard_model(self) -> None:
        """Initialize with Collibra's standard out-of-the-box types."""

        # === ASSET TYPES ===

        # Top-level asset types (5 foundational types)
        self._register_asset_type(
            "00000000-0000-0000-0000-000000000001",
            "Business Asset",
            description="Assets representing business concepts"
        )

        self._register_asset_type(
            "00000000-0000-0000-0000-000000000002",
            "Data Asset",
            description="Assets representing data resources"
        )

        self._register_asset_type(
            "00000000-0000-0000-0000-000000000003",
            "Governance Asset",
            description="Assets representing governance artifacts"
        )

        self._register_asset_type(
            "00000000-0000-0000-0000-000000000004",
            "Technology Asset",
            description="Assets representing technology components"
        )

        self._register_asset_type(
            "00000000-0000-0000-0000-000000000005",
            "Issue",
            description="Assets representing issues or tasks"
        )

        # Business Asset specializations
        self._register_asset_type(
            "00000000-0000-0000-0001-000000000001",
            "Business Capability",
            parent_id="00000000-0000-0000-0000-000000000001",
            description="A particular ability or capacity that a business may possess",
            allowed_domains={"Glossary", "Hierarchies"}
        )

        self._register_asset_type(
            "00000000-0000-0000-0001-000000000002",
            "Business Process",
            parent_id="00000000-0000-0000-0000-000000000001",
            description="A collection of related, structured activities or tasks",
            allowed_domains={"Glossary"}
        )

        self._register_asset_type(
            "00000000-0000-0000-0001-000000000003",
            "Business Term",
            parent_id="00000000-0000-0000-0000-000000000001",
            description="A word or phrase used in business context",
            allowed_domains={"Glossary"}
        )

        self._register_asset_type(
            "00000000-0000-0000-0001-000000000004",
            "Data Category",
            parent_id="00000000-0000-0000-0000-000000000001",
            description="A classification or grouping of data",
            allowed_domains={"Hierarchies", "Glossary"}
        )

        # Data Asset specializations
        self._register_asset_type(
            "00000000-0000-0000-0002-000000000001",
            "Database",
            parent_id="00000000-0000-0000-0000-000000000002",
            description="A structured set of data",
            allowed_domains={"Physical Data Dictionary"}
        )

        self._register_asset_type(
            "00000000-0000-0000-0002-000000000002",
            "Schema",
            parent_id="00000000-0000-0000-0000-000000000002",
            description="The structure of a database",
            allowed_domains={"Physical Data Dictionary"}
        )

        self._register_asset_type(
            "00000000-0000-0000-0002-000000000003",
            "Table",
            parent_id="00000000-0000-0000-0000-000000000002",
            description="A collection of related data in a database",
            allowed_domains={"Physical Data Dictionary"}
        )

        self._register_asset_type(
            "00000000-0000-0000-0002-000000000004",
            "Column",
            parent_id="00000000-0000-0000-0000-000000000002",
            description="A set of data values of a particular type",
            allowed_domains={"Physical Data Dictionary"}
        )

        self._register_asset_type(
            "00000000-0000-0000-0002-000000000005",
            "Data Element",
            parent_id="00000000-0000-0000-0000-000000000002",
            description="An atomic unit of data",
            allowed_domains={"Logical Data Dictionary", "Glossary"}
        )

        # Governance Asset specializations
        self._register_asset_type(
            "00000000-0000-0000-0003-000000000001",
            "Policy",
            parent_id="00000000-0000-0000-0000-000000000003",
            description="A principle or protocol to guide decisions",
            allowed_domains={"Policies"}
        )

        self._register_asset_type(
            "00000000-0000-0000-0003-000000000002",
            "Rule",
            parent_id="00000000-0000-0000-0000-000000000003",
            description="A prescribed guide for conduct or action",
            allowed_domains={"Policies"}
        )

        self._register_asset_type(
            "00000000-0000-0000-0003-000000000003",
            "Standard",
            parent_id="00000000-0000-0000-0000-000000000003",
            description="An established norm or requirement",
            allowed_domains={"Policies"}
        )

        # === DOMAIN TYPES ===

        self._register_domain_type(
            "10000000-0000-0000-0000-000000000001",
            "Glossary",
            description="Domain for business glossary terms"
        )

        self._register_domain_type(
            "10000000-0000-0000-0000-000000000002",
            "Physical Data Dictionary",
            description="Domain for physical data structures"
        )

        self._register_domain_type(
            "10000000-0000-0000-0000-000000000003",
            "Logical Data Dictionary",
            description="Domain for logical data models"
        )

        self._register_domain_type(
            "10000000-0000-0000-0000-000000000004",
            "Hierarchies",
            description="Domain for hierarchical classifications"
        )

        self._register_domain_type(
            "10000000-0000-0000-0000-000000000005",
            "Policies",
            description="Domain for governance policies"
        )

        self._register_domain_type(
            "10000000-0000-0000-0000-000000000006",
            "Reference Data",
            description="Domain for reference data sets"
        )

        # === RELATION TYPES ===

        # Hierarchical relations
        self._register_relation_type(
            "20000000-0000-0000-0000-000000000001",
            "groups",
            inverse="grouped by",
            description="Head asset groups tail asset in a hierarchy"
        )

        # Semantic relations
        self._register_relation_type(
            "20000000-0000-0000-0000-000000000002",
            "means",
            inverse="is meant by",
            description="Business term means data element"
        )

        self._register_relation_type(
            "20000000-0000-0000-0000-000000000003",
            "related to",
            inverse="related to",  # Symmetric
            description="General association between assets"
        )

        # Data lineage relations
        self._register_relation_type(
            "20000000-0000-0000-0000-000000000004",
            "sources from",
            inverse="targets to",
            description="Data flow from source to target"
        )

        # Governance relations
        self._register_relation_type(
            "20000000-0000-0000-0000-000000000005",
            "governs",
            inverse="governed by",
            description="Policy governs asset"
        )

        # === ATTRIBUTE TYPES ===

        self._register_attribute_type(
            "30000000-0000-0000-0000-000000000001",
            "Definition",
            description="Formal definition of the asset"
        )

        self._register_attribute_type(
            "30000000-0000-0000-0000-000000000002",
            "Description",
            description="Descriptive text about the asset"
        )

        self._register_attribute_type(
            "30000000-0000-0000-0000-000000000003",
            "Note",
            description="Additional notes or comments"
        )

        self._register_attribute_type(
            "30000000-0000-0000-0000-000000000004",
            "Effective Start Date",
            description="Date when the asset becomes effective"
        )

        self._register_attribute_type(
            "30000000-0000-0000-0000-000000000005",
            "Effective End Date",
            description="Date when the asset is no longer effective"
        )

        # === STATUS WORKFLOW ===

        self.config.status_workflow = {
            "Candidate": ["Under Review", "Rejected"],
            "Under Review": ["Approved", "Rejected"],
            "Approved": ["Archived"],
            "Rejected": ["Candidate"],
            "Archived": []
        }

    def _register_asset_type(self, type_id: str, type_name: str,
                           parent_id: Optional[str] = None,
                           description: Optional[str] = None,
                           allowed_domains: Optional[Set[str]] = None) -> None:
        """Helper to register asset type."""
        type_def = TypeDefinition(
            type_id=type_id,
            type_name=type_name,
            resource_type=ResourceType.ASSET,
            parent_type_id=parent_id,
            description=description,
            allowed_in_domain_types=allowed_domains or set()
        )
        self.config.register_type(type_def)

    def _register_domain_type(self, type_id: str, type_name: str,
                            description: Optional[str] = None) -> None:
        """Helper to register domain type."""
        type_def = TypeDefinition(
            type_id=type_id,
            type_name=type_name,
            resource_type=ResourceType.DOMAIN,
            description=description
        )
        self.config.register_type(type_def)

    def _register_relation_type(self, type_id: str, type_name: str,
                               inverse: str,
                               description: Optional[str] = None) -> None:
        """Helper to register relation type."""
        type_def = TypeDefinition(
            type_id=type_id,
            type_name=type_name,
            resource_type=ResourceType.RELATION,
            description=description
        )
        # Store inverse name in description for now
        type_def.description = f"{description} (inverse: {inverse})"
        self.config.register_type(type_def)

    def _register_attribute_type(self, type_id: str, type_name: str,
                                description: Optional[str] = None) -> None:
        """Helper to register attribute type."""
        type_def = TypeDefinition(
            type_id=type_id,
            type_name=type_name,
            resource_type=ResourceType.ATTRIBUTE,
            description=description
        )
        self.config.register_type(type_def)

    def get_asset_types(self, parent_type: Optional[str] = None) -> List[TypeDefinition]:
        """Get all asset types, optionally filtered by parent."""
        types = list(self.config.asset_types.values())

        if parent_type:
            # Find parent ID
            parent_def = next(
                (t for t in types if t.type_name == parent_type),
                None
            )
            if parent_def:
                types = [t for t in types if t.parent_type_id == parent_def.type_id]

        return types

    def get_domain_types(self) -> List[TypeDefinition]:
        """Get all domain types."""
        return list(self.config.domain_types.values())

    def get_relation_types(self) -> List[TypeDefinition]:
        """Get all relation types."""
        return list(self.config.relation_types.values())

    def validate_status_transition(self, from_status: str, to_status: str) -> bool:
        """Check if status transition is allowed."""
        allowed_transitions = self.config.status_workflow.get(from_status, [])
        return to_status in allowed_transitions

    def export_to_dict(self) -> Dict[str, Any]:
        """Export operating model to dictionary format."""
        return {
            "asset_types": {
                tid: {
                    "name": t.type_name,
                    "parent": t.parent_type_id,
                    "description": t.description
                }
                for tid, t in self.config.asset_types.items()
            },
            "domain_types": {
                tid: {
                    "name": t.type_name,
                    "description": t.description
                }
                for tid, t in self.config.domain_types.items()
            },
            "relation_types": {
                tid: {
                    "name": t.type_name,
                    "description": t.description
                }
                for tid, t in self.config.relation_types.items()
            },
            "status_workflow": self.config.status_workflow
        }


# Global singleton instance
_operating_model_instance: Optional[CollibraOperatingModel] = None


def get_operating_model() -> CollibraOperatingModel:
    """Get the global operating model instance.

    This is THE FIRST THING that should be available to everyone.
    """
    global _operating_model_instance

    if _operating_model_instance is None:
        _operating_model_instance = CollibraOperatingModel()

    return _operating_model_instance
