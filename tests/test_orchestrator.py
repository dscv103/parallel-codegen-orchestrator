"""Unit and integration tests for the TaskOrchestrator class.

Tests cover the main orchestration loop, dependency-aware execution,
error handling, and early termination features.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from src.agents.agent_pool import AgentPool, AgentStatus, ManagedAgent
from src.agents.codegen_executor import TaskResult, TaskStatus
from src.graph.dependency_graph import DependencyGraph
from src.orchestrator.orchestrator import (
    OrchestrationError,
    TaskOrchestrator,
)
from src.orchestrator.task_executor import TaskExecutor


@pytest.fixture
def mock_agent_pool():
    """Create a mock agent pool with 3 agents."""
    pool = Mock(spec=AgentPool)
    pool.max_agents = 3
    pool.org_id = "test-org"
    pool.token = "test-token"  # noqa: S105

    # Create mock agents
    agents = []
    for i in range(3):
        mock_agent = Mock()
        mock_agent.run = Mock()

        managed_agent = ManagedAgent(
            id=i,
            agent=mock_agent,
            status=AgentStatus.IDLE,
        )
        agents.append(managed_agent)

    pool.agents = agents
    pool.get_idle_agent = Mock(return_value=agents[0])
    pool.mark_busy = Mock()
    pool.mark_idle = Mock()
    pool.get_stats = Mock(return_value={"idle": 2, "busy": 1, "failed": 0})

    return pool


class TestTaskOrchestratorInit:
    """Tests for TaskOrchestrator initialization."""

    def test_init_stores_executor_and_wait_interval(self):
        """Test that orchestrator stores executor and wait interval correctly."""
        executor = Mock(spec=TaskExecutor)
        executor.agent_pool = Mock()
        executor.agent_pool.max_agents = 10

        orchestrator = TaskOrchestrator(
            executor,
            wait_interval=1.5,
        )

        assert orchestrator.executor == executor
        assert orchestrator.wait_interval == 1.5  # noqa: PLR2004

    def test_init_uses_default_wait_interval(self):
        """Test that default wait interval is used when not specified."""
        executor = Mock(spec=TaskExecutor)
        executor.agent_pool = Mock()
        executor.agent_pool.max_agents = 10

        orchestrator = TaskOrchestrator(executor)

        assert orchestrator.wait_interval == 0.5  # noqa: PLR2004


class TestOrchestrate:
    """Tests for the main orchestrate() method."""

    @pytest.mark.asyncio
    async def test_orchestrate_with_empty_tasks_returns_empty_list(self):
        """Test that orchestrating empty tasks returns empty list."""
        executor = Mock(spec=TaskExecutor)
        executor.agent_pool = Mock()
        executor.agent_pool.max_agents = 10

        orchestrator = TaskOrchestrator(executor, wait_interval=0.01)

        results = await orchestrator.orchestrate({})

        assert results == []

    @pytest.mark.asyncio
    async def test_orchestrate_executes_all_tasks_in_dependency_order(
        self,
        mock_agent_pool,
    ):
        """Test that all tasks are executed respecting dependencies."""
        # Create real dependency graph
        dep_graph = DependencyGraph()
        dep_graph.add_task("task-1", set())
        dep_graph.add_task("task-2", {"task-1"})
        dep_graph.add_task("task-3", {"task-1"})
        dep_graph.build()

        # Create executor with real graph
        executor = Mock(spec=TaskExecutor)
        executor.agent_pool = mock_agent_pool
        executor.dep_graph = dep_graph
        executor.active_tasks = set()

        # Mock execute_task to return successful results
        async def mock_execute(task_id, _task_data):
            return TaskResult(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                duration_seconds=1.0,
                result={"output": f"Result for {task_id}"},
                error=None,
            )

        executor.execute_task = AsyncMock(side_effect=mock_execute)

        orchestrator = TaskOrchestrator(executor, wait_interval=0.01)

        tasks = {
            "task-1": {"prompt": "Task 1", "repo_id": "org/repo"},
            "task-2": {"prompt": "Task 2", "repo_id": "org/repo"},
            "task-3": {"prompt": "Task 3", "repo_id": "org/repo"},
        }

        results = await orchestrator.orchestrate(tasks)

        # All 3 tasks should be executed
        assert len(results) == 3  # noqa: PLR2004
        assert executor.execute_task.call_count == 3  # noqa: PLR2004

        # Verify all tasks were executed
        executed_task_ids = {call_obj.args[0] for call_obj in executor.execute_task.call_args_list}
        assert executed_task_ids == {"task-1", "task-2", "task-3"}

    @pytest.mark.asyncio
    async def test_orchestrate_handles_task_failure_gracefully(
        self,
        mock_agent_pool,
    ):
        """Test that task failures don't block independent tasks."""
        # Create real dependency graph
        dep_graph = DependencyGraph()
        dep_graph.add_task("task-1", set())
        dep_graph.add_task("task-2", {"task-1"})
        dep_graph.add_task("task-3", {"task-1"})
        dep_graph.build()

        # Create executor
        executor = Mock(spec=TaskExecutor)
        executor.agent_pool = mock_agent_pool
        executor.dep_graph = dep_graph
        executor.active_tasks = set()

        # Make task-2 fail but task-3 should still execute
        async def mock_execute_with_failure(task_id, _task_data):
            if task_id == "task-2":
                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    start_time=datetime.now(UTC),
                    end_time=datetime.now(UTC),
                    duration_seconds=1.0,
                    result=None,
                    error="Task 2 failed",
                )

            return TaskResult(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                duration_seconds=1.0,
                result={"output": f"Result for {task_id}"},
                error=None,
            )

        executor.execute_task = AsyncMock(
            side_effect=mock_execute_with_failure,
        )

        orchestrator = TaskOrchestrator(executor, wait_interval=0.01)

        tasks = {
            "task-1": {"prompt": "Task 1", "repo_id": "org/repo"},
            "task-2": {"prompt": "Task 2", "repo_id": "org/repo"},
            "task-3": {"prompt": "Task 3", "repo_id": "org/repo"},
        }

        results = await orchestrator.orchestrate(tasks)

        # All 3 tasks should be attempted
        assert len(results) == 3  # noqa: PLR2004

        # task-1 and task-3 should succeed, task-2 should fail
        successful = [r for r in results if r.status == TaskStatus.COMPLETED]
        failed = [r for r in results if r.status == TaskStatus.FAILED]

        assert len(successful) == 2  # noqa: PLR2004
        assert len(failed) == 1
        assert failed[0].task_id == "task-2"

    @pytest.mark.asyncio
    async def test_orchestrate_handles_exception_during_task_execution(
        self,
        mock_agent_pool,
    ):
        """Test that exceptions during task execution are handled gracefully."""
        # Create real dependency graph
        dep_graph = DependencyGraph()
        dep_graph.add_task("task-1", set())
        dep_graph.add_task("task-2", {"task-1"})
        dep_graph.add_task("task-3", {"task-1"})
        dep_graph.build()

        # Create executor
        executor = Mock(spec=TaskExecutor)
        executor.agent_pool = mock_agent_pool
        executor.dep_graph = dep_graph
        executor.active_tasks = set()

        # Make task-2 raise an exception
        async def mock_execute_with_exception(task_id, _task_data):
            if task_id == "task-2":
                error_msg = "Simulated task failure"
                raise RuntimeError(error_msg)

            return TaskResult(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                duration_seconds=1.0,
                result={"output": f"Result for {task_id}"},
                error=None,
            )

        executor.execute_task = AsyncMock(
            side_effect=mock_execute_with_exception,
        )

        orchestrator = TaskOrchestrator(executor, wait_interval=0.01)

        tasks = {
            "task-1": {"prompt": "Task 1", "repo_id": "org/repo"},
            "task-2": {"prompt": "Task 2", "repo_id": "org/repo"},
            "task-3": {"prompt": "Task 3", "repo_id": "org/repo"},
        }

        results = await orchestrator.orchestrate(tasks)

        # All 3 tasks should be attempted
        assert len(results) == 3  # noqa: PLR2004

        # Verify exception was converted to failed TaskResult
        failed = [r for r in results if r.status == TaskStatus.FAILED]
        assert len(failed) == 1
        assert failed[0].task_id == "task-2"
        assert "Simulated task failure" in failed[0].error


