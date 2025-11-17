"""Example usage of GitHub GraphQL API integration.

This example demonstrates how to use the GitHubGraphQL class to:
- Fetch project items from GitHub Projects v2
- Query custom field values
- Update project item status
- Manage labels and assignees
"""

import asyncio
import logging
import os

from src.github.graphql_api import GitHubGraphQL, GraphQLError

# Configure logging to suppress print statements in production
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def demo_project_details(graphql: GitHubGraphQL, project_id: str) -> None:
    """Demonstrate fetching project details."""
    logger.info("=" * 60)
    logger.info("Example 1: Fetch Project Details")
    logger.info("=" * 60)

    try:
        details = await graphql.fetch_project_details(project_id)

        logger.info("Project: %s", details["title"])
        logger.info("Description: %s", details.get("shortDescription", "N/A"))
        logger.info("Public: %s", details["public"])
        logger.info("Custom Fields:")
        for field in details["fields"]["nodes"]:
            logger.info("  - %s (%s)", field["name"], field["dataType"])
            if "options" in field:
                options = [opt["name"] for opt in field["options"]]
                logger.info("    Options: %s", options)
    except GraphQLError:
        logger.exception("Error fetching project details")


async def demo_project_items(graphql: GitHubGraphQL, project_id: str) -> None:
    """Demonstrate fetching project items."""
    logger.info("=" * 60)
    logger.info("Example 2: Fetch Project Items")
    logger.info("=" * 60)

    try:
        items = await graphql.fetch_project_items(project_id=project_id)

        logger.info("Found %d items in project", len(items))
        for item in items[:5]:  # Show first 5
            content = item.get("content", {})
            logger.info("  #%s: %s", content.get("number"), content.get("title"))
            logger.info("  State: %s", content.get("state"))
            logger.info("  URL: %s", content.get("url"))

            # Show custom field values
            field_values = item.get("fieldValues", {}).get("nodes", [])
            if field_values:
                logger.info("  Custom Fields:")
                for fv in field_values:
                    field_name = fv.get("field", {}).get("name", "Unknown")
                    value = fv.get("name") or fv.get("text") or fv.get("date") or fv.get("number")
                    if value:
                        logger.info("    - %s: %s", field_name, value)
    except GraphQLError:
        logger.exception("Error fetching items")


async def demo_custom_field_value(graphql: GitHubGraphQL) -> None:
    """Demonstrate getting custom field value."""
    logger.info("=" * 60)
    logger.info("Example 3: Get Custom Field Value")
    logger.info("=" * 60)

    try:
        item_id = "PVTI_lADOABcDEF4Aa1bc"  # Replace with actual item ID
        field_name = "Status"

        value = await graphql.get_custom_field_value(item_id, field_name)
        logger.info("Field '%s' value: %s", field_name, value)
    except GraphQLError:
        logger.exception("Error getting field value")


async def demo_update_status(graphql: GitHubGraphQL) -> None:
    """Demonstrate updating project item status."""
    logger.info("=" * 60)
    logger.info("Example 4: Update Project Item Status")
    logger.info("=" * 60)

    try:
        project_id = "PVT_kwDOABcDEF"
        item_id = "PVTI_lADOABcDEF4Aa1bc"
        field_id = "PVTF_lADOABcDEF4Aa1bd"  # Status field ID
        option_id = "PVTSSF_lADOABcDEF4Aa1be"  # "Done" option ID

        success = await graphql.update_project_item_status(
            project_id=project_id,
            item_id=item_id,
            field_id=field_id,
            option_id=option_id,
        )

        if success:
            logger.info("✅ Successfully updated item status")
        else:
            logger.error("❌ Failed to update item status")
    except GraphQLError:
        logger.exception("Error updating status")


async def main() -> None:
    """Main example function."""
    # Initialize the GraphQL client
    token = os.getenv("GITHUB_TOKEN", "your_token_here")
    project_id = "PVT_kwDOABcDEF"  # Replace with your project ID

    async with GitHubGraphQL(token=token) as graphql:
        await demo_project_details(graphql, project_id)
        await demo_project_items(graphql, project_id)
        await demo_custom_field_value(graphql)
        await demo_update_status(graphql)

        logger.info("=" * 60)
        logger.info("Examples completed!")
        logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
