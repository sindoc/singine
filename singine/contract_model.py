"""
Contract Metamodel for Temporal Decision Analysis.

This module defines the core abstractions for contract-based scenario simulation:
- Contracts impose commitments and grant privileges
- Terms can be temporal (time-bound) or conceptual (condition-bound)
- Scenarios project contract fulfillment into the future
- Analysis measures impact of different decision paths

Design Philosophy:
- Contracts are first-class entities with clear parties, terms, and temporal bounds
- Commitments are obligations that must be fulfilled (tasks, payments, deliverables)
- Privileges are rights granted upon fulfillment (access, ownership, benefits)
- Terms define the rules that govern commitments and privileges
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Optional, Any
from pendulum import DateTime
import pendulum


class TermType(Enum):
    """Types of contract terms."""
    TEMPORAL = "temporal"          # Time-bound (e.g., "monthly rent due on 1st")
    CONCEPTUAL = "conceptual"      # Condition-bound (e.g., "upon completion of...")
    RECURRING = "recurring"        # Repeating pattern (e.g., "every month")
    CONDITIONAL = "conditional"    # If-then logic (e.g., "if late, then penalty")


class CommitmentStatus(Enum):
    """Status of a commitment."""
    PENDING = "pending"           # Not yet due
    DUE = "due"                   # Currently due
    FULFILLED = "fulfilled"       # Completed
    BREACHED = "breached"         # Missed/violated
    WAIVED = "waived"             # Cancelled by agreement


class PrivilegeStatus(Enum):
    """Status of a privilege."""
    NOT_GRANTED = "not_granted"   # Conditions not met
    GRANTED = "granted"           # Active and usable
    EXERCISED = "exercised"       # Used/consumed
    REVOKED = "revoked"           # Taken away due to breach


@dataclass
class Party:
    """A party involved in a contract."""
    party_id: str
    name: str
    role: str  # e.g., "tenant", "landlord", "employer", "employee"
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Term:
    """A term within a contract that defines rules."""
    term_id: str
    term_type: TermType
    description: str

    # Temporal terms
    start_date: Optional[DateTime] = None
    end_date: Optional[DateTime] = None
    recurrence_pattern: Optional[str] = None  # e.g., "monthly", "weekly", "day#1 of month"

    # Conceptual terms
    conditions: List[str] = field(default_factory=list)  # Logical conditions

    # References
    affects_commitments: List[str] = field(default_factory=list)  # Commitment IDs
    affects_privileges: List[str] = field(default_factory=list)   # Privilege IDs

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Commitment:
    """An obligation imposed by a contract."""
    commitment_id: str
    party_id: str  # Who must fulfill this
    description: str

    # Status tracking
    status: CommitmentStatus = CommitmentStatus.PENDING

    # Temporal aspects
    due_date: Optional[DateTime] = None
    fulfilled_date: Optional[DateTime] = None

    # Terms that govern this commitment
    governed_by_terms: List[str] = field(default_factory=list)  # Term IDs

    # What happens when fulfilled/breached
    fulfillment_grants_privileges: List[str] = field(default_factory=list)
    breach_consequences: List[str] = field(default_factory=list)

    # Quantifiable aspects
    amount: Optional[float] = None  # e.g., rent amount
    unit: Optional[str] = None      # e.g., "USD", "hours", "deliverables"

    # Evidence of fulfillment
    evidence: List[str] = field(default_factory=list)  # References to proof

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Privilege:
    """A right granted by a contract."""
    privilege_id: str
    party_id: str  # Who receives this privilege
    description: str

    # Status tracking
    status: PrivilegeStatus = PrivilegeStatus.NOT_GRANTED

    # Temporal aspects
    granted_date: Optional[DateTime] = None
    expiry_date: Optional[DateTime] = None
    exercised_date: Optional[DateTime] = None

    # Conditions for granting
    conditional_on_commitments: List[str] = field(default_factory=list)  # Must be fulfilled
    governed_by_terms: List[str] = field(default_factory=list)

    # What this privilege allows
    grants_access_to: List[str] = field(default_factory=list)
    grants_ownership_of: List[str] = field(default_factory=list)
    grants_rights: List[str] = field(default_factory=list)

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Contract:
    """A contract between parties with terms, commitments, and privileges."""
    contract_id: str
    name: str
    contract_type: str  # e.g., "tenancy", "employment", "service"
    start_date: DateTime

    # Parties involved
    parties: List[Party] = field(default_factory=list)

    # Contract structure
    terms: List[Term] = field(default_factory=list)
    commitments: List[Commitment] = field(default_factory=list)
    privileges: List[Privilege] = field(default_factory=list)

    # Temporal bounds
    end_date: Optional[DateTime] = None

    # Current state
    is_active: bool = True

    # Relationship to other contracts
    depends_on_contracts: List[str] = field(default_factory=list)
    supersedes_contracts: List[str] = field(default_factory=list)

    # Analysis metadata
    scenarios: List[str] = field(default_factory=list)  # Scenario IDs that use this contract

    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_party(self, party_id: str) -> Optional[Party]:
        """Get a party by ID."""
        return next((p for p in self.parties if p.party_id == party_id), None)

    def get_term(self, term_id: str) -> Optional[Term]:
        """Get a term by ID."""
        return next((t for t in self.terms if t.term_id == term_id), None)

    def get_commitment(self, commitment_id: str) -> Optional[Commitment]:
        """Get a commitment by ID."""
        return next((c for c in self.commitments if c.commitment_id == commitment_id), None)

    def get_privilege(self, privilege_id: str) -> Optional[Privilege]:
        """Get a privilege by ID."""
        return next((p for p in self.privileges if p.privilege_id == privilege_id), None)

    def get_commitments_for_party(self, party_id: str) -> List[Commitment]:
        """Get all commitments for a specific party."""
        return [c for c in self.commitments if c.party_id == party_id]

    def get_privileges_for_party(self, party_id: str) -> List[Privilege]:
        """Get all privileges for a specific party."""
        return [p for p in self.privileges if p.party_id == party_id]

    def get_due_commitments(self, as_of: DateTime) -> List[Commitment]:
        """Get commitments that are due as of a specific date."""
        return [
            c for c in self.commitments
            if c.due_date and c.due_date <= as_of and c.status == CommitmentStatus.PENDING
        ]

    def get_active_privileges(self, as_of: DateTime) -> List[Privilege]:
        """Get privileges that are active as of a specific date."""
        return [
            p for p in self.privileges
            if p.status == PrivilegeStatus.GRANTED
            and (not p.expiry_date or p.expiry_date > as_of)
        ]


@dataclass
class Scenario:
    """A projected future state based on contract execution."""
    scenario_id: str
    name: str
    description: str

    # Base contract(s) being simulated
    contracts: List[str] = field(default_factory=list)  # Contract IDs

    # Simulation parameters
    simulation_start: DateTime = field(default_factory=pendulum.now)
    simulation_end: DateTime = field(default_factory=lambda: pendulum.now().add(years=1))

    # Decision points and outcomes
    decisions: List[Dict[str, Any]] = field(default_factory=list)

    # Projected state
    projected_commitments: List[Commitment] = field(default_factory=list)
    projected_privileges: List[Privilege] = field(default_factory=list)

    # Analysis results
    total_cost: Optional[float] = None  # Financial impact
    time_burden: Optional[float] = None  # Time commitment (hours)
    risk_score: Optional[float] = None   # Risk assessment
    benefit_score: Optional[float] = None # Benefit assessment

    # Comparison with other scenarios
    compared_to: List[str] = field(default_factory=list)  # Other scenario IDs

    metadata: Dict[str, Any] = field(default_factory=dict)


# Example: Tenancy Contract Template
def create_tenancy_contract(
    tenant_name: str,
    landlord_name: str,
    monthly_rent: float,
    start_date: DateTime,
    duration_months: int = 12
) -> Contract:
    """
    Create a basic tenancy contract.

    This demonstrates the metamodel with a real-world example.
    """
    contract_id = f"tenancy-{start_date.format('YYYYMMDD')}"
    end_date = start_date.add(months=duration_months)

    # Parties
    tenant = Party(
        party_id="tenant-1",
        name=tenant_name,
        role="tenant"
    )

    landlord = Party(
        party_id="landlord-1",
        name=landlord_name,
        role="landlord"
    )

    # Terms
    rent_term = Term(
        term_id="term-rent-payment",
        term_type=TermType.RECURRING,
        description=f"Monthly rent of ${monthly_rent} due on the 1st of each month",
        start_date=start_date,
        end_date=end_date,
        recurrence_pattern="monthly",
        affects_commitments=["commitment-rent-payment"]
    )

    occupancy_term = Term(
        term_id="term-occupancy-right",
        term_type=TermType.CONCEPTUAL,
        description="Right to occupy premises conditional on rent payment",
        conditions=["rent is paid", "no breach of lease"],
        affects_privileges=["privilege-occupancy"]
    )

    # Commitments (Tenant's obligation)
    rent_commitments = []
    for month in range(duration_months):
        due = start_date.add(months=month).start_of('month')
        rent_commitments.append(
            Commitment(
                commitment_id=f"commitment-rent-{month+1}",
                party_id=tenant.party_id,
                description=f"Pay rent for month {month+1}",
                status=CommitmentStatus.PENDING,
                due_date=due,
                governed_by_terms=["term-rent-payment"],
                fulfillment_grants_privileges=[f"privilege-occupancy-{month+1}"],
                breach_consequences=["late-fee", "eviction-notice"],
                amount=monthly_rent,
                unit="USD"
            )
        )

    # Privileges (Tenant's right)
    occupancy_privileges = []
    for month in range(duration_months):
        start = start_date.add(months=month)
        end = start.add(months=1)
        occupancy_privileges.append(
            Privilege(
                privilege_id=f"privilege-occupancy-{month+1}",
                party_id=tenant.party_id,
                description=f"Right to occupy premises in month {month+1}",
                status=PrivilegeStatus.NOT_GRANTED,
                granted_date=None,
                expiry_date=end,
                conditional_on_commitments=[f"commitment-rent-{month+1}"],
                governed_by_terms=["term-occupancy-right"],
                grants_access_to=["premises"],
                grants_rights=["exclusive-use", "peaceful-enjoyment"]
            )
        )

    return Contract(
        contract_id=contract_id,
        name=f"Tenancy Agreement - {tenant_name}",
        contract_type="tenancy",
        parties=[tenant, landlord],
        terms=[rent_term, occupancy_term],
        commitments=rent_commitments,
        privileges=occupancy_privileges,
        start_date=start_date,
        end_date=end_date,
        is_active=True
    )
