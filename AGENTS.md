# AGENTS.md - Parallel Codegen Orchestrator Implementation Guide

## Project Overview

This repository implements a parallel agent orchestration system that uses the Codegen API for concurrent code generation tasks with dependency management via topological sorting. The orchestrator fetches tasks from GitHub (issues/projects), constructs a dependency graph, and executes tasks in parallel using a pool of up to 10 Codegen agents while respecting dependency constraints.

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│                    Main Orchestrator                         │
│  (Entry Point + CLI + Configuration Management)              │
└─────────────────┬───────────────────────────────────────────┘
                  │
    ┌─────────────┴─────────────┐
    │                           │
┌───▼────────────────┐  ┌──────▼──────────────┐
│  GitHub Integration│  │  Dependency Graph   │
│  (REST + GraphQL)  │  │  (Topological Sort) │
│  - Fetch Issues    │  │  - Build DAG        │
│  - Parse Deps      │  │  - Cycle Detection  │
│  - Post Results    │  │  - Dynamic Updates  │
└───┬────────────────┘  └──────┬──────────────┘
    │                          │
    └─────────┬────────────────┘
              │
    ┌─────────▼──────────────────────────┐
    │    Task Orchestrator Loop          │
    │  - Get ready tasks from graph      │
    │  - Dispatch with asyncio.gather    │
    │  - Mark completed tasks            │
    │  - Collect results                 │
    └─────────┬──────────────────────────┘
              │
    ┌─────────▼──────────────────────────┐
    │    Concurrent Task Executor        │
    │  - Semaphore (max 10 concurrent)   │
    │  - Agent allocation & lifecycle    │
    │  - Timeout & retry handling        │
    └─────────┬──────────────────────────┘
              │
    ┌─────────▼──────────────────────────┐
    │         Agent Pool Manager         │
    │  - Pool of 10 Codegen agents       │
    │  - Status tracking (IDLE/BUSY)     │
    │  - Agent allocation & recovery     │
    └────────────────────────────────────┘
```

## Technology Stack

- **Python**: 3.13+
- **Core Libraries**:
  - `graphlib` - Built-in topological sorting
  - `asyncio` - Async/concurrent execution
  - `PyGithub` (>=2.6.1) - GitHub REST API
  - `httpx` (>=0.27.0) - GitHub GraphQL API
  - `codegen` (>=0.56.17) - Codegen SDK
  - `pydantic` (>=2.0) - Configuration management
  - `structlog` (>=24.0) - Structured logging
  - `PyYAML` (>=6.0) - Configuration parsing
  - `pytest` (>=7.0) - Testing framework

## Implementation Phases

### Phase 1: GitHub Integration Setup

**Goal**: Establish robust GitHub API integration for fetching tasks and posting results.

#### Issue #1: GitHub REST API Integration with PyGithub
- Authenticate with GitHub token
- Fetch issues with filtering (state, labels)
- Update issue status and labels programmatically
- Create branches for agent work
- Post comments to issues/PRs
- Handle pagination and rate limits

**Key Implementation Points**:
```python
from github import Github

class GitHubIntegration:
    def __init__(self, token: str, org_id: str):
        self.github = Github(token)
    
    async def fetch_issues(self, repo_name: str, state='open'):
        repo = self.github.get_repo(repo_name)
        return repo.get_issues(state=state)
```

#### Issue #2: GitHub GraphQL Integration for Projects v2
- Use httpx async client for GraphQL queries
- Fetch project boards and items
- Query custom fields from Projects v2
- Update project item status
- Implement cursor-based pagination

**Key Implementation Points**:
```python
import httpx

class GitHubGraphQL:
    def __init__(self, token: str):
        self.client = httpx.AsyncClient(
            base_url="https://api.github.com/graphql",
            headers={"Authorization": f"Bearer {token}"}
        )
```

#### Issue #3: Dependency Parsing from Issues
- Parse issue body for dependency markers:
  - `Depends on #123`
  - `Blocked by #456`
  - `Requires #789`
- Extract dependencies from labels (e.g., `depends:issue-123`)
- Validate dependency references
- Return structured dependency data

