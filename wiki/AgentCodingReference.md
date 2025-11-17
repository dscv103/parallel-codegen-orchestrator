# Parallel Codegen Agent Orchestrator Documentation

This wiki serves as a coding reference for human and AI coding agents working on the development of the parallel-codegen-orchestrator project. It provides standardized architecture, usage guidelines, and implementation notes for every major component and workflow described in the project's epics and issues.

---

## Overview
The orchestrator runs multiple Codegen agents in parallel to automate code generation tasks, driven by dependency graphs sourced from GitHub Projects v2. It supports up to 10 concurrent agents locally (Python >= 3.13, no Docker required).

---

## Architecture Reference

- **Integration Layer**: Use PyGithub for REST API and httpx + GraphQL for Projects v2. See [GitHub Integration Issues](https://github.com/dscv103/parallel-codegen-orchestrator/issues?q=label%3Aphase-1).
- **Dependency Graph**: Directed acyclic graph management and topological sort. Python graphlib.TopologicalSorter, dynamic updates, cycle detection.
- **Agent Pool**: Up to 10 agents (Codegen SDK). Pool management, status (IDLE/BUSY/FAILED), usage statistics.
- **Task Execution**: asyncio.Semaphore to control concurrency. Orchestration loop dispatches tasks as DAG dependencies allow.
- **Results & Monitoring**: Track stats (success/fail/time/metrics), ResultManager class, CLI/JSON export. ProgressMonitor for live updates.
- **Configuration**: All components configured via Pydantic/pyyaml for type-safe config management.
- **Automation**: GitHub status updates, comment posting, auto-merge logic.
- **Testing**: High coverage with pytest (unit, integration, E2E, benchmarks, error handling).

---

## Coding Agent Guidance
- **Standard Libraries**: Use python >= 3.13, asyncio, PyGithub, httpx, pydantic, structlog, pytest.
- **Codegen API**: Interact via codegen Python SDK. Agent.run/refresh/status/result for codegen agent flows. See [Codegen SDK Guide](https://docs.codegen.com/introduction/sdk).
- **Concurrency**: Prefer asyncio patterns (Semaphore, gather) over threading. Use TaskGroup for structured task error handling.
- **Dependency References**: Use "Blocked by #N" in issue bodies and comments for workflow alignment. Maintain DAG structure when dynamically adding dependencies.
- **Config Management**: Load all major settings from config.yaml (see [Configuration Issue #13](https://github.com/dscv103/parallel-codegen-orchestrator/issues/13)). Use environment fallback for secrets.
- **Logging**: Structured, JSON-encoded logs via structlog. Always log agent/task/graph state changes with correlation IDs.
- **Testing**: All pull requests require coverage for their feature (setup pytest regression suite first).

---

## References & Further Reading
- [Project Epic with Issues/Phases](https://github.com/dscv103/parallel-codegen-orchestrator/issues/25)
- [Official Codegen API Reference](https://docs.codegen.com/api-reference/overview)
- [Async Python Task Execution Patterns](https://realpython.com/async-io-python/)
- [GitHub Projects v2 Automations](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects)
- [PyGithub Usage Tutorial](https://generalistprogrammer.com/tutorials/pygithub-python-package-guide)
- [Pydantic Models](https://docs.pydantic.dev/)

---

## FAQ/Best Practices
- All code tasks should reference the project issue and task id for traceability.
- Always handle API failures with structured retries (see Retry Logic issue).
- Dynamically update the DAG only via concurrency-safe logic.
- Track and report metrics at each orchestration stage for benchmarking.

---

_Agents, contributors, and automation tools should follow this wiki as the canonical project coding reference, providing context for design choices, testing, and automation flows._
