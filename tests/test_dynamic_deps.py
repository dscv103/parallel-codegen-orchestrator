"""Tests for Dynamic Dependency Discovery and Graph Updates.

This module tests the DynamicDependencyManager, TaskExecutionContext,
and thread-safe graph modifications.
"""

import asyncio

import pytest

from src.graph.dependency_graph import CycleDetectedError, DependencyGraph
from src.orchestrator.dynamic_deps import (
    DynamicDependencyManager,
    DynamicTaskRegistrationError,
    TaskExecutionContext,
)


class TestDynamicDependencyManager:
    """Test suite for DynamicDependencyManager."""

    @pytest.fixture
    def dep_graph(self):
        """Create a dependency graph for testing."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})
        graph.build()
        return graph

    @pytest.fixture
    def manager(self, dep_graph):
        """Create a DynamicDependencyManager for testing."""
        return DynamicDependencyManager(dep_graph)

    @pytest.mark.asyncio
    async def test_add_simple_dynamic_task(self, manager):
        """Test adding a simple task with valid dependencies."""
        new_tasks = {
            "task-3": {
                "dependencies": {"task-1"},
                "prompt": "Implement feature C",
                "repo_id": "org/repo",
            },
        }

        await manager.add_dynamic_tasks(new_tasks)

        # Verify task was added to graph
        assert "task-3" in manager.dep_graph.graph
        assert manager.dep_graph.graph["task-3"] == {"task-1"}

        # Verify task was queued
        assert not manager.new_tasks_queue.empty()
        task_id, task_data = await manager.new_tasks_queue.get()
        assert task_id == "task-3"
        assert task_data["prompt"] == "Implement feature C"

    @pytest.mark.asyncio
    async def test_add_multiple_dynamic_tasks(self, manager):
        """Test adding multiple tasks at once."""
        new_tasks = {
            "task-3": {
                "dependencies": {"task-1"},
                "prompt": "Feature C",
                "repo_id": "org/repo",
            },
            "task-4": {
                "dependencies": {"task-2"},
                "prompt": "Feature D",
                "repo_id": "org/repo",
            },
        }

        await manager.add_dynamic_tasks(new_tasks)

        # Verify both tasks added
        assert "task-3" in manager.dep_graph.graph
        assert "task-4" in manager.dep_graph.graph

        # Verify both queued
        assert manager.new_tasks_queue.qsize() == 2

    @pytest.mark.asyncio
    async def test_cycle_detection_prevents_add(self, manager):
        """Test that cycle detection prevents adding tasks that would create cycles."""
        # Try to add task-1 depending on task-2, which would create cycle
        # (task-1 -> task-2 already exists, so task-2 -> task-1 creates cycle)
        new_tasks = {
            "task-2-updated": {
                "dependencies": {"task-2"},  # task-2 depends on task-1
                "prompt": "This would create a cycle",
                "repo_id": "org/repo",
            },
        }

        # First add a task that depends on task-2
        await manager.add_dynamic_tasks(new_tasks)

        # Now try to make task-1 depend on the new task (creates cycle)
        cycle_task = {
            "task-1": {  # task-1 already exists with no deps
                "dependencies": {"task-2-updated"},
                "prompt": "Cycle creator",
                "repo_id": "org/repo",
            },
        }

        # This should raise an error
        with pytest.raises(DynamicTaskRegistrationError) as exc_info:
            await manager.add_dynamic_tasks(cycle_task)

        assert "cycle" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_invalid_dependency_reference(self, manager):
        """Test that referencing non-existent dependencies raises error."""
        new_tasks = {
            "task-3": {
                "dependencies": {"task-nonexistent"},
                "prompt": "Feature C",
                "repo_id": "org/repo",
            },
        }

        with pytest.raises(DynamicTaskRegistrationError) as exc_info:
            await manager.add_dynamic_tasks(new_tasks)

        assert "non-existent" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_missing_dependencies_field(self, manager):
        """Test that missing dependencies field raises ValueError."""
        new_tasks = {
            "task-3": {
                "prompt": "Feature C",
                "repo_id": "org/repo",
                # Missing "dependencies" field
            },
        }

        with pytest.raises(ValueError) as exc_info:
            await manager.add_dynamic_tasks(new_tasks)

        assert "dependencies" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_dependencies_as_list(self, manager):
        """Test that dependencies can be provided as list instead of set."""
        new_tasks = {
            "task-3": {
                "dependencies": ["task-1", "task-2"],  # List instead of set
                "prompt": "Feature C",
                "repo_id": "org/repo",
            },
        }

        await manager.add_dynamic_tasks(new_tasks)

        # Should be converted to set in graph
        assert "task-3" in manager.dep_graph.graph
        assert manager.dep_graph.graph["task-3"] == {"task-1", "task-2"}

    @pytest.mark.asyncio
    async def test_graph_rebuild_after_add(self, manager):
        """Test that graph is rebuilt after adding tasks."""
        # Graph should be built initially
        assert manager.dep_graph._is_built

        new_tasks = {
            "task-3": {
                "dependencies": {"task-2"},
                "prompt": "Feature C",
                "repo_id": "org/repo",
            },
        }

        await manager.add_dynamic_tasks(new_tasks)

        # Graph should still be built after dynamic addition
        assert manager.dep_graph._is_built

        # Should be able to get ready tasks
        ready = manager.dep_graph.get_ready_tasks()
        assert "task-1" in ready  # task-1 has no deps

    @pytest.mark.asyncio
    async def test_concurrent_task_additions(self, manager):
        """Test that concurrent task additions are thread-safe."""

        async def add_task(task_num):
            new_tasks = {
                f"task-concurrent-{task_num}": {
                    "dependencies": {"task-1"},
                    "prompt": f"Concurrent task {task_num}",
                    "repo_id": "org/repo",
                },
            }
            await manager.add_dynamic_tasks(new_tasks)

        # Add 10 tasks concurrently
        await asyncio.gather(*[add_task(i) for i in range(10)])

        # Verify all tasks were added
        for i in range(10):
            task_id = f"task-concurrent-{i}"
            assert task_id in manager.dep_graph.graph

        # Verify all tasks were queued
        assert manager.new_tasks_queue.qsize() == 10

    @pytest.mark.asyncio
    async def test_inter_batch_cycle_detection(self, manager):
        """Test that cycles within a batch are detected."""
        # Create a batch where tasks refer to each other in a cycle
        new_tasks = {
            "task-a": {
                "dependencies": {"task-b"},  # a depends on b
                "prompt": "Task A",
                "repo_id": "org/repo",
            },
            "task-b": {
                "dependencies": {"task-c"},  # b depends on c
                "prompt": "Task B",
                "repo_id": "org/repo",
            },
            "task-c": {
                "dependencies": {"task-a"},  # c depends on a - creates cycle!
                "prompt": "Task C",
                "repo_id": "org/repo",
            },
        }

        # This should raise an error due to the cycle
        with pytest.raises(DynamicTaskRegistrationError) as exc_info:
            await manager.add_dynamic_tasks(new_tasks)

        assert "cycle" in str(exc_info.value).lower()

        # Verify no tasks were added to the graph
        assert "task-a" not in manager.dep_graph.graph
        assert "task-b" not in manager.dep_graph.graph
        assert "task-c" not in manager.dep_graph.graph

    @pytest.mark.asyncio
    async def test_batch_with_internal_dependencies(self, manager):
        """Test that tasks within a batch can depend on each other (no cycle)."""
        # Create a batch where tasks refer to each other without cycles
        new_tasks = {
            "task-a": {
                "dependencies": {"task-1"},  # a depends on existing task
                "prompt": "Task A",
                "repo_id": "org/repo",
            },
            "task-b": {
                "dependencies": {"task-a"},  # b depends on a (in same batch)
                "prompt": "Task B",
                "repo_id": "org/repo",
            },
            "task-c": {
                "dependencies": {"task-b"},  # c depends on b (in same batch)
                "prompt": "Task C",
                "repo_id": "org/repo",
            },
        }

        # This should succeed - no cycle, just a chain
        await manager.add_dynamic_tasks(new_tasks)

        # Verify all tasks were added
        assert "task-a" in manager.dep_graph.graph
        assert "task-b" in manager.dep_graph.graph
        assert "task-c" in manager.dep_graph.graph

        # Verify dependencies are correct
        assert manager.dep_graph.graph["task-a"] == {"task-1"}
        assert manager.dep_graph.graph["task-b"] == {"task-a"}
        assert manager.dep_graph.graph["task-c"] == {"task-b"}

    @pytest.mark.asyncio
    async def test_mark_task_completed(self, manager):
        """Test marking tasks as completed."""
        manager.mark_task_completed("task-1")

        assert "task-1" in manager._completed_tasks

    @pytest.mark.asyncio
    async def test_has_pending_tasks(self, manager):
        """Test checking for pending tasks."""
        # Initially empty
        assert not await manager.has_pending_tasks()

        # Add a task
        new_tasks = {
            "task-3": {
                "dependencies": {"task-1"},
                "prompt": "Feature C",
                "repo_id": "org/repo",
            },
        }
        await manager.add_dynamic_tasks(new_tasks)

        # Should have pending tasks
        assert await manager.has_pending_tasks()

        # Drain the queue
        await manager.get_next_task()

        # Should be empty again
        assert not await manager.has_pending_tasks()

    @pytest.mark.asyncio
    async def test_get_next_task_timeout(self, manager):
        """Test get_next_task with timeout on empty queue."""
        # Queue is empty, should timeout
        result = await manager.get_next_task(timeout=0.1)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_next_task_success(self, manager):
        """Test successfully getting next task from queue."""
        new_tasks = {
            "task-3": {
                "dependencies": {"task-1"},
                "prompt": "Feature C",
                "repo_id": "org/repo",
            },
        }
        await manager.add_dynamic_tasks(new_tasks)

        task = await manager.get_next_task(timeout=1.0)
        assert task is not None
        task_id, task_data = task
        assert task_id == "task-3"
        assert task_data["prompt"] == "Feature C"

    @pytest.mark.asyncio
    async def test_empty_tasks_dict(self, manager):
        """Test that adding empty tasks dict is handled gracefully."""
        await manager.add_dynamic_tasks({})

        # Should not have added anything
        assert manager.new_tasks_queue.empty()


class TestTaskExecutionContext:
    """Test suite for TaskExecutionContext."""

    @pytest.fixture
    def dep_graph(self):
        """Create a dependency graph for testing."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.build()
        return graph

    @pytest.fixture
    def manager(self, dep_graph):
        """Create a DynamicDependencyManager for testing."""
        return DynamicDependencyManager(dep_graph)

    @pytest.fixture
    def context(self, manager):
        """Create a TaskExecutionContext for testing."""
        return TaskExecutionContext(manager, "task-1")

    @pytest.mark.asyncio
    async def test_add_discovered_task(self, context, manager):
        """Test adding a discovered task through the context."""
        await context.add_discovered_task(
            "task-discovered",
            dependencies={"task-1"},
            task_data={
                "prompt": "Discovered during execution",
                "repo_id": "org/repo",
            },
        )

        # Verify task was added
        assert "task-discovered" in manager.dep_graph.graph

        # Verify task was queued
        task = await manager.get_next_task()
        assert task is not None
        task_id, task_data = task
        assert task_id == "task-discovered"

    @pytest.mark.asyncio
    async def test_add_discovered_task_with_list_deps(self, context, manager):
        """Test adding discovered task with dependencies as list."""
        await context.add_discovered_task(
            "task-discovered",
            dependencies=["task-1"],  # List instead of set
            task_data={
                "prompt": "Discovered task",
                "repo_id": "org/repo",
            },
        )

        assert "task-discovered" in manager.dep_graph.graph

    @pytest.mark.asyncio
    async def test_add_multiple_discovered_tasks(self, context, manager):
        """Test adding multiple discovered tasks at once."""
        tasks = {
            "task-a": {
                "dependencies": {"task-1"},
                "prompt": "Feature A",
                "repo_id": "org/repo",
            },
            "task-b": {
                "dependencies": {"task-1"},
                "prompt": "Feature B",
                "repo_id": "org/repo",
            },
        }

        await context.add_multiple_discovered_tasks(tasks)

        # Verify both added
        assert "task-a" in manager.dep_graph.graph
        assert "task-b" in manager.dep_graph.graph

        # Verify both queued
        assert manager.new_tasks_queue.qsize() == 2

    @pytest.mark.asyncio
    async def test_discovered_task_validation_error(self, context):
        """Test that validation errors are propagated."""
        with pytest.raises(DynamicTaskRegistrationError):
            await context.add_discovered_task(
                "task-invalid",
                dependencies={"task-nonexistent"},
                task_data={
                    "prompt": "Invalid task",
                    "repo_id": "org/repo",
                },
            )