**Key Implementation Points**:
```python
import re
from typing import Set

class DependencyParser:
    DEPENDENCY_PATTERNS = [
        r'Depends on #(\d+)',
        r'Blocked by #(\d+)',
        r'Requires #(\d+)',
    ]
    
    def parse_dependencies(self, issue_body: str, labels: list) -> Set[str]:
        dependencies = set()
        for pattern in self.DEPENDENCY_PATTERNS:
            matches = re.findall(pattern, issue_body, re.IGNORECASE)
            dependencies.update(f"issue-{num}" for num in matches)
        return dependencies
```

### Phase 2: Dependency Graph Builder

**Goal**: Build and validate a DAG (Directed Acyclic Graph) using Python's graphlib.

#### Issue #4: Dependency Graph Construction with graphlib
- Wrap `graphlib.TopologicalSorter` in `DependencyGraph` class
- Add tasks with dependencies
- Build and validate DAG (detect cycles)
- Implement `get_ready_tasks()` - returns tasks with all dependencies met
- Implement `mark_completed()` - mark tasks as done
- Support dynamic graph updates

**Key Implementation Points**:
```python
from graphlib import TopologicalSorter
from typing import Dict, Set

class DependencyGraph:
    def __init__(self):
        self.graph: Dict[str, Set[str]] = {}
        self.sorter: TopologicalSorter = None
    
    def add_task(self, task_id: str, dependencies: Set[str]):
        self.graph[task_id] = dependencies
    
    def build(self):
        self.sorter = TopologicalSorter(self.graph)
        try:
            self.sorter.prepare()
        except ValueError as e:
            raise Exception(f"Cycle detected: {e}")
    
    def get_ready_tasks(self) -> tuple:
        if self.sorter and self.sorter.is_active():
            return self.sorter.get_ready()
        return ()
    
    def mark_completed(self, *task_ids: str):
        self.sorter.done(*task_ids)
```

#### Issue #5: Graph Validation and Cycle Detection
- Detect cycles with detailed path reporting
- Validate all task references exist
- Check for orphaned tasks
- Generate validation reports
- Implement graph visualization for debugging

### Phase 3: Agent Pool & Orchestrator

**Goal**: Manage a pool of Codegen agents for parallel execution.

#### Issue #6: Agent Pool Manager Implementation
- Initialize pool with configurable agent count (max 10)
- Track agent status: IDLE, BUSY, FAILED
- Implement `get_idle_agent()` - allocate available agent
- Implement `mark_busy()` and `mark_idle()` - status transitions
- Handle agent failure and recovery
- Provide pool statistics

**Key Implementation Points**:
```python
from enum import Enum
from dataclasses import dataclass
from codegen import Agent

class AgentStatus(Enum):
    IDLE = "idle"
    BUSY = "busy"
    FAILED = "failed"

@dataclass
class ManagedAgent:
    id: int
    agent: Agent
    status: AgentStatus
    current_task: Optional[str] = None

class AgentPool:
    def __init__(self, org_id: str, token: str, max_agents: int = 10):
        self.agents: list[ManagedAgent] = []
        self._initialize_pool()
```

#### Issue #7: Codegen Agent Integration
- Initialize Codegen agents with org_id and token
- Execute agent tasks with prompt and repo_id
- Implement async polling for task completion
- Handle task status: pending, running, completed, failed
- Extract and store results
- Implement timeout handling (default 600s)
- Add retry logic for transient failures

**Key Implementation Points**:
```python
from codegen import Agent
import asyncio

class CodegenExecutor:
    def __init__(self, agent: Agent, timeout_seconds: int = 600):
        self.agent = agent
        self.timeout = timeout_seconds
    
    async def execute_task(self, task_data: dict) -> dict:
        task = self.agent.run(
            prompt=task_data['prompt'],
            repo_id=task_data['repo_id']
        )
        
        # Poll for completion with timeout
        start_time = asyncio.get_event_loop().time()
        while task.status not in ['completed', 'failed']:
            if asyncio.get_event_loop().time() - start_time > self.timeout:
                raise TimeoutError(f"Task exceeded timeout of {self.timeout}s")
            await asyncio.sleep(2)
            task.refresh()
        
        return {
            'status': task.status,
            'result': task.result if task.status == 'completed' else None,
            'error': task.error if task.status == 'failed' else None
        }
```

### Phase 4: Asyncio Task Execution

