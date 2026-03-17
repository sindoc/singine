"""
singine-mcp-collibra — MCP server exposing Collibra REST operations.

Open-source edition (GPLv3) published via markupware.com/singine.
Commercial hosted edition available at lutino.io/mcp/collibra.

Transport: stdio (default) — register with:
  claude mcp add singine-collibra --transport stdio -- \\
      python3 /path/to/io.lutino.mcp/mcp-collibra/src/server.py

Environment variables required (same as singine collibra commands):
  COLLIBRA_BASE_URL      e.g. https://lutino.collibra.com
  COLLIBRA_USERNAME + COLLIBRA_PASSWORD   (Basic auth)
  OR
  COLLIBRA_TOKEN                          (Bearer token)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the singine package importable when run directly from this directory.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mcp.server.fastmcp import FastMCP
from singine import collibra_rest as cr

mcp = FastMCP(
    name="singine-collibra",
    version="0.1.0",
    description=(
        "Collibra REST operations: fetch communities, domains, asset types, views, "
        "workflows; search assets; validate environment."
    ),
)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def collibra_env() -> dict:
    """Validate the current Collibra environment configuration.

    Returns ok=True when COLLIBRA_BASE_URL and credentials are present.
    Safe to call first to confirm connectivity before fetching data.
    """
    return cr.check_env()


@mcp.tool()
def collibra_fetch_community(name: str = "", limit: int = 50) -> dict:
    """Fetch Communities from Collibra.

    Args:
        name:  Optional name prefix filter. Leave empty to fetch all.
        limit: Maximum number of results (default 50).

    Returns envelope with ok, data (list of community objects), count, env.
    """
    return cr.fetch_communities(name=name or None, limit=limit)


@mcp.tool()
def collibra_fetch_domain(
    community_id: str = "",
    domain_type: str = "",
    limit: int = 50,
) -> dict:
    """Fetch Domains from Collibra.

    Args:
        community_id: UUID of the parent community (optional filter).
        domain_type:  Domain type name filter, e.g. 'Glossary' (optional).
        limit:        Maximum number of results (default 50).
    """
    return cr.fetch_domains(
        community_id=community_id or None,
        domain_type=domain_type or None,
        limit=limit,
    )


@mcp.tool()
def collibra_fetch_asset_type() -> dict:
    """Fetch all AssetType definitions from Collibra.

    Returns the full metamodel asset type hierarchy including publicIds,
    parent types, symbol data, and product assignments.
    Useful for building tableViewConfig column references.
    """
    return cr.fetch_asset_types()


@mcp.tool()
def collibra_fetch_view(location: str = "", limit: int = 100) -> dict:
    """Fetch View (tableViewConfig) definitions from Collibra.

    Args:
        location: Filter by view location, e.g. 'catalog|reports' (optional).
        limit:    Maximum number of results (default 100).

    Each view contains a 'config' field with the full tableViewConfig JSON
    including column definitions, output paths, filters, and UI settings.
    """
    return cr.fetch_views(location=location or None, limit=limit)


@mcp.tool()
def collibra_fetch_workflow(limit: int = 50) -> dict:
    """Fetch Workflow definitions from Collibra.

    Returns BPMN workflow definitions with their assignment rules,
    trigger conditions, and configuration variables.
    """
    return cr.fetch_workflows(limit=limit)


@mcp.tool()
def collibra_search(
    query: str,
    asset_type: str = "",
    domain_id: str = "",
    limit: int = 25,
) -> dict:
    """Search Assets by name across Collibra.

    Args:
        query:      Name search string (prefix/contains match). Required.
        asset_type: AssetType publicId filter, e.g. 'DataSet' (optional).
        domain_id:  Restrict search to one Domain UUID (optional).
        limit:      Maximum number of results (default 25).
    """
    if not query:
        return {"ok": False, "error": "query is required"}
    return cr.search_assets(
        query=query,
        asset_type=asset_type or None,
        domain_id=domain_id or None,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
