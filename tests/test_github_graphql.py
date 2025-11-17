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
                                        }
                                    ]
                                },
                            }
                        ],
                        "pageInfo": {
                            "hasNextPage": False,
                            "endCursor": None,
                        },
                    }
                }
            }
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
        self, github_graphql, mock_httpx_client
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
                    }
                }
            }
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
                    }
                }
            }
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
        self, github_graphql, mock_httpx_client
    ):
        """Test handling GraphQL errors."""
        # Mock error response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "errors": [
                {"message": "Resource not found", "type": "NOT_FOUND"}
            ]
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
        self, github_graphql, mock_httpx_client
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
                        ]
                    },
                }
            }
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
        self, github_graphql, mock_httpx_client
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
                    }
                }
            }
        }
        mock_httpx_client.post.return_value = mock_response

        # Execute
        result = await github_graphql.get_custom_field_value(
            item_id="PVTI_123", field_name="Status"
        )

        # Verify
        assert result == "In Progress"

    @pytest.mark.asyncio
    async def test_get_custom_field_value_not_found(
        self, github_graphql, mock_httpx_client
    ):
        """Test handling when field value is not found."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "node": {
                    "fieldValueByName": None
                }
            }
        }
        mock_httpx_client.post.return_value = mock_response

        # Execute
        result = await github_graphql.get_custom_field_value(
            item_id="PVTI_123", field_name="NonExistent"
        )

        # Verify
        assert result is None


class TestUpdateProjectItemStatus:
    """Test updating project item status."""

    @pytest.mark.asyncio
    async def test_update_project_item_status_success(
        self, github_graphql, mock_httpx_client
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
                    }
                }
            }
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
        self, github_graphql, mock_httpx_client
    ):
        """Test handling update failure."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "errors": [{"message": "Field not found"}]
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
                            ]
                        }
                    }
                }
            }
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
                            "nodes": [{"login": "user1"}]
                        }
                    }
                }
            }
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
            "Invalid JSON", "", 0
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