**Goal**: Implement concurrent task execution with dependency-aware orchestration.

#### Issue #8: Concurrent Task Executor with Semaphore
- Create `TaskExecutor` class with `asyncio.Semaphore`
- Limit concurrent execution to agent pool size (max 10)
- Execute tasks using agents from pool
- Handle task lifecycle: dispatch → execute → complete
- Implement timeout handling
- Track active tasks and results
- Support graceful cancellation

**Key Implementation Points**:
```python
import asyncio

class TaskExecutor:
    def __init__(self, agent_pool: AgentPool, dep_graph: DependencyGraph):
        self.agent_pool = agent_pool
        self.dep_graph = dep_graph
        self.semaphore = asyncio.Semaphore(agent_pool.max_agents)
        self.task_results: Dict[str, Any] = {}
    
    async def execute_task(self, task_id: str, task_data: dict) -> dict:
        async with self.semaphore:
            agent = self.agent_pool.get_idle_agent()
            while agent is None:
                await asyncio.sleep(0.1)
                agent = self.agent_pool.get_idle_agent()
            
            self.agent_pool.mark_busy(agent, task_id)
            try:
                # Execute task
                result = await agent.execute(task_data)
                return result
            finally:
                self.agent_pool.mark_idle(agent)
```

#### Issue #9: Main Orchestration Loop with Topological Execution
- Integrate `DependencyGraph` with `TaskExecutor`
- Implement main loop using topological sorting
- Fetch ready tasks iteratively
- Dispatch ready tasks using `asyncio.gather`
- Mark completed tasks in graph
- Continue until all tasks processed
- Handle partial failures without blocking independent tasks

**Key Implementation Points**:
```python
class TaskOrchestrator:
    def __init__(self, executor: TaskExecutor):
        self.executor = executor
    
    async def orchestrate(self, tasks: Dict[str, dict]) -> list:
        results = []
        
        while self.executor.dep_graph.is_active():
            ready_task_ids = self.executor.dep_graph.get_ready_tasks()
            
            if not ready_task_ids:
                await asyncio.sleep(0.5)
                continue
            
            task_coroutines = [
                self.executor.execute_task(task_id, tasks[task_id])
                for task_id in ready_task_ids
            ]
            
            completed = await asyncio.gather(
                *task_coroutines, 
                return_exceptions=True
            )
            
            # Process results and mark completed
            for task_result in completed:
                if not isinstance(task_result, Exception):
                    results.append(task_result)
            
            completed_ids = [
                r['task_id'] for r in completed 
                if not isinstance(r, Exception)
            ]
            self.executor.dep_graph.mark_completed(*completed_ids)
        
        return results
```

#### Issue #10: Task Result Collection and Management
- Create `ResultManager` class for centralized storage
- Store results with metadata (task_id, status, duration, agent_id)
- Track success/failure counts
- Implement result aggregation by status
- Generate execution summary reports
- Support result export (JSON, CSV)
- Handle partial results from failed tasks

**Key Implementation Points**:
```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class TaskResult:
    task_id: str
    status: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    agent_id: int
    result: Optional[dict] = None
    error: Optional[str] = None

class ResultManager:
    def __init__(self):
        self.results: Dict[str, TaskResult] = {}
        self.success_count: int = 0
        self.failure_count: int = 0
    
    def get_summary(self) -> dict:
        return {
            'total_tasks': len(self.results),
            'successful': self.success_count,
            'failed': self.failure_count
        }
```

#### Issue #11: Dynamic Dependency Discovery and Graph Updates
- Support adding tasks dynamically during execution
- Implement thread-safe graph updates
- Rebuild topological sort on updates
- Validate no cycles introduced
- Queue newly discovered tasks
- Handle concurrent graph update race conditions

**Key Implementation Points**:
```python
class DynamicDependencyManager:
    def __init__(self, dep_graph: DependencyGraph):
        self.dep_graph = dep_graph
        self.lock = asyncio.Lock()
        self.new_tasks_queue = asyncio.Queue()
    
    async def add_dynamic_tasks(self, new_tasks: Dict[str, dict]):
        async with self.lock:
            for task_id, task_data in new_tasks.items():
                if self._would_create_cycle(task_id, task_data['dependencies']):
                    raise ValueError(f"Adding task {task_id} would create cycle")
                self.dep_graph.add_task(task_id, task_data['dependencies'])
            self.dep_graph.rebuild()
```

