"""Simple catalog of Singine operations and model objects.

This module intentionally avoids importing the full `singine.lens` package so
the catalog stays runnable on a minimal workstation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List


COLLIBRA_ASSET_TYPES = [
    "Business Asset",
    "Data Asset",
    "Governance Asset",
    "Technology Asset",
    "Issue",
    "Business Capability",
    "Business Process",
    "Business Term",
    "Data Category",
    "Database",
    "Schema",
    "Table",
    "Column",
    "Data Element",
    "Policy",
    "Rule",
    "Standard",
]

COLLIBRA_DOMAIN_TYPES = [
    "Glossary",
    "Physical Data Dictionary",
    "Logical Data Dictionary",
    "Hierarchies",
    "Policies",
    "Reference Data",
]

COLLIBRA_RELATION_TYPES = [
    "groups",
    "grouped by",
    "means",
    "related to",
    "sources from",
    "targets to",
    "governs",
    "governed by",
]


@dataclass
class ModelObject:
    name: str
    family: str
    description: str
    reference: str


def catalog() -> Dict[str, Any]:
    return {
        "bootstrappers": [
            asdict(ModelObject("install", "bootstrapper", "Install the stable singine launcher and manpages.", "singine install")),
            asdict(ModelObject("bridge-build", "bootstrapper", "Build the local bridge database across workspace sources.", "singine bridge build --db /tmp/sqlite.db")),
            asdict(ModelObject("bridge-sources", "bootstrapper", "List active bridge sources, including KnowYourAI when present.", "singine bridge sources --db /tmp/sqlite.db")),
        ],
        "auth_operations": [
            asdict(ModelObject("totp-init", "auth", "Create a local TOTP profile that 1Password or Google Authenticator can import.", "singine auth totp init --account-name you@example.com --state ~/.singine/auth/totp.json")),
            asdict(ModelObject("totp-uri", "auth", "Print the otpauth provisioning URI for manual or QR-based import.", "singine auth totp uri --state ~/.singine/auth/totp.json")),
            asdict(ModelObject("totp-code", "auth", "Show the current one-time code for a local profile.", "singine auth totp code --state ~/.singine/auth/totp.json")),
            asdict(ModelObject("login", "auth", "Verify a TOTP code and treat it as a local Singine login gate.", "singine auth login --state ~/.singine/auth/totp.json --code 123456")),
        ],
        "master_data": [
            asdict(ModelObject("code-table", "master-data", "SQLite key/value layer for Singine bootstrap and governed runtime state.", "core/src/singine/db/code_table.clj")),
            asdict(ModelObject("singine-db", "master-data", "Environment variable that points at the code-table SQLite file.", "SINGINE_DB")),
        ],
        "reference_data": [
            asdict(ModelObject("scenario-codes", "reference-data", "Four-letter scenario codex for Singine scenario IDs.", "singine codex")),
            asdict(ModelObject("iata-codes", "reference-data", "Embedded airport and country reference mapping for location resolution.", "core/java/singine/location/IataCodeTable.java")),
            asdict(ModelObject("unicode-mapping", "reference-data", "Unicode reference mapping aligned with Collibra reference data.", "core/src/singine/unicode/mapping.clj")),
            asdict(ModelObject("knowyourai-rdf", "reference-data", "RDF concept pack bridged into Singine for SPARQL inspection.", "singine bridge build")),
        ],
        "entity_families": [
            asdict(ModelObject("data_category", "entity", "CSV/Collibra-exported category entity.", "singine inspect --csv <file> <name>")),
            asdict(ModelObject("ai_concept", "entity", "RDF/SKOS concept mapped through the Collibra lens.", "singine inspect --rdf <file> <name>")),
            asdict(ModelObject("logseq_page", "entity", "Logseq page surfaced as a Collibra-style asset.", "singine inspect 'Page Name'")),
            asdict(ModelObject("todo", "entity", "Logseq task surfaced as an asset and activity.", "singine inspect 'Task text'")),
        ],
        "collibra_bridge": {
            "asset_types": COLLIBRA_ASSET_TYPES,
            "domain_types": COLLIBRA_DOMAIN_TYPES,
            "relation_types": COLLIBRA_RELATION_TYPES,
            "note": "This is the Singine-side bridge into the Collibra metamodel, not a hard runtime dependency on Collibra itself.",
        },
    }


def inspect_object(name: str) -> Dict[str, Any]:
    target = name.strip().lower()
    data = catalog()
    flattened: List[Dict[str, Any]] = []
    for key in ["bootstrappers", "auth_operations", "master_data", "reference_data", "entity_families"]:
        flattened.extend(data[key])
    for item in flattened:
        if item["name"].lower() == target:
            return item
    for family_key in ["asset_types", "domain_types", "relation_types"]:
        for item in data["collibra_bridge"][family_key]:
            if item.lower() == target:
                return {"name": item, "family": family_key[:-1], "description": "Collibra bridge metamodel value.", "reference": "singine model catalog"}
    raise KeyError(name)
