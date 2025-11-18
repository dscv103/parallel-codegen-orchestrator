"""Unit tests for DependencyGraph class.

Tests cover:
- Adding tasks with and without dependencies
- Building the graph
- Getting ready tasks
- Marking tasks completed
- Cycle detection
- Graph validation
- Edge cases and error conditions
"""

import pytest

from src.graph.dependency_graph import CycleDetectedError, DependencyGraph

# Test constants
EXPECTED_TASK_COUNT_THREE = 3
EXPECTED_TASK_COUNT_TWO = 2


class TestDependencyGraphBasics:
    """Test basic functionality of DependencyGraph."""

    def test_initialization(self):
        """Test that DependencyGraph initializes correctly."""
        graph = DependencyGraph()

        assert graph.graph == {}
        assert graph.sorter is None
        assert not graph.is_active()

    def test_add_single_task_no_dependencies(self):
        """Test adding a task with no dependencies."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())

        assert "task-1" in graph.graph
        assert graph.graph["task-1"] == set()

    def test_add_multiple_tasks(self):
        """Test adding multiple tasks with various dependencies."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})
        graph.add_task("task-3", {"task-1", "task-2"})

        assert len(graph.graph) == EXPECTED_TASK_COUNT_THREE
        assert graph.graph["task-1"] == set()
        assert graph.graph["task-2"] == {"task-1"}
        assert graph.graph["task-3"] == {"task-1", "task-2"}

    def test_add_task_with_dependencies(self):
        """Test adding a task with dependencies."""
        graph = DependencyGraph()
        dependencies = {"task-1", "task-2"}
        graph.add_task("task-3", dependencies)

        assert graph.graph["task-3"] == dependencies


class TestGraphBuilding:
    """Test graph building and validation."""

    def test_build_empty_graph(self):
        """Test building an empty graph."""
        graph = DependencyGraph()
        graph.build()

        assert graph.sorter is not None
        assert not graph.is_active()

    def test_build_simple_graph(self):
        """Test building a simple valid graph."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})

        graph.build()

        assert graph.sorter is not None
        assert graph.is_active()

    def test_build_complex_graph(self):
        """Test building a more complex valid graph."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", set())
        graph.add_task("task-3", {"task-1"})
        graph.add_task("task-4", {"task-2"})
        graph.add_task("task-5", {"task-3", "task-4"})

        graph.build()

        assert graph.is_active()

    def test_build_idempotent(self):
        """Test that multiple build calls work correctly."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())

        graph.build()

        # Building again should work (though it creates a new sorter)
        graph.build()

        assert graph.sorter is not None


class TestCycleDetection:
    """Test cycle detection in dependency graphs."""

    def test_simple_cycle_detection(self):
        """Test detection of a simple two-task cycle."""
        graph = DependencyGraph()
        graph.add_task("task-a", {"task-b"})
        graph.add_task("task-b", {"task-a"})

        with pytest.raises(CycleDetectedError) as exc_info:
            graph.build()

        assert "Cycle detected" in str(exc_info.value)

    def test_self_dependency_cycle(self):
        """Test detection of a task depending on itself."""
        graph = DependencyGraph()
        graph.add_task("task-1", {"task-1"})

        with pytest.raises(CycleDetectedError) as exc_info:
            graph.build()

        assert "Cycle detected" in str(exc_info.value)

    def test_three_task_cycle(self):
        """Test detection of a three-task cycle."""
        graph = DependencyGraph()
        graph.add_task("task-a", {"task-c"})
        graph.add_task("task-b", {"task-a"})
        graph.add_task("task-c", {"task-b"})

        with pytest.raises(CycleDetectedError) as exc_info:
            graph.build()

        assert "Cycle detected" in str(exc_info.value)

    def test_complex_graph_with_cycle(self):
        """Test cycle detection in a complex graph."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})
        graph.add_task("task-3", {"task-2"})
        graph.add_task("task-4", {"task-3"})
        graph.add_task("task-5", {"task-4"})
        graph.add_task("task-2", {"task-5"})  # Create cycle

        with pytest.raises(CycleDetectedError) as exc_info:
            graph.build()

        assert "Cycle detected" in str(exc_info.value)