#### Issue #12: Main Entry Point and CLI Integration
- Create main async entry point (main.py)
- Initialize all components in order
- Load configuration from file
- Fetch tasks from GitHub
- Build dependency graph
- Execute orchestration loop
- Post results back to GitHub
- Implement CLI with argparse/click
- Add verbose/debug modes
- Handle graceful shutdown (SIGINT/SIGTERM)

**Key Implementation Points**:
```python
import asyncio
import sys

async def main():
    try:
        # Load configuration
        config = OrchestratorConfig.from_yaml("config.yaml")
        
        # Initialize GitHub
        github = GitHubIntegration(config.github.token, config.github.organization)
        
        # Fetch tasks
        tasks = await fetch_tasks_from_github(config.github)
        
        # Build dependency graph
        dep_graph = build_dependency_graph(tasks)
        
        # Initialize agent pool
        agent_pool = AgentPool(
            config.codegen.org_id,
            config.codegen.api_token,
            config.agent.max_concurrent_agents
        )
        
        # Execute orchestration
        executor = TaskExecutor(agent_pool, dep_graph)
        orchestrator = TaskOrchestrator(executor)
        results = await orchestrator.orchestrate(tasks)
        
        # Post results
        if config.automation.post_results_as_comment:
            await post_results_to_github(github, results, config.automation)
        
        return results
        
    except KeyboardInterrupt:
        logger.warning("orchestration_interrupted")
        sys.exit(1)
    except Exception as e:
        logger.error("orchestration_failed", error=str(e))
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
```

### Phase 5: Configuration & Automation

**Goal**: Implement configuration management and GitHub automation features.

#### Issue #13: Configuration Management with Pydantic
- Define Pydantic models for all settings
- Parse YAML/JSON config files
- Implement validation rules (min/max agents, required fields)
- Support environment variable overrides
- Provide error handling for invalid config

**Key Configuration Structure**:
```python
from pydantic import BaseModel, Field

class AgentConfig(BaseModel):
    max_concurrent_agents: int = Field(default=10, ge=1, le=10)
    task_timeout_seconds: int = Field(default=600, ge=60)
    retry_attempts: int = Field(default=3, ge=0)
    retry_delay_seconds: int = Field(default=30, ge=5)

class GitHubConfig(BaseModel):
    token: str
    organization: str
    repository: str
    project_number: Optional[int] = None
    default_branch: str = "main"

class CodegenConfig(BaseModel):
    org_id: str
    api_token: str
    base_url: Optional[str] = None

class AutomationConfig(BaseModel):
    auto_merge_on_success: bool = False
    post_results_as_comment: bool = True
    update_issue_status: bool = True
    status_label_prefix: str = "status:"

class OrchestratorConfig(BaseModel):
    github: GitHubConfig
    codegen: CodegenConfig
    agent: AgentConfig
    automation: AutomationConfig
    logging_level: str = "INFO"
```

#### Issue #14: Structured Logging with structlog
- Configure structlog for contextual logging
- Log significant events (dispatch, completion, error)
- Add correlation IDs and timestamps
- Use JSONRenderer for output
- Support adjustable logging levels
- Integrate into all components

**Key Implementation Points**:
```python
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()
logger.info("task_dispatched", task_id=task_id, agent_id=agent.id)
```

#### Issue #15: GitHub Automation Features
- Post orchestration results as GitHub comments
- Auto-merge successful PRs (configurable)
- Update issue status/labels automatically
- Support status label prefix from config
- Provide toggles for automation features
- Handle GitHub rate limits

#### Issue #16: Retry Logic and Failure Handling
- Implement exponential backoff for retries
- Make retry behavior configurable
- Only retry recoverable/transient failures
- Log all retry events
- Expose retry status in task results

