"""
FIBO (Financial Industry Business Ontology) Integration for Singine.

This module integrates FIBO ontologies with Singine's contract model to support:
- Financial scenarios with hypothetical game-theoretic modeling
- Persona-based intent modeling
- Strategic decision analysis
- Financial instrument contracts

FIBO Domains Covered:
- FBC (Foundations and Business Entities)
- FND (Foundations - Agreements, Arrangements, Relations)
- BE (Business Entities - Corporations, Partnerships)
- IND (Indices and Indicators)
- SEC (Securities - Financial Instruments)

References:
- https://spec.edmcouncil.org/fibo/
- FIBO/FND/Agreements/Contracts
- FIBO/FND/AgentsAndPeople/Agents
- FIBO/IND/EconomicIndicators/EconomicIndicators
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Set
from enum import Enum
from datetime import datetime
import pendulum
from pendulum import DateTime

from .contract_model import Contract, Party, Term, Commitment, Privilege
from .rdf_ontology import RDFGraph, RDFTriple, Namespace


# ============================================================================
# FIBO Namespaces
# ============================================================================

class FIBONamespace:
    """FIBO ontology namespaces."""

    # FIBO Base
    FIBO = "https://spec.edmcouncil.org/fibo/ontology/"

    # Foundations (FND)
    FND_AAP = f"{FIBO}FND/AgentsAndPeople/Agents/"  # Agents
    FND_AGR = f"{FIBO}FND/Agreements/Contracts/"  # Contracts
    FND_ARR = f"{FIBO}FND/Arrangements/Arrangements/"  # Arrangements
    FND_REL = f"{FIBO}FND/Relations/Relations/"  # Relations
    FND_DT = f"{FIBO}FND/DatesAndTimes/FinancialDates/"  # Financial Dates

    # Business Entities (BE)
    BE_LE = f"{FIBO}BE/LegalEntities/LegalPersons/"  # Legal Persons
    BE_OAC = f"{FIBO}BE/OwnershipAndControl/OwnershipParties/"  # Ownership

    # Indices and Indicators (IND)
    IND_EI = f"{FIBO}IND/EconomicIndicators/EconomicIndicators/"  # Economic Indicators
    IND_FI = f"{FIBO}IND/FinancialIndicators/FinancialIndicators/"  # Financial Indicators

    # Securities (SEC)
    SEC_FI = f"{FIBO}SEC/Funds/Funds/"  # Financial Instruments


# ============================================================================
# Game Theory & Scenario Classes
# ============================================================================

class PlayerRole(Enum):
    """Game-theoretic player roles in financial scenarios."""
    INVESTOR = "investor"
    LENDER = "lender"
    BORROWER = "borrower"
    ISSUER = "issuer"
    UNDERWRITER = "underwriter"
    REGULATOR = "regulator"
    MARKET_MAKER = "market_maker"
    COUNTERPARTY = "counterparty"


class StrategyType(Enum):
    """Strategic approaches in financial scenarios."""
    COOPERATIVE = "cooperative"
    COMPETITIVE = "competitive"
    MIXED = "mixed"
    NASH_EQUILIBRIUM = "nash_equilibrium"
    PARETO_OPTIMAL = "pareto_optimal"
    DOMINANT = "dominant"
    RISK_AVERSE = "risk_averse"
    RISK_SEEKING = "risk_seeking"


class PayoffType(Enum):
    """Types of payoffs in game-theoretic analysis."""
    MONETARY = "monetary"
    UTILITY = "utility"
    RISK_ADJUSTED = "risk_adjusted"
    REPUTATION = "reputation"
    MARKET_SHARE = "market_share"


@dataclass
class Persona:
    """
    Financial persona for scenario modeling (FIBO Agent).

    Represents a rational actor with preferences, strategies, and goals.
    """
    persona_id: str
    name: str
    role: PlayerRole

    # FIBO Agent characteristics
    agent_type: str = "autonomous_agent"  # FIBO FND-AAP

    # Strategic preferences
    risk_tolerance: float = 0.5  # 0.0 = risk-averse, 1.0 = risk-seeking
    time_preference: float = 0.5  # 0.0 = short-term, 1.0 = long-term
    cooperation_tendency: float = 0.5  # 0.0 = competitive, 1.0 = cooperative

    # Utility function parameters
    utility_function: str = "linear"  # linear, logarithmic, exponential
    discount_rate: float = 0.05  # For time-discounted payoffs

    # Decision-making parameters
    information_level: str = "complete"  # complete, incomplete, asymmetric
    rationality: str = "bounded"  # perfect, bounded, behavioral

    # Goals and constraints
    goals: List[str] = field(default_factory=list)
    constraints: List[Dict[str, Any]] = field(default_factory=list)

    # Strategic repertoire
    available_strategies: List[str] = field(default_factory=list)
    preferred_strategy: Optional[str] = None

    # Historical behavior
    past_actions: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_rdf_graph(self) -> RDFGraph:
        """Convert persona to FIBO Agent RDF graph."""
        graph = RDFGraph(uri=self.persona_id)

        # FIBO Agent type
        graph.add_triple(
            self.persona_id,
            f"{Namespace.RDF}type",
            f"{FIBONamespace.FND_AAP}AutonomousAgent"
        )

        graph.add_triple(
            self.persona_id,
            f"{Namespace.FOAF}name",
            self.name,
            f"{Namespace.XSD}string"
        )

        graph.add_triple(
            self.persona_id,
            f"{FIBONamespace.FND_REL}hasRole",
            self.role.value,
            f"{Namespace.XSD}string"
        )

        # Strategic parameters
        graph.add_triple(
            self.persona_id,
            f"{Namespace.SINGINE}riskTolerance",
            str(self.risk_tolerance),
            f"{Namespace.XSD}float"
        )

        graph.add_triple(
            self.persona_id,
            f"{Namespace.SINGINE}cooperationTendency",
            str(self.cooperation_tendency),
            f"{Namespace.XSD}float"
        )

        return graph


@dataclass
class GameTheoreticScenario:
    """
    Game-theoretic scenario for contract analysis.

    Models strategic interactions between personas with payoffs.
    """
    scenario_id: str
    name: str
    description: str

    # Players (personas)
    players: List[Persona] = field(default_factory=list)

    # Game structure
    game_type: str = "simultaneous"  # simultaneous, sequential, repeated
    information_structure: str = "complete"  # complete, incomplete
    num_periods: int = 1  # For repeated games

    # Strategy space
    strategy_profile: Dict[str, str] = field(default_factory=dict)  # persona_id -> strategy

    # Payoff matrix
    payoffs: Dict[str, Dict[str, float]] = field(default_factory=dict)  # player -> strategy -> payoff

    # Equilibrium analysis
    nash_equilibria: List[Dict[str, str]] = field(default_factory=list)
    pareto_optimal_outcomes: List[Dict[str, Any]] = field(default_factory=list)

    # Contract reference
    contract_id: Optional[str] = None

    # Temporal dynamics
    start_time: DateTime = field(default_factory=pendulum.now)
    end_time: Optional[DateTime] = None

    # Hypothetical conditions
    assumptions: List[str] = field(default_factory=list)
    constraints: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_player(self, persona: Persona):
        """Add a player to the game."""
        self.players.append(persona)

    def set_payoff(self, player_id: str, strategy: str, payoff: float):
        """Set payoff for a player's strategy."""
        if player_id not in self.payoffs:
            self.payoffs[player_id] = {}
        self.payoffs[player_id][strategy] = payoff

    def compute_nash_equilibrium(self) -> List[Dict[str, str]]:
        """
        Compute Nash equilibrium (simplified).

        In practice, this would use proper game theory algorithms.
        """
        # Placeholder for Nash equilibrium computation
        # Would integrate with actual game theory solver
        return self.nash_equilibria

    def to_rdf_graph(self) -> RDFGraph:
        """Convert scenario to RDF graph."""
        graph = RDFGraph(uri=self.scenario_id)

        # Type declaration
        graph.add_triple(
            self.scenario_id,
            f"{Namespace.RDF}type",
            f"{Namespace.SINGINE}GameTheoreticScenario"
        )

        graph.add_triple(
            self.scenario_id,
            f"{Namespace.DCTERMS}title",
            self.name,
            f"{Namespace.XSD}string"
        )

        graph.add_triple(
            self.scenario_id,
            f"{Namespace.DCTERMS}description",
            self.description,
            f"{Namespace.XSD}string"
        )

        # Link players
        for player in self.players:
            graph.add_triple(
                self.scenario_id,
                f"{Namespace.SINGINE}hasPlayer",
                player.persona_id
            )

        # Game structure
        graph.add_triple(
            self.scenario_id,
            f"{Namespace.SINGINE}gameType",
            self.game_type,
            f"{Namespace.XSD}string"
        )

        return graph


