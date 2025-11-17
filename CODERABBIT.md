# CodeRabbit Review Instructions

This document provides detailed instructions for CodeRabbit AI to conduct effective code reviews for the Parallel Codegen Orchestrator project.

## Project Context

The Parallel Codegen Orchestrator is a sophisticated Python 3.13+ application that manages concurrent code generation tasks using:
- **Dependency Management**: DAG-based topological sorting with `graphlib`
- **Parallel Execution**: asyncio with semaphore-controlled concurrency (max 10 agents)
- **GitHub Integration**: REST and GraphQL APIs for task fetching and result posting
- **Agent Pool**: Managed pool of Codegen SDK agents with state tracking
- **Configuration**: Pydantic-based YAML/JSON configuration management
- **Observability**: Structured logging with `structlog` and metrics

## Architecture Reference

All code should align with the architecture defined in **AGENTS.md**. Key architectural components:

1. **GitHub Integration Layer** (`src/github/`) - REST, GraphQL, dependency parsing
2. **Dependency Graph** (`src/graph/`) - DAG construction, validation, cycle detection
3. **Agent Pool** (`src/agents/`) - Pool management, Codegen integration
4. **Orchestrator** (`src/orchestrator/`) - Task execution, result management, retry logic
5. **Configuration** (`src/config.py`) - Pydantic models and validation
6. **Automation** (`src/automation/`) - GitHub automation features

## Review Priorities

### 🔴 Critical (Must Address)

1. **Security Vulnerabilities**
   - Hardcoded credentials, tokens, or secrets
   - SQL injection or command injection risks
   - Unsafe deserialization
   - Exposure of sensitive data in logs
   - Insufficient input validation

2. **Correctness Issues**
   - Logic errors that could cause incorrect results
   - Race conditions in concurrent code
   - Deadlocks or resource leaks
   - Incorrect dependency graph operations
   - Cycle detection failures

3. **Data Loss Risks**
   - Missing error handling for critical operations
   - Improper transaction management
   - Missing rollback/cleanup on failures

### 🟡 Important (Should Address)

1. **Performance Issues**
   - Inefficient algorithms (O(n²) when O(n log n) is possible)
   - Unnecessary blocking operations in async code
   - Memory leaks or excessive memory usage
   - Missing pagination for large datasets
   - Inefficient API usage

2. **Maintainability**
   - Complex code without documentation
   - Violation of DRY principle
   - Poor separation of concerns
   - Missing type hints
   - Overly complex functions (cognitive complexity > 15)

3. **Testing Gaps**
   - Missing tests for critical paths
   - Insufficient edge case coverage
   - Missing error scenario tests
   - Inadequate mocking

### 🟢 Minor (Nice to Have)

1. **Code Style**
   - PEP 8 deviations
   - Inconsistent naming conventions
   - Missing docstrings for public APIs
   - Overly long lines (>100 characters)

2. **Documentation**
   - Missing inline comments for complex logic
   - Outdated docstrings
   - Missing README updates

## Python 3.13+ Best Practices

### Async/Await Patterns

✅ **Good:**
```python
async def execute_tasks(tasks: list[Task]) -> list[Result]:
    """Execute tasks concurrently with semaphore control."""
    async with asyncio.Semaphore(10) as sem:
        return await asyncio.gather(
            *(execute_single_task(task, sem) for task in tasks),
            return_exceptions=True
        )
```

❌ **Bad:**
```python
def execute_tasks(tasks):  # Missing type hints and async
    results = []
    for task in tasks:  # Sequential, not parallel
        results.append(execute_single_task(task))
    return results
```

### Type Hints (Python 3.13+)

✅ **Good:**
```python
from typing import Optional

def process_task(
    task_id: str,
    dependencies: set[str],
    config: dict[str, Any] | None = None
) -> TaskResult:
    """Process a single task with dependencies."""
    ...
```

❌ **Bad:**
```python
def process_task(task_id, dependencies, config=None):  # No type hints
    ...
```

### Error Handling