**Key Implementation Points**:
```python
async def execute_with_retry(task_id: str, task_data: dict, max_attempts: int = 3):
    for attempt in range(max_attempts):
        try:
            result = await execute_task(task_id, task_data)
            if result['status'] == 'completed':
                return result
        except Exception as e:
            if attempt == max_attempts - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

#### Issue #17: Progress Monitoring and Metrics
- Create `ProgressMonitor` class
- Track task states (completed, failed, in progress)
- Update stats after status changes
- Provide real-time reporting (JSON/dict)
- Expose metrics (throughput, duration, remaining)
- Support dashboard/CLI integration
- Log snapshots at regular intervals

### Phase 6: Testing & Monitoring

**Goal**: Comprehensive testing and performance validation.

#### Issue #18: Unit Tests for Dependency Graph
- Test adding/removing tasks
- Test marking completion
- Test cycle detection
- Validate topological sort order
- Test dynamic graph updates (concurrency, race conditions)
- Achieve high coverage with pytest

#### Issue #19: Unit & Integration Tests for Agent Pool
- Test agent allocation and status transitions
- Test edge cases (no idle agents, max agents)
- Test concurrent allocation
- Test agent recovery/failure scenarios
- Mock agents for deterministic results

#### Issue #20: Integration Tests with Mock APIs
- Mock GitHub and Codegen APIs
- Simulate various task inputs
- Test orchestration and dependency resolution
- Assert expected outputs for all flows
- Test error cases (API failure, timeouts, retries)

#### Issue #21: End-to-End Orchestration Tests
- Full workflow validation with mocked/real endpoints
- Test against sample repo/project board
- Assert final status for all tasks
- Test results posting and auto-merge
- Handle shutdown and recovery paths

#### Issue #22: Performance Benchmarking
- Benchmark parallel vs. sequential execution
- Test variable agent pool sizes (1-10)
- Measure execution time, throughput, efficiency
- Report and visualize results
- Integrate with CI for regression checks

#### Issue #23: Error Scenario Testing
- Simulate API failures, timeouts, network issues
- Validate retry/backoff triggers
- Assert clear error reporting
- Test partial result handling
- Test shutdown/recovery after critical failure

#### Issue #24: Documentation and Usage Guides
- Comprehensive README with setup instructions
- Inline code documentation
- Architecture overview diagram
- Configuration guide, troubleshooting, FAQ
- Examples and templates
- CI/CD integration guide

## Key Design Principles

### 1. **Dependency-Aware Parallel Execution**
- Tasks execute as soon as dependencies are met
- Independent tasks run concurrently (up to 10)
- No artificial synchronization barriers
- Failures don't block independent task paths

### 2. **Robust Error Handling**
- Retry logic with exponential backoff
- Graceful degradation for transient failures
- Clear error reporting and logging
- Partial result preservation

### 3. **Configuration-Driven**
- All settings externalized to config files
- Environment variable overrides
- Validation with Pydantic
- Sensible defaults provided

### 4. **Observability**
- Structured logging with correlation IDs
- Real-time progress monitoring
- Execution metrics and statistics
- Result persistence for analysis

### 5. **Testing**
- Unit tests for all components
- Integration tests with mocked APIs
- End-to-end orchestration tests
- Performance benchmarking
- Error scenario coverage

## Project File Structure

```
parallel-codegen-orchestrator/
├── README.md
├── AGENTS.md                    # This file
├── config.yaml                  # Configuration file
├── requirements.txt             # Python dependencies
├── main.py                      # Main entry point
├── src/
│   ├── __init__.py
│   ├── config.py                # Configuration models (Issue #13)
│   ├── github/
│   │   ├── __init__.py
│   │   ├── rest_api.py          # GitHub REST API (Issue #1)
│   │   ├── graphql_api.py       # GitHub GraphQL API (Issue #2)
│   │   └── dependency_parser.py # Dependency parsing (Issue #3)
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── dependency_graph.py  # Dependency graph (Issue #4)
│   │   └── validator.py         # Graph validation (Issue #5)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── agent_pool.py        # Agent pool manager (Issue #6)
│   │   └── codegen_executor.py  # Codegen integration (Issue #7)
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── task_executor.py     # Task executor (Issue #8)
│   │   ├── orchestrator.py      # Main orchestration (Issue #9)
│   │   ├── result_manager.py    # Result management (Issue #10)
│   │   ├── dynamic_deps.py      # Dynamic dependencies (Issue #11)
│   │   ├── retry.py             # Retry logic (Issue #16)
│   │   └── progress.py          # Progress monitoring (Issue #17)
│   ├── automation/
│   │   ├── __init__.py
│   │   └── github_automation.py # GitHub automation (Issue #15)
│   └── logging.py               # Structured logging (Issue #14)
├── tests/
│   ├── __init__.py
│   ├── test_dependency_graph.py # Issue #18
│   ├── test_agent_pool.py       # Issue #19
│   ├── test_integration.py      # Issue #20
│   ├── test_e2e.py              # Issue #21
│   ├── test_performance.py      # Issue #22
│   └── test_errors.py           # Issue #23
└── docs/
    └── architecture.md          # Architecture docs (Issue #24)
