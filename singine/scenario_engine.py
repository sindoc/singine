"""
Temporal Projection Engine for Contract Scenario Analysis.

This engine simulates contract execution over time to analyze:
- Commitment fulfillment paths
- Privilege activation sequences
- Cost/benefit analysis
- Risk assessment
- Decision impact measurement

The engine projects contracts into the future and generates scenarios
that can be written to Logseq via the API for analysis and comparison.
"""

from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from pendulum import DateTime
import pendulum

from .contract_model import (
    Contract, Commitment, Privilege, Scenario, Term,
    CommitmentStatus, PrivilegeStatus, TermType
)
from .logseq_api import LogseqAPIClient


@dataclass
class ProjectionEvent:
    """An event in the timeline of a contract simulation."""
    timestamp: DateTime
    event_type: str  # "commitment_due", "commitment_fulfilled", "privilege_granted", etc.
    entity_id: str   # Commitment or Privilege ID
    description: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectionResult:
    """Result of projecting a contract into the future."""
    scenario: Scenario
    timeline: List[ProjectionEvent]

    # Financial analysis
    total_commitments_cost: float
    total_privileges_value: float
    net_value: float

    # Time analysis
    commitment_hours: float
    privilege_hours: float

    # Risk metrics
    breach_probability: float
    critical_commitments: List[str]  # IDs of commitments that can't fail

    # Compliance
    fulfilled_commitments: List[str]
    breached_commitments: List[str]
    granted_privileges: List[str]
    revoked_privileges: List[str]


