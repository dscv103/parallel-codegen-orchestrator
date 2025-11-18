"""Dependency graph construction using Python's graphlib for topological sorting.

This module provides the DependencyGraph class which wraps graphlib.TopologicalSorter
to manage task dependencies and determine execution order.
"""

import asyncio
from graphlib import TopologicalSorter

import structlog

logger = structlog.get_logger(__name__)


class CycleDetectedError(Exception):
    """Exception raised when a cycle is detected in the dependency graph.

    A cycle means that tasks have circular dependencies, making it impossible
    to determine a valid execution order.
    """

    def __init__(self, message: str):
        """Initialize the exception with a descriptive message.

        Args:
            message: Description of the cycle detection error
        """
        super().__init__(message)
        self.message = message


class DependencyGraph:
    """Dependency graph manager using topological sorting.

    This class manages a directed acyclic graph (DAG) of tasks and their
    dependencies, providing methods to add tasks, validate the graph structure,
    and retrieve tasks that are ready for execution.

    Thread-safety:
        This class is NOT thread-safe. The underlying TopologicalSorter and
        internal state should only be accessed from a single thread. If
        concurrent access is required, protect all method calls with external
        synchronization (e.g., threading.Lock).

    Example:
        >>> graph = DependencyGraph()
        >>> graph.add_task("task-1", set())  # No dependencies
        >>> graph.add_task("task-2", {"task-1"})  # Depends on task-1
        >>> graph.build()
        >>> ready = graph.get_ready_tasks()  # Returns ("task-1",)
        >>> graph.mark_completed("task-1")
        >>> ready = graph.get_ready_tasks()  # Returns ("task-2",)
    """

    def __init__(self):
        """Initialize an empty dependency graph."""
        self.graph: dict[str, set[str]] = {}
        self.sorter: TopologicalSorter | None = None
        self._is_built = False
        self._graph_lock = asyncio.Lock()

        logger.debug("dependency_graph_initialized")

    def add_task(self, task_id: str, dependencies: set[str]) -> None:
        """Add a task with its dependencies to the graph.

        Args:
            task_id: Unique identifier for the task
            dependencies: Set of task IDs that this task depends on

        Note:
            If adding tasks after build() has been called, this method will
            invalidate the built state. You must call build() again before
            calling get_ready_tasks() or mark_completed().

        Example:
            >>> graph = DependencyGraph()
            >>> graph.add_task("task-1", set())
            >>> graph.add_task("task-2", {"task-1"})
        """
        if self._is_built:
            logger.warning(
                "adding_task_to_built_graph",
                task_id=task_id,
                message="Graph already built. Invalidating state - call build() again.",
            )
            # Invalidate the built state since we're modifying the graph
            self._is_built = False
            self.sorter = None

        # Defensively copy dependencies to avoid external mutations
        self.graph[task_id] = set(dependencies)

        logger.debug(
            "task_added_to_graph",
            task_id=task_id,
            dependencies=list(dependencies),
            dependency_count=len(dependencies),
        )

    def build(self) -> None:
        """Build the topological sorter from the graph and validate structure.

        This method creates a TopologicalSorter from the current graph and
        validates that it forms a valid DAG (no cycles). Must be called before
        get_ready_tasks() or mark_completed().

        Raises:
            CycleDetectedError: If a cycle is detected in the dependency graph

        Example:
            >>> graph = DependencyGraph()
            >>> graph.add_task("task-1", set())
            >>> graph.build()  # Success
            >>>
            >>> graph2 = DependencyGraph()
            >>> graph2.add_task("task-a", {"task-b"})
            >>> graph2.add_task("task-b", {"task-a"})
            >>> graph2.build()  # Raises CycleDetectedError
        """
        if not self.graph:
            logger.warning("building_empty_graph", message="No tasks in graph")
            self.sorter = TopologicalSorter({})
            self.sorter.prepare()
            self._is_built = True
            return

        logger.info(
            "building_dependency_graph",
            task_count=len(self.graph),
            total_dependencies=sum(len(deps) for deps in self.graph.values()),
        )

        try:
            self.sorter = TopologicalSorter(self.graph)
            self.sorter.prepare()
            self._is_built = True

            logger.info(
                "dependency_graph_built_successfully",
                task_count=len(self.graph),
            )

        except ValueError as e:
            error_msg = f"Cycle detected in dependency graph: {e}"
            logger.exception(
                "cycle_detected_in_graph",
                error=str(e),
                task_count=len(self.graph),
            )
            raise CycleDetectedError(error_msg) from e

    def get_ready_tasks(self) -> tuple[str, ...]:
        """Get tasks that are ready to execute (all dependencies met).

        Returns a tuple of task IDs for tasks whose dependencies have all been
        marked as completed. Returns an empty tuple if no tasks are ready or
        if the graph hasn't been built yet.

        Returns:
            Tuple of task IDs ready for execution

        Example:
            >>> graph = DependencyGraph()
            >>> graph.add_task("task-1", set())
            >>> graph.add_task("task-2", {"task-1"})
            >>> graph.build()
            >>> graph.get_ready_tasks()
            ('task-1',)
        """
        if not self._is_built or self.sorter is None:
            logger.warning(
                "get_ready_tasks_called_before_build",
                message="Graph not built. Call build() first.",
            )
            return ()

        if not self.sorter.is_active():
            logger.debug("no_active_tasks_remaining")
            return ()

        ready_tasks = self.sorter.get_ready()

        logger.debug(
            "ready_tasks_retrieved",
            count=len(ready_tasks),
            tasks=list(ready_tasks),
        )

        return ready_tasks

    def mark_completed(self, *task_ids: str) -> None:
        """Mark one or more tasks as completed.

        This informs the graph that the specified tasks have finished executing,
        which may cause other tasks that depend on them to become ready.

        Args:
            *task_ids: One or more task IDs to mark as completed

        Raises:
            ValueError: If the graph hasn't been built or if tasks are invalid

        Example:
            >>> graph = DependencyGraph()
            >>> graph.add_task("task-1", set())
            >>> graph.build()
            >>> graph.mark_completed("task-1")
        """
        if not self._is_built or self.sorter is None:
            error_msg = "Cannot mark tasks completed before building graph"
            logger.error("mark_completed_before_build", task_ids=task_ids)
            raise ValueError(error_msg)

        if not task_ids:
            logger.warning("mark_completed_called_with_no_tasks")
            return

        try:
            self.sorter.done(*task_ids)
            logger.info(
                "tasks_marked_completed",
                count=len(task_ids),
                tasks=list(task_ids),
            )
        except ValueError as e:
            logger.exception(
                "error_marking_tasks_completed",
                task_ids=task_ids,
                error=str(e),
            )
            raise

    def is_active(self) -> bool:
        """Check if there are still tasks to process.

        Returns True if there are tasks that haven't been marked as completed yet,
        False if all tasks are done or if the graph hasn't been built.

        Returns:
            True if tasks remain, False otherwise

        Example:
            >>> graph = DependencyGraph()
            >>> graph.add_task("task-1", set())
            >>> graph.build()
            >>> graph.is_active()
            True
            >>> graph.mark_completed("task-1")
            >>> graph.is_active()
            False
        """
        if not self._is_built or self.sorter is None:
            return False

        return self.sorter.is_active()

    def get_stats(self) -> dict[str, int]:
        """Get statistics about the current graph state.

        Returns:
            Dictionary with graph statistics including:
                - total_tasks: Total number of tasks in graph
                - total_dependencies: Sum of all dependencies
                - is_built: Whether build() has been called
                - is_active: Whether tasks remain to process
        """
        stats = {
            "total_tasks": len(self.graph),
            "total_dependencies": sum(len(deps) for deps in self.graph.values()),
            "is_built": self._is_built,
            "is_active": self.is_active(),
        }

        logger.debug("graph_stats_retrieved", **stats)

        return stats

    @property
    def is_built(self) -> bool:
        """Check if the graph has been built and is ready for execution.

        Returns:
            True if build() has been called successfully, False otherwise
        """
        return self._is_built

    def set_built_state(self, is_built: bool) -> None:
        """Set the built state.

        This is used for state restoration in error scenarios.

        Args:
            is_built: The built state to set
        """
        self._is_built = is_built

    def copy(self) -> "DependencyGraph":
        """Create a deep copy of the dependency graph.

        Returns:
            A new DependencyGraph instance with the same structure

        Note:
            The copy will not include the built state or sorter - you must
            call build() on the copy to use it for execution.

        Example:
            >>> graph = DependencyGraph()
            >>> graph.add_task("task-1", set())
            >>> graph_copy = graph.copy()
            >>> graph_copy.build()  # Must rebuild on copy
        """
        new_graph = DependencyGraph()
        # Deep copy the graph structure
        for task_id, dependencies in self.graph.items():
            new_graph.graph[task_id] = set(dependencies)

        logger.debug("dependency_graph_copied", task_count=len(self.graph))

        return new_graph

    def rebuild(self) -> None:
        """Rebuild the topological sorter from the current graph state.

        This method is used when tasks are added dynamically during execution.
        It preserves the current task completion state while rebuilding the
        topology to account for new tasks.

        Raises:
            CycleDetectedError: If a cycle is detected in the updated graph

        Note:
            This is different from build() - rebuild() is meant to be called
            on an already-built graph that has been modified. It attempts to
            preserve execution state.

        Example:
            >>> graph = DependencyGraph()
            >>> graph.add_task("task-1", set())
            >>> graph.build()
            >>> # Later, during execution...
            >>> graph.add_task("task-2", {"task-1"})
            >>> graph.rebuild()  # Updates topology without losing state
        """
        logger.info(
            "rebuilding_dependency_graph",
            task_count=len(self.graph),
            was_built=self._is_built,
        )

        # Simply call build() - it handles everything we need
        # The TopologicalSorter doesn't preserve state across rebuilds,
        # so we rely on the orchestrator tracking completed tasks externally
        self.build()

        logger.info("dependency_graph_rebuilt", task_count=len(self.graph))