# ============================================================================
# FIBO Contract Extensions
# ============================================================================

@dataclass
class FIBOFinancialContract:
    """
    Financial contract following FIBO ontology.

    Maps to FIBO FND-AGR Contract.
    """
    contract_id: str
    contract_type: str  # loan, bond, derivative, equity, etc.

    # FIBO Contract parties
    parties: List[Persona] = field(default_factory=list)

    # Financial terms
    principal_amount: Optional[float] = None
    currency: str = "USD"
    interest_rate: Optional[float] = None
    maturity_date: Optional[DateTime] = None

    # FIBO Dates
    effective_date: DateTime = field(default_factory=pendulum.now)
    termination_date: Optional[DateTime] = None

    # Covenants and conditions
    covenants: List[Dict[str, Any]] = field(default_factory=list)
    conditions_precedent: List[str] = field(default_factory=list)

    # Risk factors
    credit_risk: Optional[float] = None
    market_risk: Optional[float] = None
    operational_risk: Optional[float] = None

    # Payoff structure (for game theory)
    payoff_function: Optional[str] = None  # Mathematical expression

    # Linked scenarios
    scenarios: List[str] = field(default_factory=list)  # Scenario IDs

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_rdf_graph(self) -> RDFGraph:
        """Convert to FIBO Contract RDF graph."""
        graph = RDFGraph(uri=self.contract_id)

        # FIBO Contract type
        graph.add_triple(
            self.contract_id,
            f"{Namespace.RDF}type",
            f"{FIBONamespace.FND_AGR}Contract"
        )

        graph.add_triple(
            self.contract_id,
            f"{Namespace.DCTERMS}type",
            self.contract_type,
            f"{Namespace.XSD}string"
        )

        # Financial terms
        if self.principal_amount is not None:
            graph.add_triple(
                self.contract_id,
                f"{Namespace.SINGINE}principalAmount",
                str(self.principal_amount),
                f"{Namespace.XSD}float"
            )

        graph.add_triple(
            self.contract_id,
            f"{Namespace.SINGINE}currency",
            self.currency,
            f"{Namespace.XSD}string"
        )

        # FIBO Dates
        graph.add_triple(
            self.contract_id,
            f"{FIBONamespace.FND_DT}hasEffectiveDate",
            self.effective_date.isoformat(),
            f"{Namespace.XSD}dateTime"
        )

        if self.maturity_date:
            graph.add_triple(
                self.contract_id,
                f"{FIBONamespace.FND_DT}hasMaturityDate",
                self.maturity_date.isoformat(),
                f"{Namespace.XSD}dateTime"
            )

        # Parties
        for party in self.parties:
            graph.add_triple(
                self.contract_id,
                f"{FIBONamespace.FND_AGR}hasContractParty",
                party.persona_id
            )

        return graph


