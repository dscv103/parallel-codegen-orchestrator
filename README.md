# Parallel Codegen Orchestrator

A parallel agent orchestration system using Codegen API for concurrent code generation tasks with dependency management via topological sorting.

## Features

- ✅ **GitHub REST API Integration** - Fetch issues/PRs, create branches, post comments
- ✅ **GitHub GraphQL Integration** - Projects v2 management, custom fields, queries
- 🔄 **Parallel Execution** - Up to 10 concurrent Codegen agents
- 📊 **Dependency Management** - Topological sorting with cycle detection
- 🔄 **Dynamic Dependency Discovery** - Tasks can discover and add new dependencies at runtime
- 🔐 **Rate Limit Handling** - Automatic rate limit monitoring and backoff
- 🧪 **Test Coverage** - Comprehensive unit tests (85%+ coverage)

## Quick Start

### Prerequisites

- Python 3.13+
- GitHub personal access token with `repo` permissions
- Codegen API credentials

### Installation

```bash
# Clone the repository
git clone https://github.com/dscv101/parallel-codegen-orchestrator.git
cd parallel-codegen-orchestrator

# Create virtual environment
python3.13 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Or install development dependencies
pip install PyGithub>=2.6.1 httpx>=0.27.0 codegen>=0.56.17 pydantic>=2.0 \
            structlog>=24.0 PyYAML>=6.0 pytest>=7.0 pytest-cov>=4.0
```

### Configuration

1. Copy the example configuration:
```bash
cp config.example.yaml config.yaml
```

2. Edit `config.yaml` with your credentials:
```yaml
github:
  token: "ghp_your_github_token_here"
  organization: "your-org"
  repository: "your-org/your-repo"

codegen:
  org_id: "your-codegen-org-id"
  api_token: "your-codegen-api-token"
```

## GitHub REST API Integration

The `GitHubIntegration` class provides comprehensive GitHub API functionality:

### Features

- ✅ Authentication with GitHub tokens
- ✅ Fetch issues with state/label filtering
- ✅ Fetch pull requests with metadata
- ✅ Update issue status and labels
- ✅ Create branches programmatically
- ✅ Post comments to issues/PRs
- ✅ Pagination support for large result sets
- ✅ Rate limit handling with automatic backoff

### Usage Example

```python
from src.github import GitHubIntegration

# Initialize
github = GitHubIntegration(
    token="ghp_your_token",
    org_id="your-org"
)

# Fetch open issues
issues = github.fetch_issues("owner/repo", state="open")
for issue in issues:
    print(f"#{issue.number}: {issue.title}")

# Create a new branch
github.create_branch(
    "owner/repo",
    branch_name="feature/new-feature",
    from_branch="main"
)

# Post a comment
github.post_comment(
    "owner/repo",
    issue_number=123,
    comment="Task completed successfully! ✅"
)

# Check rate limit
rate_info = github.get_rate_limit()
print(f"Remaining: {rate_info['remaining']}/{rate_info['limit']}")
```

## GitHub GraphQL Integration

The `GitHubGraphQL` class provides GitHub Projects v2 and advanced query functionality:

### Features

- ✅ Async httpx client for GraphQL queries
- ✅ Fetch project boards and items with pagination
- ✅ Retrieve custom field values from Projects v2
- ✅ Update project item status programmatically
- ✅ Manage labels and assignees on project items
- ✅ Automatic cursor-based pagination
- ✅ Comprehensive error handling

### Usage Example

```python
import asyncio
from src.github import GitHubGraphQL, GraphQLError

async def main():
    async with GitHubGraphQL(token="ghp_your_token") as graphql:
        # Fetch project details with custom fields
        project = await graphql.fetch_project_details("PVT_kwDOABcDEF")
        print(f"Project: {project['title']}")
        
        # Fetch all project items with pagination
        items = await graphql.fetch_project_items("PVT_kwDOABcDEF")
        for item in items:
            content = item['content']
            print(f"#{content['number']}: {content['title']}")
        
        # Get custom field value
        status = await graphql.get_custom_field_value(
            item_id="PVTI_lADOABcDEF4Aa1bc",
            field_name="Status"
        )
        print(f"Status: {status}")
        
        # Update project item status
        await graphql.update_project_item_status(
            project_id="PVT_kwDOABcDEF",
            item_id="PVTI_lADOABcDEF4Aa1bc",
            field_id="PVTF_lADOABcDEF4Aa1bd",
            option_id="PVTSSF_lADOABcDEF4Aa1be"
        )
        
        # Add labels
        await graphql.add_labels_to_item(
            item_id="I_kwDOABcDEF4Aa1bc",
            label_ids=["LA_kwDOABcDEF8AAAAA"]
        )

asyncio.run(main())
```

