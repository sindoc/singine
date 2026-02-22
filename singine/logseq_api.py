"""
Logseq HTTP API Client for write operations.

This client provides programmatic access to Logseq's Plugin SDK via HTTP API.
Used for scenario creation, contract simulation, and future state projection.

Standard Operating Model:
- File-based operations: Read actual state (what IS)
- API-based operations: Create projections (what IF)
- Hybrid: Compare simulated vs actual

Authentication:
- Requires Logseq HTTP API server to be running (Settings → Features → Enable HTTP APIs)
- Requires valid API token (Settings → API → Authorization tokens → Create new)
"""

import requests
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path


class LogseqAPIError(Exception):
    """Raised when Logseq API returns an error."""
    pass


class LogseqAPIClient:
    """Client for Logseq HTTP API operations."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:12315",
        token: Optional[str] = None
    ):
        """
        Initialize Logseq API client.

        Args:
            base_url: Logseq API server URL (default: http://127.0.0.1:12315)
            token: Authorization token (required for API calls)
        """
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.headers = {
            "Content-Type": "application/json"
        }

        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def _call_api(self, method: str, args: List[Any] = None) -> Any:
        """
        Call Logseq Plugin SDK method via HTTP API.

        Args:
            method: Plugin SDK method (e.g., "logseq.Editor.getBlock")
            args: List of arguments for the method

        Returns:
            API response data

        Raises:
            LogseqAPIError: If API call fails
        """
        if not self.token:
            raise LogseqAPIError("API token required. Set token in config or pass to constructor.")

        payload = {
            "method": method,
            "args": args or []
        }

        try:
            response = requests.post(
                f"{self.base_url}/api",
                json=payload,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()

            result = response.json()

            # Check for API-level errors
            if isinstance(result, dict) and result.get('error'):
                raise LogseqAPIError(f"API error: {result['error']}")

            return result

        except requests.exceptions.RequestException as e:
            raise LogseqAPIError(f"HTTP request failed: {e}")
        except json.JSONDecodeError as e:
            raise LogseqAPIError(f"Failed to parse API response: {e}")

    def test_connection(self) -> bool:
        """
        Test if API server is running and token is valid.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Simple API call to check connectivity
            self._call_api("logseq.App.getCurrentGraph")
            return True
        except LogseqAPIError:
            return False

    # -------------------------------------------------------------------------
    # BLOCK OPERATIONS
    # -------------------------------------------------------------------------

    def get_block(self, block_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get a block by UUID.

        Args:
            block_uuid: Block UUID

        Returns:
            Block data dict or None if not found
        """
        return self._call_api("logseq.Editor.getBlock", [block_uuid])

    def insert_block(
        self,
        target: str,  # Page name or block UUID
        content: str,
        sibling: bool = False,
        before: bool = False,
        properties: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Insert a new block.

        Args:
            target: Target page name or parent block UUID
            content: Block content (markdown)
            sibling: If True, insert as sibling; if False, insert as child
            before: If True, insert before target; if False, insert after
            properties: Optional block properties

        Returns:
            Created block data
        """
        options = {
            "sibling": sibling,
            "before": before
        }

        if properties:
            options["properties"] = properties

        return self._call_api("logseq.Editor.insertBlock", [target, content, options])

    def update_block(self, block_uuid: str, content: str) -> Dict[str, Any]:
        """
        Update a block's content.

        Args:
            block_uuid: Block UUID
            content: New block content

        Returns:
            Updated block data
        """
        return self._call_api("logseq.Editor.updateBlock", [block_uuid, content])

    def delete_block(self, block_uuid: str) -> bool:
        """
        Delete a block.

        Args:
            block_uuid: Block UUID

        Returns:
            True if successful
        """
        result = self._call_api("logseq.Editor.removeBlock", [block_uuid])
        return result is not None

    # -------------------------------------------------------------------------
    # PAGE OPERATIONS
    # -------------------------------------------------------------------------

    def get_page(self, page_name: str) -> Optional[Dict[str, Any]]:
        """
        Get a page by name.

        Args:
            page_name: Page name (case-insensitive)

        Returns:
            Page data or None if not found
        """
        return self._call_api("logseq.Editor.getPage", [page_name])

    def create_page(
        self,
        page_name: str,
        properties: Optional[Dict[str, Any]] = None,
        create_first_block: bool = True
    ) -> Dict[str, Any]:
        """
        Create a new page.

        Args:
            page_name: Name of the page to create
            properties: Optional page properties
            create_first_block: If True, create an initial block

        Returns:
            Created page data
        """
        page = self._call_api("logseq.Editor.createPage", [page_name, properties or {}])

        if create_first_block and page:
            # Insert a placeholder block (Logseq requires pages to have at least one block)
            self.insert_block(page_name, "", sibling=False)

        return page

    def delete_page(self, page_name: str) -> bool:
        """
        Delete a page.

        Args:
            page_name: Name of page to delete

        Returns:
            True if successful
        """
        result = self._call_api("logseq.Editor.deletePage", [page_name])
        return result is not None

    # -------------------------------------------------------------------------
    # QUERY OPERATIONS
    # -------------------------------------------------------------------------

    def query_datalog(self, query: str) -> List[Any]:
        """
        Execute a Datalog query.

        Args:
            query: Datalog query string

        Returns:
            Query results

        Example:
            query = '''
            [:find (pull ?b [*])
             :where
             [?b :block/marker "TODO"]]
            '''
            results = client.query_datalog(query)
        """
        return self._call_api("logseq.DB.q", [query])

    def query_todos(self, statuses: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Query all TODO blocks.

        Args:
            statuses: Optional list of statuses to filter (e.g., ["TODO", "DOING"])

        Returns:
            List of TODO blocks
        """
        if statuses:
            status_set = "{" + " ".join(f'"{s}"' for s in statuses) + "}"
            query = f'''
            [:find (pull ?b [*])
             :where
             [?b :block/marker ?marker]
             [(contains? #{status_set} ?marker)]]
            '''
        else:
            query = '''
            [:find (pull ?b [*])
             :where
             [?b :block/marker ?marker]]
            '''

        results = self.query_datalog(query)

        # Extract blocks from query results
        return [result[0] for result in results if result]

    # -------------------------------------------------------------------------
    # UI OPERATIONS
    # -------------------------------------------------------------------------

    def show_message(self, message: str, status: str = "success") -> None:
        """
        Show a message in Logseq UI.

        Args:
            message: Message to display
            status: Message type ("success", "warning", "error")
        """
        self._call_api("logseq.UI.showMsg", [message, status])

    # -------------------------------------------------------------------------
    # APP OPERATIONS
    # -------------------------------------------------------------------------

    def get_current_graph(self) -> Dict[str, Any]:
        """
        Get information about the current graph.

        Returns:
            Graph information (name, path, etc.)
        """
        return self._call_api("logseq.App.getCurrentGraph")

    # -------------------------------------------------------------------------
    # CONTRACT-SPECIFIC OPERATIONS
    # -------------------------------------------------------------------------

    def create_contract_page(
        self,
        contract_name: str,
        contract_type: str,
        namespace: str = "scenarios"
    ) -> str:
        """
        Create a page for contract scenario analysis.

        Args:
            contract_name: Name of the contract
            contract_type: Type of contract (e.g., "tenancy", "employment")
            namespace: Namespace for scenarios (default: "scenarios")

        Returns:
            Page name of created contract page
        """
        page_name = f"{namespace}/{contract_type}/{contract_name}"

        properties = {
            "type": "contract",
            "contract-type": contract_type,
            "namespace": namespace,
            "created-at": datetime.now().isoformat()
        }

        self.create_page(page_name, properties=properties, create_first_block=False)

        # Create initial structure
        self.insert_block(page_name, f"# Contract: {contract_name}")
        self.insert_block(page_name, f"- **Type**: {contract_type}")
        self.insert_block(page_name, f"- **Status**: simulation")

        return page_name

    def create_commitment_block(
        self,
        page_name: str,
        commitment_id: str,
        description: str,
        due_date: Optional[str] = None,
        amount: Optional[float] = None,
        party: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a commitment block in a contract page.

        Args:
            page_name: Contract page name
            commitment_id: Unique commitment ID
            description: Commitment description
            due_date: Optional due date (ISO format)
            amount: Optional monetary amount
            party: Optional party responsible

        Returns:
            Created block data
        """
        content = f"TODO {description}"

        if amount:
            content += f" (${amount:.2f})"

        properties = {
            "commitment-id": commitment_id,
            "type": "commitment"
        }

        if due_date:
            properties["due-date"] = due_date

        if party:
            properties["party"] = party

        return self.insert_block(page_name, content, sibling=False, properties=properties)

    def create_privilege_block(
        self,
        page_name: str,
        privilege_id: str,
        description: str,
        conditional_on: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create a privilege block in a contract page.

        Args:
            page_name: Contract page name
            privilege_id: Unique privilege ID
            description: Privilege description
            conditional_on: Optional list of commitment IDs this depends on

        Returns:
            Created block data
        """
        content = f"PRIVILEGE: {description}"

        properties = {
            "privilege-id": privilege_id,
            "type": "privilege"
        }

        if conditional_on:
            properties["conditional-on"] = ", ".join(conditional_on)

        return self.insert_block(page_name, content, sibling=False, properties=properties)

    def create_scenario(
        self,
        scenario_name: str,
        contract_type: str,
        description: str
    ) -> str:
        """
        Create a scenario page for contract analysis.

        Args:
            scenario_name: Name of the scenario
            contract_type: Type of contract being analyzed
            description: Scenario description

        Returns:
            Page name of created scenario
        """
        page_name = f"scenarios/{contract_type}/{scenario_name}"

        properties = {
            "type": "scenario",
            "contract-type": contract_type,
            "created-at": datetime.now().isoformat()
        }

        self.create_page(page_name, properties=properties, create_first_block=False)

        # Create scenario structure
        self.insert_block(page_name, f"# Scenario: {scenario_name}")
        self.insert_block(page_name, f"- **Description**: {description}")
        self.insert_block(page_name, "## Assumptions")
        self.insert_block(page_name, "## Projected Commitments")
        self.insert_block(page_name, "## Projected Privileges")
        self.insert_block(page_name, "## Analysis")

        return page_name