# ============================================================================
# FIBO-based Scenario Builder
# ============================================================================

class FIBOScenarioBuilder:
    """
    Builder for creating FIBO-compliant financial scenarios with game theory.

    Usage:
        scenario = (FIBOScenarioBuilder()
            .with_name("Bond Issuance Negotiation")
            .add_persona(issuer_persona)
            .add_persona(investor_persona)
            .set_game_type("sequential")
            .with_contract(bond_contract)
            .build())
    """

    def __init__(self):
        self.scenario_id = f"scenario-{pendulum.now().format('YYYYMMDDHHmmss')}"
        self.name = ""
        self.description = ""
        self.personas: List[Persona] = []
        self.game_type = "simultaneous"
        self.contract_id: Optional[str] = None
        self.payoffs: Dict[str, Dict[str, float]] = {}
        self.assumptions: List[str] = []

    def with_name(self, name: str) -> 'FIBOScenarioBuilder':
        """Set scenario name."""
        self.name = name
        return self

    def with_description(self, description: str) -> 'FIBOScenarioBuilder':
        """Set scenario description."""
        self.description = description
        return self

    def add_persona(
        self,
        name: str,
        role: PlayerRole,
        risk_tolerance: float = 0.5,
        cooperation_tendency: float = 0.5
    ) -> 'FIBOScenarioBuilder':
        """Add a persona to the scenario."""
        persona = Persona(
            persona_id=f"persona-{role.value}-{len(self.personas)}",
            name=name,
            role=role,
            risk_tolerance=risk_tolerance,
            cooperation_tendency=cooperation_tendency
        )
        self.personas.append(persona)
        return self

    def set_game_type(self, game_type: str) -> 'FIBOScenarioBuilder':
        """Set game type (simultaneous, sequential, repeated)."""
        self.game_type = game_type
        return self

    def with_contract(self, contract_id: str) -> 'FIBOScenarioBuilder':
        """Link to a financial contract."""
        self.contract_id = contract_id
        return self

    def set_payoff(self, player_idx: int, strategy: str, payoff: float) -> 'FIBOScenarioBuilder':
        """Set payoff for a player's strategy."""
        if player_idx >= len(self.personas):
            raise ValueError(f"Player index {player_idx} out of range")

        player_id = self.personas[player_idx].persona_id
        if player_id not in self.payoffs:
            self.payoffs[player_id] = {}
        self.payoffs[player_id][strategy] = payoff
        return self

    def with_assumption(self, assumption: str) -> 'FIBOScenarioBuilder':
        """Add an assumption to the scenario."""
        self.assumptions.append(assumption)
        return self

    def build(self) -> GameTheoreticScenario:
        """Build the scenario."""
        return GameTheoreticScenario(
            scenario_id=self.scenario_id,
            name=self.name,
            description=self.description,
            players=self.personas,
            game_type=self.game_type,
            contract_id=self.contract_id,
            payoffs=self.payoffs,
            assumptions=self.assumptions
        )