class TestOrchestrateWithEarlyTermination:
    """Tests for orchestrate_with_early_termination() method."""

    @pytest.mark.asyncio
    async def test_early_termination_stops_on_critical_task_failure(
        self,
        mock_agent_pool,
    ):
        """Test that orchestration stops when a critical task fails."""
        # Create real dependency graph
        dep_graph = DependencyGraph()
        dep_graph.add_task("task-1", set())
        dep_graph.add_task("task-2", {"task-1"})
        dep_graph.add_task("task-3", {"task-1"})
        dep_graph.build()

        # Create executor
        executor = Mock(spec=TaskExecutor)
        executor.agent_pool = mock_agent_pool
        executor.dep_graph = dep_graph
        executor.active_tasks = set()

        # Make task-1 fail (which is critical)
        async def mock_execute_with_failure(task_id, _task_data):
            if task_id == "task-1":
                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    start_time=datetime.now(UTC),
                    end_time=datetime.now(UTC),
                    duration_seconds=1.0,
                    result=None,
                    error="Critical task failed",
                )

            return TaskResult(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                duration_seconds=1.0,
                result={"output": f"Result for {task_id}"},
                error=None,
            )

        executor.execute_task = AsyncMock(
            side_effect=mock_execute_with_failure,
        )

        orchestrator = TaskOrchestrator(executor, wait_interval=0.01)

        tasks = {
            "task-1": {"prompt": "Task 1", "repo_id": "org/repo"},
            "task-2": {"prompt": "Task 2", "repo_id": "org/repo"},
            "task-3": {"prompt": "Task 3", "repo_id": "org/repo"},
        }

        # task-1 is critical - failure should stop orchestration
        with pytest.raises(OrchestrationError) as exc_info:
            await orchestrator.orchestrate_with_early_termination(
                tasks,
                critical_task_ids={"task-1"},
            )

        assert "Critical task 'task-1' failed" in str(exc_info.value)
        assert exc_info.value.task_id == "task-1"

    @pytest.mark.asyncio
    async def test_early_termination_stops_on_critical_exception(
        self,
        mock_agent_pool,
    ):
        """Test that orchestration stops when a critical task raises exception."""
        # Create real dependency graph
        dep_graph = DependencyGraph()
        dep_graph.add_task("task-1", set())
        dep_graph.add_task("task-2", {"task-1"})
        dep_graph.build()

        # Create executor
        executor = Mock(spec=TaskExecutor)
        executor.agent_pool = mock_agent_pool
        executor.dep_graph = dep_graph
        executor.active_tasks = set()

        # Make task-1 raise an exception (task-1 is critical)
        async def mock_execute_with_exception(task_id, _task_data):
            if task_id == "task-1":
                error_msg = "Critical task exception"
                raise RuntimeError(error_msg)

            return TaskResult(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                duration_seconds=1.0,
                result={"output": f"Result for {task_id}"},
                error=None,
            )

        executor.execute_task = AsyncMock(
            side_effect=mock_execute_with_exception,
        )

        orchestrator = TaskOrchestrator(executor, wait_interval=0.01)

        tasks = {
            "task-1": {"prompt": "Task 1", "repo_id": "org/repo"},
            "task-2": {"prompt": "Task 2", "repo_id": "org/repo"},
        }

        with pytest.raises(OrchestrationError) as exc_info:
            await orchestrator.orchestrate_with_early_termination(
                tasks,
                critical_task_ids={"task-1"},
            )

        assert "Critical task 'task-1' failed" in str(exc_info.value)
        assert "Critical task exception" in str(exc_info.value)


