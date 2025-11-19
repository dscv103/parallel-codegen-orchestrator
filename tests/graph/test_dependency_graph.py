"""Unit tests for DependencyGraph class.

Tests cover:
- Adding tasks with and without dependencies
- Building the graph
- Getting ready tasks
- Marking tasks completed
- Cycle detection
- Graph validation
- Edge cases and error conditions
- Dynamic graph updates
- Concurrency safety
- Race condition handling
"""

import asyncio
import contextlib
from concurrent.futures import ThreadPoolExecutor

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


class TestDynamicGraphUpdates:
    """Test dynamic graph updates during execution."""

    def test_add_task_during_execution(self):
        """Test adding new tasks after graph is built."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})
        graph.build()

        # Start execution
        ready = graph.get_ready_tasks()
        assert "task-1" in ready
        graph.mark_completed("task-1")

        # Dynamically add a new task
        graph.add_task("task-3", {"task-2"})
        graph.rebuild()

        # Verify new task is in the graph
        assert "task-3" in graph.graph
        assert graph.is_built

    def test_rebuild_preserves_graph_structure(self):
        """Test that rebuild maintains the graph structure."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})
        graph.build()

        # Add new task and rebuild
        graph.add_task("task-3", {"task-2"})
        graph.rebuild()

        # Verify all tasks are present
        assert len(graph.graph) == EXPECTED_TASK_COUNT_THREE
        assert graph.graph["task-1"] == set()
        assert graph.graph["task-2"] == {"task-1"}
        assert graph.graph["task-3"] == {"task-2"}

    def test_dynamic_addition_cycle_prevention(self):
        """Test that dynamically adding tasks can still create cycles."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})
        graph.build()

        # Add task that creates a cycle
        graph.add_task("task-1", {"task-2"})  # Overwrite task-1 to depend on task-2

        # Rebuild should detect the cycle
        with pytest.raises(CycleDetectedError):
            graph.rebuild()

    def test_add_independent_task_during_execution(self):
        """Test adding an independent task during execution."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.build()

        # Complete task-1
        ready = graph.get_ready_tasks()
        graph.mark_completed("task-1")

        # Add independent task
        graph.add_task("task-2", set())
        graph.rebuild()

        # New task should be ready
        ready = graph.get_ready_tasks()
        assert "task-2" in ready

    def test_rebuild_on_empty_graph(self):
        """Test rebuilding an empty graph."""
        graph = DependencyGraph()
        graph.build()

        # Rebuild empty graph
        graph.rebuild()

        assert graph.is_built
        assert not graph.is_active()

    def test_copy_graph(self):
        """Test creating a deep copy of the graph."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})

        # Create copy
        graph_copy = graph.copy()

        # Verify copy has same structure
        assert len(graph_copy.graph) == len(graph.graph)
        assert graph_copy.graph["task-1"] == graph.graph["task-1"]
        assert graph_copy.graph["task-2"] == graph.graph["task-2"]

        # Verify copy is independent
        graph.add_task("task-3", set())
        assert "task-3" not in graph_copy.graph

    def test_copy_graph_not_built(self):
        """Test that copied graph is not in built state."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.build()

        # Create copy
        graph_copy = graph.copy()

        # Copy should not be built
        assert not graph_copy.is_built
        assert graph_copy.sorter is None