class TestExecuteQueryEdgeCases:
    """Test _execute_query edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_execute_query_with_variables(
        self, github_graphql, mock_httpx_client
    ):
        """Test _execute_query correctly passes variables."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"viewer": {"login": "testuser"}}
        }
        mock_httpx_client.post.return_value = mock_response

        query = "query($login: String!) { viewer(login: $login) { login } }"
        variables = {"login": "testuser"}

        result = await github_graphql._execute_query(query, variables)

        # Verify variables were passed in the payload
        call_args = mock_httpx_client.post.call_args
        assert call_args[1]["json"]["variables"] == variables
        assert result["data"]["viewer"]["login"] == "testuser"

    @pytest.mark.asyncio
    async def test_execute_query_without_variables(
        self, github_graphql, mock_httpx_client
    ):
        """Test _execute_query works without variables."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"viewer": {"login": "test"}}}
        mock_httpx_client.post.return_value = mock_response

        query = "query { viewer { login } }"
        result = await github_graphql._execute_query(query)

        # Verify no variables were passed
        call_args = mock_httpx_client.post.call_args
        assert "variables" not in call_args[1]["json"]
        assert result["data"]["viewer"]["login"] == "test"

    @pytest.mark.asyncio
    async def test_execute_query_multiple_errors(
        self, github_graphql, mock_httpx_client
    ):
        """Test handling multiple GraphQL errors."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "errors": [
                {"message": "Authentication required", "type": "UNAUTHORIZED"},
                {"message": "Rate limit exceeded", "type": "RATE_LIMITED"},
            ]
        }
        mock_httpx_client.post.return_value = mock_response

        with pytest.raises(GraphQLError) as exc_info:
            await github_graphql._execute_query("query { viewer { login } }")

        error_msg = str(exc_info.value)
        assert "Authentication required" in error_msg
        assert "Rate limit exceeded" in error_msg

    @pytest.mark.asyncio
    async def test_execute_query_http_status_errors(
        self, github_graphql, mock_httpx_client
    ):
        """Test handling various HTTP status errors."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )
        mock_httpx_client.post.return_value = mock_response

        with pytest.raises(httpx.HTTPStatusError):
            await github_graphql._execute_query("query { viewer { login } }")

    @pytest.mark.asyncio
    async def test_execute_query_timeout(self, github_graphql, mock_httpx_client):
        """Test handling request timeout."""
        mock_httpx_client.post.side_effect = httpx.TimeoutException(
            "Request timed out"
        )

        with pytest.raises(httpx.TimeoutException) as exc_info:
            await github_graphql._execute_query("query { viewer { login } }")

        assert "timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_query_network_error(
        self, github_graphql, mock_httpx_client
    ):
        """Test handling network connection errors."""
        mock_httpx_client.post.side_effect = httpx.ConnectError(
            "Failed to connect"
        )

        with pytest.raises(httpx.ConnectError):
            await github_graphql._execute_query("query { viewer { login } }")


class TestFetchProjectItemsEdgeCases:
    """Test fetch_project_items edge cases."""

    @pytest.mark.asyncio
    async def test_fetch_project_items_empty_project(
        self, github_graphql, mock_httpx_client
    ):
        """Test fetching items from an empty project."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "node": {
                    "items": {
                        "nodes": [],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        }
        mock_httpx_client.post.return_value = mock_response

        result = await github_graphql.fetch_project_items(project_id="PVT_empty")

        assert result == []
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_fetch_project_items_with_pull_requests(
        self, github_graphql, mock_httpx_client
    ):
        """Test fetching project items that include pull requests."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "node": {
                    "items": {
                        "nodes": [
                            {
                                "id": "PVTI_pr1",
                                "content": {
                                    "number": 42,
                                    "title": "Add new feature",
                                    "body": "PR description",
                                    "state": "OPEN",
                                    "url": "https://github.com/org/repo/pull/42",
                                },
                                "fieldValues": {"nodes": []},
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        }
        mock_httpx_client.post.return_value = mock_response

        result = await github_graphql.fetch_project_items(project_id="PVT_test")

        assert len(result) == 1
        assert result[0]["content"]["number"] == 42
        assert result[0]["content"]["state"] == "OPEN"

    @pytest.mark.asyncio
    async def test_fetch_project_items_custom_page_size(
        self, github_graphql, mock_httpx_client
    ):
        """Test fetching project items with custom page size."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "node": {
                    "items": {
                        "nodes": [{"id": f"PVTI_{i}"} for i in range(50)],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        }
        mock_httpx_client.post.return_value = mock_response

        result = await github_graphql.fetch_project_items(
            project_id="PVT_test", first=50
        )

        assert len(result) == 50
        # Verify the first parameter was passed correctly
        call_args = mock_httpx_client.post.call_args
        assert call_args[1]["json"]["variables"]["first"] == 50

    @pytest.mark.asyncio
    async def test_fetch_project_items_with_all_field_types(
        self, github_graphql, mock_httpx_client
    ):
        """Test fetching items with all custom field types."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "node": {
                    "items": {
                        "nodes": [
                            {
                                "id": "PVTI_1",
                                "content": {"number": 1, "title": "Test"},
                                "fieldValues": {
                                    "nodes": [
                                        {
                                            "field": {"name": "Status"},
                                            "name": "In Progress",
                                        },
                                        {
                                            "field": {"name": "Notes"},
                                            "text": "Important notes",
                                        },
                                        {
                                            "field": {"name": "DueDate"},
                                            "date": "2024-12-31",
                                        },
                                        {
                                            "field": {"name": "Priority"},
                                            "number": 5.0,
                                        },
                                    ]
                                },
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        }
        mock_httpx_client.post.return_value = mock_response

        result = await github_graphql.fetch_project_items(project_id="PVT_test")

        assert len(result) == 1
        field_values = result[0]["fieldValues"]["nodes"]
        assert len(field_values) == 4
        # Verify all field types are present
        assert any(fv.get("name") == "In Progress" for fv in field_values)
        assert any(fv.get("text") == "Important notes" for fv in field_values)
        assert any(fv.get("date") == "2024-12-31" for fv in field_values)
        assert any(fv.get("number") == 5.0 for fv in field_values)

    @pytest.mark.asyncio
    async def test_fetch_project_items_null_content(
        self, github_graphql, mock_httpx_client
    ):
        """Test fetching items with null content (archived items)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "node": {
                    "items": {
                        "nodes": [
                            {
                                "id": "PVTI_1",
                                "content": None,
                                "fieldValues": {"nodes": []},
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        }
        mock_httpx_client.post.return_value = mock_response

        result = await github_graphql.fetch_project_items(project_id="PVT_test")

        assert len(result) == 1
        assert result[0]["content"] is None

    @pytest.mark.asyncio
    async def test_fetch_project_items_large_pagination(
        self, github_graphql, mock_httpx_client
    ):
        """Test fetching items with many pages."""
        # Create 5 pages of responses
        pages = []
        for i in range(5):
            page = {
                "data": {
                    "node": {
                        "items": {
                            "nodes": [
                                {"id": f"PVTI_{i * 100 + j}", "content": {}}
                                for j in range(100)
                            ],
                            "pageInfo": {
                                "hasNextPage": i < 4,
                                "endCursor": f"cursor_{i}" if i < 4 else None,
                            },
                        }
                    }
                }
            }
            pages.append(page)

        # Setup mock responses
        mock_responses = []
        for page in pages:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = page
            mock_responses.append(mock_response)

        mock_httpx_client.post.side_effect = mock_responses

        result = await github_graphql.fetch_project_items(project_id="PVT_test")

        assert len(result) == 500  # 5 pages * 100 items
        assert mock_httpx_client.post.call_count == 5


class TestFetchProjectDetailsEdgeCases:
    """Test fetch_project_details edge cases."""

    @pytest.mark.asyncio
    async def test_fetch_project_details_closed_project(
        self, github_graphql, mock_httpx_client
    ):
        """Test fetching details of a closed project."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "node": {
                    "title": "Closed Project",
                    "shortDescription": "This project is closed",
                    "public": False,
                    "closed": True,
                    "fields": {"nodes": []},
                }
            }
        }
        mock_httpx_client.post.return_value = mock_response

        result = await github_graphql.fetch_project_details(project_id="PVT_closed")

        assert result["closed"] is True
        assert result["public"] is False

    @pytest.mark.asyncio
    async def test_fetch_project_details_with_iteration_field(
        self, github_graphql, mock_httpx_client
    ):
        """Test fetching project with iteration field type."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "node": {
                    "title": "Sprint Project",
                    "shortDescription": "Sprint planning",
                    "public": True,
                    "closed": False,
                    "fields": {
                        "nodes": [
                            {
                                "id": "PVTF_iter",
                                "name": "Sprint",
                                "dataType": "ITERATION",
                                "configuration": {
                                    "iterations": [
                                        {"id": "ITER_1", "title": "Sprint 1"},
                                        {"id": "ITER_2", "title": "Sprint 2"},
                                    ]
                                },
                            }
                        ]
                    },
                }
            }
        }
        mock_httpx_client.post.return_value = mock_response

        result = await github_graphql.fetch_project_details(project_id="PVT_sprint")

        assert len(result["fields"]["nodes"]) == 1
        field = result["fields"]["nodes"][0]
        assert field["dataType"] == "ITERATION"
        assert len(field["configuration"]["iterations"]) == 2

    @pytest.mark.asyncio
    async def test_fetch_project_details_no_description(
        self, github_graphql, mock_httpx_client
    ):
        """Test fetching project without description."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "node": {
                    "title": "No Description Project",
                    "shortDescription": None,
                    "public": True,
                    "closed": False,
                    "fields": {"nodes": []},
                }
            }
        }
        mock_httpx_client.post.return_value = mock_response

        result = await github_graphql.fetch_project_details(project_id="PVT_nodesc")

        assert result["shortDescription"] is None

    @pytest.mark.asyncio
    async def test_fetch_project_details_not_found(
        self, github_graphql, mock_httpx_client
    ):
        """Test fetching non-existent project."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"node": None}}
        mock_httpx_client.post.return_value = mock_response

        with pytest.raises(GraphQLError) as exc_info:
            await github_graphql.fetch_project_details(project_id="PVT_invalid")

        assert "Project not found" in str(exc_info.value)
        assert "PVT_invalid" in str(exc_info.value)