class TestReadyTasks:
    """Test retrieval of ready tasks."""

    def test_get_ready_tasks_before_build(self):
        """Test that get_ready_tasks returns empty before build."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())

        ready = graph.get_ready_tasks()

        assert ready == ()

    def test_get_ready_tasks_single_task(self):
        """Test getting ready task with no dependencies."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.build()

        ready = graph.get_ready_tasks()

        assert len(ready) == 1
        assert "task-1" in ready

    def test_get_ready_tasks_multiple_independent(self):
        """Test that multiple independent tasks are all ready."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", set())
        graph.add_task("task-3", set())
        graph.build()

        ready = graph.get_ready_tasks()

        assert len(ready) == EXPECTED_TASK_COUNT_THREE
        assert set(ready) == {"task-1", "task-2", "task-3"}

    def test_get_ready_tasks_with_dependencies(self):
        """Test that only tasks with satisfied dependencies are ready."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})
        graph.add_task("task-3", {"task-2"})
        graph.build()

        ready = graph.get_ready_tasks()

        # Only task-1 should be ready initially
        assert len(ready) == 1
        assert "task-1" in ready

    def test_get_ready_tasks_mixed_dependencies(self):
        """Test getting ready tasks in a complex dependency scenario."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", set())
        graph.add_task("task-3", {"task-1"})
        graph.add_task("task-4", {"task-1", "task-2"})
        graph.build()

        ready = graph.get_ready_tasks()

        # task-1 and task-2 should be ready
        assert len(ready) == EXPECTED_TASK_COUNT_TWO
        assert set(ready) == {"task-1", "task-2"}


class TestMarkCompleted:
    """Test marking tasks as completed."""

    def test_mark_single_task_completed(self):
        """Test marking a single task as completed."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.build()

        # Must get ready tasks before marking them completed
        ready = graph.get_ready_tasks()
        assert "task-1" in ready

        graph.mark_completed("task-1")

        # After marking completed, no tasks should be ready
        ready = graph.get_ready_tasks()
        assert ready == ()

    def test_mark_completed_unlocks_dependent_task(self):
        """Test that completing a task makes dependent tasks ready."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})
        graph.build()

        # Get ready tasks first
        ready = graph.get_ready_tasks()
        assert "task-1" in ready

        # Mark task-1 completed
        graph.mark_completed("task-1")

        # Now task-2 should be ready
        ready = graph.get_ready_tasks()
        assert len(ready) == 1
        assert "task-2" in ready

    def test_mark_multiple_tasks_completed(self):
        """Test marking multiple tasks completed at once."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", set())
        graph.add_task("task-3", {"task-1", "task-2"})
        graph.build()

        # Get ready tasks first
        ready = graph.get_ready_tasks()
        assert set(ready) == {"task-1", "task-2"}

        # Mark both prerequisites completed
        graph.mark_completed("task-1", "task-2")

        # Now task-3 should be ready
        ready = graph.get_ready_tasks()
        assert len(ready) == 1
        assert "task-3" in ready

    def test_mark_completed_before_build_raises_error(self):
        """Test that marking completed before build raises ValueError."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())

        with pytest.raises(ValueError, match="before building graph"):
            graph.mark_completed("task-1")

    def test_mark_completed_with_no_tasks(self):
        """Test marking completed with no task IDs (edge case)."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.build()

        # Should not raise an error
        graph.mark_completed()


