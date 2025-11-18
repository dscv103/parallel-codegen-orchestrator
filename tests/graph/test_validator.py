"""Unit tests for GraphValidator class.

Tests cover:
- Cycle detection with path reporting
- Missing reference detection
- Orphaned task detection
- Validation report generation
- Graph visualization
- Edge cases and error conditions
"""

import pytest

from src.graph.dependency_graph import DependencyGraph
from src.graph.validator import GraphValidator, ValidationReport


class TestValidationReport:
    """Test ValidationReport functionality."""

    def test_initialization(self):
        """Test that ValidationReport initializes correctly."""
        report = ValidationReport()

        assert report.is_valid is True
        assert report.errors == []
        assert report.warnings == []
        assert report.cycles == []
        assert report.missing_refs == set()
        assert report.orphaned_tasks == set()

    def test_add_error(self):
        """Test adding errors marks validation as failed."""
        report = ValidationReport()
        report.add_error("Test error")

        assert not report.is_valid
        assert len(report.errors) == 1
        assert "Test error" in report.errors

    def test_add_warning(self):
        """Test adding warnings doesn't fail validation."""
        report = ValidationReport()
        report.add_warning("Test warning")

        assert report.is_valid
        assert len(report.warnings) == 1
        assert "Test warning" in report.warnings

    def test_summary_empty_report(self):
        """Test summary generation for empty report."""
        report = ValidationReport()
        summary = report.summary()

        assert "Validation Status: PASS" in summary
        assert "Errors: 0" in summary
        assert "Warnings: 0" in summary

    def test_summary_with_errors(self):
        """Test summary generation with errors."""
        report = ValidationReport()
        report.add_error("Error 1")
        report.add_error("Error 2")
        summary = report.summary()

        assert "Validation Status: FAIL" in summary
        assert "Errors: 2" in summary
        assert "Error 1" in summary
        assert "Error 2" in summary

    def test_summary_with_cycles(self):
        """Test summary generation with cycle information."""
        report = ValidationReport()
        report.cycles = [["task-a", "task-b", "task-a"]]
        summary = report.summary()

        assert "Cycles: 1" in summary
        assert "task-a -> task-b -> task-a" in summary


class TestCycleDetection:
    """Test detailed cycle detection with path reporting."""

    def test_no_cycles_in_valid_graph(self):
        """Test that valid graphs report no cycles."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})

        validator = GraphValidator()
        report = validator.validate(graph)

        assert report.is_valid
        assert len(report.cycles) == 0
        assert len(report.errors) == 0

    def test_simple_two_task_cycle(self):
        """Test detection of simple two-task cycle with path."""
        graph = DependencyGraph()
        graph.add_task("task-a", {"task-b"})
        graph.add_task("task-b", {"task-a"})

        validator = GraphValidator()
        report = validator.validate(graph)

        assert not report.is_valid
        assert len(report.cycles) == 1
        cycle = report.cycles[0]
        # Cycle should be [task-a, task-b, task-a] or [task-b, task-a, task-b]
        assert len(cycle) == 3
        assert cycle[0] == cycle[-1]  # First and last should be same (cycle)

    def test_self_dependency_cycle(self):
        """Test detection of task depending on itself."""
        graph = DependencyGraph()
        graph.add_task("task-1", {"task-1"})

        validator = GraphValidator()
        report = validator.validate(graph)

        assert not report.is_valid
        assert len(report.cycles) == 1
        cycle = report.cycles[0]
        assert cycle == ["task-1", "task-1"]

    def test_three_task_cycle(self):
        """Test detection of three-task cycle with complete path."""
        graph = DependencyGraph()
        graph.add_task("task-a", {"task-c"})
        graph.add_task("task-b", {"task-a"})
        graph.add_task("task-c", {"task-b"})

        validator = GraphValidator()
        report = validator.validate(graph)

        assert not report.is_valid
        assert len(report.cycles) == 1
        cycle = report.cycles[0]
        # Should contain all three tasks plus one repeated to show cycle
        assert len(cycle) == 4
        assert cycle[0] == cycle[-1]

    def test_complex_graph_with_cycle(self):
        """Test cycle detection in graph with both valid and cyclic parts."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})
        # Create a cycle between task-3 and task-4
        graph.add_task("task-3", {"task-4"})
        graph.add_task("task-4", {"task-3"})

        validator = GraphValidator()
        report = validator.validate(graph)

        assert not report.is_valid
        assert len(report.cycles) == 1

    def test_multiple_cycles(self):
        """Test detection of multiple independent cycles."""
        graph = DependencyGraph()
        # First cycle: task-a <-> task-b
        graph.add_task("task-a", {"task-b"})
        graph.add_task("task-b", {"task-a"})
        # Second cycle: task-c <-> task-d
        graph.add_task("task-c", {"task-d"})
        graph.add_task("task-d", {"task-c"})

        validator = GraphValidator()
        report = validator.validate(graph)

        assert not report.is_valid
        # Should detect at least one cycle (DFS may find both or just one per component)
        assert len(report.cycles) >= 1


