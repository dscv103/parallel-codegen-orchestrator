"""Unit tests for GitHub GraphQL API integration."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.github.graphql_api import GitHubGraphQL, GraphQLError


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx AsyncClient."""
    with patch("src.github.graphql_api.httpx.AsyncClient") as mock:
        client = AsyncMock()
        mock.return_value = client
        yield client


@pytest.fixture
def github_graphql(mock_httpx_client):
    """Create a GitHubGraphQL instance with mocked client."""
    return GitHubGraphQL(token="test_token_12345")


class TestInitialization:
    """Test GitHubGraphQL initialization."""

    def test_init_with_valid_token(self, mock_httpx_client):
        """Test initialization with valid token."""
        graphql = GitHubGraphQL(token="test_token")

        assert graphql.token == "test_token"
        assert graphql.base_url == "https://api.github.com/graphql"

    def test_init_sets_correct_headers(self):
        """Test that correct headers are set on initialization."""
        with patch("src.github.graphql_api.httpx.AsyncClient") as mock_client:
            graphql = GitHubGraphQL(token="test_token_123")

            # Verify AsyncClient was called with correct headers
            mock_client.assert_called_once()
            call_kwargs = mock_client.call_args[1]

            assert "headers" in call_kwargs
            assert call_kwargs["headers"]["Authorization"] == "Bearer test_token_123"
            assert call_kwargs["headers"]["Content-Type"] == "application/json"


class TestFetchProjectItems:
    """Test fetching project items."""

    @pytest.mark.asyncio
    async def test_fetch_project_items_success(self, github_graphql, mock_httpx_client):
        """Test successfully fetching project items."""
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "node": {
                    "items": {
                        "nodes": [
                            {
                                "id": "PVTI_item1",
                                "content": {
                                    "number": 1,
                                    "title": "Test Issue",
                                    "body": "Test body",
                                },
                                "fieldValues": {
                                    "nodes": [
                                        {
                                            "field": {"name": "Status"},
                                            "name": "In Progress",
                                        },
                                    ],
                                },
                            },
                        ],
                        "pageInfo": {
                            "hasNextPage": False,
                            "endCursor": None,
                        },
                    },
                },
            },
        }
        mock_httpx_client.post.return_value = mock_response

        # Execute
        result = await github_graphql.fetch_project_items(project_id="PVT_test123")

        # Verify
        assert len(result) == 1
        assert result[0]["id"] == "PVTI_item1"
        assert result[0]["content"]["title"] == "Test Issue"

        # Verify the GraphQL query was called
        mock_httpx_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_project_items_with_pagination(
        self, github_graphql, mock_httpx_client,
    ):
        """Test fetching project items with pagination."""
        # First page response
        first_page = {
            "data": {
                "node": {
                    "items": {
                        "nodes": [{"id": "PVTI_1", "content": {"number": 1}}],
                        "pageInfo": {
                            "hasNextPage": True,
                            "endCursor": "cursor123",
                        },
                    },
                },
            },
        }

        # Second page response
        second_page = {
            "data": {
                "node": {
                    "items": {
                        "nodes": [{"id": "PVTI_2", "content": {"number": 2}}],
                        "pageInfo": {
                            "hasNextPage": False,
                            "endCursor": None,
                        },
                    },
                },
            },
        }

        # Setup mock responses
        mock_response1 = MagicMock()
        mock_response1.status_code = 200
        mock_response1.json.return_value = first_page

        mock_response2 = MagicMock()
        mock_response2.status_code = 200
        mock_response2.json.return_value = second_page

        mock_httpx_client.post.side_effect = [mock_response1, mock_response2]

        # Execute
        result = await github_graphql.fetch_project_items(project_id="PVT_test")

        # Verify
        assert len(result) == 2
        assert result[0]["id"] == "PVTI_1"
        assert result[1]["id"] == "PVTI_2"
        assert mock_httpx_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_fetch_project_items_with_errors(
        self, github_graphql, mock_httpx_client,
    ):
        """Test handling GraphQL errors."""
        # Mock error response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "errors": [
                {"message": "Resource not found", "type": "NOT_FOUND"},
            ],
        }
        mock_httpx_client.post.return_value = mock_response

        # Execute and verify exception
        with pytest.raises(GraphQLError) as exc_info:
            await github_graphql.fetch_project_items(project_id="invalid_id")

        assert "Resource not found" in str(exc_info.value)


