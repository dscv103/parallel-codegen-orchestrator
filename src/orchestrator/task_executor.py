"""Task Executor with Semaphore-based Concurrency Control.

This module implements the TaskExecutor class that manages concurrent task execution
using asyncio.Semaphore to limit parallelism to the agent pool size.
"""

import asyncio
from typing import Any

from src.agents.agent_pool import AgentPool, ManagedAgent
from src.agents.codegen_executor import CodegenExecutor, TaskResult
from src.graph.dependency_graph import DependencyGraph
from src.log_config import get_logger
from src.orchestrator.retry import RetryConfig, execute_with_retry

# Initialize logger
logger = get_logger(__name__)

# Constants
DEFAULT_AGENT_WAIT_INTERVAL = 0.1  # seconds to wait when no agent is available


class TaskExecutor:
    """Concurrent task executor with semaphore-based concurrency control.

    Manages concurrent execution of tasks using a pool of Codegen agents with
    semaphore-based limiting. The semaphore ensures that at most `max_agents`
    tasks execute concurrently.

    The executor coordinates with the AgentPool to allocate agents and with
    the DependencyGraph to respect task dependencies.

    Example:
        >>> agent_pool = AgentPool(org_id="123", token="abc", max_agents=10)
        >>> dep_graph = DependencyGraph()
        >>> dep_graph.add_task("task-1", set())
        >>> dep_graph.build()
        >>>
        >>> executor = TaskExecutor(agent_pool, dep_graph)
        >>> task_data = {
        ...     'task_id': 'task-1',
        ...     'prompt': 'Implement feature X',
        ...     'repo_id': 'org/repo'
        ... }
        >>> result = await executor.execute_task("task-1", task_data)

    Attributes:
        agent_pool: Pool of Codegen agents for task execution
        dep_graph: Dependency graph for task coordination
        semaphore: Asyncio semaphore limiting concurrent tasks
        task_results: Dictionary mapping task IDs to their results
        active_tasks: Set of currently executing task IDs
        agent_executors: Dictionary mapping agent IDs to their CodegenExecutor instances
    """

    def __init__(
        self,
        agent_pool: AgentPool,
        dep_graph: DependencyGraph,
        timeout_seconds: int = 600,
        poll_interval_seconds: int = 2,
        retry_config: RetryConfig | None = None,
    ):
        """Initialize the task executor.

        Args:
            agent_pool: Pool of agents to use for execution
            dep_graph: Dependency graph for task ordering
            timeout_seconds: Timeout for individual task execution (default: 600)
            poll_interval_seconds: Polling interval for task status (default: 2)
            retry_config: Configuration for retry behavior (default: None, creates default config)

        Example:
            >>> executor = TaskExecutor(
            ...     agent_pool=pool,
            ...     dep_graph=graph,
            ...     timeout_seconds=300,
            ...     retry_config=RetryConfig(max_attempts=3, base_delay_seconds=30)
            ... )
        """
        self.agent_pool = agent_pool
        self.dep_graph = dep_graph
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.retry_config = retry_config or RetryConfig()

        # Semaphore limits concurrent tasks to pool size
        self.semaphore = asyncio.Semaphore(agent_pool.max_agents)

        # Track task results and active tasks
        self.task_results: dict[str, TaskResult] = {}
        self.active_tasks: set[str] = set()

        # Cache CodegenExecutor instances per agent
        self.agent_executors: dict[int, CodegenExecutor] = {}

        logger.info(
            "task_executor_initialized",
            max_concurrent=agent_pool.max_agents,
            timeout_seconds=timeout_seconds,
            retry_enabled=self.retry_config.enabled,
            retry_attempts=self.retry_config.max_attempts,
        )

    def _get_or_create_executor(self, agent: ManagedAgent) -> CodegenExecutor:
        """Get or create a CodegenExecutor for the given agent.

        Args:
            agent: The managed agent to get executor for

        Returns:
            CodegenExecutor instance for the agent
        """
        if agent.id not in self.agent_executors:
            self.agent_executors[agent.id] = CodegenExecutor(
                agent=agent.agent,
                timeout_seconds=self.timeout_seconds,
                poll_interval_seconds=self.poll_interval_seconds,
            )
            logger.debug("codegen_executor_created", agent_id=agent.id)

        return self.agent_executors[agent.id]

    async def execute_task(self, task_id: str, task_data: dict[str, Any]) -> TaskResult:
        """Execute a single task using an available agent.

        Acquires the semaphore, waits for an idle agent, executes the task,
        and releases resources. This method is safe to call concurrently.

        Args:
            task_id: Unique identifier for the task
            task_data: Task configuration dictionary containing:
                - prompt: Task prompt/description
                - repo_id: Repository identifier (optional)
                - Additional task-specific parameters

        Returns:
            TaskResult with execution details and outcome

        Raises:
            Exception: If task execution fails after all retries

        Example:
            >>> task_data = {
            ...     'task_id': 'task-1',
            ...     'prompt': 'Add input validation',
            ...     'repo_id': 'org/repo'
            ... }
            >>> result = await executor.execute_task("task-1", task_data)
            >>> print(result.status)
        """
        async with self.semaphore:
            logger.info(
                "task_execution_started",
                task_id=task_id,
                active_count=len(self.active_tasks),
            )

            # Mark task as active
            self.active_tasks.add(task_id)

            try:
                # Wait for an idle agent
                agent = await self._wait_for_idle_agent()

                # Mark agent as busy with this task
                self.agent_pool.mark_busy(agent, task_id)

                logger.info(
                    "agent_allocated_to_task",
                    task_id=task_id,
                    agent_id=agent.id,
                )

                try:
                    # Get or create executor for this agent
                    executor = self._get_or_create_executor(agent)

                    # Execute the task with retry logic if enabled
                    if self.retry_config.enabled:
                        result = await execute_with_retry(
                            task_id=task_id,
                            func=executor.execute_task,
                            max_attempts=self.retry_config.max_attempts,
                            base_delay_seconds=self.retry_config.base_delay_seconds,
                            task_data=task_data,
                        )
                    else:
                        # Execute without retry
                        result = await executor.execute_task(task_data)

                    # Store result
                    self.task_results[task_id] = result

                    logger.info(
                        "task_execution_completed",
                        task_id=task_id,
                        agent_id=agent.id,
                        status=result.status.value,
                        duration_seconds=result.duration_seconds,
                    )

                    return result

                finally:
                    # Always release the agent back to the pool
                    self.agent_pool.mark_idle(agent)
                    logger.debug("agent_released", task_id=task_id, agent_id=agent.id)

            except Exception as e:
                logger.exception(
                    "task_execution_error",
                    task_id=task_id,
                    error=str(e),
                )
                raise

            finally:
                # Remove from active tasks
                self.active_tasks.discard(task_id)

    async def _wait_for_idle_agent(self) -> ManagedAgent:
        """Wait for an idle agent to become available.

        Polls the agent pool at regular intervals until an agent is available.

        Returns:
            ManagedAgent that is idle and ready for work

        Note:
            This method will block until an agent becomes available. In practice,
            this should not wait long because the semaphore already limits
            concurrent tasks to the pool size.
        """
        while True:
            agent = self.agent_pool.get_idle_agent()
            if agent is not None:
                return agent

            # Wait briefly before checking again
            logger.debug("waiting_for_idle_agent")
            await asyncio.sleep(DEFAULT_AGENT_WAIT_INTERVAL)

    async def cancel_task(self, task_id: str) -> None:
        """Cancel a running task gracefully.

        Attempts to cancel a task that is currently executing. This is a
        best-effort operation and may not immediately stop task execution.

        Args:
            task_id: ID of the task to cancel

        Note:
            This method marks the intent to cancel but does not force-kill
            the task. The actual cancellation depends on the task's ability
            to handle cancellation.
        """
        if task_id in self.active_tasks:
            logger.warning(
                "task_cancellation_requested",
                task_id=task_id,
            )
            # Note: Actual cancellation implementation would require
            # coordination with the Codegen API to cancel the running task
            # For now, we just log the cancellation request
        else:
            logger.warning(
                "task_cancellation_failed_not_active",
                task_id=task_id,
            )

    def get_result(self, task_id: str) -> TaskResult | None:
        """Get the result of a completed task.

        Args:
            task_id: ID of the task to get result for

        Returns:
            TaskResult if task has completed, None otherwise

        Example:
            >>> result = executor.get_result("task-1")
            >>> if result:
            ...     print(f"Status: {result.status}")
        """
        return self.task_results.get(task_id)

    def get_stats(self) -> dict[str, Any]:
        """Get execution statistics.

        Returns:
            Dictionary with execution statistics including:
                - active_tasks: Number of currently executing tasks
                - completed_tasks: Number of completed tasks
                - total_tasks: Total number of tasks executed
                - agent_pool_stats: Statistics from the agent pool

        Example:
            >>> stats = executor.get_stats()
            >>> print(f"Active: {stats['active_tasks']}")
        """
        stats = {
            "active_tasks": len(self.active_tasks),
            "completed_tasks": len(self.task_results),
            "total_tasks": len(self.active_tasks) + len(self.task_results),
            "agent_pool_stats": self.agent_pool.get_stats(),
        }

        logger.debug("executor_stats_retrieved", **stats)

        return stats

    def clear_results(self) -> None:
        """Clear all stored task results.

        Useful for resetting state between executions or to free memory.

        Example:
            >>> executor.clear_results()
        """
        logger.info(
            "clearing_task_results",
            cleared_count=len(self.task_results),
        )
        self.task_results.clear()
