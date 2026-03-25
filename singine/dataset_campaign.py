"""Governed dataset campaign planning for contract- and realm-driven work."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


DEFAULT_TITLE = "Contract-Linked Dataset Campaign"
DEFAULT_SUMMARY = (
    "Create a governed collection of datasets phased by direct and indirect "
    "standards pressure from active contracts and active contacts."
)

DEFAULT_STANDARDS_PHASES = [
    {
        "phase": "phase-1-foundation",
        "focus": "direct-contract-standards",
        "description": "Capture the minimum vocabulary, contract parties, and obligations required by active contracts.",
        "driven_by": ["active_contracts", "business_terms", "data_governance"],
    },
    {
        "phase": "phase-2-alignment",
        "focus": "indirect-ecosystem-standards",
        "description": "Align datasets to common vocabulary, stewardship, interoperability, and external collaboration expectations.",
        "driven_by": ["active_contacts", "reference_data", "collibra_bridge"],
    },
    {
        "phase": "phase-3-evidence",
        "focus": "scientific-and-operational-traceability",
        "description": "Attach evidence, lineage, and domain-specific traceability for health, molecular biology, and imaging work.",
        "driven_by": ["trusted_realms", "evidence_model", "lineage"],
    },
]

DEFAULT_VOCABULARY = [
    {"term": "active contract", "kind": "business-term", "definition": "Current agreement that directly shapes dataset scope, access, retention, or evidence obligations."},
    {"term": "active contact", "kind": "business-term", "definition": "Current stakeholder or collaborator linked to one or more active contracts or delivery paths."},
    {"term": "common vocabulary", "kind": "business-term", "definition": "Shared glossary spanning business, technical, and scientific concepts."},
    {"term": "trusted realm", "kind": "business-term", "definition": "Domain or environment approved as a governed source, steward, or dissemination boundary."},
    {"term": "dataset standard phase", "kind": "business-term", "definition": "Named stage describing how strongly a standard constrains a dataset at a given time."},
    {"term": "molecular traceability", "kind": "business-term", "definition": "Ability to link biological statements back to evidence, method, and imaging source."},
    {"term": "functional medicine", "kind": "business-term", "definition": "Clinical framing used here as a domain vocabulary source for health-oriented datasets."},
    {"term": "functional programming statement", "kind": "business-term", "definition": "Deterministic expression of domain statements suitable for reproducible data transformation."},
]

DEFAULT_DATASET_BLUEPRINTS = [
    {
        "dataset_id": "contract-obligation-register",
        "name": "Contract Obligation Register",
        "domain_type": "Policies",
        "asset_type": "Policy",
        "description": "Maps active contracts to obligations, rights, dataset scope, and delivery phases.",
        "required_vocabulary": ["active contract", "dataset standard phase", "common vocabulary"],
        "primary_phase": "phase-1-foundation",
    },
    {
        "dataset_id": "contact-contract-network",
        "name": "Contact and Contract Network",
        "domain_type": "Reference Data",
        "asset_type": "Business Asset",
        "description": "Connects contacts, contracts, organisations, and stewardship roles to show how the business links to the wider organisation.",
        "required_vocabulary": ["active contract", "active contact", "common vocabulary"],
        "primary_phase": "phase-1-foundation",
    },
    {
        "dataset_id": "governance-glossary",
        "name": "Governance Glossary",
        "domain_type": "Glossary",
        "asset_type": "Business Term",
        "description": "Defines the common vocabulary across governance, AI/LLM/MLOps, health, and scientific domains.",
        "required_vocabulary": ["common vocabulary", "functional medicine", "functional programming statement"],
        "primary_phase": "phase-2-alignment",
    },
    {
        "dataset_id": "dataset-standards-crosswalk",
        "name": "Dataset Standards Crosswalk",
        "domain_type": "Reference Data",
        "asset_type": "Standard",
        "description": "Tracks which standards apply directly or indirectly to each dataset and when each phase becomes active.",
        "required_vocabulary": ["dataset standard phase", "common vocabulary"],
        "primary_phase": "phase-2-alignment",
    },
    {
        "dataset_id": "trusted-realm-registry",
        "name": "Trusted Realm Registry",
        "domain_type": "Reference Data",
        "asset_type": "Technology Asset",
        "description": "Registers trusted source and dissemination realms, including evidence about trust posture and usage constraints.",
        "required_vocabulary": ["trusted realm", "common vocabulary"],
        "primary_phase": "phase-2-alignment",
    },
    {
        "dataset_id": "molecular-statement-catalog",
        "name": "Molecular Statement Catalog",
        "domain_type": "Logical Data Dictionary",
        "asset_type": "Data Element",
        "description": "Captures functional-programming-friendly statements for molecular biology with explicit evidence hooks.",
        "required_vocabulary": ["molecular traceability", "functional programming statement"],
        "primary_phase": "phase-3-evidence",
    },
    {
        "dataset_id": "imaging-evidence-lineage",
        "name": "Imaging Evidence Lineage",
        "domain_type": "Physical Data Dictionary",
        "asset_type": "Data Asset",
        "description": "Links imaging artefacts, assays, observations, and publication paths back to a trusted source realm.",
        "required_vocabulary": ["trusted realm", "molecular traceability"],
        "primary_phase": "phase-3-evidence",
    },
]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _dedupe(values: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(cleaned)
    return ordered


def _domain_tags(brief: str) -> List[str]:
    lowered = brief.lower()
    tags = []
    for keyword, tag in [
        ("collibra", "collibra"),
        ("llm", "ai-llm"),
        ("mlops", "ai-mlops"),
        ("health", "health"),
        ("functional medicine", "functional-medicine"),
        ("functional programming", "functional-programming"),
        ("molecular", "molecular-biology"),
        ("imaging", "molecular-imaging"),
    ]:
        if keyword in lowered:
            tags.append(tag)
    return _dedupe(tags)


def _campaign_vocabulary(extra_terms: Sequence[str]) -> List[Dict[str, str]]:
    vocabulary = deepcopy(DEFAULT_VOCABULARY)
    for term in _dedupe(extra_terms):
        vocabulary.append(
            {
                "term": term,
                "kind": "campaign-term",
                "definition": "Campaign-specific term captured from the launch brief or operator input.",
            }
        )
    return vocabulary


def _dataset_entries(
    *,
    active_contracts: Sequence[str],
    active_contacts: Sequence[str],
    trusted_realms: Sequence[str],
    brief: str,
) -> List[Dict[str, Any]]:
    domain_tags = _domain_tags(brief)
    datasets: List[Dict[str, Any]] = []
    for blueprint in DEFAULT_DATASET_BLUEPRINTS:
        dataset = deepcopy(blueprint)
        dataset["contracts_in_scope"] = list(active_contracts)
        dataset["contacts_in_scope"] = list(active_contacts)
        dataset["trusted_realms"] = list(trusted_realms)
        dataset["tags"] = domain_tags
        dataset["collection_path"] = f"campaign/{dataset['dataset_id']}"
        dataset["governance_questions"] = [
            "Which active contracts make this dataset mandatory?",
            "Which active contacts are accountable for stewardship?",
            "Which vocabulary terms must be standardised before publication?",
            "Which trusted realms may source or receive the data?",
        ]
        datasets.append(dataset)
    return datasets


def launch_dataset_campaign(
    *,
    brief: str,
    title: str = DEFAULT_TITLE,
    active_contracts: Optional[Sequence[str]] = None,
    active_contacts: Optional[Sequence[str]] = None,
    trusted_realms: Optional[Sequence[str]] = None,
    vocabulary_terms: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    contracts = _dedupe(active_contracts or [])
    contacts = _dedupe(active_contacts or [])
    realms = _dedupe([*(trusted_realms or []), "molecularimaging.be"])
    extra_terms = _dedupe(vocabulary_terms or [])

    summary = DEFAULT_SUMMARY
    if brief.strip():
        summary = brief.strip()

    return {
        "campaign_id": f"campaign-{_slug(title or DEFAULT_TITLE)}",
        "title": title or DEFAULT_TITLE,
        "summary": summary,
        "brief": brief.strip(),
        "governance_position": {
            "core_source": "singine-core",
            "campaign_type": "dataset-collection",
            "collibra_alignment": "common-vocabulary-and-crosswalk-first",
            "trusted_realm_default": "molecularimaging.be",
        },
        "scope": {
            "active_contracts": contracts,
            "active_contacts": contacts,
            "trusted_realms": realms,
        },
        "standards_phases": deepcopy(DEFAULT_STANDARDS_PHASES),
        "common_vocabulary": _campaign_vocabulary(extra_terms),
        "datasets": _dataset_entries(
            active_contracts=contracts,
            active_contacts=contacts,
            trusted_realms=realms,
            brief=brief,
        ),
    }


def write_campaign(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