class TestGetStats:
    """Tests for get_stats() method."""

    def test_get_stats_returns_executor_and_graph_stats(self):
        """Test that get_stats returns stats from executor and graph."""
        executor = Mock(spec=TaskExecutor)
        executor.agent_pool = Mock()
        executor.agent_pool.max_agents = 10
        executor.get_stats = Mock(
            return_value={
                "active_tasks": 0,
                "completed_tasks": 2,
                "total_tasks": 2,
                "agent_pool_stats": {"idle": 10, "busy": 0, "failed": 0},
            },
        )
        executor.dep_graph = Mock()
        executor.dep_graph.get_stats = Mock(
            return_value={
                "total_tasks": 2,
                "total_dependencies": 1,
                "is_built": True,
                "is_active": False,
            },
        )

        orchestrator = TaskOrchestrator(executor, wait_interval=0.01)

        stats = orchestrator.get_stats()

        assert "executor_stats" in stats
        assert "graph_stats" in stats

        assert stats["executor_stats"]["active_tasks"] == 0
        assert stats["graph_stats"]["total_tasks"] == 2  # noqa: PLR2004


class TestIntegrationOrchestrator:
    """Integration tests with real TaskExecutor and DependencyGraph."""

    @pytest.mark.asyncio
    async def test_integration_orchestrate_with_real_components(
        self,
        mock_agent_pool,
    ):
        """Test orchestration with real TaskExecutor and DependencyGraph."""
        # Create real dependency graph
        dep_graph = DependencyGraph()
        dep_graph.add_task("task-1", set())
        dep_graph.add_task("task-2", {"task-1"})
        dep_graph.build()

        # Create real TaskExecutor
        executor = TaskExecutor(
            agent_pool=mock_agent_pool,
            dep_graph=dep_graph,
            timeout_seconds=60,
        )

        # Mock the execute_task to return immediately
        async def mock_execute(task_id, _task_data):
            return TaskResult(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                duration_seconds=0.1,
                result={"output": f"Result for {task_id}"},
                error=None,
            )

        executor.execute_task = AsyncMock(side_effect=mock_execute)

        # Create orchestrator
        orchestrator = TaskOrchestrator(executor, wait_interval=0.01)

        tasks = {
            "task-1": {"prompt": "Task 1", "repo_id": "org/repo"},
            "task-2": {"prompt": "Task 2", "repo_id": "org/repo"},
        }

        results = await orchestrator.orchestrate(tasks)

        # Verify both tasks completed
        assert len(results) == 2  # noqa: PLR2004
        assert all(r.status == TaskStatus.COMPLETED for r in results)

        # Verify execution order - task-1 should execute before task-2
        executed_order = [call_obj.args[0] for call_obj in executor.execute_task.call_args_list]

        # task-1 should be executed first (no dependencies)
        assert executed_order[0] == "task-1"
        # task-2 should be executed after task-1 completes
        assert executed_order[1] == "task-2"