class TestMissingReferences:
    """Test detection of missing task references."""

    def test_no_missing_references_in_complete_graph(self):
        """Test that complete graphs report no missing references."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})

        validator = GraphValidator()
        report = validator.validate(graph)

        assert len(report.missing_refs) == 0
        assert report.is_valid

    def test_single_missing_reference(self):
        """Test detection of single missing task reference."""
        graph = DependencyGraph()
        graph.add_task("task-1", {"nonexistent-task"})

        validator = GraphValidator()
        report = validator.validate(graph)

        assert len(report.missing_refs) == 1
        assert "nonexistent-task" in report.missing_refs
        assert len(report.warnings) > 0
        assert report.is_valid  # Missing refs are warnings, not errors

    def test_multiple_missing_references(self):
        """Test detection of multiple missing references."""
        graph = DependencyGraph()
        graph.add_task("task-1", {"missing-a", "missing-b"})
        graph.add_task("task-2", {"missing-c"})

        validator = GraphValidator()
        report = validator.validate(graph)

        assert len(report.missing_refs) == 3
        assert "missing-a" in report.missing_refs
        assert "missing-b" in report.missing_refs
        assert "missing-c" in report.missing_refs

    def test_missing_reference_with_valid_dependencies(self):
        """Test mixed valid and missing dependencies."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1", "missing-task"})

        validator = GraphValidator()
        report = validator.validate(graph)

        assert len(report.missing_refs) == 1
        assert "missing-task" in report.missing_refs
        assert "task-1" not in report.missing_refs


class TestOrphanedTasks:
    """Test detection of orphaned tasks."""

    def test_no_orphaned_tasks_in_valid_graph(self):
        """Test that valid graphs report no orphaned tasks."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})
        graph.add_task("task-3", {"task-2"})

        validator = GraphValidator()
        report = validator.validate(graph)

        assert len(report.orphaned_tasks) == 0

    def test_orphaned_task_in_disconnected_subgraph(self):
        """Test detection of task in disconnected subgraph.

        In this case, we have two separate graphs:
        - task-1 -> task-2
        - task-3 -> task-4

        Since task-3 and task-4 don't connect to the main end nodes,
        they might be considered orphaned depending on implementation.
        """
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})
        # Disconnected subgraph
        graph.add_task("task-3", set())
        graph.add_task("task-4", {"task-3"})

        validator = GraphValidator()
        report = validator.validate(graph)

        # Both disconnected parts have end nodes, so no orphans
        assert len(report.orphaned_tasks) == 0

    def test_empty_graph_no_orphaned_tasks(self):
        """Test that empty graph reports no orphaned tasks."""
        graph = DependencyGraph()

        validator = GraphValidator()
        report = validator.validate(graph)

        assert len(report.orphaned_tasks) == 0


class TestGraphVisualization:
    """Test graph visualization generation."""

    def test_mermaid_visualization_empty_graph(self):
        """Test Mermaid visualization for empty graph."""
        graph = DependencyGraph()

        validator = GraphValidator()
        viz = validator.generate_visualization(graph, output_format="mermaid")

        assert "graph TD" in viz
        assert "Empty" in viz

    def test_mermaid_visualization_simple_graph(self):
        """Test Mermaid visualization for simple graph."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})

        validator = GraphValidator()
        viz = validator.generate_visualization(graph, output_format="mermaid")

        assert "graph TD" in viz
        assert "task_1" in viz or "task-1" in viz
        assert "task_2" in viz or "task-2" in viz
        assert "-->" in viz

    def test_mermaid_visualization_complex_graph(self):
        """Test Mermaid visualization for complex graph."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})
        graph.add_task("task-3", {"task-1"})
        graph.add_task("task-4", {"task-2", "task-3"})

        validator = GraphValidator()
        viz = validator.generate_visualization(graph, output_format="mermaid")

        assert "graph TD" in viz
        # Should have 4 nodes
        assert viz.count("task") >= 4

    def test_graphviz_visualization_simple_graph(self):
        """Test Graphviz DOT visualization."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", {"task-1"})

        validator = GraphValidator()
        viz = validator.generate_visualization(graph, output_format="dot")

        assert "digraph DependencyGraph" in viz
        assert "task-1" in viz
        assert "task-2" in viz
        assert "->" in viz

    def test_unsupported_visualization_format(self):
        """Test that unsupported format raises ValueError."""
        graph = DependencyGraph()

        validator = GraphValidator()
        with pytest.raises(ValueError, match="Unsupported format"):
            validator.generate_visualization(graph, output_format="invalid")