class TestGraphCopyAndRebuild:
    """Test suite for DependencyGraph copy and rebuild functionality."""

    def test_graph_copy(self):
        """Test that graph copy creates independent copy."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})

        copy = graph.copy()

        # Should have same structure
        assert copy.graph == graph.graph

        # Should not share references
        copy.add_task("task-3", set())
        assert "task-3" not in graph.graph
        assert "task-3" in copy.graph

    def test_graph_rebuild(self):
        """Test rebuilding graph after adding tasks."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})
        graph.build()

        # Add a new task
        graph.add_task("task-3", {"task-2"})

        # Rebuild
        graph.rebuild()

        # Should be able to get ready tasks
        assert graph._is_built
        ready = graph.get_ready_tasks()
        assert "task-1" in ready

    def test_rebuild_detects_cycles(self):
        """Test that rebuild detects cycles in modified graph."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})
        graph.build()

        # Add a task that creates a cycle
        graph.add_task("task-1", {"task-2"})  # Overwrite task-1 to depend on task-2

        # Rebuild should detect the cycle
        with pytest.raises(CycleDetectedError):
            graph.rebuild()


class TestThreadSafety:
    """Test suite for thread-safety of concurrent operations."""

    @pytest.mark.asyncio
    async def test_lock_prevents_race_conditions(self):
        """Test that lock prevents race conditions during concurrent adds."""
        graph = DependencyGraph()
        graph.add_task("task-base", set())
        graph.build()

        manager = DynamicDependencyManager(graph)

        async def add_dependent_task(task_num):
            """Add a task that depends on task-base."""
            await manager.add_dynamic_tasks(
                {
                    f"task-concurrent-{task_num}": {
                        "dependencies": {"task-base"},
                        "prompt": f"Task {task_num}",
                        "repo_id": "org/repo",
                    },
                },
            )

        # Add 20 tasks concurrently
        await asyncio.gather(*[add_dependent_task(i) for i in range(20)])

        # All tasks should be in the graph
        assert len(manager.dep_graph.graph) == 21  # Original task-base + 20 new tasks

        # Graph should still be valid
        assert manager.dep_graph._is_built

        # All new tasks should be queued
        assert manager.new_tasks_queue.qsize() == 20
