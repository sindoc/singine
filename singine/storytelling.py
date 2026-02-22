"""Storytelling Framework - Minimum Requirements for Telling a Story.

A story requires:
1. Operating Model (the grammar/structure)
2. Data Categories (containing insights about the world)
3. Context-specific Lens (making sense for the situation)
4. People (who's involved, with what roles)
5. Location (where this is happening - physical, organizational, conceptual)

This module provides the abstraction for composing coherent narratives
from knowledge graph entities.
"""

from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import pendulum
from pendulum import DateTime

from .operating_model import CollibraOperatingModel, get_operating_model
from .lens.collibra import CollibraAsset, CollibraLens
from .lens.activity import Activity, Agent, AgentType, AgentRole
from .knowledge_graph import KnowledgeGraph, KnowledgeGraphEntity


class LocationType(Enum):
    """Types of locations where stories happen."""
    # Physical locations
    OFFICE = "Office"
    DATA_CENTER = "Data Center"
    REGION = "Region"
    COUNTRY = "Country"

    # Organizational locations
    DEPARTMENT = "Department"
    TEAM = "Team"
    BUSINESS_UNIT = "Business Unit"
    COMMUNITY = "Community"

    # Conceptual locations
    DOMAIN = "Domain"
    SYSTEM = "System"
    PLATFORM = "Platform"
    ECOSYSTEM = "Ecosystem"


@dataclass
class Location:
    """A location where part of the story takes place."""
    location_id: str
    location_type: LocationType
    name: str
    parent_location_id: Optional[str] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.name} ({self.location_type.value})"


@dataclass
class Person:
    """A person involved in the story."""
    person_id: str
    name: str
    roles: List[AgentRole] = field(default_factory=list)

    # Context
    location: Optional[Location] = None
    organization: Optional[str] = None
    department: Optional[str] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_agent(self) -> Agent:
        """Convert to Activity Agent."""
        return Agent(
            agent_id=self.person_id,
            agent_type=AgentType.HUMAN_PERSON,
            display_name=self.name,
            roles=self.roles,
            metadata=self.metadata
        )

    def __str__(self) -> str:
        roles_str = ", ".join([r.value for r in self.roles]) if self.roles else "No specific role"
        return f"{self.name} ({roles_str})"


@dataclass
class Context:
    """The context in which a story takes place.

    Context defines the lens through which we view the data.
    """
    context_id: str
    name: str
    description: Optional[str] = None

    # Lens configuration
    lens_name: str = "collibra"  # Which lens to use
    lens_config: Dict[str, Any] = field(default_factory=dict)

    # Scope filters
    asset_types_in_scope: Set[str] = field(default_factory=set)
    domains_in_scope: Set[str] = field(default_factory=set)
    communities_in_scope: Set[str] = field(default_factory=set)

    # Temporal scope
    time_range_start: Optional[DateTime] = None
    time_range_end: Optional[DateTime] = None

    def is_in_scope(self, asset: CollibraAsset) -> bool:
        """Check if an asset is in scope for this context."""
        # Check asset type
        if self.asset_types_in_scope and asset.asset_type.value not in self.asset_types_in_scope:
            return False

        # Check domain
        if self.domains_in_scope and asset.domain not in self.domains_in_scope:
            return False

        # Check community
        if self.communities_in_scope and asset.community not in self.communities_in_scope:
            return False

        return True

    def __str__(self) -> str:
        return f"Context: {self.name} (lens: {self.lens_name})"


@dataclass
class StoryElement:
    """A single element (beat) in a story."""
    element_id: str

    # Core entity
    entity: KnowledgeGraphEntity

    # Story context
    timestamp: Optional[DateTime] = None
    people: List[Person] = field(default_factory=list)
    location: Optional[Location] = None

    # Narrative
    narrative: Optional[str] = None  # Human-readable description
    significance: Optional[str] = None  # Why this matters

    def __str__(self) -> str:
        parts = []

        if self.timestamp:
            parts.append(f"[{self.timestamp.to_date_string()}]")

        parts.append(self.entity.display_name)

        if self.people:
            people_names = ", ".join([p.name for p in self.people])
            parts.append(f"(involving {people_names})")

        if self.location:
            parts.append(f"at {self.location.name}")

        return " ".join(parts)


