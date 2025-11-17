# Codegen Setup Guide for Parallel Codegen Orchestrator

This guide provides setup instructions and commands for using Codegen (codegen-sh) to develop the Parallel Codegen Orchestrator project.

## Prerequisites

- Python 3.13+
- Git
- GitHub account
- Codegen account and organization

## Initial Setup

### 1. Install Codegen CLI

```bash
# Install via pip
pip install codegen

# Or install from source
git clone https://github.com/codegen-sh/codegen-python.git
cd codegen-python
pip install -e .

# Verify installation
codegen --version
```

### 2. Authenticate with Codegen

```bash
# Login to Codegen
codegen login

# Or set API token directly
export CODEGEN_API_TOKEN="your-api-token-here"

# Verify authentication
codegen whoami
```

### 3. Clone and Setup Repository

```bash
# Clone the repository
git clone https://github.com/dscv101/parallel-codegen-orchestrator.git
cd parallel-codegen-orchestrator

# Create virtual environment
python3.13 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt || echo "No requirements.txt yet"

# Install development tools
pip install ruff mypy black isort pytest pytest-cov pytest-asyncio pytest-mock
pip install bandit yamllint radon pre-commit

# Setup pre-commit hooks
pre-commit install
```

### 4. Create Initial Requirements File

```bash
cat > requirements.txt << 'EOF'
# Core dependencies
PyGithub>=2.6.1
httpx>=0.27.0
codegen>=0.56.17
pydantic>=2.0
structlog>=24.0
PyYAML>=6.0

# Testing
pytest>=7.0
pytest-cov>=4.0
pytest-asyncio>=0.21.0
pytest-mock>=3.0

# Development tools
ruff>=0.1.9
mypy>=1.8.0
black>=23.12.0
isort>=5.13.0
pre-commit>=3.5.0
EOF

pip install -r requirements.txt
```

## Codegen Configuration

### 5. Initialize Codegen

```bash
# Initialize Codegen in the repository
codegen init

# Set organization ID
export CODEGEN_ORG_ID="your-org-id"

# Configure repository
codegen config set repo-id dscv101/parallel-codegen-orchestrator
```

### 6. Create Codegen Configuration File

Create `.codegen.yaml`:

```yaml
# Codegen configuration for Parallel Codegen Orchestrator

project:
  name: parallel-codegen-orchestrator
  description: Parallel agent orchestration system with dependency management
  language: python
  version: "0.1.0"

python:
  version: "3.13"
  package_manager: pip
  virtual_env: .venv

generation:
  architecture_guide: AGENTS.md
  
  style:
    line_length: 100
    formatter: black
    linter: ruff
    type_checker: mypy
    docstring_style: google
  
  patterns:
    - async_await
    - dependency_injection
    - type_hints
    - structured_logging
    - error_handling
    - testing
  
  security:
    - no_hardcoded_secrets
    - input_validation
    - safe_api_calls
    - proper_authentication

testing:
  framework: pytest
  coverage_target: 80
  async_support: true
  fixtures: true
  mocking: true

structure:
  src_dir: src
  test_dir: tests
  docs_dir: docs
```

## Phase-by-Phase Implementation

### Phase 1: GitHub Integration (Issues #1-3)

```bash
# Issue #1: GitHub REST API
codegen run \
  --issue 1 \
  --file src/github/rest_api.py \
  --prompt "Implement GitHubIntegration class with PyGithub for REST API operations" \
  --context AGENTS.md

# Issue #2: GitHub GraphQL
codegen run \
  --issue 2 \
  --file src/github/graphql_api.py \
  --prompt "Implement GitHubGraphQL class using httpx for Projects v2 API" \
  --context AGENTS.md

# Issue #3: Dependency Parsing
codegen run \
  --issue 3 \
  --file src/github/dependency_parser.py \
  --prompt "Implement DependencyParser class to extract dependencies from issue bodies" \
  --context AGENTS.md
```

### Phase 2: Dependency Graph (Issues #4-5)

