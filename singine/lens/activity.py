"""Activity lens for tracking human-led and machine-led activities.

This lens uses the PROV-O (Provenance Ontology) to model activities,
agents (human/machine), and their relationships to entities.

PROV-O Core Concepts:
- Entity: A physical, digital, conceptual, or other kind of thing
- Activity: Something that occurs over a period of time and acts upon entities
- Agent: Something that bears responsibility for an activity (Person, Software, Organization)

Extended for Collibra integration:
- Activities can be linked to Collibra Assets
- Agents can be human (Data Steward, Business Owner) or machine (AI System, ETL Process)
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import pendulum
from pendulum import DateTime

from .base import Lens, LensEntity
from .collibra import CollibraAsset, CollibraAssetType


class ActivityType(Enum):
    """Types of activities in the context of data governance and AI."""
    # Data Governance Activities
    DATA_CLASSIFICATION = "Data Classification"
    DATA_QUALITY_CHECK = "Data Quality Check"
    DATA_STEWARDSHIP = "Data Stewardship"
    METADATA_CURATION = "Metadata Curation"

    # AI/ML Activities
    MODEL_TRAINING = "Model Training"
    MODEL_INFERENCE = "Model Inference"
    DATA_LABELING = "Data Labeling"
    FEATURE_ENGINEERING = "Feature Engineering"

    # Knowledge Management Activities
    KNOWLEDGE_CAPTURE = "Knowledge Capture"
    DOCUMENT_REVIEW = "Document Review"
    TASK_EXECUTION = "Task Execution"

    # Business Activities
    DECISION_MAKING = "Decision Making"
    PROCESS_EXECUTION = "Process Execution"
    APPROVAL = "Approval"


class AgentType(Enum):
    """Types of agents that can perform activities."""
    # Human Agents
    HUMAN_PERSON = "Person"
    HUMAN_TEAM = "Team"
    HUMAN_ORGANIZATION = "Organization"

    # Machine Agents
    AI_SYSTEM = "AI System"
    SOFTWARE_APPLICATION = "Software Application"
    AUTOMATED_PROCESS = "Automated Process"
    ML_MODEL = "ML Model"

    # Hybrid
    HUMAN_AI_COLLABORATION = "Human-AI Collaboration"


class AgentRole(Enum):
    """Roles that agents can play in activities."""
    # Human Roles
    DATA_STEWARD = "Data Steward"
    BUSINESS_OWNER = "Business Owner"
    DATA_ANALYST = "Data Analyst"
    KNOWLEDGE_WORKER = "Knowledge Worker"

    # Machine Roles
    AI_ASSISTANT = "AI Assistant"
    AI_MANAGER = "AI Manager"
    AUTONOMOUS_AGENT = "Autonomous Agent"
    DATA_PROCESSOR = "Data Processor"


@dataclass
class Agent:
    """Represents an agent (human or machine) that performs activities."""
    agent_id: str
    agent_type: AgentType
    display_name: str
    roles: List[AgentRole] = field(default_factory=list)

    # Agent metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    # For machine agents: link to AI system concept
    ai_system_category: Optional[str] = None  # e.g., "AI as a Tool", "AI as an Assistant"

    def is_human(self) -> bool:
        """Check if agent is human."""
        return self.agent_type in [
            AgentType.HUMAN_PERSON,
            AgentType.HUMAN_TEAM,
            AgentType.HUMAN_ORGANIZATION
        ]

    def is_machine(self) -> bool:
        """Check if agent is machine."""
        return self.agent_type in [
            AgentType.AI_SYSTEM,
            AgentType.SOFTWARE_APPLICATION,
            AgentType.AUTOMATED_PROCESS,
            AgentType.ML_MODEL
        ]

    def is_hybrid(self) -> bool:
        """Check if agent represents human-AI collaboration."""
        return self.agent_type == AgentType.HUMAN_AI_COLLABORATION


@dataclass
class Activity(LensEntity):
    """Represents an activity performed by agents on entities.

    Following PROV-O model with Collibra extensions.
    """
    activity_id: str
    activity_type: ActivityType

    # Temporal attributes
    start_time: Optional[DateTime] = None
    end_time: Optional[DateTime] = None

    # Agents
    agents: List[Agent] = field(default_factory=list)

    # Entities involved
    used_entities: List[str] = field(default_factory=list)  # Input entities
    generated_entities: List[str] = field(default_factory=list)  # Output entities

    # Collibra integration
    related_assets: List[CollibraAsset] = field(default_factory=list)

    # Activity attributes
    description: Optional[str] = None
    status: Optional[str] = None  # "in_progress", "completed", "failed"

    def add_agent(self, agent: Agent) -> None:
        """Add an agent to this activity."""
        self.agents.append(agent)

    def add_used_entity(self, entity_id: str) -> None:
        """Add an entity that was used (input) by this activity."""
        self.used_entities.append(entity_id)

    def add_generated_entity(self, entity_id: str) -> None:
        """Add an entity that was generated (output) by this activity."""
        self.generated_entities.append(entity_id)

    def get_human_agents(self) -> List[Agent]:
        """Get all human agents involved."""
        return [a for a in self.agents if a.is_human()]

    def get_machine_agents(self) -> List[Agent]:
        """Get all machine agents involved."""
        return [a for a in self.agents if a.is_machine()]

    def is_human_led(self) -> bool:
        """Check if activity is primarily human-led."""
        human_count = len(self.get_human_agents())
        machine_count = len(self.get_machine_agents())
        return human_count > 0 and human_count >= machine_count

    def is_machine_led(self) -> bool:
        """Check if activity is primarily machine-led."""
        machine_count = len(self.get_machine_agents())
        human_count = len(self.get_human_agents())
        return machine_count > 0 and machine_count > human_count

    def is_collaborative(self) -> bool:
        """Check if activity involves both human and machine agents."""
        return len(self.get_human_agents()) > 0 and len(self.get_machine_agents()) > 0


class ActivityLens(Lens):
    """Lens for viewing entities as activities with agent provenance."""

    @property
    def name(self) -> str:
        return "activity"

    @property
    def description(self) -> str:
        return "Maps entities to PROV-O activities with human/machine agent tracking"

    def supports_source_type(self, source_type: str) -> bool:
        """Check if source type is supported."""
        supported = [
            "logseq_todo",
            "logseq_clock_entry",
            "collibra_asset",
            "rdf_ai_system"
        ]
        return source_type in supported

    def transform(self, source: Any) -> Activity:
        """Transform source entity to Activity.

        Args:
            source: Source entity

        Returns:
            Activity object
        """
        source_type = self._detect_source_type(source)

        if source_type == "logseq_todo":
            return self._transform_logseq_todo(source)
        elif source_type == "collibra_asset":
            return self._transform_collibra_asset(source)
        else:
            raise ValueError(f"Unsupported source type: {source_type}")

    def _detect_source_type(self, source: Any) -> str:
        """Detect the type of source entity."""
        if hasattr(source, 'status') and hasattr(source, 'content'):
            return "logseq_todo"
        elif isinstance(source, CollibraAsset):
            return "collibra_asset"
        return "unknown"

    def _transform_logseq_todo(self, todo) -> Activity:
        """Transform Logseq Todo to Activity.

        A TODO represents a task (activity) that needs to be executed.

        Args:
            todo: Todo object

        Returns:
            Activity
        """
        # Infer activity type from content
        activity_type = self._infer_activity_type(todo.content)

        # Map status to activity status
        activity_status = self._map_todo_status_to_activity_status(todo.status.value)

        activity = Activity(
            entity_id=f"activity:{todo.file_path.name}:{todo.line_number}",
            activity_id=f"activity:{todo.file_path.name}:{todo.line_number}",
            activity_type=activity_type,
            entity_type="Activity",
            display_name=todo.content[:100],
            source_type="logseq_todo",
            source_id=f"{todo.file_path}:{todo.line_number}",
            metadata={
                "file_path": str(todo.file_path),
                "line_number": todo.line_number,
                "priority": todo.priority,
                "todo_status": todo.status.value
            },

            start_time=todo.created_date,
            end_time=todo.last_updated if todo.status.value == "DONE" else None,
            description=todo.content,
            status=activity_status
        )

        # Infer agent from context (default: human knowledge worker)
        # In reality, you'd extract this from Logseq properties or assignee
        human_agent = Agent(
            agent_id="user:default",
            agent_type=AgentType.HUMAN_PERSON,
            display_name="Knowledge Worker",
            roles=[AgentRole.KNOWLEDGE_WORKER]
        )
        activity.add_agent(human_agent)

        # Check if AI is involved (based on content)
        if self._involves_ai(todo.content):
            ai_agent = Agent(
                agent_id="ai:assistant",
                agent_type=AgentType.AI_SYSTEM,
                display_name="AI Assistant",
                roles=[AgentRole.AI_ASSISTANT],
                ai_system_category="AI as an Assistant"
            )
            activity.add_agent(ai_agent)

        return activity

    def _transform_collibra_asset(self, asset: CollibraAsset) -> Activity:
        """Transform Collibra Asset to Activity.

        For certain asset types (e.g., Issue, Process), the asset represents
        an activity itself.

        Args:
            asset: CollibraAsset

        Returns:
            Activity
        """
        # Map asset type to activity type
        activity_type_map = {
            CollibraAssetType.ISSUE: ActivityType.TASK_EXECUTION,
            CollibraAssetType.BUSINESS_PROCESS: ActivityType.PROCESS_EXECUTION,
        }

        activity_type = activity_type_map.get(
            asset.asset_type,
            ActivityType.TASK_EXECUTION
        )

        activity = Activity(
            entity_id=f"activity:{asset.asset_id}",
            activity_id=f"activity:{asset.asset_id}",
            activity_type=activity_type,
            entity_type="Activity",
            display_name=asset.display_name,
            source_type="collibra_asset",
            source_id=asset.asset_id,
            metadata=asset.metadata,

            description=asset.description,
            status=asset.status.value.lower().replace(" ", "_")
        )

        # Parse dates from attributes
        start_date_str = asset.get_attribute("Effective Start Date")
        if start_date_str:
            activity.start_time = pendulum.parse(start_date_str)

        end_date_str = asset.get_attribute("Effective End Date")
        if end_date_str:
            activity.end_time = pendulum.parse(end_date_str)

        activity.related_assets.append(asset)

        return activity

    def _infer_activity_type(self, content: str) -> ActivityType:
        """Infer activity type from content."""
        content_lower = content.lower()

        if "review" in content_lower or "approve" in content_lower:
            return ActivityType.DOCUMENT_REVIEW
        elif "classify" in content_lower or "categorize" in content_lower:
            return ActivityType.DATA_CLASSIFICATION
        elif "train" in content_lower and "model" in content_lower:
            return ActivityType.MODEL_TRAINING
        elif "label" in content_lower or "annotate" in content_lower:
            return ActivityType.DATA_LABELING
        elif "decide" in content_lower or "decision" in content_lower:
            return ActivityType.DECISION_MAKING
        else:
            return ActivityType.TASK_EXECUTION

    def _map_todo_status_to_activity_status(self, todo_status: str) -> str:
        """Map Logseq TODO status to activity status."""
        mapping = {
            "TODO": "planned",
            "DOING": "in_progress",
            "NOW": "in_progress",
            "DONE": "completed",
            "CANCELED": "canceled",
            "LATER": "planned",
            "WAITING": "waiting"
        }
        return mapping.get(todo_status, "planned")

    def _involves_ai(self, content: str) -> bool:
        """Check if activity involves AI based on content."""
        ai_keywords = ["ai", "gpt", "claude", "llm", "model", "machine learning", "ml"]
        content_lower = content.lower()
        return any(keyword in content_lower for keyword in ai_keywords)