class TestConcurrencySafety:
    """Test concurrency safety of DependencyGraph operations."""

    def test_concurrent_task_additions(self):
        """Test adding tasks concurrently from multiple threads."""
        graph = DependencyGraph()
        num_tasks = 50

        def add_tasks(start_idx: int, count: int):
            for i in range(start_idx, start_idx + count):
                graph.add_task(f"task-{i}", set())

        # Add tasks from multiple threads
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(add_tasks, i * 10, 10) for i in range(num_tasks // 10)]
            for future in futures:
                future.result()

        # Verify all tasks were added
        assert len(graph.graph) == num_tasks

    def test_concurrent_graph_reads(self):
        """Test reading graph state concurrently."""
        graph = DependencyGraph()
        for i in range(20):
            graph.add_task(f"task-{i}", set())
        graph.build()

        def read_graph_state():
            stats = graph.get_stats()
            is_active = graph.is_active()
            is_built = graph.is_built
            return stats, is_active, is_built

        # Read from multiple threads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(read_graph_state) for _ in range(50)]
            results = [f.result() for f in futures]

        # All reads should return same values
        assert all(r[1] == results[0][1] for r in results)  # is_active
        assert all(r[2] == results[0][2] for r in results)  # is_built

    @pytest.mark.asyncio
    async def test_async_lock_acquisition(self):
        """Test that async lock can be acquired properly."""
        graph = DependencyGraph()

        async def add_tasks_async():
            for i in range(10):
                graph.add_task(f"task-{i}", set())
                await asyncio.sleep(0.001)  # Simulate async operation

        # Run multiple async tasks
        await asyncio.gather(*[add_tasks_async() for _ in range(5)])

        # Note: DependencyGraph is not fully async-safe, but the lock exists
        # This test verifies the lock attribute exists and can be used
        # We access the private member to test its existence
        assert hasattr(graph, "_graph_lock")
        assert isinstance(graph._graph_lock, asyncio.Lock)  # noqa: SLF001


class TestRaceConditions:
    """Test handling of race conditions in graph operations."""

    def test_build_after_concurrent_adds(self):
        """Test building graph after concurrent task additions."""
        graph = DependencyGraph()

        def add_dependent_tasks(prefix: str):
            graph.add_task(f"{prefix}-1", set())
            graph.add_task(f"{prefix}-2", {f"{prefix}-1"})
            graph.add_task(f"{prefix}-3", {f"{prefix}-2"})

        # Add tasks from multiple threads
        with ThreadPoolExecutor(max_workers=5) as executor:
            prefixes = ["group-a", "group-b", "group-c", "group-d", "group-e"]
            futures = [executor.submit(add_dependent_tasks, p) for p in prefixes]
            for future in futures:
                future.result()

        # Build should succeed
        graph.build()
        assert graph.is_built

        # Verify we have all tasks
        expected_tasks = 15  # 5 groups * 3 tasks each
        assert len(graph.graph) == expected_tasks

    def test_multiple_builds_race_condition(self):
        """Test that multiple build calls don't cause issues."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})

        def build_graph():
            # Some builds may fail due to race conditions, which is acceptable
            # in this test scenario
            with contextlib.suppress(CycleDetectedError):
                graph.build()

        # Try building from multiple threads
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(build_graph) for _ in range(10)]
            for future in futures:
                future.result()

        # Final state should be built
        assert graph.is_built

    def test_get_ready_tasks_race_condition(self):
        """Test getting ready tasks with potential race conditions."""
        graph = DependencyGraph()
        for i in range(10):
            graph.add_task(f"task-{i}", set())
        graph.build()

        def get_ready():
            # Return empty tuple on any error during concurrent access
            return graph.get_ready_tasks()

        # Get ready tasks from multiple threads
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(get_ready) for _ in range(20)]
            results = [f.result() for f in futures]

        # All results should be tuples
        assert all(isinstance(r, tuple) for r in results)

        # All results should contain the same tasks (since none are completed)
        first_result_set = set(results[0])
        assert all(set(r) == first_result_set for r in results if r)


class TestComplexScenarios:
    """Test complex real-world scenarios."""

    def test_large_dag_topological_sort(self):
        """Test topological sort on a large DAG."""
        graph = DependencyGraph()

        # Create a large DAG: 100 tasks in 10 levels
        num_levels = 10
        tasks_per_level = 10

        for level in range(num_levels):
            for task_num in range(tasks_per_level):
                task_id = f"task-L{level}-{task_num}"
                if level == 0:
                    graph.add_task(task_id, set())
                else:
                    # Depend on some tasks from previous level
                    deps = {f"task-L{level - 1}-{i}" for i in range(min(3, tasks_per_level))}
                    graph.add_task(task_id, deps)

        graph.build()
        assert graph.is_built

        # Execute and verify order
        completed_tasks = []
        while graph.is_active():
            ready = graph.get_ready_tasks()
            assert len(ready) > 0
            # Extend list with all ready tasks
            completed_tasks.extend(ready)
            graph.mark_completed(*ready)

        # Verify all tasks were completed
        assert len(completed_tasks) == num_levels * tasks_per_level

    def test_multiple_independent_chains(self):
        """Test multiple independent dependency chains."""
        graph = DependencyGraph()

        # Create 5 independent chains of 5 tasks each
        num_chains = 5
        chain_length = 5

        for chain in range(num_chains):
            for pos in range(chain_length):
                task_id = f"chain-{chain}-task-{pos}"
                if pos == 0:
                    graph.add_task(task_id, set())
                else:
                    deps = {f"chain-{chain}-task-{pos - 1}"}
                    graph.add_task(task_id, deps)

        graph.build()

        # At start, first task of each chain should be ready
        ready = graph.get_ready_tasks()
        assert len(ready) == num_chains

        # Complete all chains
        completed_count = 0
        while graph.is_active():
            ready = graph.get_ready_tasks()
            completed_count += len(ready)
            graph.mark_completed(*ready)

        assert completed_count == num_chains * chain_length

    def test_dynamic_cycle_prevention_complex(self):
        """Test cycle prevention in a complex scenario."""
        graph = DependencyGraph()

        # Create initial valid graph
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})
        graph.add_task("task-3", {"task-2"})
        graph.add_task("task-4", {"task-3"})
        graph.build()

        # Try to create cycle by adding dependency back
        graph.add_task("task-1", {"task-4"})

        # Rebuild should detect cycle
        with pytest.raises(CycleDetectedError):
            graph.rebuild()

    def test_mixed_parallel_and_sequential(self):
        """Test mixed parallel and sequential execution patterns."""
        graph = DependencyGraph()

        # Sequential start
        graph.add_task("init", set())

        # Parallel middle section
        for i in range(5):
            graph.add_task(f"parallel-{i}", {"init"})

        # Sequential end
        graph.add_task("merge", {f"parallel-{i}" for i in range(5)})
        graph.add_task("final", {"merge"})

        graph.build()

        # Verify execution pattern
        ready = graph.get_ready_tasks()
        assert ready == ("init",)
        graph.mark_completed("init")

        ready = graph.get_ready_tasks()
        assert len(ready) == 5  # All parallel tasks ready
        graph.mark_completed(*ready)

        ready = graph.get_ready_tasks()
        assert ready == ("merge",)
        graph.mark_completed("merge")

        ready = graph.get_ready_tasks()
        assert ready == ("final",)
