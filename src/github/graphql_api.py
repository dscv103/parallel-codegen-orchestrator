"""GitHub GraphQL API Integration using httpx.

Provides methods for GitHub Projects v2 management and queries.
"""

import types
from typing import Any

import httpx

from src.log_config import get_logger

# Initialize logger
logger = get_logger(__name__)


class GraphQLError(Exception):
    """Exception raised for GraphQL API errors."""


class GitHubGraphQL:
    """GitHub GraphQL API integration class using httpx.

    Handles Projects v2 queries, custom field management, and item updates
    with automatic pagination support.
    """

    def __init__(self, token: str, base_url: str = "https://api.github.com/graphql"):
        """Initialize GitHub GraphQL integration with authentication.

        Args:
            token: GitHub personal access token or OAuth token
            base_url: GraphQL API endpoint URL
        """
        self.token = token
        self.base_url = base_url
        logger.info("github_graphql_initializing", base_url=base_url)
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        logger.info("github_graphql_initialized", base_url=base_url)

    async def execute_query(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query with error handling.

        Args:
            query: GraphQL query string
            variables: Optional variables for the query

        Returns:
            Response data dictionary

        Raises:
            GraphQLError: If GraphQL errors are returned
            httpx.HTTPError: If HTTP request fails
        """
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        response = await self.client.post("", json=payload)
        response.raise_for_status()

        data = response.json()

        # Check for GraphQL errors
        if "errors" in data:
            error_messages = [err.get("message", "Unknown error") for err in data["errors"]]
            error_msg = f"GraphQL errors: {', '.join(error_messages)}"
            raise GraphQLError(error_msg)

        return data

    async def fetch_project_items(
        self,
        project_id: str,
        first: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch all items from a GitHub Projects v2 board with pagination.

        Args:
            project_id: Project node ID (format: PVT_...)
            first: Number of items per page (max 100)

        Returns:
            List of project item dictionaries

        Raises:
            GraphQLError: If query fails
        """
        query = """
        query($projectId: ID!, $first: Int!, $after: String) {
            node(id: $projectId) {
                ... on ProjectV2 {
                    items(first: $first, after: $after) {
                        nodes {
                            id
                            content {
                                ... on Issue {
                                    number
                                    title
                                    body
                                    state
                                    url
                                }
                                ... on PullRequest {
                                    number
                                    title
                                    body
                                    state
                                    url
                                }
                            }
                            fieldValues(first: 20) {
                                nodes {
                                    ... on ProjectV2ItemFieldSingleSelectValue {
                                        field {
                                            ... on ProjectV2SingleSelectField {
                                                name
                                            }
                                        }
                                        name
                                    }
                                    ... on ProjectV2ItemFieldTextValue {
                                        field {
                                            ... on ProjectV2Field {
                                                name
                                            }
                                        }
                                        text
                                    }
                                    ... on ProjectV2ItemFieldDateValue {
                                        field {
                                            ... on ProjectV2Field {
                                                name
                                            }
                                        }
                                        date
                                    }
                                    ... on ProjectV2ItemFieldNumberValue {
                                        field {
                                            ... on ProjectV2Field {
                                                name
                                            }
                                        }
                                        number
                                    }
                                }
                            }
                        }
                        pageInfo {
                            hasNextPage
                            endCursor
                        }
                    }
                }
            }
        }
        """

        items = []
        has_next_page = True
        after_cursor = None

        while has_next_page:
            variables = {
                "projectId": project_id,
                "first": first,
                "after": after_cursor,
            }

            result = await self.execute_query(query, variables)

            # Extract items
            project_node = result["data"]["node"]
            if not project_node:
                error_msg = f"Project not found: {project_id}"
                raise GraphQLError(error_msg)

            items_data = project_node["items"]
            items.extend(items_data["nodes"])

            # Handle pagination
            page_info = items_data["pageInfo"]
            has_next_page = page_info["hasNextPage"]
            after_cursor = page_info["endCursor"]

        return items

    async def fetch_project_details(self, project_id: str) -> dict[str, Any]:
        """Fetch details about a GitHub Projects v2 board including custom fields.

        Args:
            project_id: Project node ID (format: PVT_...)

        Returns:
            Project details dictionary including fields

        Raises:
            GraphQLError: If query fails
        """
        query = """
        query($projectId: ID!) {
            node(id: $projectId) {
                ... on ProjectV2 {
                    title
                    shortDescription
                    public
                    closed
                    fields(first: 20) {
                        nodes {
                            ... on ProjectV2Field {
                                id
                                name
                                dataType
                            }
                            ... on ProjectV2SingleSelectField {
                                id
                                name
                                dataType
                                options {
                                    id
                                    name
                                }
                            }
                            ... on ProjectV2IterationField {
                                id
                                name
                                dataType
                                configuration {
                                    iterations {
                                        id
                                        title
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        variables = {"projectId": project_id}
        result = await self.execute_query(query, variables)

        project = result["data"]["node"]
        if not project:
            error_msg = f"Project not found: {project_id}"
            raise GraphQLError(error_msg)

        return project

    async def get_custom_field_value(
        self,
        item_id: str,
        field_name: str,
    ) -> str | None:
        """Retrieve a custom field value from a project item.

        Args:
            item_id: Project item node ID (format: PVTI_...)
            field_name: Name of the custom field

        Returns:
            Field value as string, or None if not set

        Raises:
            GraphQLError: If query fails
        """
        query = """
        query($itemId: ID!, $fieldName: String!) {
            node(id: $itemId) {
                ... on ProjectV2Item {
                    fieldValueByName(name: $fieldName) {
                        ... on ProjectV2ItemFieldSingleSelectValue {
                            name
                            field {
                                ... on ProjectV2SingleSelectField {
                                    name
                                }
                            }
                        }
                        ... on ProjectV2ItemFieldTextValue {
                            text
                            field {
                                ... on ProjectV2Field {
                                    name
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        variables = {"itemId": item_id, "fieldName": field_name}
        result = await self.execute_query(query, variables)

        item = result["data"]["node"]
        if not item:
            error_msg = f"Item not found: {item_id}"
            raise GraphQLError(error_msg)

        field_value = item.get("fieldValueByName")
        if not field_value:
            return None

        # Extract value based on field type
        if "name" in field_value:
            return field_value["name"]
        if "text" in field_value:
            return field_value["text"]

        return None

    async def update_project_item_status(
        self,
        project_id: str,
        item_id: str,
        field_id: str,
        option_id: str,
    ) -> bool:
        """Update a project item's status field.

        Args:
            project_id: Project node ID (format: PVT_...)
            item_id: Project item node ID (format: PVTI_...)
            field_id: Field node ID (format: PVTF_...)
            option_id: Option node ID (format: PVTSSF_...)

        Returns:
            True if update successful

        Raises:
            GraphQLError: If mutation fails
        """
        mutation = """
        mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: ProjectV2FieldValue!) {
            updateProjectV2ItemFieldValue(
                input: {
                    projectId: $projectId
                    itemId: $itemId
                    fieldId: $fieldId
                    value: $value
                }
            ) {
                projectV2Item {
                    id
                    fieldValueByName(name: "Status") {
                        ... on ProjectV2ItemFieldSingleSelectValue {
                            name
                        }
                    }
                }
            }
        }
        """

        variables = {
            "projectId": project_id,
            "itemId": item_id,
            "fieldId": field_id,
            "value": {"singleSelectOptionId": option_id},
        }

        await self.execute_query(mutation, variables)
        return True

    async def add_labels_to_item(
        self,
        item_id: str,
        label_ids: list[str],
    ) -> bool:
        """Add labels to a project item (issue/PR).

        Args:
            item_id: Issue or PR node ID
            label_ids: List of label node IDs

        Returns:
            True if labels added successfully

        Raises:
            GraphQLError: If mutation fails
        """
        mutation = """
        mutation($itemId: ID!, $labelIds: [ID!]!) {
            addLabelsToLabelable(
                input: {
                    labelableId: $itemId
                    labelIds: $labelIds
                }
            ) {
                labelable {
                    labels(first: 10) {
                        nodes {
                            name
                        }
                    }
                }
            }
        }
        """

        variables = {"itemId": item_id, "labelIds": label_ids}
        await self.execute_query(mutation, variables)
        return True

    async def assign_users_to_item(
        self,
        item_id: str,
        assignee_ids: list[str],
    ) -> bool:
        """Assign users to a project item (issue/PR).

        Args:
            item_id: Issue or PR node ID
            assignee_ids: List of user node IDs

        Returns:
            True if users assigned successfully

        Raises:
            GraphQLError: If mutation fails
        """
        mutation = """
        mutation($itemId: ID!, $assigneeIds: [ID!]!) {
            addAssigneesToAssignable(
                input: {
                    assignableId: $itemId
                    assigneeIds: $assigneeIds
                }
            ) {
                assignable {
                    assignees(first: 10) {
                        nodes {
                            login
                        }
                    }
                }
            }
        }
        """

        variables = {"itemId": item_id, "assigneeIds": assignee_ids}
        await self.execute_query(mutation, variables)
        return True

    async def close(self) -> None:
        """Close the httpx client and cleanup resources."""
        await self.client.aclose()

    async def __aenter__(self) -> "GitHubGraphQL":
        """Enter async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Exit async context manager and cleanup."""
        await self.close()
