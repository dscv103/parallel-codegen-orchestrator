"""Dynamic Dependency Discovery and Graph Updates.

This module implements runtime dependency discovery, allowing tasks to add new
dependencies and tasks during execution while maintaining thread-safety and
preventing cycles.
"""

import asyncio
from typing import Any

import structlog

from src.graph.dependency_graph import CycleDetectedError, DependencyGraph

# Initialize logger
logger = structlog.get_logger(__name__)


class DynamicTaskRegistrationError(Exception):
    """Exception raised when a dynamic task cannot be registered.

    This can happen due to cycle detection, invalid dependencies,
    or other validation failures.
    """

    def __init__(self, message: str, task_id: str | None = None):
        """Initialize the exception with a descriptive message.

        Args:
            message: Description of the registration error
            task_id: Optional task ID that caused the error
        """
        super().__init__(message)
        self.message = message
        self.task_id = task_id


class DynamicDependencyManager:
    """Manager for dynamically adding tasks and dependencies during execution.

    This class provides thread-safe operations for adding tasks to the dependency
    graph at runtime. It validates new dependencies, detects cycles, and rebuilds
    the topological sort as needed.

    Thread-safety is provided through asyncio.Lock to prevent race conditions
    when multiple tasks attempt to add dependencies concurrently.

    Example:
        >>> dep_graph = DependencyGraph()
        >>> manager = DynamicDependencyManager(dep_graph)
        >>>
        >>> # During execution, a task discovers new work
        >>> new_tasks = {
        ...     "task-3": {
        ...         "dependencies": {"task-1"},
        ...         "prompt": "New task discovered",
        ...         "repo_id": "org/repo"
        ...     }
        ... }
        >>> await manager.add_dynamic_tasks(new_tasks)

    Attributes:
        dep_graph: The DependencyGraph to manage
        lock: Asyncio lock for thread-safe operations
        new_tasks_queue: Queue of newly discovered tasks awaiting execution
        _completed_tasks: Set of task IDs that have completed (for validation)
    """

    def __init__(self, dep_graph: DependencyGraph):
        """Initialize the dynamic dependency manager.

        Args:
            dep_graph: The DependencyGraph instance to manage

        Example:
            >>> graph = DependencyGraph()
            >>> manager = DynamicDependencyManager(graph)
        """
        self.dep_graph = dep_graph
        self.lock = asyncio.Lock()
        self.new_tasks_queue: asyncio.Queue = asyncio.Queue()
        self._completed_tasks: set[str] = set()

        logger.info("dynamic_dependency_manager_initialized")

    async def add_dynamic_tasks(self, new_tasks: dict[str, dict[str, Any]]) -> None:
        """Add newly discovered tasks to the execution queue.

        This method validates that adding the new tasks won't create cycles,
        adds them to the dependency graph, rebuilds the topological sort,
        and queues them for execution.

        The validation is done in two phases:
        1. Normalize and validate individual task data
        2. Test the entire batch on a temporary graph copy to detect inter-batch cycles

        Only if both phases succeed are the tasks added to the real graph.

        Args:
            new_tasks: Dictionary mapping task IDs to task data:
                {
                    "task-id": {
                        "dependencies": {"dep-1", "dep-2"},
                        "prompt": "Task description",
                        "repo_id": "org/repo",
                        ...additional task parameters
                    }
                }

        Raises:
            DynamicTaskRegistrationError: If a task would create a cycle or
                has invalid dependencies
            ValueError: If task data is malformed

        Example:
            >>> new_tasks = {
            ...     "task-3": {
            ...         "dependencies": {"task-1"},
            ...         "prompt": "Implement feature C",
            ...         "repo_id": "org/repo"
            ...     }
            ... }
            >>> await manager.add_dynamic_tasks(new_tasks)
        """
        if not new_tasks:
            logger.warning("add_dynamic_tasks_called_with_empty_dict")
            return

        logger.info(
            "adding_dynamic_tasks",
            task_count=len(new_tasks),
            task_ids=list(new_tasks.keys()),
        )

        # Acquire lock for thread-safe graph modifications
        async with self.lock:
            # Phase 1: Normalize and validate task data structure
            new_task_ids = set(new_tasks.keys())
            normalized_tasks: dict[str, set[str]] = {}

            for task_id, task_data in new_tasks.items():
                # Validate dependencies field exists
                if "dependencies" not in task_data:
                    error_msg = f"Task {task_id} missing 'dependencies' field"
                    logger.error("invalid_task_data", task_id=task_id, error=error_msg)
                    raise ValueError(error_msg)

                dependencies = task_data["dependencies"]

                # Validate dependencies type
                if not isinstance(dependencies, (set, list)):
                    error_msg = f"Task {task_id} dependencies must be set or list"
                    logger.error("invalid_dependencies_type", task_id=task_id)
                    raise ValueError(error_msg)

                # Normalize to set
                dep_set = set(dependencies) if isinstance(dependencies, list) else dependencies

                # Validate dependencies exist (either in current graph, completed tasks, or new batch)
                for dep_id in dep_set:
                    if (
                        dep_id not in self.dep_graph.graph
                        and dep_id not in self._completed_tasks
                        and dep_id not in new_task_ids
                    ):
                        error_msg = (
                            f"Task {task_id} depends on non-existent task {dep_id}. "
                            "Dependencies must reference existing tasks or other tasks in this batch."
                        )
                        logger.error(
                            "invalid_dependency_reference",
                            task_id=task_id,
                            missing_dependency=dep_id,
                        )
                        raise DynamicTaskRegistrationError(error_msg, task_id=task_id)

                normalized_tasks[task_id] = dep_set

            # Phase 2: Test the entire batch on a temporary graph to detect cycles
            temp_graph = self.dep_graph.copy()

            logger.debug(
                "validating_batch_on_temp_graph",
                task_count=len(normalized_tasks),
            )

            try:
                # Add all new tasks to the temporary graph
                for task_id, dep_set in normalized_tasks.items():
                    temp_graph.add_task(task_id, dep_set)

                # Try to build the temporary graph - this will detect any cycles
                temp_graph.build()

                logger.debug(
                    "batch_validation_passed",
                    task_count=len(normalized_tasks),
                )

            except CycleDetectedError as e:
                # Cycle detected across the batch
                error_msg = f"Adding task batch would create a cycle in the dependency graph: {e}"
                logger.error(
                    "cycle_detected_in_batch",
                    task_count=len(normalized_tasks),
                    task_ids=list(normalized_tasks.keys()),
                    error=str(e),
                )
                raise DynamicTaskRegistrationError(error_msg) from e

            # Phase 3: Validation passed - now safely add tasks to real graph
            # Save original state in case we need to rollback
            original_graph_state = self.dep_graph.copy()
            original_is_built = self.dep_graph._is_built

            try:
                # Add all validated tasks to the real dependency graph
                for task_id, dep_set in normalized_tasks.items():
                    self.dep_graph.add_task(task_id, dep_set)

                    logger.info(
                        "dynamic_task_added_to_graph",
                        task_id=task_id,
                        dependencies=list(dep_set),
                    )

                # Rebuild the topological sorter to include new tasks
                self.dep_graph.rebuild()
                logger.info("graph_rebuilt_after_dynamic_addition", task_count=len(new_tasks))

            except Exception as e:
                # Something went wrong during mutation/rebuild - restore original state
                logger.error(
                    "error_during_graph_mutation_restoring_state",
                    task_count=len(new_tasks),
                    error=str(e),
                )

                # Restore original graph state
                self.dep_graph.graph = original_graph_state.graph
                self.dep_graph._is_built = original_is_built
                self.dep_graph.sorter = original_graph_state.sorter

                logger.info("graph_state_restored_after_error")

                # Re-raise as DynamicTaskRegistrationError
                raise DynamicTaskRegistrationError(
                    f"Failed to add tasks to graph: {e}",
                ) from e

            # Queue tasks for execution
            for task_id, task_data in new_tasks.items():
                await self.new_tasks_queue.put((task_id, task_data))

                logger.debug(
                    "dynamic_task_queued_for_execution",
                    task_id=task_id,
                    queue_size=self.new_tasks_queue.qsize(),
                )

        logger.info(
            "dynamic_tasks_added_successfully",
            task_count=len(new_tasks),
            queue_size=self.new_tasks_queue.qsize(),
        )

    def mark_task_completed(self, task_id: str) -> None:
        """Mark a task as completed for dependency validation.

        Args:
            task_id: ID of the completed task

        Note:
            This is used to track completed tasks for validation purposes.
            The actual graph state is managed by DependencyGraph.mark_completed().
        """
        self._completed_tasks.add(task_id)
        logger.debug("task_marked_completed_in_dynamic_manager", task_id=task_id)

    async def has_pending_tasks(self) -> bool:
        """Check if there are tasks waiting in the queue.

        Returns:
            True if tasks are queued, False otherwise
        """
        return not self.new_tasks_queue.empty()

    async def get_next_task(self, timeout: float = 1.0) -> tuple[str, dict[str, Any]] | None:
        """Get the next task from the queue.

        Args:
            timeout: Maximum time to wait for a task in seconds

        Returns:
            Tuple of (task_id, task_data) or None if timeout reached

        Example:
            >>> task = await manager.get_next_task(timeout=2.0)
            >>> if task:
            ...     task_id, task_data = task
            ...     print(f"Got task: {task_id}")
        """
        try:
            task_id, task_data = await asyncio.wait_for(
                self.new_tasks_queue.get(),
                timeout=timeout,
            )

            logger.debug(
                "dynamic_task_retrieved_from_queue",
                task_id=task_id,
                remaining_queue_size=self.new_tasks_queue.qsize(),
            )

            return (task_id, task_data)

        except TimeoutError:
            logger.debug("no_dynamic_tasks_available", timeout=timeout)
            return None