class TestIntegration:
    """Integration tests for complete validation workflows."""

    def test_validate_valid_complex_graph(self):
        """Test validation of a valid complex graph."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        graph.add_task("task-2", set())
        graph.add_task("task-3", {"task-1"})
        graph.add_task("task-4", {"task-2"})
        graph.add_task("task-5", {"task-3", "task-4"})

        validator = GraphValidator()
        report = validator.validate(graph)

        assert report.is_valid
        assert len(report.errors) == 0
        assert len(report.cycles) == 0
        assert len(report.missing_refs) == 0

    def test_validate_graph_with_all_issues(self):
        """Test validation of graph with cycles and missing references."""
        graph = DependencyGraph()
        # Valid task
        graph.add_task("task-1", set())
        # Task with missing reference
        graph.add_task("task-2", {"missing-task"})
        # Cycle
        graph.add_task("task-a", {"task-b"})
        graph.add_task("task-b", {"task-a"})

        validator = GraphValidator()
        report = validator.validate(graph)

        assert not report.is_valid
        assert len(report.errors) > 0  # Cycles are errors
        assert len(report.warnings) > 0  # Missing refs are warnings
        assert len(report.cycles) >= 1
        assert len(report.missing_refs) >= 1

    def test_validation_report_summary_completeness(self):
        """Test that validation report summary contains all relevant info."""
        graph = DependencyGraph()
        graph.add_task("task-a", {"task-b"})
        graph.add_task("task-b", {"task-a"})
        graph.add_task("task-c", {"missing-task"})

        validator = GraphValidator()
        report = validator.validate(graph)
        summary = report.summary()

        assert "Validation Status: FAIL" in summary
        assert "Cycles" in summary
        assert "Missing References" in summary
        assert "Errors:" in summary
        assert "Warnings:" in summary


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_single_task_no_dependencies(self):
        """Test validation of single task with no dependencies."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())

        validator = GraphValidator()
        report = validator.validate(graph)

        assert report.is_valid
        assert len(report.cycles) == 0
        assert len(report.missing_refs) == 0
        assert len(report.orphaned_tasks) == 0

    def test_empty_graph_validation(self):
        """Test validation of empty graph."""
        graph = DependencyGraph()

        validator = GraphValidator()
        report = validator.validate(graph)

        assert report.is_valid
        assert len(report.cycles) == 0
        assert len(report.missing_refs) == 0

    def test_task_with_empty_dependencies_set(self):
        """Test task with explicitly empty dependencies."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())

        validator = GraphValidator()
        report = validator.validate(graph)

        assert report.is_valid

    def test_duplicate_dependencies(self):
        """Test that duplicate dependencies in set don't cause issues."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())
        # Sets automatically deduplicate, but test explicit duplicates
        deps = {"task-1"}
        graph.add_task("task-2", deps)

        validator = GraphValidator()
        report = validator.validate(graph)

        assert report.is_valid

    def test_long_dependency_chain(self):
        """Test validation of long linear dependency chain."""
        graph = DependencyGraph()
        graph.add_task("task-1", set())

        for i in range(2, 11):
            graph.add_task(f"task-{i}", {f"task-{i-1}"})

        validator = GraphValidator()
        report = validator.validate(graph)

        assert report.is_valid
        assert len(report.cycles) == 0

    def test_visualization_with_special_characters(self):
        """Test visualization handles task IDs with special characters."""
        graph = DependencyGraph()
        graph.add_task("task-1.0", set())
        graph.add_task("task-2-beta", {"task-1.0"})

        validator = GraphValidator()
        viz = validator.generate_visualization(graph, output_format="mermaid")

        # Should handle special characters without errors
        assert "graph TD" in viz
        assert viz is not None
