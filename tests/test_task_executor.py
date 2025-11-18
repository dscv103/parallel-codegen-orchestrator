"""Unit tests for the TaskExecutor class.

Tests cover semaphore-based concurrency control, agent allocation,
task execution, timeout handling, and graceful cancellation.
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.agents.agent_pool import AgentPool, AgentStatus, ManagedAgent
from src.agents.codegen_executor import TaskResult, TaskStatus
from src.graph.dependency_graph import DependencyGraph
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


@pytest.fixture
def dependency_graph():
    """Create a simple dependency graph."""
    graph = DependencyGraph()
    graph.add_task("task-1", set())
    graph.add_task("task-2", {"task-1"})
    graph.build()
    return graph


@pytest.fixture
def task_executor(mock_agent_pool, dependency_graph):
    """Create a TaskExecutor instance for testing."""
    return TaskExecutor(
        agent_pool=mock_agent_pool,
        dep_graph=dependency_graph,
        timeout_seconds=60,
        poll_interval_seconds=1,
    )


class TestTaskExecutorInit:
    """Tests for TaskExecutor initialization."""

    def test_init_creates_semaphore_with_correct_value(
        self,
        mock_agent_pool,
        dependency_graph,
    ):
        """Test that semaphore is created with pool size."""
        executor = TaskExecutor(mock_agent_pool, dependency_graph)

        assert executor.semaphore._value == 3  # noqa: SLF001
        assert executor.agent_pool == mock_agent_pool
        assert executor.dep_graph == dependency_graph

    def test_init_initializes_empty_collections(self, mock_agent_pool, dependency_graph):
        """Test that task tracking collections are initialized empty."""
        executor = TaskExecutor(mock_agent_pool, dependency_graph)

        assert executor.task_results == {}
        assert executor.active_tasks == set()
        assert executor.agent_executors == {}

    def test_init_stores_timeout_settings(self, mock_agent_pool, dependency_graph):
        """Test that timeout settings are stored correctly."""
        executor = TaskExecutor(
            mock_agent_pool,
            dependency_graph,
            timeout_seconds=300,
            poll_interval_seconds=5,
        )

        assert executor.timeout_seconds == 300
        assert executor.poll_interval_seconds == 5


class TestExecuteTask:
    """Tests for task execution."""

    @pytest.mark.asyncio
    async def test_execute_task_success(self, task_executor, mock_agent_pool):
        """Test successful task execution."""
        # Setup mock executor
        mock_result = TaskResult(
            task_id="task-1",
            status=TaskStatus.COMPLETED,
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC),
            duration_seconds=10.0,
            result={"data": "success"},
        )

        with patch.object(
            task_executor,
            "_get_or_create_executor",
        ) as mock_get_executor:
            mock_executor = AsyncMock()
            mock_executor.execute_task = AsyncMock(return_value=mock_result)
            mock_get_executor.return_value = mock_executor

            # Execute task
            task_data = {
                "task_id": "task-1",
                "prompt": "Test task",
                "repo_id": "org/repo",
            }
            result = await task_executor.execute_task("task-1", task_data)

            # Verify result
            assert result.task_id == "task-1"
            assert result.status == TaskStatus.COMPLETED
            assert result.result == {"data": "success"}

            # Verify agent pool interactions
            mock_agent_pool.get_idle_agent.assert_called_once()
            mock_agent_pool.mark_busy.assert_called_once()
            mock_agent_pool.mark_idle.assert_called_once()

            # Verify result was stored
            assert "task-1" in task_executor.task_results
            assert task_executor.task_results["task-1"] == mock_result

    @pytest.mark.asyncio
    async def test_execute_task_adds_to_active_tasks(self, task_executor):
        """Test that task is added to active tasks during execution."""
        executed_active_tasks = None

        async def capture_active_tasks(*args, **kwargs):  # noqa: ARG001
            nonlocal executed_active_tasks
            executed_active_tasks = task_executor.active_tasks.copy()
            return TaskResult(
                task_id="task-1",
                status=TaskStatus.COMPLETED,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                duration_seconds=1.0,
            )

        with patch.object(
            task_executor,
            "_get_or_create_executor",
        ) as mock_get_executor:
            mock_executor = AsyncMock()
            mock_executor.execute_task = capture_active_tasks
            mock_get_executor.return_value = mock_executor

            task_data = {"task_id": "task-1", "prompt": "Test"}
            await task_executor.execute_task("task-1", task_data)

            # Verify task was in active set during execution
            assert "task-1" in executed_active_tasks

            # Verify task is removed after completion
            assert "task-1" not in task_executor.active_tasks

    @pytest.mark.asyncio
    async def test_execute_task_releases_agent_on_exception(
        self,
        task_executor,
        mock_agent_pool,
    ):
        """Test that agent is released even if execution fails."""
        with patch.object(
            task_executor,
            "_get_or_create_executor",
        ) as mock_get_executor:
            mock_executor = AsyncMock()
            mock_executor.execute_task = AsyncMock(
                side_effect=RuntimeError("Execution failed"),
            )
            mock_get_executor.return_value = mock_executor

            task_data = {"task_id": "task-1", "prompt": "Test"}

            with pytest.raises(RuntimeError, match="Execution failed"):
                await task_executor.execute_task("task-1", task_data)

            # Verify agent was marked idle despite exception
            mock_agent_pool.mark_idle.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_task_execution_respects_semaphore(
        self,
        mock_agent_pool,
        dependency_graph,
    ):
        """Test that semaphore limits concurrent execution."""
        # Create executor with max 2 concurrent tasks
        mock_agent_pool.max_agents = 2
        executor = TaskExecutor(mock_agent_pool, dependency_graph)

        # Track concurrent execution
        concurrent_count = 0
        max_concurrent = 0

        async def slow_execution(*args, **kwargs):  # noqa: ARG001
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)

            await asyncio.sleep(0.1)  # Simulate work

            concurrent_count -= 1

            return TaskResult(
                task_id=args[0]["task_id"],
                status=TaskStatus.COMPLETED,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                duration_seconds=0.1,
            )

        # Setup agents to return different mock agents
        agents_used = []

        def get_different_agent():
            agent = ManagedAgent(
                id=len(agents_used),
                agent=Mock(),
                status=AgentStatus.IDLE,
            )
            agents_used.append(agent)
            return agent

        mock_agent_pool.get_idle_agent = get_different_agent

        with patch.object(
            executor,
            "_get_or_create_executor",
        ) as mock_get_executor:
            mock_executor = AsyncMock()
            mock_executor.execute_task = slow_execution
            mock_get_executor.return_value = mock_executor

            # Execute 4 tasks concurrently
            tasks = [{"task_id": f"task-{i}", "prompt": f"Task {i}"} for i in range(4)]

            results = await asyncio.gather(
                *[executor.execute_task(t["task_id"], t) for t in tasks],
            )

            # Verify max concurrent was limited by semaphore
            assert max_concurrent <= 2
            assert len(results) == 4


class TestWaitForIdleAgent:
    """Tests for agent allocation."""

    @pytest.mark.asyncio
    async def test_wait_returns_immediately_when_agent_available(
        self,
        task_executor,
        mock_agent_pool,
    ):
        """Test that method returns immediately if agent is available."""
        agent = await task_executor._wait_for_idle_agent()  # noqa: SLF001

        assert agent is not None
        assert agent.id == 0
        mock_agent_pool.get_idle_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_polls_until_agent_available(self, task_executor, mock_agent_pool):
        """Test that method polls until an agent becomes available."""
        # First 2 calls return None, third call returns agent
        call_count = 0

        def get_agent_after_delay():
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                return mock_agent_pool.agents[0]
            return None

        mock_agent_pool.get_idle_agent = get_agent_after_delay

        agent = await task_executor._wait_for_idle_agent()  # noqa: SLF001

        assert agent is not None
        assert call_count == 3


class TestGetOrCreateExecutor:
    """Tests for executor caching."""

    def test_creates_executor_for_new_agent(self, task_executor, mock_agent_pool):
        """Test that new executor is created for agent."""
        agent = mock_agent_pool.agents[0]

        executor = task_executor._get_or_create_executor(agent)  # noqa: SLF001

        assert executor is not None
        assert agent.id in task_executor.agent_executors
        assert task_executor.agent_executors[agent.id] == executor

    def test_returns_cached_executor_for_existing_agent(
        self,
        task_executor,
        mock_agent_pool,
    ):
        """Test that cached executor is returned for same agent."""
        agent = mock_agent_pool.agents[0]

        # Create executor first time
        executor1 = task_executor._get_or_create_executor(agent)  # noqa: SLF001

        # Get executor second time
        executor2 = task_executor._get_or_create_executor(agent)  # noqa: SLF001

        # Should be same instance
        assert executor1 is executor2


class TestCancelTask:
    """Tests for task cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_active_task_logs_request(self, task_executor):
        """Test that cancelling active task logs the request."""
        # Add task to active set
        task_executor.active_tasks.add("task-1")

        # Cancel should not raise
        await task_executor.cancel_task("task-1")

        # Task remains in active set (actual cancellation not implemented)
        assert "task-1" in task_executor.active_tasks

    @pytest.mark.asyncio
    async def test_cancel_non_active_task_logs_warning(self, task_executor):
        """Test that cancelling non-active task logs warning."""
        # Cancel non-existent task should not raise
        await task_executor.cancel_task("non-existent")