class TestFetchProjectDetails:
    """Test fetching project details."""

    @pytest.mark.asyncio
    async def test_fetch_project_details_success(
        self, github_graphql, mock_httpx_client,
    ):
        """Test successfully fetching project details."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "node": {
                    "title": "My Project",
                    "shortDescription": "Project description",
                    "public": True,
                    "fields": {
                        "nodes": [
                            {
                                "id": "PVTF_field1",
                                "name": "Status",
                                "dataType": "SINGLE_SELECT",
                            },
                            {
                                "id": "PVTF_field2",
                                "name": "Priority",
                                "dataType": "SINGLE_SELECT",
                            },
                        ],
                    },
                },
            },
        }
        mock_httpx_client.post.return_value = mock_response

        # Execute
        result = await github_graphql.fetch_project_details(project_id="PVT_123")

        # Verify
        assert result["title"] == "My Project"
        assert result["shortDescription"] == "Project description"
        assert len(result["fields"]["nodes"]) == 2
        assert result["fields"]["nodes"][0]["name"] == "Status"


class TestGetCustomFieldValue:
    """Test retrieving custom field values."""

    @pytest.mark.asyncio
    async def test_get_custom_field_value_success(
        self, github_graphql, mock_httpx_client,
    ):
        """Test successfully getting a custom field value."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "node": {
                    "fieldValueByName": {
                        "name": "In Progress",
                        "field": {"name": "Status"},
                    },
                },
            },
        }
        mock_httpx_client.post.return_value = mock_response

        # Execute
        result = await github_graphql.get_custom_field_value(
            item_id="PVTI_123", field_name="Status",
        )

        # Verify
        assert result == "In Progress"

    @pytest.mark.asyncio
    async def test_get_custom_field_value_not_found(
        self, github_graphql, mock_httpx_client,
    ):
        """Test handling when field value is not found."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "node": {
                    "fieldValueByName": None,
                },
            },
        }
        mock_httpx_client.post.return_value = mock_response

        # Execute
        result = await github_graphql.get_custom_field_value(
            item_id="PVTI_123", field_name="NonExistent",
        )

        # Verify
        assert result is None


class TestUpdateProjectItemStatus:
    """Test updating project item status."""

    @pytest.mark.asyncio
    async def test_update_project_item_status_success(
        self, github_graphql, mock_httpx_client,
    ):
        """Test successfully updating project item status."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "updateProjectV2ItemFieldValue": {
                    "projectV2Item": {
                        "id": "PVTI_123",
                        "fieldValueByName": {"name": "Done"},
                    },
                },
            },
        }
        mock_httpx_client.post.return_value = mock_response

        # Execute
        result = await github_graphql.update_project_item_status(
            project_id="PVT_proj",
            item_id="PVTI_123",
            field_id="PVTF_status",
            option_id="PVTSSF_done",
        )

        # Verify
        assert result is True
        mock_httpx_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_project_item_status_failure(
        self, github_graphql, mock_httpx_client,
    ):
        """Test handling update failure."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "errors": [{"message": "Field not found"}],
        }
        mock_httpx_client.post.return_value = mock_response

        # Execute and verify
        with pytest.raises(GraphQLError):
            await github_graphql.update_project_item_status(
                project_id="PVT_proj",
                item_id="PVTI_123",
                field_id="invalid",
                option_id="invalid",
            )


class TestUpdateItemMetadata:
    """Test updating project item metadata (labels, assignees)."""

    @pytest.mark.asyncio
    async def test_add_labels_to_item(self, github_graphql, mock_httpx_client):
        """Test adding labels to a project item."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "addLabelsToLabelable": {
                    "labelable": {
                        "labels": {
                            "nodes": [
                                {"name": "bug"},
                                {"name": "enhancement"},
                            ],
                        },
                    },
                },
            },
        }
        mock_httpx_client.post.return_value = mock_response

        # Execute
        result = await github_graphql.add_labels_to_item(
            item_id="ISSUE_123",
            label_ids=["LA_bug", "LA_enhancement"],
        )

        # Verify
        assert result is True

    @pytest.mark.asyncio
    async def test_assign_users_to_item(self, github_graphql, mock_httpx_client):
        """Test assigning users to a project item."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "addAssigneesToAssignable": {
                    "assignable": {
                        "assignees": {
                            "nodes": [{"login": "user1"}],
                        },
                    },
                },
            },
        }
        mock_httpx_client.post.return_value = mock_response

        # Execute
        result = await github_graphql.assign_users_to_item(
            item_id="ISSUE_123",
            assignee_ids=["U_user1"],
        )

        # Verify
        assert result is True


class TestErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_http_error_handling(self, github_graphql, mock_httpx_client):
        """Test handling HTTP errors."""
        mock_httpx_client.post.side_effect = httpx.HTTPError("Connection failed")

        # Execute and verify
        with pytest.raises(httpx.HTTPError):
            await github_graphql.fetch_project_items(project_id="PVT_123")

    @pytest.mark.asyncio
    async def test_invalid_json_response(self, github_graphql, mock_httpx_client):
        """Test handling invalid JSON responses."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError(
            "Invalid JSON", "", 0,
        )
        mock_httpx_client.post.return_value = mock_response

        # Execute and verify
        with pytest.raises(json.JSONDecodeError):
            await github_graphql.fetch_project_items(project_id="PVT_123")


class TestCleanup:
    """Test resource cleanup."""

    @pytest.mark.asyncio
    async def test_close_client(self, github_graphql, mock_httpx_client):
        """Test closing the httpx client."""
        await github_graphql.close()

        mock_httpx_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_httpx_client):
        """Test using GitHubGraphQL as async context manager."""
        async with GitHubGraphQL(token="test") as graphql:
            assert graphql.token == "test"

        mock_httpx_client.aclose.assert_called_once()