class TestGetCustomFieldValueEdgeCases:
    """Test get_custom_field_value edge cases."""

    @pytest.mark.asyncio
    async def test_get_custom_field_value_text_field(
        self, github_graphql, mock_httpx_client
    ):
        """Test getting text field value."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "node": {
                    "fieldValueByName": {
                        "text": "This is a text value",
                        "field": {"name": "Notes"},
                    }
                }
            }
        }
        mock_httpx_client.post.return_value = mock_response

        result = await github_graphql.get_custom_field_value(
            item_id="PVTI_123", field_name="Notes"
        )

        assert result == "This is a text value"

    @pytest.mark.asyncio
    async def test_get_custom_field_value_empty_string(
        self, github_graphql, mock_httpx_client
    ):
        """Test getting empty string field value."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "node": {
                    "fieldValueByName": {
                        "text": "",
                        "field": {"name": "Notes"},
                    }
                }
            }
        }
        mock_httpx_client.post.return_value = mock_response

        result = await github_graphql.get_custom_field_value(
            item_id="PVTI_123", field_name="Notes"
        )

        # Empty string should return None as it's falsy
        assert result is None

    @pytest.mark.asyncio
    async def test_get_custom_field_value_item_not_found(
        self, github_graphql, mock_httpx_client
    ):
        """Test getting field value for non-existent item."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"node": None}}
        mock_httpx_client.post.return_value = mock_response

        with pytest.raises(GraphQLError) as exc_info:
            await github_graphql.get_custom_field_value(
                item_id="PVTI_invalid", field_name="Status"
            )

        assert "Item not found" in str(exc_info.value)
        assert "PVTI_invalid" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_custom_field_value_unsupported_type(
        self, github_graphql, mock_httpx_client
    ):
        """Test getting field value with unsupported field type."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "node": {
                    "fieldValueByName": {
                        "field": {"name": "CustomField"},
                        # No name, text, date, or number fields
                    }
                }
            }
        }
        mock_httpx_client.post.return_value = mock_response

        result = await github_graphql.get_custom_field_value(
            item_id="PVTI_123", field_name="CustomField"
        )

        assert result is None


