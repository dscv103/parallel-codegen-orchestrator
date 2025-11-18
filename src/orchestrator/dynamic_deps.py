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
            # Validate each task before adding any
            for task_id, task_data in new_tasks.items():
                if "dependencies" not in task_data:
                    error_msg = f"Task {task_id} missing 'dependencies' field"
                    logger.error("invalid_task_data", task_id=task_id, error=error_msg)
                    raise ValueError(error_msg)

                dependencies = task_data["dependencies"]
                if not isinstance(dependencies, (set, list)):
                    error_msg = f"Task {task_id} dependencies must be set or list"
                    logger.error("invalid_dependencies_type", task_id=task_id)
                    raise ValueError(error_msg)

                # Convert to set if needed
                dep_set = set(dependencies) if isinstance(dependencies, list) else dependencies

                # Check if adding this task would create a cycle
                if self._would_create_cycle(task_id, dep_set):
                    error_msg = (
                        f"Adding task {task_id} would create a cycle in the dependency graph"
                    )
                    logger.error(
                        "cycle_detected_during_dynamic_add",
                        task_id=task_id,
                        dependencies=list(dep_set),
                    )
                    raise DynamicTaskRegistrationError(error_msg, task_id=task_id)

                # Validate that dependencies exist or will exist
                self._validate_dependencies_exist(task_id, dep_set)

            # All validations passed - now add tasks to graph
            for task_id, task_data in new_tasks.items():
                dependencies = task_data["dependencies"]
                dep_set = set(dependencies) if isinstance(dependencies, list) else dependencies

                # Add to dependency graph
                self.dep_graph.add_task(task_id, dep_set)

                logger.info(
                    "dynamic_task_added_to_graph",
                    task_id=task_id,
                    dependencies=list(dep_set),
                )

            # Rebuild the topological sorter to include new tasks
            try:
                self.dep_graph.rebuild()
                logger.info("graph_rebuilt_after_dynamic_addition", task_count=len(new_tasks))
            except CycleDetectedError as e:
                # This shouldn't happen since we validated, but handle it anyway
                logger.exception(
                    "unexpected_cycle_during_rebuild",
                    task_count=len(new_tasks),
                    error=str(e),
                )
                raise DynamicTaskRegistrationError(
                    f"Unexpected cycle detected during rebuild: {e}",
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

    def _would_create_cycle(self, new_task_id: str, dependencies: set[str]) -> bool:
        """Check if adding this task would create a cycle.

        Creates a temporary copy of the graph, adds the new task, and attempts
        to build it. If building fails with a cycle error, returns True.

        Args:
            new_task_id: ID of the task to potentially add
            dependencies: Set of task IDs this task depends on

        Returns:
            True if adding the task would create a cycle, False otherwise

        Example:
            >>> # Graph has: task-1 -> task-2
            >>> manager._would_create_cycle("task-1", {"task-2"})
            True  # Would create cycle: task-1 -> task-2 -> task-1
        """
        # Create a temporary graph copy
        temp_graph = self.dep_graph.copy()

        # Add the new task to the temporary graph
        temp_graph.add_task(new_task_id, dependencies)

        # Try to build - if it fails with a cycle, return True
        try:
            temp_graph.build()
            logger.debug(
                "cycle_check_passed",
                new_task_id=new_task_id,
                dependencies=list(dependencies),
            )
            return False
        except CycleDetectedError:
            logger.warning(
                "cycle_detected_in_validation",
                new_task_id=new_task_id,
                dependencies=list(dependencies),
            )
            return True

    def _validate_dependencies_exist(self, task_id: str, dependencies: set[str]) -> None:
        """Validate that all dependencies exist in the graph.

        Args:
            task_id: ID of the task being validated
            dependencies: Set of task IDs this task depends on

        Raises:
            DynamicTaskRegistrationError: If any dependency doesn't exist

        Note:
            This allows dependencies on tasks that haven't completed yet,
            but requires they at least exist in the graph structure.
        """
        for dep_id in dependencies:
            if dep_id not in self.dep_graph.graph and dep_id not in self._completed_tasks:
                error_msg = (
                    f"Task {task_id} depends on non-existent task {dep_id}. "
                    "Dependencies must reference existing tasks."
                )
                logger.error(
                    "invalid_dependency_reference",
                    task_id=task_id,
                    missing_dependency=dep_id,
                )
                raise DynamicTaskRegistrationError(error_msg, task_id=task_id)

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