```bash
# Issue #4: Dependency Graph Construction
codegen run \
  --issue 4 \
  --file src/graph/dependency_graph.py \
  --prompt "Implement DependencyGraph class wrapping graphlib.TopologicalSorter" \
  --context AGENTS.md

# Issue #5: Graph Validation
codegen run \
  --issue 5 \
  --file src/graph/validator.py \
  --prompt "Implement GraphValidator class with cycle detection" \
  --context AGENTS.md
```

### Phase 3: Agent Pool (Issues #6-7)

```bash
# Issue #6: Agent Pool Manager
codegen run \
  --issue 6 \
  --file src/agents/agent_pool.py \
  --prompt "Implement AgentPool class managing up to 10 Codegen agents with asyncio.Lock" \
  --context AGENTS.md

# Issue #7: Codegen Agent Integration
codegen run \
  --issue 7 \
  --file src/agents/codegen_executor.py \
  --prompt "Implement CodegenExecutor class for agent task execution with async polling" \
  --context AGENTS.md
```

### Phase 4: Orchestration (Issues #8-12)

```bash
# Issue #8: Task Executor
codegen run \
  --issue 8 \
  --file src/orchestrator/task_executor.py \
  --prompt "Implement TaskExecutor class using asyncio.Semaphore" \
  --context AGENTS.md

# Issue #9: Main Orchestration Loop
codegen run \
  --issue 9 \
  --file src/orchestrator/orchestrator.py \
  --prompt "Implement TaskOrchestrator class with topological execution loop" \
  --context AGENTS.md

# Issue #10: Result Management
codegen run \
  --issue 10 \
  --file src/orchestrator/result_manager.py \
  --prompt "Implement ResultManager class for task result collection" \
  --context AGENTS.md

# Issue #11: Dynamic Dependencies
codegen run \
  --issue 11 \
  --file src/orchestrator/dynamic_deps.py \
  --prompt "Implement DynamicDependencyManager class for runtime graph updates" \
  --context AGENTS.md

# Issue #12: Main Entry Point
codegen run \
  --issue 12 \
  --file main.py \
  --prompt "Implement main async entry point with CLI and signal handling" \
  --context AGENTS.md
```

### Phase 5: Configuration & Automation (Issues #13-17)

```bash
# Issue #13: Configuration Management
codegen run \
  --issue 13 \
  --file src/config.py \
  --prompt "Implement Pydantic configuration models with validation" \
  --context AGENTS.md

# Issue #14: Structured Logging
codegen run \
  --issue 14 \
  --file src/logging.py \
  --prompt "Configure structlog with JSON renderer and correlation IDs" \
  --context AGENTS.md

# Issue #15: GitHub Automation
codegen run \
  --issue 15 \
  --file src/automation/github_automation.py \
  --prompt "Implement GitHub automation features for results posting" \
  --context AGENTS.md

# Issue #16: Retry Logic
codegen run \
  --issue 16 \
  --file src/orchestrator/retry.py \
  --prompt "Implement exponential backoff retry logic" \
  --context AGENTS.md

# Issue #17: Progress Monitoring
codegen run \
  --issue 17 \
  --file src/orchestrator/progress.py \
  --prompt "Implement ProgressMonitor class for real-time metrics" \
  --context AGENTS.md
```

### Phase 6: Testing & Documentation (Issues #18-24)

```bash
# Generate tests
codegen test generate --module src/graph/dependency_graph.py --output tests/test_dependency_graph.py
codegen test generate --module src/agents/agent_pool.py --output tests/test_agent_pool.py

# Issue #24: Documentation
codegen run \
  --issue 24 \
  --prompt "Generate comprehensive documentation with setup instructions" \
  --context AGENTS.md
```

## Batch Processing

```bash
# Process all Phase 1 issues sequentially
codegen batch run --issues 1,2,3 --sequential

# Process entire project (all 24 issues)
codegen batch run --issues 1-24 --sequential --context AGENTS.md

# Parallel processing (independent issues only)
codegen batch run --issues 1,6,13 --parallel --max-concurrent 3
```