See [examples/graphql_usage.py](examples/graphql_usage.py) for more detailed examples.

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test files
pytest tests/test_github_rest.py -v
pytest tests/test_github_graphql.py -v

# Run with coverage
pytest tests/ --cov=src/github --cov-report=html
pytest tests/ --cov=src/github --cov-report=term-missing
```

## Dynamic Dependency Discovery

The orchestrator supports **dynamic dependency discovery**, allowing tasks to add new dependencies and tasks during execution. This enables adaptive workflows where tasks can spawn subtasks based on their findings.

### Key Features

- **Thread-Safe Graph Updates** - Uses `asyncio.Lock` for concurrent modifications
- **Cycle Detection** - Validates new dependencies won't create cycles
- **Automatic Rebuild** - Topological sort rebuilds after adding tasks
- **Task Callback Interface** - Clean API for tasks to report discoveries
- **Race Condition Handling** - Properly handles concurrent updates

### Usage Example

```python
from src.orchestrator import (
    DynamicDependencyManager,
    TaskExecutionContext,
)
from src.graph import DependencyGraph

# Initialize dependency graph and manager
dep_graph = DependencyGraph()
dep_graph.add_task("task-1", set())
dep_graph.build()

manager = DynamicDependencyManager(dep_graph)

# During task execution, use the context to discover new tasks
context = TaskExecutionContext(manager, "task-1")

# Discover a single task
await context.add_discovered_task(
    "task-discovered",
    dependencies={"task-1"},
    task_data={
        "prompt": "Follow-up work discovered during execution",
        "repo_id": "org/repo",
    },
)

# Or discover multiple tasks at once (more efficient)
await context.add_multiple_discovered_tasks({
    "task-a": {
        "dependencies": {"task-1"},
        "prompt": "Feature A",
        "repo_id": "org/repo",
    },
    "task-b": {
        "dependencies": {"task-1"},
        "prompt": "Feature B",
        "repo_id": "org/repo",
    },
})
```

### Use Cases

1. **Adaptive Planning** - Tasks spawn subtasks based on findings
   - Example: Test task discovers bugs, creates fix tasks dynamically
   
2. **Conditional Dependencies** - Dependencies discovered based on runtime conditions
   - Example: Only add migration task if schema changes detected
   
3. **Progressive Refinement** - Break down complex tasks into smaller ones dynamically
   - Example: Feature task discovers it needs 3 sub-features

### Error Handling

The system validates all dynamic task additions:

- **Cycle Detection** - Rejects tasks that would create circular dependencies
- **Dependency Validation** - Ensures all referenced dependencies exist
- **Type Checking** - Validates task data structure

```python
try:
    await context.add_discovered_task(
        "task-invalid",
        dependencies={"task-nonexistent"},  # Invalid dependency
        task_data={"prompt": "...", "repo_id": "..."},
    )
except DynamicTaskRegistrationError as e:
    logger.error(f"Failed to register task: {e}")
```

### Implementation Details

For detailed implementation information, see:
- `src/orchestrator/dynamic_deps.py` - Core dynamic dependency manager
- `src/graph/dependency_graph.py` - Graph copy and rebuild methods
- `tests/test_dynamic_deps.py` - Comprehensive test suite

## Project Status

### Phase 1: GitHub Integration Setup ✅

- [x] **Issue #1**: GitHub REST API Integration with PyGithub ✅
- [x] **Issue #2**: GitHub GraphQL Integration for Projects v2 ✅
- [ ] Issue #3: Dependency Parsing from Issues

## Documentation

For detailed implementation information, see:
- [AGENTS.md](AGENTS.md) - Comprehensive implementation guide
- [CI-CD-GUIDE.md](CI-CD-GUIDE.md) - CI/CD setup and workflows
- [CODEGEN-SETUP.md](CODEGEN-SETUP.md) - Codegen configuration

## License

MIT License - see LICENSE file for details
