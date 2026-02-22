"""Base lens abstraction for metamodel transformations."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Type, Optional
from dataclasses import dataclass


@dataclass
class LensEntity:
    """Base class for entities viewed through a lens."""
    entity_id: str
    entity_type: str
    display_name: str
    source_type: str  # "logseq_page", "logseq_todo", "csv_row", "rdf_concept"
    source_id: str
    metadata: Dict[str, Any]


class Lens(ABC):
    """Abstract base class for metamodel lenses.

    A lens transforms source entities (Logseq pages, todos, CSV rows, RDF concepts)
    into a target metamodel representation (e.g., Collibra, DCAT, Dublin Core).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Lens name (e.g., 'collibra', 'dcat')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of this lens."""
        pass

    @abstractmethod
    def transform(self, source: Any) -> LensEntity:
        """Transform a source entity into the lens's metamodel representation.

        Args:
            source: Source entity (PageMetadata, Todo, CSV row, RDF concept, etc.)

        Returns:
            LensEntity in the target metamodel
        """
        pass

    @abstractmethod
    def supports_source_type(self, source_type: str) -> bool:
        """Check if this lens supports transforming the given source type.

        Args:
            source_type: Type identifier (e.g., 'logseq_page', 'csv_data_category')

        Returns:
            True if lens can transform this source type
        """
        pass


class LensRegistry:
    """Registry for managing available lenses."""

    _lenses: Dict[str, Lens] = {}

    @classmethod
    def register(cls, lens: Lens) -> None:
        """Register a lens.

        Args:
            lens: Lens instance to register
        """
        cls._lenses[lens.name] = lens

    @classmethod
    def get(cls, name: str) -> Optional[Lens]:
        """Get a lens by name.

        Args:
            name: Lens name

        Returns:
            Lens instance or None if not found
        """
        return cls._lenses.get(name)

    @classmethod
    def list_all(cls) -> List[str]:
        """List all registered lens names."""
        return list(cls._lenses.keys())

    @classmethod
    def find_for_source(cls, source_type: str) -> List[Lens]:
        """Find all lenses that support a given source type.

        Args:
            source_type: Source type identifier

        Returns:
            List of compatible lenses
        """
        return [
            lens for lens in cls._lenses.values()
            if lens.supports_source_type(source_type)
        ]
