"""Main Orchestration Loop with Topological Execution.

This module implements the TaskOrchestrator class that coordinates dependency
graph traversal with concurrent task execution using asyncio.gather.
"""

import asyncio
from typing import Any

import structlog

from src.agents.codegen_executor import TaskResult, TaskStatus
from src.orchestrator.task_executor import TaskExecutor

# Initialize logger
logger = structlog.get_logger(__name__)

# Constants
DEFAULT_WAIT_INTERVAL = 0.5  # seconds to wait when no tasks are ready


class OrchestrationError(Exception):
    """Exception raised when orchestration encounters a critical failure.

    A critical failure is one that should stop the entire orchestration process,
    such as configuration errors or system-level failures.
    """

    def __init__(self, message: str, task_id: str | None = None):
        """Initialize the exception with a descriptive message.

        Args:
            message: Description of the orchestration error
            task_id: Optional task ID that caused the error
        """
        super().__init__(message)
        self.message = message
        self.task_id = task_id


class TaskOrchestrator:
    """Main orchestrator coordinating dependency-aware parallel task execution.

    The orchestrator integrates the DependencyGraph with TaskExecutor to enable
    concurrent execution of independent tasks while respecting dependencies. It
    uses topological sorting to determine execution order and asyncio.gather
    for parallel dispatch.

    Key Features:
        - Parallel execution of independent tasks (up to 10 concurrent)
        - Dependency respect: tasks only execute when dependencies complete
        - Continuous flow: no artificial synchronization barriers
        - Error resilience: failures don't block independent task paths

    Example:
        >>> agent_pool = AgentPool(org_id="123", token="abc", max_agents=10)
        >>> dep_graph = DependencyGraph()
        >>> dep_graph.add_task("task-1", set())
        >>> dep_graph.add_task("task-2", {"task-1"})
        >>> dep_graph.build()
        >>>
        >>> executor = TaskExecutor(agent_pool, dep_graph)
        >>> orchestrator = TaskOrchestrator(executor)
        >>>
        >>> tasks = {
        ...     "task-1": {"prompt": "Implement feature A", "repo_id": "org/repo"},
        ...     "task-2": {"prompt": "Implement feature B", "repo_id": "org/repo"}
        ... }
        >>> results = await orchestrator.orchestrate(tasks)

    Attributes:
        executor: TaskExecutor instance for managing task execution
        wait_interval: Seconds to wait when no tasks are ready
    """

    def __init__(self, executor: TaskExecutor, wait_interval: float = DEFAULT_WAIT_INTERVAL):
        """Initialize the task orchestrator.

        Args:
            executor: TaskExecutor instance with agent pool and dependency graph
            wait_interval: Seconds to wait when no tasks are ready (default: 0.5)

        Example:
            >>> executor = TaskExecutor(agent_pool, dep_graph)
            >>> orchestrator = TaskOrchestrator(executor, wait_interval=1.0)
        """
        self.executor = executor
        self.wait_interval = wait_interval

        logger.info(
            "task_orchestrator_initialized",
            max_concurrent=executor.agent_pool.max_agents,
            wait_interval=wait_interval,
        )

    async def orchestrate(self, tasks: dict[str, dict[str, Any]]) -> list[TaskResult]:
        """Execute main orchestration loop using topological sorting.

        Continuously fetches ready tasks from the dependency graph, dispatches
        them for concurrent execution using asyncio.gather, processes results,
        and marks completed tasks. Continues until all tasks are processed.

        The orchestrator handles partial failures gracefully - a task failure
        will not block execution of independent tasks that don't depend on it.

        Args:
            tasks: Dictionary mapping task IDs to task configuration:
                {
                    "task-id": {
                        "prompt": "Task description",
                        "repo_id": "org/repo",
                        ...additional task-specific parameters
                    }
                }

        Returns:
            List of TaskResult objects for all completed tasks (successful and failed)

        Raises:
            OrchestrationError: If a critical failure prevents orchestration
            ValueError: If tasks dictionary is empty or contains invalid data

        Example:
            >>> tasks = {
            ...     "task-1": {"prompt": "Add validation", "repo_id": "org/repo"},
            ...     "task-2": {"prompt": "Update tests", "repo_id": "org/repo"}
            ... }
            >>> results = await orchestrator.orchestrate(tasks)
            >>> successful = [r for r in results if r.status == TaskStatus.COMPLETED]
            >>> print(f"Completed {len(successful)}/{len(results)} tasks")
        """
        if not tasks:
            logger.warning("orchestrate_called_with_empty_tasks")
            return []

        logger.info(
            "orchestration_started",
            total_tasks=len(tasks),
            task_ids=list(tasks.keys()),
        )

        results: list[TaskResult] = []
        failed_task_ids: set[str] = set()
        iteration = 0

        try:
            # Main orchestration loop - continues while graph has active tasks
            while self.executor.dep_graph.is_active():
                iteration += 1

                # Get tasks that are ready (all dependencies met)
                ready_task_ids = self.executor.dep_graph.get_ready_tasks()

                if not ready_task_ids:
                    # No tasks ready yet - wait for running tasks to complete
                    logger.debug(
                        "no_ready_tasks_waiting",
                        iteration=iteration,
                        active_tasks=len(self.executor.active_tasks),
                    )
                    await asyncio.sleep(self.wait_interval)
                    continue

                logger.info(
                    "dispatching_ready_tasks",
                    iteration=iteration,
                    ready_count=len(ready_task_ids),
                    task_ids=list(ready_task_ids),
                )

                # Create coroutines for all ready tasks
                task_coroutines = [
                    self.executor.execute_task(task_id, tasks[task_id])
                    for task_id in ready_task_ids
                ]

                # Execute tasks concurrently using asyncio.gather
                # return_exceptions=True ensures exceptions don't cancel other tasks
                completed = await asyncio.gather(
                    *task_coroutines,
                    return_exceptions=True,
                )

                # Process results and separate successful from failed tasks
                completed_task_ids: list[str] = []

                for i, task_result in enumerate(completed):
                    task_id = list(ready_task_ids)[i]

                    if isinstance(task_result, Exception):
                        # Task execution raised an exception
                        logger.error(
                            "task_execution_exception",
                            task_id=task_id,
                            error=str(task_result),
                            error_type=type(task_result).__name__,
                        )
                        failed_task_ids.add(task_id)

                        # Create a failed TaskResult for tracking
                        failed_result = TaskResult(
                            task_id=task_id,
                            status=TaskStatus.FAILED,
                            start_time=None,
                            end_time=None,
                            duration_seconds=0.0,
                            result=None,
                            error=str(task_result),
                        )
                        results.append(failed_result)
                        # Mark failed tasks as completed so dependent tasks can proceed
                        completed_task_ids.append(task_id)

                    elif task_result.status == TaskStatus.FAILED:
                        # Task completed but with failed status
                        logger.warning(
                            "task_completed_with_failure",
                            task_id=task_result.task_id,
                            error=task_result.error,
                        )
                        failed_task_ids.add(task_result.task_id)
                        results.append(task_result)
                        completed_task_ids.append(task_result.task_id)

                    else:
                        # Task completed successfully
                        logger.info(
                            "task_completed_successfully",
                            task_id=task_result.task_id,
                            duration_seconds=task_result.duration_seconds,
                        )
                        results.append(task_result)
                        completed_task_ids.append(task_result.task_id)

                # Mark completed tasks in dependency graph
                # This allows dependent tasks to become ready
                if completed_task_ids:
                    self.executor.dep_graph.mark_completed(*completed_task_ids)
                    logger.debug(
                        "tasks_marked_completed_in_graph",
                        count=len(completed_task_ids),
                        task_ids=completed_task_ids,
                    )

            # Orchestration complete
            successful_count = len([r for r in results if r.status == TaskStatus.COMPLETED])
            failed_count = len([r for r in results if r.status == TaskStatus.FAILED])

            logger.info(
                "orchestration_completed",
                total_tasks=len(tasks),
                successful=successful_count,
                failed=failed_count,
                iterations=iteration,
            )

            return results  # noqa: TRY300

        except KeyboardInterrupt:
            logger.warning(
                "orchestration_interrupted",
                completed_tasks=len(results),
                total_tasks=len(tasks),
            )
            raise

        except Exception as e:
            logger.exception(
                "orchestration_failed",
                error=str(e),
                completed_tasks=len(results),
                total_tasks=len(tasks),
            )
            error_msg = f"Critical orchestration failure: {e}"
            raise OrchestrationError(error_msg) from e

    async def orchestrate_with_early_termination(
        self,
        tasks: dict[str, dict[str, Any]],
        critical_task_ids: set[str] | None = None,
    ) -> list[TaskResult]:
        """Execute orchestration with early termination on critical failures.

        Similar to orchestrate() but stops execution if any critical task fails.
        This is useful when certain tasks are essential and their failure makes
        continuing the orchestration pointless.

        Args:
            tasks: Dictionary mapping task IDs to task configuration
            critical_task_ids: Set of task IDs that should trigger early termination
                              if they fail. If None, no early termination occurs.

        Returns:
            List of TaskResult objects for all executed tasks

        Raises:
            OrchestrationError: If a critical task fails
            ValueError: If tasks dictionary is empty or contains invalid data

        Example:
            >>> tasks = {
            ...     "setup": {"prompt": "Setup environment", "repo_id": "org/repo"},
            ...     "task-1": {"prompt": "Feature 1", "repo_id": "org/repo"},
            ...     "task-2": {"prompt": "Feature 2", "repo_id": "org/repo"}
            ... }
            >>> critical_tasks = {"setup"}  # Fail fast if setup fails
            >>> results = await orchestrator.orchestrate_with_early_termination(
            ...     tasks, critical_tasks
            ... )
        """
        if critical_task_ids is None:
            # No critical tasks - use regular orchestration
            return await self.orchestrate(tasks)

        logger.info(
            "orchestration_with_early_termination_started",
            total_tasks=len(tasks),
            critical_tasks=len(critical_task_ids),
            critical_task_ids=list(critical_task_ids),
        )

        results: list[TaskResult] = []
        iteration = 0

        try:
            while self.executor.dep_graph.is_active():
                iteration += 1

                ready_task_ids = self.executor.dep_graph.get_ready_tasks()

                if not ready_task_ids:
                    await asyncio.sleep(self.wait_interval)
                    continue

                # Execute ready tasks
                task_coroutines = [
                    self.executor.execute_task(task_id, tasks[task_id])
                    for task_id in ready_task_ids
                ]

                completed = await asyncio.gather(
                    *task_coroutines,
                    return_exceptions=True,
                )

                completed_task_ids: list[str] = []

                for i, task_result in enumerate(completed):
                    task_id = list(ready_task_ids)[i]

                    # Check for critical task failure
                    is_critical = task_id in critical_task_ids
                    is_failed = isinstance(task_result, Exception) or (
                        hasattr(task_result, "status") and task_result.status == TaskStatus.FAILED
                    )

                    if is_critical and is_failed:
                        error_msg = (
                            str(task_result)
                            if isinstance(task_result, Exception)
                            else task_result.error
                        )
                        logger.error(
                            "critical_task_failed_terminating",
                            task_id=task_id,
                            error=error_msg,
                        )
                        critical_error_msg = f"Critical task '{task_id}' failed: {error_msg}"
                        raise OrchestrationError(critical_error_msg, task_id=task_id)  # noqa: TRY301

                    # Process result normally
                    if isinstance(task_result, Exception):
                        failed_result = TaskResult(
                            task_id=task_id,
                            status=TaskStatus.FAILED,
                            start_time=None,
                            end_time=None,
                            duration_seconds=0.0,
                            result=None,
                            error=str(task_result),
                        )
                        results.append(failed_result)
                    else:
                        results.append(task_result)
                        if task_result.status != TaskStatus.FAILED:
                            completed_task_ids.append(task_result.task_id)

                if completed_task_ids:
                    self.executor.dep_graph.mark_completed(*completed_task_ids)

            logger.info(
                "orchestration_with_early_termination_completed",
                total_tasks=len(tasks),
                completed_tasks=len(results),
            )

            return results  # noqa: TRY300

        except OrchestrationError:
            # Re-raise orchestration errors
            raise

        except Exception as e:
            logger.exception(
                "orchestration_with_early_termination_failed",
                error=str(e),
            )
            critical_failure_msg = f"Critical failure during orchestration: {e}"
            raise OrchestrationError(critical_failure_msg) from e

    def get_stats(self) -> dict[str, Any]:
        """Get orchestration statistics.

        Returns:
            Dictionary with orchestration statistics including:
                - executor_stats: Statistics from the TaskExecutor
                - graph_stats: Statistics from the DependencyGraph

        Example:
            >>> stats = orchestrator.get_stats()
            >>> print(f"Active tasks: {stats['executor_stats']['active_tasks']}")
        """
        return {
            "executor_stats": self.executor.get_stats(),
            "graph_stats": self.executor.dep_graph.get_stats(),
        }