@dataclass
class Story:
    """A complete story composed of multiple elements.

    A story is a coherent narrative that:
    - Uses a specific lens (Collibra metamodel)
    - Involves specific people in specific roles
    - Happens in specific locations
    - Spans a particular context (time, scope, purpose)
    """
    story_id: str
    title: str
    description: Optional[str] = None

    # Story components (minimum requirements)
    operating_model: CollibraOperatingModel = field(default_factory=get_operating_model)
    context: Optional[Context] = None
    people: List[Person] = field(default_factory=list)
    locations: List[Location] = field(default_factory=list)

    # Story elements (the beats)
    elements: List[StoryElement] = field(default_factory=list)

    # Metadata
    created_at: DateTime = field(default_factory=pendulum.now)
    author: Optional[str] = None

    def add_element(self, element: StoryElement) -> None:
        """Add an element to the story."""
        # Validate element is in context scope
        if self.context and element.entity.collibra_asset:
            if not self.context.is_in_scope(element.entity.collibra_asset):
                raise ValueError(f"Element {element.element_id} is out of context scope")

        self.elements.append(element)

    def get_timeline(self) -> List[StoryElement]:
        """Get story elements in chronological order."""
        timestamped = [e for e in self.elements if e.timestamp]
        return sorted(timestamped, key=lambda e: e.timestamp)

    def get_people_involved(self) -> Set[Person]:
        """Get all unique people involved in the story."""
        people = set()
        for element in self.elements:
            people.update(element.people)
        people.update(self.people)  # Include story-level people
        return people

    def get_locations_involved(self) -> Set[Location]:
        """Get all unique locations involved in the story."""
        locations = set()
        for element in self.elements:
            if element.location:
                locations.add(element.location)
        locations.update(self.locations)  # Include story-level locations
        return locations

    def get_entities_by_type(self, entity_type: str) -> List[KnowledgeGraphEntity]:
        """Get all entities of a specific type in the story."""
        return [
            e.entity for e in self.elements
            if e.entity.entity_type == entity_type
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Export story to dictionary format."""
        return {
            "story_id": self.story_id,
            "title": self.title,
            "description": self.description,
            "context": str(self.context) if self.context else None,
            "people": [str(p) for p in self.get_people_involved()],
            "locations": [str(l) for l in self.get_locations_involved()],
            "elements": [
                {
                    "timestamp": str(e.timestamp) if e.timestamp else None,
                    "entity": e.entity.display_name,
                    "entity_type": e.entity.entity_type,
                    "people": [p.name for p in e.people],
                    "location": str(e.location) if e.location else None,
                    "narrative": e.narrative
                }
                for e in self.elements
            ],
            "created_at": str(self.created_at),
            "author": self.author
        }

    def render_markdown(self) -> str:
        """Render story as markdown."""
        lines = []

        lines.append(f"# {self.title}")
        lines.append("")

        if self.description:
            lines.append(self.description)
            lines.append("")

        # Context
        if self.context:
            lines.append(f"**Context:** {self.context.name}")
            lines.append("")

        # People
        people = self.get_people_involved()
        if people:
            lines.append("**People Involved:**")
            for person in people:
                lines.append(f"- {person}")
            lines.append("")

        # Locations
        locations = self.get_locations_involved()
        if locations:
            lines.append("**Locations:**")
            for location in locations:
                lines.append(f"- {location}")
            lines.append("")

        # Timeline
        lines.append("## Timeline")
        lines.append("")

        timeline = self.get_timeline()
        for element in timeline:
            lines.append(f"### {element.timestamp.to_date_string() if element.timestamp else 'Unknown Date'}")
            lines.append("")
            lines.append(f"**{element.entity.display_name}**")
            lines.append("")

            if element.narrative:
                lines.append(element.narrative)
                lines.append("")

            if element.people:
                people_str = ", ".join([p.name for p in element.people])
                lines.append(f"*Involving: {people_str}*")
                lines.append("")

            if element.location:
                lines.append(f"*Location: {element.location}*")
                lines.append("")

            if element.significance:
                lines.append(f"> {element.significance}")
                lines.append("")

        return "\n".join(lines)

    def __str__(self) -> str:
        people_count = len(self.get_people_involved())
        locations_count = len(self.get_locations_involved())
        return (f"Story: {self.title} "
                f"({len(self.elements)} elements, "
                f"{people_count} people, "
                f"{locations_count} locations)")


class StoryBuilder:
    """Builder for constructing stories from knowledge graph entities."""

    def __init__(self, knowledge_graph: KnowledgeGraph,
                 operating_model: Optional[CollibraOperatingModel] = None):
        """Initialize story builder.

        Args:
            knowledge_graph: Knowledge graph to source entities from
            operating_model: Operating model (defaults to global instance)
        """
        self.kg = knowledge_graph
        self.operating_model = operating_model or get_operating_model()

    def create_story(self, story_id: str, title: str,
                    context: Optional[Context] = None) -> Story:
        """Create a new story.

        Args:
            story_id: Unique identifier
            title: Story title
            context: Optional context defining scope and lens

        Returns:
            New Story instance
        """
        return Story(
            story_id=story_id,
            title=title,
            context=context,
            operating_model=self.operating_model
        )

    def add_entity_as_element(self, story: Story, entity_id: str,
                            people: Optional[List[Person]] = None,
                            location: Optional[Location] = None,
                            narrative: Optional[str] = None) -> StoryElement:
        """Add a knowledge graph entity to the story.

        Args:
            story: Story to add to
            entity_id: Entity ID from knowledge graph
            people: People involved
            location: Location
            narrative: Human-readable narrative

        Returns:
            Created StoryElement
        """
        entity = self.kg.entities.get(entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")

        # Extract timestamp from entity
        timestamp = None
        if entity.collibra_asset:
            if entity.collibra_asset.metadata.get("modified_date"):
                timestamp = entity.collibra_asset.metadata["modified_date"]
        elif entity.activity:
            timestamp = entity.activity.start_time

        element = StoryElement(
            element_id=f"{story.story_id}:element:{len(story.elements)}",
            entity=entity,
            timestamp=timestamp,
            people=people or [],
            location=location,
            narrative=narrative
        )

        story.add_element(element)
        return element

    def build_data_category_story(self, root_category_name: str,
                                  title: Optional[str] = None) -> Story:
        """Build a story around a Data Category hierarchy.

        Args:
            root_category_name: Name of root Data Category
            title: Story title (defaults to category name)

        Returns:
            Story showing the hierarchy and relationships
        """
        root_entity = self.kg.query_by_name(root_category_name)
        if not root_entity:
            raise ValueError(f"Data Category not found: {root_category_name}")

        story = self.create_story(
            story_id=f"story:data_category:{root_category_name.lower().replace(' ', '_')}",
            title=title or f"The {root_category_name} Story",
            context=Context(
                context_id="ctx:data_categories",
                name="Data Category Taxonomy",
                lens_name="collibra",
                asset_types_in_scope={"Data Category"}
            )
        )

        # Add root
        self.add_entity_as_element(
            story,
            root_entity.entity_id,
            narrative=f"{root_category_name} is the root of this taxonomy."
        )

        # Add hierarchy
        tree = self.kg.query_hierarchy(root_entity.entity_id)
        self._add_hierarchy_to_story(story, tree, level=1)

        return story

    def _add_hierarchy_to_story(self, story: Story, tree: Dict[str, Any],
                               level: int = 0) -> None:
        """Recursively add hierarchy tree to story."""
        for child_tree in tree.get('children', []):
            child_entity = child_tree['entity']

            indent = "  " * level
            self.add_entity_as_element(
                story,
                child_entity.entity_id,
                narrative=f"{indent}→ {child_entity.display_name} is a sub-category."
            )

            # Recurse
            self._add_hierarchy_to_story(story, child_tree, level + 1)


def create_context(name: str, lens_name: str = "collibra",
                   asset_types: Optional[List[str]] = None,
                   domains: Optional[List[str]] = None,
                   communities: Optional[List[str]] = None) -> Context:
    """Convenience function to create a Context.

    Args:
        name: Context name
        lens_name: Lens to use (default: "collibra")
        asset_types: Asset types in scope
        domains: Domains in scope
        communities: Communities in scope

    Returns:
        Context instance
    """
    return Context(
        context_id=f"ctx:{name.lower().replace(' ', '_')}",
        name=name,
        lens_name=lens_name,
        asset_types_in_scope=set(asset_types or []),
        domains_in_scope=set(domains or []),
        communities_in_scope=set(communities or [])
    )


def create_person(name: str, roles: Optional[List[AgentRole]] = None,
                 location: Optional[Location] = None,
                 organization: Optional[str] = None) -> Person:
    """Convenience function to create a Person.

    Args:
        name: Person's name
        roles: Agent roles
        location: Location
        organization: Organization name

    Returns:
        Person instance
    """
    return Person(
        person_id=f"person:{name.lower().replace(' ', '_')}",
        name=name,
        roles=roles or [],
        location=location,
        organization=organization
    )


def create_location(name: str, location_type: LocationType,
                   parent: Optional[Location] = None) -> Location:
    """Convenience function to create a Location.

    Args:
        name: Location name
        location_type: Type of location
        parent: Parent location

    Returns:
        Location instance
    """
    return Location(
        location_id=f"loc:{name.lower().replace(' ', '_')}",
        name=name,
        location_type=location_type,
        parent_location_id=parent.location_id if parent else None
    )
