"""Example usage of GitHub GraphQL API integration.

This example demonstrates how to use the GitHubGraphQL class to:
- Fetch project items from GitHub Projects v2
- Query custom field values
- Update project item status
- Manage labels and assignees
"""

import asyncio
import os

from src.github.graphql_api import GitHubGraphQL, GraphQLError


async def main():
    """Main example function."""
    # Initialize the GraphQL client
    token = os.getenv("GITHUB_TOKEN", "your_token_here")
    
    async with GitHubGraphQL(token=token) as graphql:
        # Example 1: Fetch project details
        print("=" * 60)
        print("Example 1: Fetch Project Details")
        print("=" * 60)
        
        try:
            project_id = "PVT_kwDOABcDEF"  # Replace with your project ID
            details = await graphql.fetch_project_details(project_id)
            
            print(f"Project: {details['title']}")
            print(f"Description: {details.get('shortDescription', 'N/A')}")
            print(f"Public: {details['public']}")
            print("\nCustom Fields:")
            for field in details['fields']['nodes']:
                print(f"  - {field['name']} ({field['dataType']})")
                if 'options' in field:
                    print(f"    Options: {[opt['name'] for opt in field['options']]}")
        except GraphQLError as e:
            print(f"Error fetching project details: {e}")
        
        # Example 2: Fetch all project items
        print("\n" + "=" * 60)
        print("Example 2: Fetch Project Items")
        print("=" * 60)
        
        try:
            items = await graphql.fetch_project_items(project_id="PVT_kwDOABcDEF")
            
            print(f"Found {len(items)} items in project")
            for item in items[:5]:  # Show first 5
                content = item.get('content', {})
                print(f"\n  #{content.get('number')}: {content.get('title')}")
                print(f"  State: {content.get('state')}")
                print(f"  URL: {content.get('url')}")
                
                # Show custom field values
                field_values = item.get('fieldValues', {}).get('nodes', [])
                if field_values:
                    print("  Custom Fields:")
                    for fv in field_values:
                        field_name = fv.get('field', {}).get('name', 'Unknown')
                        value = fv.get('name') or fv.get('text') or fv.get('date') or fv.get('number')
                        if value:
                            print(f"    - {field_name}: {value}")
        except GraphQLError as e:
            print(f"Error fetching items: {e}")
        
        # Example 3: Get custom field value
        print("\n" + "=" * 60)
        print("Example 3: Get Custom Field Value")
        print("=" * 60)
        
        try:
            item_id = "PVTI_lADOABcDEF4Aa1bc"  # Replace with actual item ID
            field_name = "Status"
            
            value = await graphql.get_custom_field_value(item_id, field_name)
            print(f"Field '{field_name}' value: {value}")
        except GraphQLError as e:
            print(f"Error getting field value: {e}")
        
        # Example 4: Update project item status
        print("\n" + "=" * 60)
        print("Example 4: Update Project Item Status")
        print("=" * 60)
        
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
                print("✅ Successfully updated item status")
            else:
                print("❌ Failed to update item status")
        except GraphQLError as e:
            print(f"Error updating status: {e}")
        
        print("\n" + "=" * 60)
        print("Examples completed!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