class ScenarioEngine:
    """Engine for projecting contracts into the future and analyzing scenarios."""

    def __init__(self, api_client: Optional[LogseqAPIClient] = None):
        """
        Initialize scenario engine.

        Args:
            api_client: Optional Logseq API client for writing scenarios to Logseq
        """
        self.api_client = api_client

    def project_contract(
        self,
        contract: Contract,
        simulation_end: DateTime,
        fulfillment_assumptions: Optional[Dict[str, bool]] = None
    ) -> ProjectionResult:
        """
        Project a contract into the future based on fulfillment assumptions.

        Args:
            contract: Contract to project
            simulation_end: End date of simulation
            fulfillment_assumptions: Dict of commitment_id -> will_fulfill (bool)
                                   If None, assumes all commitments are fulfilled

        Returns:
            ProjectionResult with timeline and analysis
        """
        # Default: assume perfect fulfillment
        if fulfillment_assumptions is None:
            fulfillment_assumptions = {
                c.commitment_id: True
                for c in contract.commitments
            }

        # Create scenario
        scenario = Scenario(
            scenario_id=f"scenario-{pendulum.now().format('YYYYMMDDHHmmss')}",
            name=f"Projection of {contract.name}",
            description="Automated projection with fulfillment assumptions",
            contracts=[contract.contract_id],
            simulation_start=contract.start_date,
            simulation_end=simulation_end
        )

        timeline: List[ProjectionEvent] = []

        # Clone commitments and privileges for projection
        projected_commitments = [self._clone_commitment(c) for c in contract.commitments]
        projected_privileges = [self._clone_privilege(p) for p in contract.privileges]

        # Sort commitments by due date
        sorted_commitments = sorted(
            [c for c in projected_commitments if c.due_date],
            key=lambda c: c.due_date
        )

        # Simulate timeline
        for commitment in sorted_commitments:
            if commitment.due_date > simulation_end:
                break

            # Record commitment due event
            timeline.append(ProjectionEvent(
                timestamp=commitment.due_date,
                event_type="commitment_due",
                entity_id=commitment.commitment_id,
                description=f"Commitment due: {commitment.description}",
                metadata={"amount": commitment.amount, "unit": commitment.unit}
            ))

            # Check fulfillment assumption
            will_fulfill = fulfillment_assumptions.get(commitment.commitment_id, True)

            if will_fulfill:
                # Mark as fulfilled
                commitment.status = CommitmentStatus.FULFILLED
                commitment.fulfilled_date = commitment.due_date

                timeline.append(ProjectionEvent(
                    timestamp=commitment.due_date,
                    event_type="commitment_fulfilled",
                    entity_id=commitment.commitment_id,
                    description=f"Commitment fulfilled: {commitment.description}",
                    metadata={"amount": commitment.amount}
                ))

                # Grant associated privileges
                for privilege_id in commitment.fulfillment_grants_privileges:
                    privilege = self._find_privilege(projected_privileges, privilege_id)
                    if privilege and privilege.status == PrivilegeStatus.NOT_GRANTED:
                        # Check if all conditional commitments are fulfilled
                        if self._check_privilege_conditions(
                            privilege,
                            projected_commitments
                        ):
                            privilege.status = PrivilegeStatus.GRANTED
                            privilege.granted_date = commitment.due_date

                            timeline.append(ProjectionEvent(
                                timestamp=commitment.due_date,
                                event_type="privilege_granted",
                                entity_id=privilege.privilege_id,
                                description=f"Privilege granted: {privilege.description}",
                                metadata={"grants": privilege.grants_rights}
                            ))
            else:
                # Mark as breached
                commitment.status = CommitmentStatus.BREACHED

                timeline.append(ProjectionEvent(
                    timestamp=commitment.due_date,
                    event_type="commitment_breached",
                    entity_id=commitment.commitment_id,
                    description=f"Commitment breached: {commitment.description}",
                    metadata={"consequences": commitment.breach_consequences}
                ))

                # Revoke dependent privileges
                for privilege in projected_privileges:
                    if commitment.commitment_id in privilege.conditional_on_commitments:
                        if privilege.status == PrivilegeStatus.GRANTED:
                            privilege.status = PrivilegeStatus.REVOKED

                            timeline.append(ProjectionEvent(
                                timestamp=commitment.due_date,
                                event_type="privilege_revoked",
                                entity_id=privilege.privilege_id,
                                description=f"Privilege revoked: {privilege.description}",
                                metadata={"reason": "commitment_breach"}
                            ))

        # Analyze results
        result = self._analyze_projection(
            scenario,
            timeline,
            projected_commitments,
            projected_privileges
        )

        return result

    def compare_scenarios(
        self,
        contract: Contract,
        scenario_specs: List[Dict[str, Any]]
    ) -> List[ProjectionResult]:
        """
        Compare multiple scenarios with different fulfillment assumptions.

        Args:
            contract: Contract to analyze
            scenario_specs: List of scenario specifications, each containing:
                - name: Scenario name
                - simulation_end: End date
                - fulfillment_assumptions: Dict of commitment_id -> bool

        Returns:
            List of ProjectionResults for comparison
        """
        results = []

        for spec in scenario_specs:
            result = self.project_contract(
                contract,
                spec['simulation_end'],
                spec.get('fulfillment_assumptions')
            )
            result.scenario.name = spec.get('name', result.scenario.name)
            results.append(result)

        return results

    def write_scenario_to_logseq(
        self,
        projection: ProjectionResult,
        contract: Contract
    ) -> str:
        """
        Write a projected scenario to Logseq for review and analysis.

        Args:
            projection: ProjectionResult to write
            contract: Original contract

        Returns:
            Page name of created scenario

        Raises:
            RuntimeError: If API client not configured
        """
        if not self.api_client:
            raise RuntimeError("API client required to write scenarios to Logseq")

        # Create scenario page
        page_name = self.api_client.create_scenario(
            scenario_name=projection.scenario.name,
            contract_type=contract.contract_type,
            description=projection.scenario.description
        )

        # Write financial analysis
        self.api_client.insert_block(
            page_name,
            f"### Financial Analysis",
            sibling=False
        )
        self.api_client.insert_block(
            page_name,
            f"- Total Commitments Cost: ${projection.total_commitments_cost:,.2f}",
            sibling=False
        )
        self.api_client.insert_block(
            page_name,
            f"- Total Privileges Value: ${projection.total_privileges_value:,.2f}",
            sibling=False
        )
        self.api_client.insert_block(
            page_name,
            f"- Net Value: ${projection.net_value:,.2f}",
            sibling=False
        )

        # Write timeline
        self.api_client.insert_block(
            page_name,
            f"### Projected Timeline ({len(projection.timeline)} events)",
            sibling=False
        )

        for event in projection.timeline[:20]:  # Limit to first 20 events for readability
            event_str = f"- **{event.timestamp.format('YYYY-MM-DD')}**: {event.description}"
            self.api_client.insert_block(page_name, event_str, sibling=False)

        # Write commitments
        self.api_client.insert_block(
            page_name,
            f"### Commitments ({len(projection.fulfilled_commitments)} fulfilled, "
            f"{len(projection.breached_commitments)} breached)",
            sibling=False
        )

        # Write privileges
        self.api_client.insert_block(
            page_name,
            f"### Privileges ({len(projection.granted_privileges)} granted, "
            f"{len(projection.revoked_privileges)} revoked)",
            sibling=False
        )

        # Write risk assessment
        self.api_client.insert_block(
            page_name,
            f"### Risk Assessment",
            sibling=False
        )
        self.api_client.insert_block(
            page_name,
            f"- Breach Probability: {projection.breach_probability:.1%}",
            sibling=False
        )
        self.api_client.insert_block(
            page_name,
            f"- Critical Commitments: {len(projection.critical_commitments)}",
            sibling=False
        )

        return page_name

    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------

    def _clone_commitment(self, commitment: Commitment) -> Commitment:
        """Create a copy of a commitment for projection."""
        return Commitment(
            commitment_id=commitment.commitment_id,
            party_id=commitment.party_id,
            description=commitment.description,
            status=commitment.status,
            due_date=commitment.due_date,
            fulfilled_date=commitment.fulfilled_date,
            governed_by_terms=commitment.governed_by_terms.copy(),
            fulfillment_grants_privileges=commitment.fulfillment_grants_privileges.copy(),
            breach_consequences=commitment.breach_consequences.copy(),
            amount=commitment.amount,
            unit=commitment.unit,
            evidence=commitment.evidence.copy(),
            metadata=commitment.metadata.copy()
        )

    def _clone_privilege(self, privilege: Privilege) -> Privilege:
        """Create a copy of a privilege for projection."""
        return Privilege(
            privilege_id=privilege.privilege_id,
            party_id=privilege.party_id,
            description=privilege.description,
            status=privilege.status,
            granted_date=privilege.granted_date,
            expiry_date=privilege.expiry_date,
            exercised_date=privilege.exercised_date,
            conditional_on_commitments=privilege.conditional_on_commitments.copy(),
            governed_by_terms=privilege.governed_by_terms.copy(),
            grants_access_to=privilege.grants_access_to.copy(),
            grants_ownership_of=privilege.grants_ownership_of.copy(),
            grants_rights=privilege.grants_rights.copy(),
            metadata=privilege.metadata.copy()
        )

    def _find_privilege(
        self,
        privileges: List[Privilege],
        privilege_id: str
    ) -> Optional[Privilege]:
        """Find a privilege by ID."""
        return next((p for p in privileges if p.privilege_id == privilege_id), None)

    def _check_privilege_conditions(
        self,
        privilege: Privilege,
        commitments: List[Commitment]
    ) -> bool:
        """Check if all conditions for granting a privilege are met."""
        for commitment_id in privilege.conditional_on_commitments:
            commitment = next(
                (c for c in commitments if c.commitment_id == commitment_id),
                None
            )
            if not commitment or commitment.status != CommitmentStatus.FULFILLED:
                return False
        return True

    def _analyze_projection(
        self,
        scenario: Scenario,
        timeline: List[ProjectionEvent],
        commitments: List[Commitment],
        privileges: List[Privilege]
    ) -> ProjectionResult:
        """Analyze projection results and compute metrics."""

        # Financial analysis
        total_commitments_cost = sum(
            c.amount or 0
            for c in commitments
            if c.status == CommitmentStatus.FULFILLED
        )

        # Simplified privilege valuation (can be enhanced)
        total_privileges_value = len([
            p for p in privileges
            if p.status == PrivilegeStatus.GRANTED
        ]) * 1000.0  # Placeholder value

        net_value = total_privileges_value - total_commitments_cost

        # Compliance tracking
        fulfilled = [c.commitment_id for c in commitments if c.status == CommitmentStatus.FULFILLED]
        breached = [c.commitment_id for c in commitments if c.status == CommitmentStatus.BREACHED]
        granted = [p.privilege_id for p in privileges if p.status == PrivilegeStatus.GRANTED]
        revoked = [p.privilege_id for p in privileges if p.status == PrivilegeStatus.REVOKED]

        # Risk assessment
        total_commitments = len(commitments)
        breach_count = len(breached)
        breach_probability = breach_count / total_commitments if total_commitments > 0 else 0.0

        # Identify critical commitments (those that grant important privileges)
        critical = [
            c.commitment_id
            for c in commitments
            if c.fulfillment_grants_privileges
        ]

        # Update scenario with analysis
        scenario.projected_commitments = commitments
        scenario.projected_privileges = privileges
        scenario.total_cost = total_commitments_cost
        scenario.benefit_score = total_privileges_value
        scenario.risk_score = breach_probability

        return ProjectionResult(
            scenario=scenario,
            timeline=timeline,
            total_commitments_cost=total_commitments_cost,
            total_privileges_value=total_privileges_value,
            net_value=net_value,
            commitment_hours=0.0,  # TODO: implement time tracking
            privilege_hours=0.0,
            breach_probability=breach_probability,
            critical_commitments=critical,
            fulfilled_commitments=fulfilled,
            breached_commitments=breached,
            granted_privileges=granted,
            revoked_privileges=revoked
        )
