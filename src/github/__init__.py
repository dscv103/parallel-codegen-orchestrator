"""GitHub Integration Module."""

from .graphql_api import GitHubGraphQL, GraphQLError
from .rest_api import GitHubIntegration

__all__ = ["GitHubIntegration", "GitHubGraphQL", "GraphQLError"]
