"""
RDF/OWL Ontology Layer for Singine Collibra Integration.

This module provides semantic web standard mappings (RDF, OWL, DCAT, PROV)
for the Singine contract model, enabling cross-system contract execution
with intent-based authorization.

Foundations:
- RDF (Resource Description Framework) for graph representation
- OWL (Web Ontology Language) for formal semantics
- DCAT (Data Catalog Vocabulary) for dataset metadata
- PROV (Provenance Ontology) for execution tracking
- Mathematical dependencies from ir2008 (Belgian engineering algebra/calculus)

Design:
- Contracts as executable RDF graphs
- Intent-based authorization using ODRL (Open Digital Rights Language)
- Cross-system execution via linked data principles
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Set
from datetime import datetime
from enum import Enum
import pendulum
from pendulum import DateTime
import json

from .contract_model import (
    Contract, Party, Term, Commitment, Privilege,
    CommitmentStatus, PrivilegeStatus, TermType
)
from .collibra_translator import (
    CollibraAccessRequest, TemporalConstraint, TerritorialConstraint
)


# ============================================================================
# RDF/OWL Namespace Definitions
# ============================================================================

class Namespace:
    """Standard semantic web namespaces plus custom Singine namespace."""

    # W3C Standards
    RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    RDFS = "http://www.w3.org/2000/01/rdf-schema#"
    OWL = "http://www.w3.org/2002/07/owl#"
    XSD = "http://www.w3.org/2001/XMLSchema#"

    # Data & Provenance
    DCAT = "http://www.w3.org/ns/dcat#"
    PROV = "http://www.w3.org/ns/prov#"
    DCTERMS = "http://purl.org/dc/terms/"
    FOAF = "http://xmlns.com/foaf/0.1/"

    # Rights & Policies
    ODRL = "http://www.w3.org/ns/odrl/2/"
    VCARD = "http://www.w3.org/2006/vcard/ns#"

    # Time & Location
    TIME = "http://www.w3.org/2006/time#"
    GEO = "http://www.w3.org/2003/01/geo/wgs84_pos#"
    SCHEMA = "http://schema.org/"

    # Singine Custom
    SINGINE = "http://singine.io/ontology#"
    IR2008 = "http://ir2008.be/engineering#"  # Belgian engineering initiative

    # Collibra Custom (for edge server)
    COLLIBRA = "http://collibra.com/semantics#"


# ============================================================================
# OWL Class Definitions
# ============================================================================

class SingineOWLClass(Enum):
    """OWL class URIs for Singine entities."""

    # Core Contract Classes
    CONTRACT = f"{Namespace.SINGINE}Contract"
    PARTY = f"{Namespace.SINGINE}Party"
    TERM = f"{Namespace.SINGINE}Term"
    COMMITMENT = f"{Namespace.SINGINE}Commitment"
    PRIVILEGE = f"{Namespace.SINGINE}Privilege"

    # Temporal Classes
    TEMPORAL_CONSTRAINT = f"{Namespace.SINGINE}TemporalConstraint"
    TEMPORAL_EXPRESSION = f"{Namespace.SINGINE}TemporalExpression"
    TEMPORAL_INTERVAL = f"{Namespace.TIME}Interval"

    # Territorial Classes
    TERRITORIAL_CONSTRAINT = f"{Namespace.SINGINE}TerritorialConstraint"
    LOCATION = f"{Namespace.SCHEMA}Place"
    ORGANIZATION = f"{Namespace.SCHEMA}Organization"

    # Intent & Authorization
    INTENT = f"{Namespace.SINGINE}Intent"
    AUTHORIZATION = f"{Namespace.SINGINE}Authorization"
    EXECUTION_CONTEXT = f"{Namespace.SINGINE}ExecutionContext"

    # Data Access
    ACCESS_REQUEST = f"{Namespace.COLLIBRA}AccessRequest"
    DATA_ASSET = f"{Namespace.DCAT}Dataset"
    DATA_CATALOG = f"{Namespace.DCAT}Catalog"

    # Mathematical Dependencies (ir2008)
    MATHEMATICAL_PROBLEM = f"{Namespace.IR2008}Problem"
    ALGEBRAIC_CONSTRAINT = f"{Namespace.IR2008}AlgebraicConstraint"
    CALCULUS_DEPENDENCY = f"{Namespace.IR2008}CalculusDependency"


class SingineOWLProperty(Enum):
    """OWL property URIs for Singine relationships."""

    # Contract Relations
    HAS_PARTY = f"{Namespace.SINGINE}hasParty"
    HAS_TERM = f"{Namespace.SINGINE}hasTerm"
    HAS_COMMITMENT = f"{Namespace.SINGINE}hasCommitment"
    HAS_PRIVILEGE = f"{Namespace.SINGINE}hasPrivilege"

    # Temporal Relations
    HAS_TEMPORAL_CONSTRAINT = f"{Namespace.SINGINE}hasTemporalConstraint"
    HAS_START_DATE = f"{Namespace.TIME}hasBeginning"
    HAS_END_DATE = f"{Namespace.TIME}hasEnd"
    HAS_DURATION = f"{Namespace.TIME}hasDuration"

    # Territorial Relations
    HAS_TERRITORIAL_CONSTRAINT = f"{Namespace.SINGINE}hasTerritorialConstraint"
    HAS_LOCATION = f"{Namespace.SCHEMA}location"
    IN_REGION = f"{Namespace.SCHEMA}containedInPlace"

    # Intent & Authorization
    HAS_INTENT = f"{Namespace.SINGINE}hasIntent"
    AUTHORIZED_BY = f"{Namespace.SINGINE}authorizedBy"
    EXECUTES_ON = f"{Namespace.SINGINE}executesOn"
    REQUIRES_APPROVAL = f"{Namespace.SINGINE}requiresApproval"

    # ODRL Policy Relations
    HAS_POLICY = f"{Namespace.ODRL}hasPolicy"
    HAS_PERMISSION = f"{Namespace.ODRL}permission"
    HAS_PROHIBITION = f"{Namespace.ODRL}prohibition"
    HAS_OBLIGATION = f"{Namespace.ODRL}obligation"

    # Provenance
    WAS_GENERATED_BY = f"{Namespace.PROV}wasGeneratedBy"
    WAS_ATTRIBUTED_TO = f"{Namespace.PROV}wasAttributedTo"
    USED = f"{Namespace.PROV}used"

    # Mathematical Dependencies (ir2008)
    DEPENDS_ON_SOLUTION = f"{Namespace.IR2008}dependsOnSolution"
    SATISFIES_CONSTRAINT = f"{Namespace.IR2008}satisfiesConstraint"


# ============================================================================
# RDF Triple Representation
# ============================================================================

@dataclass
class RDFTriple:
    """An RDF triple (subject, predicate, object)."""
    subject: str  # URI
    predicate: str  # URI
    object: str  # URI or literal
    object_type: Optional[str] = None  # XSD type for literals

    def to_ntriples(self) -> str:
        """Serialize to N-Triples format."""
        obj = f'"{self.object}"' if self.object_type else f'<{self.object}>'
        if self.object_type:
            obj += f"^^<{self.object_type}>"
        return f"<{self.subject}> <{self.predicate}> {obj} ."

    def to_turtle_snippet(self) -> str:
        """Serialize to Turtle format (single line)."""
        obj = f'"{self.object}"' if self.object_type else f'<{self.object}>'
        if self.object_type:
            obj += f"^^<{self.object_type}>"
        return f"  {self._short_uri(self.predicate)} {obj} ;"

    @staticmethod
    def _short_uri(uri: str) -> str:
        """Shorten URI using namespace prefixes."""
        for attr in dir(Namespace):
            if not attr.startswith('_'):
                ns_uri = getattr(Namespace, attr)
                if uri.startswith(ns_uri):
                    return f"{attr.lower()}:{uri[len(ns_uri):]}"
        return f"<{uri}>"


@dataclass
class RDFGraph:
    """A collection of RDF triples forming a graph."""
    uri: str
    triples: List[RDFTriple] = field(default_factory=list)
    namespaces: Dict[str, str] = field(default_factory=dict)

    def add_triple(self, subject: str, predicate: str, obj: str, obj_type: Optional[str] = None):
        """Add a triple to the graph."""
        self.triples.append(RDFTriple(subject, predicate, obj, obj_type))

    def to_turtle(self) -> str:
        """Serialize entire graph to Turtle format."""
        # Namespace declarations
        prefixes = []
        for attr in dir(Namespace):
            if not attr.startswith('_'):
                ns_uri = getattr(Namespace, attr)
                prefixes.append(f"@prefix {attr.lower()}: <{ns_uri}> .")

        # Triples
        turtle = "\n".join(prefixes) + "\n\n"
        for triple in self.triples:
            turtle += triple.to_ntriples() + "\n"

        return turtle

    def to_json_ld(self) -> Dict[str, Any]:
        """Serialize to JSON-LD format."""
        context = {attr.lower(): getattr(Namespace, attr)
                   for attr in dir(Namespace) if not attr.startswith('_')}

        graph = []
        for triple in self.triples:
            graph.append({
                "@id": triple.subject,
                triple.predicate: {
                    "@id": triple.object if not triple.object_type else None,
                    "@value": triple.object if triple.object_type else None,
                    "@type": triple.object_type
                }
            })

        return {
            "@context": context,
            "@graph": graph
        }


# ============================================================================
# Intent-Based Authorization
# ============================================================================

@dataclass
class Intent:
    """
    User intent for cross-system contract execution.

    This represents the minimal requirement: an approved intent.
    """
    intent_id: str
    citizen_id: str
    citizen_name: str

    # Intent description in natural language
    intent_statement: str

    # Temporal scope of intent
    temporal_scope: Optional[TemporalConstraint] = None

    # Territorial scope of intent
    territorial_scope: Optional[TerritorialConstraint] = None

    # What the intent aims to accomplish
    goal: str = ""
    reasoning: str = ""

    # Approval status
    is_approved: bool = False
    approved_by: List[str] = field(default_factory=list)
    approved_date: Optional[DateTime] = None

    # Execution constraints
    max_executions: Optional[int] = None
    execution_count: int = 0

    # Mathematical dependencies (ir2008)
    depends_on_problems: List[str] = field(default_factory=list)
    algebraic_constraints: List[Dict[str, Any]] = field(default_factory=list)
    calculus_dependencies: List[Dict[str, Any]] = field(default_factory=list)

    # RDF metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_rdf_graph(self) -> RDFGraph:
        """Convert intent to RDF graph."""
        graph = RDFGraph(uri=self.intent_id)

        # Type declaration
        graph.add_triple(
            self.intent_id,
            f"{Namespace.RDF}type",
            SingineOWLClass.INTENT.value
        )

        # Basic properties
        graph.add_triple(
            self.intent_id,
            f"{Namespace.DCTERMS}description",
            self.intent_statement,
            f"{Namespace.XSD}string"
        )

        graph.add_triple(
            self.intent_id,
            f"{Namespace.SINGINE}citizenId",
            self.citizen_id,
            f"{Namespace.XSD}string"
        )

        graph.add_triple(
            self.intent_id,
            f"{Namespace.SINGINE}goal",
            self.goal,
            f"{Namespace.XSD}string"
        )

        # Approval status
        graph.add_triple(
            self.intent_id,
            f"{Namespace.SINGINE}isApproved",
            str(self.is_approved).lower(),
            f"{Namespace.XSD}boolean"
        )

        if self.approved_date:
            graph.add_triple(
                self.intent_id,
                f"{Namespace.SINGINE}approvedDate",
                self.approved_date.isoformat(),
                f"{Namespace.XSD}dateTime"
            )

        # Mathematical dependencies (ir2008)
        for problem_id in self.depends_on_problems:
            graph.add_triple(
                self.intent_id,
                SingineOWLProperty.DEPENDS_ON_SOLUTION.value,
                problem_id
            )

        return graph


@dataclass
class ExecutionContext:
    """
    Context for cross-system contract execution.

    This tracks the execution of a contract across multiple systems
    based on an approved intent.
    """
    execution_id: str
    intent_id: str
    contract_id: str

    # Execution metadata
    started_at: DateTime = field(default_factory=pendulum.now)
    completed_at: Optional[DateTime] = None
    status: str = "pending"  # pending, executing, completed, failed

    # Target systems
    target_systems: List[str] = field(default_factory=list)

    # Execution trace (provenance)
    execution_steps: List[Dict[str, Any]] = field(default_factory=list)

    # Results
    outputs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_rdf_graph(self) -> RDFGraph:
        """Convert execution context to RDF graph with PROV ontology."""
        graph = RDFGraph(uri=self.execution_id)

        # Type declaration
        graph.add_triple(
            self.execution_id,
            f"{Namespace.RDF}type",
            SingineOWLClass.EXECUTION_CONTEXT.value
        )

        graph.add_triple(
            self.execution_id,
            f"{Namespace.RDF}type",
            f"{Namespace.PROV}Activity"
        )

        # Link to intent
        graph.add_triple(
            self.execution_id,
            SingineOWLProperty.HAS_INTENT.value,
            self.intent_id
        )

        # Temporal bounds
        graph.add_triple(
            self.execution_id,
            f"{Namespace.PROV}startedAtTime",
            self.started_at.isoformat(),
            f"{Namespace.XSD}dateTime"
        )

        if self.completed_at:
            graph.add_triple(
                self.execution_id,
                f"{Namespace.PROV}endedAtTime",
                self.completed_at.isoformat(),
                f"{Namespace.XSD}dateTime"
            )

        # Status
        graph.add_triple(
            self.execution_id,
            f"{Namespace.SINGINE}executionStatus",
            self.status,
            f"{Namespace.XSD}string"
        )

        # Outputs (provenance)
        for output in self.outputs:
            graph.add_triple(
                self.execution_id,
                f"{Namespace.PROV}generated",
                output
            )

        return graph


# ============================================================================
# RDF Translator for Singine → Semantic Web
# ============================================================================

class RDFTranslator:
    """
    Translate Singine contracts and Collibra access requests to RDF graphs
    conforming to W3C semantic web standards (RDF, OWL, DCAT, PROV, ODRL).
    """

    def __init__(self):
        self.base_uri = Namespace.SINGINE

    def contract_to_rdf(self, contract: Contract) -> RDFGraph:
        """Convert a Singine contract to an RDF graph."""
        graph = RDFGraph(uri=contract.contract_id)

        # Type declaration
        graph.add_triple(
            contract.contract_id,
            f"{Namespace.RDF}type",
            SingineOWLClass.CONTRACT.value
        )

        # Basic properties
        graph.add_triple(
            contract.contract_id,
            f"{Namespace.DCTERMS}title",
            contract.name,
            f"{Namespace.XSD}string"
        )

        graph.add_triple(
            contract.contract_id,
            f"{Namespace.DCTERMS}type",
            contract.contract_type,
            f"{Namespace.XSD}string"
        )

        # Temporal properties
        graph.add_triple(
            contract.contract_id,
            SingineOWLProperty.HAS_START_DATE.value,
            contract.start_date.isoformat(),
            f"{Namespace.XSD}dateTime"
        )

        if contract.end_date:
            graph.add_triple(
                contract.contract_id,
                SingineOWLProperty.HAS_END_DATE.value,
                contract.end_date.isoformat(),
                f"{Namespace.XSD}dateTime"
            )

        # Parties
        for party in contract.parties:
            party_uri = f"{self.base_uri}{party.party_id}"
            graph.add_triple(
                contract.contract_id,
                SingineOWLProperty.HAS_PARTY.value,
                party_uri
            )
            self._add_party_triples(graph, party, party_uri)

        # Terms as ODRL policies
        for term in contract.terms:
            term_uri = f"{self.base_uri}{term.term_id}"
            graph.add_triple(
                contract.contract_id,
                SingineOWLProperty.HAS_TERM.value,
                term_uri
            )
            self._add_term_triples(graph, term, term_uri)

        # Commitments as ODRL obligations
        for commitment in contract.commitments:
            comm_uri = f"{self.base_uri}{commitment.commitment_id}"
            graph.add_triple(
                contract.contract_id,
                SingineOWLProperty.HAS_COMMITMENT.value,
                comm_uri
            )
            self._add_commitment_triples(graph, commitment, comm_uri)

        # Privileges as ODRL permissions
        for privilege in contract.privileges:
            priv_uri = f"{self.base_uri}{privilege.privilege_id}"
            graph.add_triple(
                contract.contract_id,
                SingineOWLProperty.HAS_PRIVILEGE.value,
                priv_uri
            )
            self._add_privilege_triples(graph, privilege, priv_uri)

        return graph

    def _add_party_triples(self, graph: RDFGraph, party: Party, uri: str):
        """Add RDF triples for a party using FOAF."""
        graph.add_triple(uri, f"{Namespace.RDF}type", SingineOWLClass.PARTY.value)
        graph.add_triple(uri, f"{Namespace.FOAF}name", party.name, f"{Namespace.XSD}string")
        graph.add_triple(uri, f"{Namespace.SCHEMA}roleName", party.role, f"{Namespace.XSD}string")

    def _add_term_triples(self, graph: RDFGraph, term: Term, uri: str):
        """Add RDF triples for a term using ODRL."""
        graph.add_triple(uri, f"{Namespace.RDF}type", SingineOWLClass.TERM.value)
        graph.add_triple(uri, f"{Namespace.RDF}type", f"{Namespace.ODRL}Policy")
        graph.add_triple(uri, f"{Namespace.DCTERMS}description", term.description, f"{Namespace.XSD}string")

        if term.start_date:
            graph.add_triple(uri, SingineOWLProperty.HAS_START_DATE.value,
                           term.start_date.isoformat(), f"{Namespace.XSD}dateTime")

    def _add_commitment_triples(self, graph: RDFGraph, commitment: Commitment, uri: str):
        """Add RDF triples for a commitment using ODRL obligation."""
        graph.add_triple(uri, f"{Namespace.RDF}type", SingineOWLClass.COMMITMENT.value)
        graph.add_triple(uri, f"{Namespace.RDF}type", f"{Namespace.ODRL}Duty")
        graph.add_triple(uri, f"{Namespace.DCTERMS}description", commitment.description, f"{Namespace.XSD}string")

        if commitment.due_date:
            graph.add_triple(uri, f"{Namespace.SINGINE}dueDate",
                           commitment.due_date.isoformat(), f"{Namespace.XSD}dateTime")

    def _add_privilege_triples(self, graph: RDFGraph, privilege: Privilege, uri: str):
        """Add RDF triples for a privilege using ODRL permission."""
        graph.add_triple(uri, f"{Namespace.RDF}type", SingineOWLClass.PRIVILEGE.value)
        graph.add_triple(uri, f"{Namespace.RDF}type", f"{Namespace.ODRL}Permission")
        graph.add_triple(uri, f"{Namespace.DCTERMS}description", privilege.description, f"{Namespace.XSD}string")

    def access_request_to_rdf(self, request: CollibraAccessRequest) -> RDFGraph:
        """Convert a Collibra access request to RDF using DCAT."""
        graph = RDFGraph(uri=request.request_id)

        # Type declaration
        graph.add_triple(
            request.request_id,
            f"{Namespace.RDF}type",
            SingineOWLClass.ACCESS_REQUEST.value
        )

        # Citizen (FOAF)
        graph.add_triple(
            request.request_id,
            f"{Namespace.FOAF}member",
            request.citizen_id
        )

        # Purpose
        graph.add_triple(
            request.request_id,
            f"{Namespace.DCTERMS}description",
            request.access_purpose,
            f"{Namespace.XSD}string"
        )

        # Requested assets (DCAT)
        for asset_id in request.requested_assets:
            asset_uri = f"{Namespace.COLLIBRA}{asset_id}"
            graph.add_triple(
                request.request_id,
                f"{Namespace.DCAT}dataset",
                asset_uri
            )

        # Temporal constraints
        for tc in request.temporal_constraints:
            tc_uri = f"{self.base_uri}{tc.constraint_id}"
            graph.add_triple(
                request.request_id,
                SingineOWLProperty.HAS_TEMPORAL_CONSTRAINT.value,
                tc_uri
            )
            self._add_temporal_constraint_triples(graph, tc, tc_uri)

        return graph

    def _add_temporal_constraint_triples(self, graph: RDFGraph, tc: TemporalConstraint, uri: str):
        """Add RDF triples for temporal constraint using TIME ontology."""
        graph.add_triple(uri, f"{Namespace.RDF}type", SingineOWLClass.TEMPORAL_CONSTRAINT.value)
        graph.add_triple(uri, f"{Namespace.RDF}type", f"{Namespace.TIME}Interval")

        if tc.start_date:
            graph.add_triple(uri, SingineOWLProperty.HAS_START_DATE.value,
                           tc.start_date.isoformat(), f"{Namespace.XSD}dateTime")
        if tc.end_date:
            graph.add_triple(uri, SingineOWLProperty.HAS_END_DATE.value,
                           tc.end_date.isoformat(), f"{Namespace.XSD}dateTime")


# ============================================================================
# ir2008 Mathematical Dependencies Integration
# ============================================================================

@dataclass
class IR2008Problem:
    """
    Reference to an ir2008 engineering problem solution.

    ir2008 was a Belgian initiative documenting Brussels' leading
    engineering problems in algebra, calculus, and other mathematical domains.
    """
    problem_id: str
    domain: str  # "algebra", "calculus", "topology", etc.
    description: str
    solution_uri: Optional[str] = None  # Link to documented solution
    constraints: List[Dict[str, Any]] = field(default_factory=list)

    def to_rdf_graph(self) -> RDFGraph:
        """Convert to RDF graph."""
        graph = RDFGraph(uri=self.problem_id)

        graph.add_triple(
            self.problem_id,
            f"{Namespace.RDF}type",
            SingineOWLClass.MATHEMATICAL_PROBLEM.value
        )

        graph.add_triple(
            self.problem_id,
            f"{Namespace.DCTERMS}subject",
            self.domain,
            f"{Namespace.XSD}string"
        )

        graph.add_triple(
            self.problem_id,
            f"{Namespace.DCTERMS}description",
            self.description,
            f"{Namespace.XSD}string"
        )

        if self.solution_uri:
            graph.add_triple(
                self.problem_id,
                f"{Namespace.RDFS}seeAlso",
                self.solution_uri
            )

        return graph
