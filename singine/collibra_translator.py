"""
Collibra Semantic Model Translator for Singine.

This module translates Singine's temporal contract model into Collibra's semantic model,
supporting metadata-sealed content access requests with temporal and territorial requirements.

The translation follows this conceptual mapping:
    Singine Contract -> Collibra Asset
    Commitment -> Data Access Request
    Privilege -> Data Access Grant
    Term -> Governance Policy
    Party -> Stakeholder/Data Citizen

Integration point: Custom Collibra Edge Server for metadata-sealed content.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Set
from datetime import datetime
from enum import Enum
import pendulum
from pendulum import DateTime

from .contract_model import (
    Contract, Party, Term, Commitment, Privilege,
    CommitmentStatus, PrivilegeStatus, TermType
)
from .temporal import TemporalParser


class CollibraAssetType(Enum):
    """Collibra Asset Types for semantic model."""
    DATA_ASSET = "Data Asset"
    DATABASE = "Database"
    TABLE = "Table"
    COLUMN = "Column"
    BUSINESS_TERM = "Business Term"
    DATA_ELEMENT = "Data Element"
    POLICY = "Policy"
    REGULATION = "Regulation"


class CollibraRelationType(Enum):
    """Collibra Relation Types."""
    CONTAINS = "contains"
    IS_PART_OF = "is part of"
    GOVERNED_BY = "is governed by"
    OWNS = "owns"
    MANAGES = "manages"
    ACCESSES = "accesses"
    DEPENDS_ON = "depends on"


class TerritorialScope(Enum):
    """Territorial/geographical scopes for data access."""
    GLOBAL = "global"
    REGIONAL = "regional"
    COUNTRY = "country"
    STATE_PROVINCE = "state_province"
    CITY = "city"
    ORGANIZATION = "organization"
    DEPARTMENT = "department"
    TEAM = "team"


class AccessRequestStatus(Enum):
    """Status of a Collibra data access request."""
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass
class TemporalConstraint:
    """Temporal constraint for data access."""
    constraint_id: str
    constraint_type: str  # "absolute", "relative", "recurring", "duration"

    # Absolute temporal bounds
    start_date: Optional[DateTime] = None
    end_date: Optional[DateTime] = None

    # Relative temporal expressions (using Singine's temporal algebra)
    start_expression: Optional[str] = None  # e.g., pastDay#"3 months"
    end_expression: Optional[str] = None    # e.g., futureDay#"6 months"

    # Recurring patterns
    recurrence_pattern: Optional[str] = None  # e.g., "monthly", "quarterly"
    recurrence_window: Optional[Dict[str, Any]] = None  # Active window within recurrence

    # Duration-based
    max_duration: Optional[str] = None  # e.g., "90 days", "1 year"

    # Metadata
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TerritorialConstraint:
    """Territorial/geographical constraint for data access."""
    constraint_id: str
    scope: TerritorialScope

    # Geographic identifiers
    regions: List[str] = field(default_factory=list)  # e.g., ["EU", "APAC"]
    countries: List[str] = field(default_factory=list)  # ISO country codes
    states_provinces: List[str] = field(default_factory=list)
    cities: List[str] = field(default_factory=list)

    # Organizational boundaries
    organizations: List[str] = field(default_factory=list)
    departments: List[str] = field(default_factory=list)
    teams: List[str] = field(default_factory=list)

    # Include/exclude logic
    is_inclusive: bool = True  # True = allow these, False = exclude these

    # Metadata
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataAccessPolicy:
    """Collibra governance policy with temporal and territorial constraints."""
    policy_id: str
    name: str
    policy_type: str  # e.g., "access_control", "data_residency", "retention"

    # Constraints
    temporal_constraints: List[TemporalConstraint] = field(default_factory=list)
    territorial_constraints: List[TerritorialConstraint] = field(default_factory=list)

    # Policy rules
    rules: List[Dict[str, Any]] = field(default_factory=list)

    # Applicability
    applies_to_assets: List[str] = field(default_factory=list)  # Asset IDs
    applies_to_roles: List[str] = field(default_factory=list)   # Role names

    # Metadata
    description: str = ""
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CollibraAccessRequest:
    """
    Collibra data access request with temporal and territorial requirements.

    Follows the pattern: citizen.data.collibra.access.request.builder()
    """
    request_id: str
    citizen_id: str  # Data citizen making the request
    citizen_name: str

    # What is being requested
    requested_assets: List[str] = field(default_factory=list)  # Asset IDs
    requested_attributes: List[str] = field(default_factory=list)  # Specific columns/attributes
    access_purpose: str = ""

    # Temporal requirements
    temporal_constraints: List[TemporalConstraint] = field(default_factory=list)

    # Territorial requirements
    territorial_constraints: List[TerritorialConstraint] = field(default_factory=list)

    # Request lifecycle
    status: AccessRequestStatus = AccessRequestStatus.DRAFT
    submitted_date: Optional[DateTime] = None
    reviewed_date: Optional[DateTime] = None
    approved_date: Optional[DateTime] = None
    expiry_date: Optional[DateTime] = None

    # Governance
    governed_by_policies: List[str] = field(default_factory=list)  # Policy IDs
    approvers: List[str] = field(default_factory=list)

    # Justification and evidence
    business_justification: str = ""
    compliance_requirements: List[str] = field(default_factory=list)
    evidence_documents: List[str] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CollibraSemanticModel:
    """
    Complete Collibra semantic model representation.

    This is the target model for translation from Singine contracts.
    """
    model_id: str
    name: str

    # Core entities
    assets: List[Dict[str, Any]] = field(default_factory=list)  # Collibra assets
    stakeholders: List[Dict[str, Any]] = field(default_factory=list)  # Data citizens, stewards
    policies: List[DataAccessPolicy] = field(default_factory=list)

    # Relations
    relations: List[Dict[str, Any]] = field(default_factory=list)  # Asset-to-asset relationships

    # Access management
    access_requests: List[CollibraAccessRequest] = field(default_factory=list)

    # Metadata
    created_date: DateTime = field(default_factory=pendulum.now)
    last_updated: DateTime = field(default_factory=pendulum.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class CollibraTranslator:
    """
    Translator from Singine contract model to Collibra semantic model.

    Usage:
        translator = CollibraTranslator()
        collibra_model = translator.translate_contract(contract)
        access_request = translator.create_access_request_from_privilege(privilege)
    """

    def __init__(self):
        """Initialize translator with temporal parser."""
        self.temporal_parser = TemporalParser()

    def translate_contract(self, contract: Contract) -> CollibraSemanticModel:
        """
        Translate a Singine contract to Collibra semantic model.

        Mapping:
        - Contract -> Collection of related Collibra assets
        - Parties -> Stakeholders (data citizens, stewards)
        - Terms -> Governance policies
        - Commitments -> Access request obligations
        - Privileges -> Granted access rights
        """
        model = CollibraSemanticModel(
            model_id=f"collibra-{contract.contract_id}",
            name=f"Semantic Model for {contract.name}"
        )

        # Translate parties to stakeholders
        for party in contract.parties:
            model.stakeholders.append(self._party_to_stakeholder(party))

        # Translate terms to policies
        for term in contract.terms:
            policy = self._term_to_policy(term)
            if policy:
                model.policies.append(policy)

        # Translate commitments to access request obligations
        for commitment in contract.commitments:
            # Commitments can become requirements in access requests
            model.metadata.setdefault('commitments', []).append({
                'commitment_id': commitment.commitment_id,
                'party_id': commitment.party_id,
                'description': commitment.description,
                'due_date': commitment.due_date.isoformat() if commitment.due_date else None,
                'status': commitment.status.value
            })

        # Translate privileges to access grants
        for privilege in contract.privileges:
            access_request = self.create_access_request_from_privilege(
                privilege,
                contract
            )
            if access_request:
                model.access_requests.append(access_request)

        return model

    def _party_to_stakeholder(self, party: Party) -> Dict[str, Any]:
        """Convert Singine Party to Collibra stakeholder."""
        return {
            'stakeholder_id': party.party_id,
            'name': party.name,
            'role': party.role,
            'type': 'data_citizen',
            'attributes': party.attributes,
            'responsibilities': []
        }

    def _term_to_policy(self, term: Term) -> Optional[DataAccessPolicy]:
        """Convert Singine Term to Collibra data access policy."""
        policy = DataAccessPolicy(
            policy_id=term.term_id,
            name=f"Policy: {term.description[:50]}",
            policy_type=self._map_term_type_to_policy_type(term.term_type),
            description=term.description
        )

        # Handle temporal terms
        if term.term_type == TermType.TEMPORAL or term.start_date or term.end_date:
            temporal_constraint = TemporalConstraint(
                constraint_id=f"{term.term_id}-temporal",
                constraint_type="absolute",
                start_date=term.start_date,
                end_date=term.end_date,
                description=f"Temporal bounds for {term.description}"
            )
            policy.temporal_constraints.append(temporal_constraint)

        # Handle recurring terms
        if term.term_type == TermType.RECURRING and term.recurrence_pattern:
            recurring_constraint = TemporalConstraint(
                constraint_id=f"{term.term_id}-recurring",
                constraint_type="recurring",
                recurrence_pattern=term.recurrence_pattern,
                description=f"Recurring pattern: {term.recurrence_pattern}"
            )
            policy.temporal_constraints.append(recurring_constraint)

        # Map affected entities
        policy.applies_to_assets = term.affects_commitments + term.affects_privileges

        return policy

    def _map_term_type_to_policy_type(self, term_type: TermType) -> str:
        """Map Singine TermType to Collibra policy type."""
        mapping = {
            TermType.TEMPORAL: "temporal_access_control",
            TermType.CONCEPTUAL: "conditional_access",
            TermType.RECURRING: "recurring_access",
            TermType.CONDITIONAL: "conditional_policy"
        }
        return mapping.get(term_type, "general_policy")

    def create_access_request_from_privilege(
        self,
        privilege: Privilege,
        contract: Contract
    ) -> Optional[CollibraAccessRequest]:
        """
        Create a Collibra access request from a Singine privilege.

        This implements the citizen.data.collibra.access.request.builder() pattern.
        """
        if not privilege.party_id:
            return None

        # Get party information
        party = contract.get_party(privilege.party_id)
        if not party:
            return None

        # Build access request
        request = CollibraAccessRequest(
            request_id=f"access-req-{privilege.privilege_id}",
            citizen_id=party.party_id,
            citizen_name=party.name,
            access_purpose=privilege.description,
            business_justification=f"Privilege granted under {contract.name}"
        )

        # Map granted resources to requested assets
        request.requested_assets = privilege.grants_access_to
        request.requested_attributes = privilege.grants_rights

        # Extract temporal constraints
        if privilege.granted_date or privilege.expiry_date:
            temporal_constraint = TemporalConstraint(
                constraint_id=f"{privilege.privilege_id}-temporal",
                constraint_type="absolute",
                start_date=privilege.granted_date,
                end_date=privilege.expiry_date,
                description=f"Access window for {privilege.description}"
            )
            request.temporal_constraints.append(temporal_constraint)

        # Map status
        status_mapping = {
            PrivilegeStatus.NOT_GRANTED: AccessRequestStatus.DRAFT,
            PrivilegeStatus.GRANTED: AccessRequestStatus.ACTIVE,
            PrivilegeStatus.EXERCISED: AccessRequestStatus.ACTIVE,
            PrivilegeStatus.REVOKED: AccessRequestStatus.REVOKED
        }
        request.status = status_mapping.get(privilege.status, AccessRequestStatus.DRAFT)

        # Link to governing policies
        request.governed_by_policies = privilege.governed_by_terms

        # Set dates based on privilege status
        if privilege.status == PrivilegeStatus.GRANTED:
            request.approved_date = privilege.granted_date
        request.expiry_date = privilege.expiry_date

        return request

    def build_temporal_constraint_from_expression(
        self,
        expression: str,
        constraint_id: str = "auto-temporal"
    ) -> TemporalConstraint:
        """
        Build a TemporalConstraint from Singine's temporal expression.

        Examples:
            pastDay#"3 months" -> constraint from 3 months ago to now
            futureDay#"6 months" -> constraint from now to 6 months ahead
            day#"start of next month" -> specific date constraint
        """
        parsed_date = self.temporal_parser.parse_temporal_expression(expression)

        # Determine if this is a start or end bound based on expression type
        is_past = "pastDay#" in expression
        is_future = "futureDay#" in expression

        constraint = TemporalConstraint(
            constraint_id=constraint_id,
            constraint_type="relative"
        )

        if is_past:
            constraint.start_expression = expression
            constraint.start_date = parsed_date
            constraint.end_date = pendulum.now()
        elif is_future:
            constraint.start_date = pendulum.now()
            constraint.end_expression = expression
            constraint.end_date = parsed_date
        else:
            # Absolute date expression
            constraint.constraint_type = "absolute"
            constraint.start_date = parsed_date
            constraint.start_expression = expression

        return constraint


class CollibraAccessRequestBuilder:
    """
    Builder for constructing Collibra access requests with fluent API.

    Usage:
        request = (CollibraAccessRequestBuilder()
            .for_citizen("user-123", "John Doe")
            .requesting_assets(["asset-1", "asset-2"])
            .with_temporal_constraint(pastDay#"3 months", futureDay#"6 months")
            .with_territorial_constraint(scope=TerritorialScope.COUNTRY, countries=["US", "CA"])
            .with_purpose("Quarterly financial analysis")
            .build())
    """

    def __init__(self):
        self.request_id = f"req-{pendulum.now().format('YYYYMMDDHHmmss')}"
        self.citizen_id = ""
        self.citizen_name = ""
        self.assets: List[str] = []
        self.attributes: List[str] = []
        self.temporal_constraints: List[TemporalConstraint] = []
        self.territorial_constraints: List[TerritorialConstraint] = []
        self.purpose = ""
        self.justification = ""
        self.policies: List[str] = []
        self.translator = CollibraTranslator()

    def for_citizen(self, citizen_id: str, citizen_name: str) -> 'CollibraAccessRequestBuilder':
        """Set the data citizen making the request."""
        self.citizen_id = citizen_id
        self.citizen_name = citizen_name
        return self

    def requesting_assets(self, asset_ids: List[str]) -> 'CollibraAccessRequestBuilder':
        """Set the assets being requested."""
        self.assets = asset_ids
        return self

    def requesting_attributes(self, attributes: List[str]) -> 'CollibraAccessRequestBuilder':
        """Set specific attributes/columns being requested."""
        self.attributes = attributes
        return self

    def with_temporal_constraint(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        recurrence: Optional[str] = None
    ) -> 'CollibraAccessRequestBuilder':
        """
        Add temporal constraint using Singine's temporal expressions.

        Examples:
            .with_temporal_constraint(start=pastDay#"1 month", end=futureDay#"3 months")
            .with_temporal_constraint(recurrence="monthly")
        """
        constraint_id = f"temporal-{len(self.temporal_constraints) + 1}"

        constraint = TemporalConstraint(
            constraint_id=constraint_id,
            constraint_type="relative" if start or end else "recurring"
        )

        if start:
            constraint.start_expression = start
            constraint.start_date = self.translator.temporal_parser.parse_temporal_expression(start)

        if end:
            constraint.end_expression = end
            constraint.end_date = self.translator.temporal_parser.parse_temporal_expression(end)

        if recurrence:
            constraint.recurrence_pattern = recurrence

        self.temporal_constraints.append(constraint)
        return self

    def with_territorial_constraint(
        self,
        scope: TerritorialScope,
        regions: Optional[List[str]] = None,
        countries: Optional[List[str]] = None,
        organizations: Optional[List[str]] = None,
        is_inclusive: bool = True
    ) -> 'CollibraAccessRequestBuilder':
        """Add territorial constraint."""
        constraint_id = f"territorial-{len(self.territorial_constraints) + 1}"

        constraint = TerritorialConstraint(
            constraint_id=constraint_id,
            scope=scope,
            regions=regions or [],
            countries=countries or [],
            organizations=organizations or [],
            is_inclusive=is_inclusive
        )

        self.territorial_constraints.append(constraint)
        return self

    def with_purpose(self, purpose: str) -> 'CollibraAccessRequestBuilder':
        """Set the access purpose."""
        self.purpose = purpose
        return self

    def with_justification(self, justification: str) -> 'CollibraAccessRequestBuilder':
        """Set business justification."""
        self.justification = justification
        return self

    def governed_by(self, policy_ids: List[str]) -> 'CollibraAccessRequestBuilder':
        """Set governing policies."""
        self.policies = policy_ids
        return self

    def build(self) -> CollibraAccessRequest:
        """Build the final access request."""
        return CollibraAccessRequest(
            request_id=self.request_id,
            citizen_id=self.citizen_id,
            citizen_name=self.citizen_name,
            requested_assets=self.assets,
            requested_attributes=self.attributes,
            temporal_constraints=self.temporal_constraints,
            territorial_constraints=self.territorial_constraints,
            access_purpose=self.purpose,
            business_justification=self.justification,
            governed_by_policies=self.policies,
            status=AccessRequestStatus.DRAFT
        )
