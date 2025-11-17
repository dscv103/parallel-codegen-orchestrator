# Parallel Codegen Orchestrator

A parallel agent orchestration system using Codegen API for concurrent code generation tasks with dependency management via topological sorting.

## Features

- ✅ **GitHub REST API Integration** - Fetch issues/PRs, create branches, post comments
- 🔄 **Parallel Execution** - Up to 10 concurrent Codegen agents
- 📊 **Dependency Management** - Topological sorting with cycle detection
- 🔐 **Rate Limit Handling** - Automatic rate limit monitoring and backoff
- 🧪 **Test Coverage** - Comprehensive unit tests (80%+ coverage)

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

## Testing

```bash
# Run tests
pytest tests/test_github_rest.py -v

# Run with coverage
pytest tests/test_github_rest.py --cov=src/github --cov-report=html
```

## Project Status

### Phase 1: GitHub Integration Setup ✅

- [x] **Issue #1**: GitHub REST API Integration with PyGithub
- [ ] Issue #2: GitHub GraphQL Integration for Projects v2
- [ ] Issue #3: Dependency Parsing from Issues

## Documentation

For detailed implementation information, see:
- [AGENTS.md](AGENTS.md) - Comprehensive implementation guide
- [CI-CD-GUIDE.md](CI-CD-GUIDE.md) - CI/CD setup and workflows
- [CODEGEN-SETUP.md](CODEGEN-SETUP.md) - Codegen configuration

## License

MIT License - see LICENSE file for details