class TestGetResult:
    """Tests for result retrieval."""

    def test_get_result_returns_stored_result(self, task_executor):
        """Test that stored results can be retrieved."""
        result = TaskResult(
            task_id="task-1",
            status=TaskStatus.COMPLETED,
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC),
            duration_seconds=5.0,
        )

        task_executor.task_results["task-1"] = result

        retrieved = task_executor.get_result("task-1")
        assert retrieved == result

    def test_get_result_returns_none_for_missing_task(self, task_executor):
        """Test that None is returned for non-existent task."""
        result = task_executor.get_result("non-existent")
        assert result is None


class TestGetStats:
    """Tests for statistics retrieval."""

    def test_get_stats_returns_correct_counts(
        self,
        task_executor,
        mock_agent_pool,  # noqa: ARG002
    ):
        """Test that statistics reflect current state."""
        # Add some active tasks and results
        task_executor.active_tasks.add("task-1")
        task_executor.active_tasks.add("task-2")

        task_executor.task_results["task-3"] = TaskResult(
            task_id="task-3",
            status=TaskStatus.COMPLETED,
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC),
            duration_seconds=1.0,
        )

        stats = task_executor.get_stats()

        assert stats["active_tasks"] == 2
        assert stats["completed_tasks"] == 1
        assert stats["total_tasks"] == 3
        assert stats["agent_pool_stats"] == {"idle": 2, "busy": 1, "failed": 0}


class TestClearResults:
    """Tests for result clearing."""

    def test_clear_results_removes_all_stored_results(self, task_executor):
        """Test that clearing removes all results."""
        # Add some results
        for i in range(3):
            task_executor.task_results[f"task-{i}"] = TaskResult(
                task_id=f"task-{i}",
                status=TaskStatus.COMPLETED,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                duration_seconds=1.0,
            )

        assert len(task_executor.task_results) == 3

        task_executor.clear_results()

        assert len(task_executor.task_results) == 0
