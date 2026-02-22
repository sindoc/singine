"""Context enrichment for entities with location, sentiment, and tech environment.

Adds contextual dimensions to entities:
- Location (physical, organizational, conceptual)
- Sentiment (mood, tone, emotional context)
- Tech Environment (platforms, tools, standards)
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import re


class LocationDimension(Enum):
    """Types of location dimensions."""
    PHYSICAL = "Physical"           # Office, city, country
    ORGANIZATIONAL = "Organizational"  # Department, team, business unit
    CONCEPTUAL = "Conceptual"       # Domain, ecosystem, namespace


class SentimentType(Enum):
    """Sentiment/mood types."""
    POSITIVE = "Positive"
    NEGATIVE = "Negative"
    NEUTRAL = "Neutral"
    MIXED = "Mixed"
    URGENT = "Urgent"
    CRITICAL = "Critical"


@dataclass
class ContextDimensions:
    """Complete context dimensions for an entity."""

    # Location dimension
    locations: List[Dict[str, str]] = field(default_factory=list)

    # Sentiment dimension
    sentiment: Optional[SentimentType] = None
    sentiment_score: Optional[float] = None  # -1.0 to 1.0
    mood_indicators: List[str] = field(default_factory=list)

    # Tech environment dimension
    tech_platforms: List[str] = field(default_factory=list)
    tech_tools: List[str] = field(default_factory=list)
    tech_standards: List[str] = field(default_factory=list)
    tech_protocols: List[str] = field(default_factory=list)

    # Additional context
    temporal_context: Optional[str] = None  # "current", "historical", "future"
    business_context: Optional[str] = None  # "strategic", "operational", "tactical"


class ContextEnricher:
    """Enriches entities with contextual dimensions."""

    # Keywords for sentiment detection
    POSITIVE_KEYWORDS = {
        'success', 'achieve', 'improve', 'benefit', 'advantage', 'opportunity',
        'growth', 'innovation', 'efficient', 'effective', 'excellent', 'great'
    }

    NEGATIVE_KEYWORDS = {
        'problem', 'issue', 'failure', 'risk', 'threat', 'challenge', 'concern',
        'difficulty', 'error', 'bug', 'critical', 'urgent', 'blocker'
    }

    URGENT_KEYWORDS = {
        'urgent', 'critical', 'asap', 'emergency', 'immediate', 'now', 'priority'
    }

    # Tech environment patterns
    TECH_PLATFORM_PATTERNS = {
        'collibra': 'Collibra',
        'logseq': 'Logseq',
        'aws': 'AWS',
        'azure': 'Azure',
        'gcp': 'Google Cloud',
        'kubernetes': 'Kubernetes',
        'docker': 'Docker',
        'databricks': 'Databricks'
    }

    TECH_STANDARD_PATTERNS = {
        'iso': 'ISO Standards',
        'ieee': 'IEEE Standards',
        'w3c': 'W3C Standards',
        'rdf': 'RDF/Semantic Web',
        'skos': 'SKOS',
        'dcat': 'DCAT',
        'prov': 'PROV-O'
    }

    def enrich(self, entity_content: str, entity_metadata: Dict[str, Any]) -> ContextDimensions:
        """Enrich an entity with context dimensions.

        Args:
            entity_content: Text content of the entity
            entity_metadata: Metadata dictionary

        Returns:
            ContextDimensions with extracted context
        """
        context = ContextDimensions()

        # Extract location
        context.locations = self._extract_locations(entity_content, entity_metadata)

        # Extract sentiment
        sentiment_data = self._extract_sentiment(entity_content)
        context.sentiment = sentiment_data['type']
        context.sentiment_score = sentiment_data['score']
        context.mood_indicators = sentiment_data['indicators']

        # Extract tech environment
        tech_data = self._extract_tech_environment(entity_content, entity_metadata)
        context.tech_platforms = tech_data['platforms']
        context.tech_tools = tech_data['tools']
        context.tech_standards = tech_data['standards']
        context.tech_protocols = tech_data['protocols']

        # Infer temporal and business context
        context.temporal_context = self._infer_temporal_context(entity_content)
        context.business_context = self._infer_business_context(entity_content)

        return context

    def _extract_locations(self, content: str, metadata: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract location information."""
        locations = []
        content_lower = content.lower()

        # Physical locations (countries, cities)
        country_pattern = r'\b(netherlands|usa|uk|germany|france|amsterdam|london|new york)\b'
        for match in re.finditer(country_pattern, content_lower, re.IGNORECASE):
            locations.append({
                'type': LocationDimension.PHYSICAL.value,
                'name': match.group(0).title(),
                'dimension': 'geography'
            })

        # Organizational locations from metadata
        if 'domain' in metadata:
            locations.append({
                'type': LocationDimension.ORGANIZATIONAL.value,
                'name': metadata['domain'],
                'dimension': 'domain'
            })

        if 'community' in metadata:
            locations.append({
                'type': LocationDimension.ORGANIZATIONAL.value,
                'name': metadata['community'],
                'dimension': 'community'
            })

        # Conceptual locations (namespaces from page names)
        if 'page_name' in metadata and '/' in metadata['page_name']:
            namespace = metadata['page_name'].split('/')[0]
            locations.append({
                'type': LocationDimension.CONCEPTUAL.value,
                'name': namespace,
                'dimension': 'namespace'
            })

        return locations

    def _extract_sentiment(self, content: str) -> Dict[str, Any]:
        """Extract sentiment from content."""
        content_lower = content.lower()
        words = set(content_lower.split())

        # Count sentiment indicators
        positive_count = len(words & self.POSITIVE_KEYWORDS)
        negative_count = len(words & self.NEGATIVE_KEYWORDS)
        urgent_count = len(words & self.URGENT_KEYWORDS)

        indicators = []

        # Determine sentiment type
        if urgent_count > 0:
            sentiment_type = SentimentType.URGENT
            indicators.extend([w for w in words if w in self.URGENT_KEYWORDS])
        elif positive_count > negative_count * 1.5:
            sentiment_type = SentimentType.POSITIVE
            indicators.extend([w for w in words if w in self.POSITIVE_KEYWORDS])
        elif negative_count > positive_count * 1.5:
            sentiment_type = SentimentType.NEGATIVE
            indicators.extend([w for w in words if w in self.NEGATIVE_KEYWORDS])
        elif positive_count > 0 and negative_count > 0:
            sentiment_type = SentimentType.MIXED
            indicators.extend([w for w in words if w in (self.POSITIVE_KEYWORDS | self.NEGATIVE_KEYWORDS)])
        else:
            sentiment_type = SentimentType.NEUTRAL

        # Calculate score (-1.0 to 1.0)
        total = positive_count + negative_count
        if total > 0:
            score = (positive_count - negative_count) / total
        else:
            score = 0.0

        return {
            'type': sentiment_type,
            'score': score,
            'indicators': list(set(indicators))[:5]  # Top 5 unique indicators
        }

    def _extract_tech_environment(self, content: str, metadata: Dict[str, Any]) -> Dict[str, List[str]]:
        """Extract technology environment information."""
        content_lower = content.lower()

        platforms = []
        tools = []
        standards = []
        protocols = []

        # Detect platforms
        for keyword, platform_name in self.TECH_PLATFORM_PATTERNS.items():
            if keyword in content_lower:
                platforms.append(platform_name)

        # Detect standards
        for keyword, standard_name in self.TECH_STANDARD_PATTERNS.items():
            if keyword in content_lower:
                standards.append(standard_name)

        # Extract from linked pages (if metadata has links)
        if 'outbound_links' in metadata:
            for link in metadata.get('outbound_links', []):
                link_lower = link.lower()

                # Check for tech-related links
                if any(tech in link_lower for tech in ['api', 'sdk', 'framework', 'library']):
                    tools.append(link)

                if any(std in link_lower for std in ['standard', 'protocol', 'spec']):
                    standards.append(link)

        # Detect protocols
        protocol_patterns = r'\b(http|https|ftp|ssh|smtp|rest|graphql|grpc|mqtt)\b'
        for match in re.finditer(protocol_patterns, content_lower):
            protocols.append(match.group(0).upper())

        return {
            'platforms': list(set(platforms)),
            'tools': list(set(tools))[:10],  # Limit to 10
            'standards': list(set(standards)),
            'protocols': list(set(protocols))
        }

    def _infer_temporal_context(self, content: str) -> str:
        """Infer temporal context (current, historical, future)."""
        content_lower = content.lower()

        future_indicators = {'will', 'plan', 'future', 'upcoming', 'roadmap', 'next'}
        past_indicators = {'was', 'had', 'historical', 'legacy', 'deprecated', 'old'}

        words = set(content_lower.split())

        future_count = len(words & future_indicators)
        past_count = len(words & past_indicators)

        if future_count > past_count:
            return "future"
        elif past_count > future_count:
            return "historical"
        else:
            return "current"

    def _infer_business_context(self, content: str) -> str:
        """Infer business context (strategic, operational, tactical)."""
        content_lower = content.lower()

        strategic_indicators = {'strategy', 'vision', 'goal', 'objective', 'roadmap', 'direction'}
        operational_indicators = {'process', 'procedure', 'workflow', 'operation', 'execution'}
        tactical_indicators = {'task', 'action', 'implement', 'fix', 'update', 'change'}

        words = set(content_lower.split())

        strategic_count = len(words & strategic_indicators)
        operational_count = len(words & operational_indicators)
        tactical_count = len(words & tactical_indicators)

        counts = {
            'strategic': strategic_count,
            'operational': operational_count,
            'tactical': tactical_count
        }

        return max(counts, key=counts.get) if max(counts.values()) > 0 else "operational"


def enrich_entity_with_context(entity, content: str = None) -> ContextDimensions:
    """Convenience function to enrich an entity with context.

    Args:
        entity: Entity object (with collibra_asset attribute)
        content: Optional content string (uses entity description if not provided)

    Returns:
        ContextDimensions object
    """
    enricher = ContextEnricher()

    # Get content
    if content is None:
        if hasattr(entity, 'collibra_asset') and entity.collibra_asset:
            content = entity.collibra_asset.description or ""
        else:
            content = ""

    # Get metadata
    metadata = {}
    if hasattr(entity, 'collibra_asset') and entity.collibra_asset:
        asset = entity.collibra_asset
        metadata = {
            'domain': asset.domain,
            'community': asset.community,
            'page_name': entity.entity_id,
            'outbound_links': []
        }

        # Add links from relations
        if asset.relations:
            metadata['outbound_links'] = [r.tail_asset_name for r in asset.relations]

        # Add metadata dict if available
        if hasattr(asset, 'metadata') and asset.metadata:
            metadata.update(asset.metadata)

    return enricher.enrich(content, metadata)