class TaskExecutionContext:
    """Context object providing callback interface for tasks to discover dependencies.

    This context is injected into task execution environments, allowing tasks
    to report newly discovered dependencies back to the orchestrator.

    Example:
        >>> # Inside a task execution
        >>> context = TaskExecutionContext(manager, "task-1")
        >>> await context.add_discovered_task(
        ...     "task-new",
        ...     dependencies={"task-1"},
        ...     task_data={
        ...         "prompt": "Follow-up work",
        ...         "repo_id": "org/repo"
        ...     }
        ... )

    Attributes:
        manager: The DynamicDependencyManager to report to
        caller_task_id: ID of the task using this context
    """

    def __init__(self, manager: DynamicDependencyManager, caller_task_id: str):
        """Initialize the task execution context.

        Args:
            manager: DynamicDependencyManager instance for registering tasks
            caller_task_id: ID of the task that owns this context
        """
        self.manager = manager
        self.caller_task_id = caller_task_id

        logger.debug("task_execution_context_created", task_id=caller_task_id)

    async def add_discovered_task(
        self,
        task_id: str,
        dependencies: set[str] | list[str],
        task_data: dict[str, Any],
    ) -> None:
        """Register a newly discovered task.

        Args:
            task_id: Unique ID for the new task
            dependencies: Set or list of task IDs this task depends on
            task_data: Dictionary with task configuration (prompt, repo_id, etc.)

        Raises:
            DynamicTaskRegistrationError: If the task cannot be registered
            ValueError: If task data is invalid

        Example:
            >>> await context.add_discovered_task(
            ...     "task-follow-up",
            ...     dependencies={"task-1", "task-2"},
            ...     task_data={
            ...         "prompt": "Implement follow-up feature",
            ...         "repo_id": "org/repo"
            ...     }
            ... )
        """
        logger.info(
            "task_discovering_new_dependency",
            caller_task=self.caller_task_id,
            discovered_task=task_id,
            dependencies=list(dependencies) if isinstance(dependencies, set) else dependencies,
        )

        # Prepare task data with dependencies
        full_task_data = {
            "dependencies": dependencies,
            **task_data,
        }

        # Register with the manager
        await self.manager.add_dynamic_tasks({task_id: full_task_data})

        logger.info(
            "task_successfully_discovered",
            caller_task=self.caller_task_id,
            discovered_task=task_id,
        )

    async def add_multiple_discovered_tasks(
        self,
        tasks: dict[str, dict[str, Any]],
    ) -> None:
        """Register multiple newly discovered tasks at once.

        This is more efficient than calling add_discovered_task() multiple times
        as it acquires the lock only once.

        Args:
            tasks: Dictionary mapping task IDs to task data:
                {
                    "task-id": {
                        "dependencies": {"dep-1"},
                        "prompt": "...",
                        "repo_id": "..."
                    }
                }

        Raises:
            DynamicTaskRegistrationError: If any task cannot be registered
            ValueError: If task data is invalid

        Example:
            >>> tasks = {
            ...     "task-a": {
            ...         "dependencies": {"task-1"},
            ...         "prompt": "Feature A",
            ...         "repo_id": "org/repo"
            ...     },
            ...     "task-b": {
            ...         "dependencies": {"task-1"},
            ...         "prompt": "Feature B",
            ...         "repo_id": "org/repo"
            ...     }
            ... }
            >>> await context.add_multiple_discovered_tasks(tasks)
        """
        logger.info(
            "task_discovering_multiple_dependencies",
            caller_task=self.caller_task_id,
            task_count=len(tasks),
            task_ids=list(tasks.keys()),
        )

        await self.manager.add_dynamic_tasks(tasks)

        logger.info(
            "multiple_tasks_successfully_discovered",
            caller_task=self.caller_task_id,
            task_count=len(tasks),
        )