class TestUpdateProjectItemStatusEdgeCases:
    """Test update_project_item_status edge cases."""

    @pytest.mark.asyncio
    async def test_update_project_item_status_with_null_response(
        self, github_graphql, mock_httpx_client
    ):
        """Test updating status with null response (should still succeed)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "updateProjectV2ItemFieldValue": {
                    "projectV2Item": None
                }
            }
        }
        mock_httpx_client.post.return_value = mock_response

        result = await github_graphql.update_project_item_status(
            project_id="PVT_proj",
            item_id="PVTI_123",
            field_id="PVTF_status",
            option_id="PVTSSF_done",
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_update_project_item_status_invalid_option(
        self, github_graphql, mock_httpx_client
    ):
        """Test updating status with invalid option ID."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "errors": [
                {
                    "message": "Option not found for field",
                    "type": "NOT_FOUND",
                }
            ]
        }
        mock_httpx_client.post.return_value = mock_response

        with pytest.raises(GraphQLError) as exc_info:
            await github_graphql.update_project_item_status(
                project_id="PVT_proj",
                item_id="PVTI_123",
                field_id="PVTF_status",
                option_id="INVALID",
            )

        assert "Option not found" in str(exc_info.value)


class TestAddLabelsEdgeCases:
    """Test add_labels_to_item edge cases."""

    @pytest.mark.asyncio
    async def test_add_labels_empty_list(
        self, github_graphql, mock_httpx_client
    ):
        """Test adding empty list of labels."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "addLabelsToLabelable": {
                    "labelable": {
                        "labels": {"nodes": []}
                    }
                }
            }
        }
        mock_httpx_client.post.return_value = mock_response

        result = await github_graphql.add_labels_to_item(
            item_id="ISSUE_123",
            label_ids=[],
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_add_labels_single_label(
        self, github_graphql, mock_httpx_client
    ):
        """Test adding a single label."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "addLabelsToLabelable": {
                    "labelable": {
                        "labels": {
                            "nodes": [{"name": "bug"}]
                        }
                    }
                }
            }
        }
        mock_httpx_client.post.return_value = mock_response

        result = await github_graphql.add_labels_to_item(
            item_id="ISSUE_123",
            label_ids=["LA_bug"],
        )

        assert result is True
        call_args = mock_httpx_client.post.call_args
        assert call_args[1]["json"]["variables"]["labelIds"] == ["LA_bug"]

    @pytest.mark.asyncio
    async def test_add_labels_invalid_item_id(
        self, github_graphql, mock_httpx_client
    ):
        """Test adding labels to non-existent item."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "errors": [
                {
                    "message": "Could not resolve to a node with the global id of 'INVALID'",
                    "type": "NOT_FOUND",
                }
            ]
        }
        mock_httpx_client.post.return_value = mock_response

        with pytest.raises(GraphQLError) as exc_info:
            await github_graphql.add_labels_to_item(
                item_id="INVALID",
                label_ids=["LA_bug"],
            )

        assert "Could not resolve to a node" in str(exc_info.value)


class TestAssignUsersEdgeCases:
    """Test assign_users_to_item edge cases."""

    @pytest.mark.asyncio
    async def test_assign_users_empty_list(
        self, github_graphql, mock_httpx_client
    ):
        """Test assigning empty list of users."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "addAssigneesToAssignable": {
                    "assignable": {
                        "assignees": {"nodes": []}
                    }
                }
            }
        }
        mock_httpx_client.post.return_value = mock_response

        result = await github_graphql.assign_users_to_item(
            item_id="ISSUE_123",
            assignee_ids=[],
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_assign_users_multiple_users(
        self, github_graphql, mock_httpx_client
    ):
        """Test assigning multiple users."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "addAssigneesToAssignable": {
                    "assignable": {
                        "assignees": {
                            "nodes": [
                                {"login": "user1"},
                                {"login": "user2"},
                                {"login": "user3"},
                            ]
                        }
                    }
                }
            }
        }
        mock_httpx_client.post.return_value = mock_response

        result = await github_graphql.assign_users_to_item(
            item_id="ISSUE_123",
            assignee_ids=["U_user1", "U_user2", "U_user3"],
        )

        assert result is True
        call_args = mock_httpx_client.post.call_args
        assert len(call_args[1]["json"]["variables"]["assigneeIds"]) == 3


class TestInitializationEdgeCases:
    """Test GitHubGraphQL initialization edge cases."""

    def test_init_with_custom_base_url(self):
        """Test initialization with custom base URL."""
        with patch("src.github.graphql_api.httpx.AsyncClient") as mock_client:
            custom_url = "https://custom.github.com/graphql"
            graphql = GitHubGraphQL(token="test", base_url=custom_url)

            assert graphql.base_url == custom_url
            call_kwargs = mock_client.call_args[1]
            assert call_kwargs["base_url"] == custom_url

    def test_init_with_empty_token(self):
        """Test initialization with empty token (should still create instance)."""
        with patch("src.github.graphql_api.httpx.AsyncClient"):
            graphql = GitHubGraphQL(token="")

            assert graphql.token == ""

    def test_init_timeout_configuration(self):
        """Test that timeout is configured correctly."""
        with patch("src.github.graphql_api.httpx.AsyncClient") as mock_client:
            graphql = GitHubGraphQL(token="test")

            call_kwargs = mock_client.call_args[1]
            assert call_kwargs["timeout"] == 30.0


class TestContextManagerEdgeCases:
    """Test context manager edge cases."""

    @pytest.mark.asyncio
    async def test_context_manager_with_exception(self, mock_httpx_client):
        """Test that context manager cleans up even with exceptions."""
        try:
            async with GitHubGraphQL(token="test") as graphql:
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Should still close the client
        mock_httpx_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_multiple_operations(
        self, mock_httpx_client
    ):
        """Test multiple operations within context manager."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"node": {"title": "Test", "fields": {"nodes": []}}}
        }
        mock_httpx_client.post.return_value = mock_response

        async with GitHubGraphQL(token="test") as graphql:
            await graphql.fetch_project_details("PVT_1")
            await graphql.fetch_project_details("PVT_2")

        # Should be called twice
        assert mock_httpx_client.post.call_count == 2
        # And closed once
        mock_httpx_client.aclose.assert_called_once()