## Python SDK Usage

Create `run_agents.py`:

```python
import asyncio
from codegen import Agent

async def run_phase_1():
    agent = Agent(
        org_id="your-org-id",
        api_token="your-api-token"
    )
    
    task = agent.run(
        prompt="Implement GitHub REST API integration per AGENTS.md Phase 1.1",
        repo_id="dscv101/parallel-codegen-orchestrator",
        files=["src/github/rest_api.py"],
        context_files=["AGENTS.md"]
    )
    
    while task.status not in ['completed', 'failed']:
        await asyncio.sleep(5)
        task.refresh()
        print(f"Status: {task.status}")
    
    return task

if __name__ == "__main__":
    asyncio.run(run_phase_1())
```

Run:
```bash
python run_agents.py
```

## Environment Variables

Create `.env`:

```bash
CODEGEN_ORG_ID=your-org-id
CODEGEN_API_TOKEN=your-api-token

GITHUB_TOKEN=your-github-token
GITHUB_ORGANIZATION=dscv101
GITHUB_REPOSITORY=parallel-codegen-orchestrator

MAX_CONCURRENT_AGENTS=10
TASK_TIMEOUT_SECONDS=600
RETRY_ATTEMPTS=3
LOGGING_LEVEL=INFO
```

Load:
```bash
source .env
```

## Monitoring and Review

```bash
# Sync GitHub issues
codegen sync issues --repo dscv101/parallel-codegen-orchestrator

# List all issues
codegen list issues

# Check agent status
codegen status

# Monitor progress
codegen watch --issue 1

# Review generated code
codegen review --issue 1

# Request changes
codegen review comment --issue 1 --comment "Add error handling"

# Approve and merge
codegen approve --issue 1
codegen merge --issue 1 --branch main
```

## Advanced Configuration

```bash
# Custom system prompt
codegen run \
  --issue 6 \
  --system-prompt "You are a Python async/await expert. Follow AGENTS.md strictly." \
  --user-prompt "Implement AgentPool with thread-safe allocation."

# Multiple context files
codegen run \
  --issue 8 \
  --context AGENTS.md \
  --context CODERABBIT.md \
  --context .coderabbit.yaml

# Enable verbose logging
codegen run --issue 1 --verbose --log-file codegen.log
```

## Best Practices

1. **Always reference AGENTS.md** in context
2. **Test incrementally** - run one phase at a time
3. **Review generated code** before merging
4. **Use CI/CD checks** to validate output
5. **Keep context small** - only essential files
6. **Monitor agent progress** with `codegen watch`
7. **Save logs** for debugging
8. **Follow dependency chain** from AGENTS.md

## Troubleshooting

### Authentication Failed
```bash
codegen logout
codegen login
```

### Agent Timeout
```bash
codegen run --issue 1 --timeout 1200  # 20 minutes
```

### Rate Limit Exceeded
```bash
sleep 60
codegen retry --issue 1
```

### Context Too Large
```bash
codegen run --issue 1 --context AGENTS.md  # Only essential
```

## Quick Start

```bash
# Complete setup in one go
git clone https://github.com/dscv101/parallel-codegen-orchestrator.git
cd parallel-codegen-orchestrator
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pre-commit install

# Configure Codegen
export CODEGEN_ORG_ID="your-org-id"
export CODEGEN_API_TOKEN="your-api-token"
codegen init

# Start with Phase 1
codegen run --issue 1 --context AGENTS.md
```

## Resources

- [Codegen Documentation](https://docs.codegen.com/)
- [Codegen Python SDK](https://github.com/codegen-sh/codegen-python)
- [AGENTS.md](./AGENTS.md) - Project architecture
- [CI-CD-GUIDE.md](./CI-CD-GUIDE.md) - Pipeline docs
- [CODERABBIT.md](./CODERABBIT.md) - Review guidelines

---

**Ready to start?** Run `codegen run --issue 1` to begin!