✅ **Good:**
```python
import structlog

logger = structlog.get_logger()

async def fetch_with_retry(url: str, max_attempts: int = 3) -> dict:
    """Fetch data with exponential backoff retry."""
    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            if attempt == max_attempts - 1:
                logger.error("fetch_failed", url=url, error=str(e))
                raise
            wait_time = 2 ** attempt
            logger.warning(
                "fetch_retry",
                url=url,
                attempt=attempt + 1,
                wait_seconds=wait_time
            )
            await asyncio.sleep(wait_time)
```

❌ **Bad:**
```python
async def fetch_with_retry(url, max_attempts=3):
    try:
        return await client.get(url).json()  # No retry, no logging
    except:  # Bare except, no context
        pass
```

### Resource Management

✅ **Good:**
```python
class AgentPool:
    """Managed pool of Codegen agents."""
    
    def __init__(self, size: int):
        self._agents: list[Agent] = []
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> Agent:
        """Acquire an idle agent from the pool."""
        async with self._lock:
            while not self._agents:
                await asyncio.sleep(0.1)
            return self._agents.pop()
    
    async def release(self, agent: Agent) -> None:
        """Release an agent back to the pool."""
        async with self._lock:
            self._agents.append(agent)
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup all agents on exit."""
        for agent in self._agents:
            await agent.cleanup()
```

❌ **Bad:**
```python
class AgentPool:
    def __init__(self, size):
        self.agents = []  # No lock, no cleanup
    
    def acquire(self):  # Not async, blocking
        return self.agents.pop()
```

## Specific Review Guidelines by Component

### GitHub Integration (`src/github/`)

**Check for:**
- Proper rate limit handling with exponential backoff
- Pagination implementation for large result sets
- Secure token storage (environment variables, not hardcoded)
- GraphQL query optimization (batch operations)
- Proper error handling for API failures
- Async/await for all network operations

### Dependency Graph (`src/graph/`)

**Check for:**
- Correct cycle detection implementation
- Thread-safe graph modifications
- Proper topological sort usage
- Edge cases (empty graph, single node, disconnected components)
- Memory efficiency for large graphs
- Clear error messages for cycle detection

### Agent Pool (`src/agents/`)

**Check for:**
- Race condition prevention in agent allocation
- Proper agent state transitions (IDLE → BUSY → IDLE)
- Timeout handling for stuck agents
- Resource cleanup on agent failure
- Statistics tracking (utilization, wait times)
- Graceful shutdown procedures

### Orchestrator (`src/orchestrator/`)

**Check for:**
- Proper semaphore usage for concurrency control
- Deadlock prevention
- Task cancellation handling
- Result collection and aggregation
- Error propagation from child tasks
- Performance optimization

### Configuration (`src/config.py`)

**Check for:**
- Comprehensive Pydantic validation
- Sensible default values
- Environment variable support
- Security (no sensitive defaults)
- Clear validation error messages
- Field constraints (min/max values)

### Testing (`tests/`)

**Check for:**
- Test coverage (aim for 80%+)
- Proper mocking of external dependencies
- Edge case coverage
- Error scenario testing
- Performance test validity
- Test isolation and independence

## Common Anti-Patterns to Flag

### Blocking Operations in Async Code
### Missing Timeout Handling
### Unprotected Shared State
### Poor Error Context

## Review Response Templates
### For Security Issues
### For Performance Issues
### For Architecture Misalignment
### For Testing Gaps
### Praise Good Code
### Questions to Ask

## Review Workflow
- First Pass (security & correctness)
- Second Pass (architecture & performance)
- Third Pass (code quality, testing, docs)
- Summary (high-level, prioritized feedback)

## Exclusions
Exclude generated files, third-party code, and build artifacts.

## Success Metrics
- Catch all critical issues
- Improve maintainability
- Align architecture
- Educate/developers
- Prioritize feedback

## References
- AGENTS.md document, Python/async/structlog/Pydantic docs

---
The goal is to be specific and constructive, explain recommendations, and keep morale high.