class TestRateLimitAndRetry:
    """Test rate limiting and retry scenarios."""

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, github_graphql, mock_httpx_client):
        """Test handling rate limit errors."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "errors": [
                {
                    "message": "API rate limit exceeded",
                    "type": "RATE_LIMITED",
                }
            ]
        }
        mock_httpx_client.post.return_value = mock_response

        with pytest.raises(GraphQLError) as exc_info:
            await github_graphql.fetch_project_items(project_id="PVT_123")

        assert "rate limit" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_server_error_response(self, github_graphql, mock_httpx_client):
        """Test handling 500 server errors."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Internal Server Error", request=MagicMock(), response=mock_response
        )
        mock_httpx_client.post.return_value = mock_response

        with pytest.raises(httpx.HTTPStatusError):
            await github_graphql.fetch_project_items(project_id="PVT_123")


class TestMalformedResponses:
    """Test handling of malformed or unexpected responses."""

    @pytest.mark.asyncio
    async def test_missing_data_field(self, github_graphql, mock_httpx_client):
        """Test response without data field."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}  # No 'data' field
        mock_httpx_client.post.return_value = mock_response

        with pytest.raises(KeyError):
            await github_graphql.fetch_project_items(project_id="PVT_123")

    @pytest.mark.asyncio
    async def test_unexpected_response_structure(
        self, github_graphql, mock_httpx_client
    ):
        """Test response with unexpected structure."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "node": {
                    "items": {
                        # Missing 'nodes' field
                        "pageInfo": {"hasNextPage": False, "endCursor": None}
                    }
                }
            }
        }
        mock_httpx_client.post.return_value = mock_response

        with pytest.raises(KeyError):
            await github_graphql.fetch_project_items(project_id="PVT_123")

    @pytest.mark.asyncio
    async def test_empty_error_message(self, github_graphql, mock_httpx_client):
        """Test error with empty message."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "errors": [
                {"message": ""}  # Empty message
            ]
        }
        mock_httpx_client.post.return_value = mock_response

        with pytest.raises(GraphQLError) as exc_info:
            await github_graphql.fetch_project_items(project_id="PVT_123")

        # Should still raise, might have "Unknown error" or empty string
        assert "GraphQL errors" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_error_without_message_field(
        self, github_graphql, mock_httpx_client
    ):
        """Test error object without message field."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "errors": [
                {"type": "UNKNOWN"}  # No message field
            ]
        }
        mock_httpx_client.post.return_value = mock_response

        with pytest.raises(GraphQLError) as exc_info:
            await github_graphql.fetch_project_items(project_id="PVT_123")

        # Should use "Unknown error" fallback
        assert "Unknown error" in str(exc_info.value)