```

## Implementation Order & Dependencies

### Critical Path
1. **Phase 1** (Issues #1-3): GitHub Integration → Enables task fetching
2. **Phase 2** (Issues #4-5): Dependency Graph → Core orchestration logic
3. **Phase 3** (Issues #6-7): Agent Pool → Execution capability
4. **Phase 4** (Issues #8-12): Orchestration → Complete system integration
5. **Phase 5** (Issues #13-17): Configuration & Automation → Production readiness
6. **Phase 6** (Issues #18-24): Testing & Documentation → Quality assurance

### Dependency Map
```
#1 (GitHub REST) ──┬──> #3 (Dep Parsing) ──> #4 (Dep Graph) ──┬──> #8 (Executor)
                   │                                            │
#2 (GitHub GraphQL)┘                                            │
                                                                │
#6 (Agent Pool) ──> #7 (Codegen) ────────────────────────────> #8
                                                                │
                                                                ▼
                                                            #9 (Orchestrator)
                                                                │
                                    ┌───────────────────────────┼───────────────┐
                                    ▼                           ▼               ▼
                                #10 (Results)              #11 (Dynamic)   #12 (Main)
                                                                                │
                            ┌───────────────────────────────────────────────────┤
                            ▼                                                   ▼
                    #13 (Config) ──> #14 (Logging) ──> #15-17 (Automation)    │
                                                                                │
                                            ┌───────────────────────────────────┘
                                            ▼
                                    #18-24 (Testing & Docs)
```

## Configuration Example

```yaml
github:
  token: ${GITHUB_TOKEN}
  organization: "dscv101"
  repository: "parallel-codegen-orchestrator"
  project_number: 1
  default_branch: "main"

codegen:
  org_id: ${CODEGEN_ORG_ID}
  api_token: ${CODEGEN_API_TOKEN}
  base_url: null

agent:
  max_concurrent_agents: 10
  task_timeout_seconds: 600
  retry_attempts: 3
  retry_delay_seconds: 30

automation:
  auto_merge_on_success: false
  post_results_as_comment: true
  update_issue_status: true
  status_label_prefix: "status:"

logging_level: "INFO"
```

## Usage Examples

### Basic Usage
```bash
# Run orchestrator with config file
python main.py --config config.yaml

# Verbose mode
python main.py --config config.yaml --verbose

# Debug mode with detailed logging
python main.py --config config.yaml --debug

# Dry run (validate without executing)
python main.py --config config.yaml --dry-run
```

### Programmatic Usage
```python
import asyncio
from src.config import OrchestratorConfig
from main import main

async def run_orchestration():
    config = OrchestratorConfig.from_yaml("config.yaml")
    results = await main()
    print(f"Completed {len(results)} tasks")