class TestIsActive:
    """Test the is_active method."""

    def test_is_active_before_build(self):
        """Test that is_active returns False before build."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())

        assert not graph.is_active()

    def test_is_active_after_build(self):
        """Test that is_active returns True after build with tasks."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.build()

        assert graph.is_active()

    def test_is_active_after_all_completed(self):
        """Test that is_active returns False after all tasks completed."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})
        graph.build()

        # Get and complete task-1
        graph.get_ready_tasks()
        graph.mark_completed("task-1")

        # Get and complete task-2
        graph.get_ready_tasks()
        graph.mark_completed("task-2")

        assert not graph.is_active()

    def test_is_active_empty_graph(self):
        """Test is_active with empty graph."""
        graph = DependencyGraph()
        graph.build()

        assert not graph.is_active()


class TestTopologicalOrder:
    """Test that tasks are retrieved in correct topological order."""

    def test_linear_dependency_chain(self):
        """Test linear chain of dependencies."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})
        graph.add_task("task-3", {"task-2"})
        graph.build()

        # Execute in topological order
        order = []

        while graph.is_active():
            ready = graph.get_ready_tasks()
            assert len(ready) == 1  # Linear chain = only one ready at a time
            task_id = ready[0]
            order.append(task_id)
            graph.mark_completed(task_id)

        assert order == ["task-1", "task-2", "task-3"]

    def test_parallel_branches(self):
        """Test parallel branches that converge."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2a", {"task-1"})
        graph.add_task("task-2b", {"task-1"})
        graph.add_task("task-3", {"task-2a", "task-2b"})
        graph.build()

        # First, task-1 should be ready
        ready = graph.get_ready_tasks()
        assert ready == ("task-1",)
        graph.mark_completed("task-1")

        # Then both task-2a and task-2b should be ready
        ready = graph.get_ready_tasks()
        assert len(ready) == EXPECTED_TASK_COUNT_TWO
        assert set(ready) == {"task-2a", "task-2b"}
        graph.mark_completed("task-2a", "task-2b")

        # Finally task-3 should be ready
        ready = graph.get_ready_tasks()
        assert ready == ("task-3",)

    def test_diamond_dependency(self):
        """Test diamond-shaped dependency pattern."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})
        graph.add_task("task-3", {"task-1"})
        graph.add_task("task-4", {"task-2", "task-3"})
        graph.build()

        # Process through the diamond
        ready = graph.get_ready_tasks()
        assert ready == ("task-1",)
        graph.mark_completed("task-1")

        ready = graph.get_ready_tasks()
        assert set(ready) == {"task-2", "task-3"}
        graph.mark_completed("task-2", "task-3")

        ready = graph.get_ready_tasks()
        assert ready == ("task-4",)


class TestGraphStats:
    """Test graph statistics."""

    def test_get_stats_empty_graph(self):
        """Test stats for empty graph."""
        graph = DependencyGraph()
        stats = graph.get_stats()

        assert stats["total_tasks"] == 0
        assert stats["total_dependencies"] == 0
        assert not stats["is_built"]
        assert not stats["is_active"]

    def test_get_stats_before_build(self):
        """Test stats after adding tasks but before build."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})

        stats = graph.get_stats()

        assert stats["total_tasks"] == EXPECTED_TASK_COUNT_TWO
        assert stats["total_dependencies"] == 1
        assert not stats["is_built"]
        assert not stats["is_active"]

    def test_get_stats_after_build(self):
        """Test stats after building graph."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})
        graph.add_task("task-3", {"task-1", "task-2"})
        graph.build()

        stats = graph.get_stats()

        assert stats["total_tasks"] == EXPECTED_TASK_COUNT_THREE
        assert stats["total_dependencies"] == EXPECTED_TASK_COUNT_THREE  # 0 + 1 + 2
        assert stats["is_built"]
        assert stats["is_active"]


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_task_with_nonexistent_dependency(self):
        """Test adding a task with dependencies that don't exist as tasks.

        Note: graphlib handles this by adding the nonexistent task as a node
        with no dependencies, so it appears as ready first.
        """
        graph = DependencyGraph()
        graph.add_task("task-1", {"nonexistent-task"})

        # This should build successfully
        graph.build()

        # The nonexistent-task will appear as ready first (no deps)
        ready = graph.get_ready_tasks()
        assert "nonexistent-task" in ready

        # Complete the nonexistent task to unblock task-1
        graph.mark_completed("nonexistent-task")

        # Now task-1 should be ready
        ready = graph.get_ready_tasks()
        assert "task-1" in ready

    def test_duplicate_task_overwrites(self):
        """Test that adding a task with the same ID overwrites the previous one."""
        graph = DependencyGraph()
        graph.add_task("task-1", {"dep-1"})
        graph.add_task("task-1", {"dep-2"})  # Overwrite

        assert graph.graph["task-1"] == {"dep-2"}

    def test_add_task_after_build_warning(self):
        """Test that adding tasks after build logs a warning but still works."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.build()

        # Adding after build should work but require rebuild
        graph.add_task("task-2", set())

        # The new task is in the graph
        assert "task-2" in graph.graph

    def test_empty_dependencies_set(self):
        """Test task with explicitly empty dependencies set."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.build()

        ready = graph.get_ready_tasks()
        assert "task-1" in ready