# ============================================================================
# Intent with FIBO Persona
# ============================================================================

@dataclass
class PersonaIntent:
    """
    Intent from a FIBO persona's perspective.

    Combines intent-based authorization with game-theoretic persona modeling.
    """
    intent_id: str
    persona: Persona
    intent_statement: str

    # Strategic context
    strategy: StrategyType = StrategyType.COOPERATIVE
    expected_payoff: Optional[float] = None
    payoff_type: PayoffType = PayoffType.UTILITY

    # Temporal scope
    valid_from: DateTime = field(default_factory=pendulum.now)
    valid_until: Optional[DateTime] = None

    # Approval
    is_approved: bool = False
    approved_by: List[str] = field(default_factory=list)

    # Dependencies
    requires_intents: List[str] = field(default_factory=list)  # Other intent IDs
    conflicts_with: List[str] = field(default_factory=list)  # Conflicting intent IDs

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_rdf_graph(self) -> RDFGraph:
        """Convert to RDF graph combining FIBO and Singine ontologies."""
        graph = RDFGraph(uri=self.intent_id)

        # Type declarations
        graph.add_triple(
            self.intent_id,
            f"{Namespace.RDF}type",
            f"{Namespace.SINGINE}Intent"
        )

        graph.add_triple(
            self.intent_id,
            f"{Namespace.RDF}type",
            f"{FIBONamespace.FND_AAP}AgentIntent"
        )

        # Link to persona
        graph.add_triple(
            self.intent_id,
            f"{Namespace.PROV}wasAttributedTo",
            self.persona.persona_id
        )

        # Intent statement
        graph.add_triple(
            self.intent_id,
            f"{Namespace.DCTERMS}description",
            self.intent_statement,
            f"{Namespace.XSD}string"
        )

        # Strategy
        graph.add_triple(
            self.intent_id,
            f"{Namespace.SINGINE}strategy",
            self.strategy.value,
            f"{Namespace.XSD}string"
        )

        if self.expected_payoff is not None:
            graph.add_triple(
                self.intent_id,
                f"{Namespace.SINGINE}expectedPayoff",
                str(self.expected_payoff),
                f"{Namespace.XSD}float"
            )

        return graph