asyncio.run(run_orchestration())
```

## Testing Strategy

### Unit Tests
- Test each component in isolation
- Mock external dependencies
- Focus on edge cases and error conditions
- Target 80%+ code coverage

### Integration Tests
- Test component interactions
- Use mocked APIs for isolation
- Validate data flow between components
- Test concurrent execution scenarios

### End-to-End Tests
- Full orchestration workflow
- Real or well-mocked APIs
- Multiple tasks with dependencies
- Result posting and automation
- Error and recovery paths

### Performance Tests
- Benchmark parallel vs. sequential execution
- Test scaling with agent pool sizes
- Measure throughput and latency
- Identify bottlenecks

## Common Pitfalls & Solutions

### 1. **Circular Dependencies**
- **Problem**: Tasks reference each other in cycles
- **Solution**: Validate graph before execution, provide clear cycle path in error

### 2. **Race Conditions in Agent Pool**
- **Problem**: Multiple tasks trying to allocate same agent
- **Solution**: Use asyncio.Lock for agent state transitions

### 3. **GitHub Rate Limits**
- **Problem**: API calls exceed rate limits
- **Solution**: Implement exponential backoff, batch operations, cache results

### 4. **Task Timeouts**
- **Problem**: Agents hang indefinitely
- **Solution**: Implement configurable timeouts with graceful cleanup

### 5. **Memory Leaks in Long-Running Orchestration**
- **Problem**: Result accumulation consumes memory
- **Solution**: Stream results to disk, implement periodic cleanup

### 6. **Graceful Shutdown**
- **Problem**: SIGINT leaves tasks in inconsistent state
- **Solution**: Catch signals, cancel pending tasks, save partial results

## Monitoring & Observability

### Structured Logging
All components emit structured logs with:
- **Timestamp**: ISO format
- **Level**: INFO, WARNING, ERROR, DEBUG
- **Event**: Descriptive event name (e.g., "task_dispatched")
- **Context**: task_id, agent_id, duration, status
- **Correlation ID**: Trace requests across components

### Metrics to Track
- Total tasks executed
- Success/failure rates
- Average task duration
- Agent utilization (% time busy)
- API call counts and errors
- Queue depths and wait times

### Health Checks
- Agent pool status (idle/busy counts)
- Dependency graph state (active/completed)
- API connectivity (GitHub, Codegen)
- Queue depths and backlog

## Security Considerations

1. **API Token Management**
   - Store tokens in environment variables
   - Never commit tokens to repository
   - Use least-privilege tokens
   - Rotate tokens regularly

2. **Input Validation**
   - Validate all configuration inputs
   - Sanitize issue body content
   - Validate dependency references

3. **Rate Limiting**
   - Respect GitHub API rate limits
   - Implement backoff strategies
   - Monitor rate limit headers

4. **Error Information Disclosure**
   - Avoid leaking sensitive data in logs
   - Sanitize error messages
   - Use structured logging for debugging

## Success Criteria

A successful implementation will:
1. ✅ Fetch tasks from GitHub (issues/projects)
2. ✅ Parse dependencies from issue descriptions
3. ✅ Build valid dependency graph with cycle detection
4. ✅ Execute up to 10 tasks concurrently
5. ✅ Respect task dependencies (topological order)
6. ✅ Handle failures gracefully without blocking independent tasks
7. ✅ Post results back to GitHub
8. ✅ Support configuration via YAML/JSON
9. ✅ Provide structured logging and monitoring
10. ✅ Include comprehensive test coverage
11. ✅ Complete documentation and usage guides

## References & Resources

- [Python graphlib Documentation](https://docs.python.org/3/library/graphlib.html)
- [asyncio Documentation](https://docs.python.org/3/library/asyncio.html)
- [PyGithub Documentation](https://pygithub.readthedocs.io/)
- [GitHub REST API](https://docs.github.com/en/rest)
- [GitHub GraphQL API](https://docs.github.com/en/graphql)
- [GitHub Projects v2 API](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects)
- [Codegen API Reference](https://docs.codegen.com/api-reference/overview)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [structlog Documentation](https://www.structlog.org/en/stable/)
- [pytest Documentation](https://docs.pytest.org/en/stable/)

## Contribution Guidelines

When implementing features:
1. Follow the phase order and dependency chain
2. Write tests alongside implementation
3. Use structured logging for all significant events
4. Document complex logic with inline comments
5. Update this AGENTS.md if architecture changes
6. Run full test suite before submitting
7. Update issue status and labels upon completion

## Getting Started Checklist

For coding agents starting work:
- [ ] Read this entire AGENTS.md document
- [ ] Review all open issues in GitHub (#1-24)
- [ ] Understand the epic structure (Issue #25)
- [ ] Set up development environment
- [ ] Install dependencies from requirements.txt
- [ ] Configure API tokens (GitHub, Codegen)
- [ ] Run existing tests to verify setup
- [ ] Start with Phase 1, Issue #1
- [ ] Follow dependency chain for implementation order
- [ ] Update issue status as you progress

---

**Document Version**: 1.0  
**Last Updated**: 2025-11-17  
**Maintained By**: Project Orchestrator Team