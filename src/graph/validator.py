"""Graph validation with detailed cycle detection and reporting.

This module provides comprehensive validation for dependency graphs,
including cycle detection with path reporting, missing reference checks,
and orphaned task detection.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from src.graph.dependency_graph import DependencyGraph

logger = structlog.get_logger(__name__)


@dataclass
class ValidationReport:
    """Report containing validation results for a dependency graph.

    Attributes:
        is_valid: Whether the graph passed all validation checks
        errors: List of error messages (critical issues)
        warnings: List of warning messages (potential issues)
        cycles: List of detected cycles, each represented as a list of task IDs
        missing_refs: List of task IDs referenced as dependencies but not defined
        orphaned_tasks: List of task IDs that cannot reach completion
    """

    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    missing_refs: set[str] = field(default_factory=set)
    orphaned_tasks: set[str] = field(default_factory=set)

    def add_error(self, message: str) -> None:
        """Add an error message and mark validation as failed."""
        self.errors.append(message)
        self.is_valid = False
        logger.error("validation_error", message=message)

    def add_warning(self, message: str) -> None:
        """Add a warning message without failing validation."""
        self.warnings.append(message)
        logger.warning("validation_warning", message=message)

    def summary(self) -> str:
        """Generate a human-readable summary of the validation report."""
        lines = []
        lines.append(f"Validation Status: {'PASS' if self.is_valid else 'FAIL'}")
        lines.append(f"Errors: {len(self.errors)}")
        lines.append(f"Warnings: {len(self.warnings)}")
        lines.append(f"Cycles: {len(self.cycles)}")
        lines.append(f"Missing References: {len(self.missing_refs)}")
        lines.append(f"Orphaned Tasks: {len(self.orphaned_tasks)}")

        if self.errors:
            lines.append("\nErrors:")
            lines.extend(f"  - {error}" for error in self.errors)

        if self.warnings:
            lines.append("\nWarnings:")
            lines.extend(f"  - {warning}" for warning in self.warnings)

        if self.cycles:
            lines.append("\nCycles Detected:")
            for i, cycle in enumerate(self.cycles, 1):
                cycle_path = " -> ".join(cycle)
                lines.append(f"  {i}. {cycle_path}")

        if self.missing_refs:
            lines.append(f"\nMissing References: {', '.join(sorted(self.missing_refs))}")

        if self.orphaned_tasks:
            lines.append(f"\nOrphaned Tasks: {', '.join(sorted(self.orphaned_tasks))}")

        return "\n".join(lines)


class GraphValidator:
    """Validator for dependency graphs with detailed error reporting.

    This class provides comprehensive validation including:
    - Cycle detection with complete path information
    - Missing reference validation
    - Orphaned task detection
    - Graph visualization generation
    """

    def __init__(self):
        """Initialize the graph validator."""
        self._visited: set[str] = set()
        self._rec_stack: set[str] = set()
        self._path: list[str] = []

    def validate(self, graph: "DependencyGraph") -> ValidationReport:
        """Validate a dependency graph and generate a detailed report.

        Args:
            graph: The DependencyGraph to validate

        Returns:
            ValidationReport containing all validation results
        """
        logger.info("starting_graph_validation", task_count=len(graph.graph))

        report = ValidationReport()

        # Check for cycles
        cycles = self._detect_cycles(graph.graph)
        if cycles:
            report.cycles = cycles
            for cycle in cycles:
                cycle_path = " -> ".join(cycle)
                report.add_error(f"Cycle detected: {cycle_path}")

        # Check for missing references
        missing = self._check_missing_refs(graph.graph)
        if missing:
            report.missing_refs = missing
            refs_str = ", ".join(sorted(missing))
            report.add_warning(
                f"Tasks referenced as dependencies but not defined: {refs_str}",
            )

        # Check for orphaned tasks (only if no cycles)
        if not cycles:
            orphaned = self._check_orphaned_tasks(graph.graph)
            if orphaned:
                report.orphaned_tasks = orphaned
                orphaned_str = ", ".join(sorted(orphaned))
                report.add_warning(f"Orphaned tasks with no path to completion: {orphaned_str}")

        logger.info(
            "graph_validation_complete",
            is_valid=report.is_valid,
            error_count=len(report.errors),
            warning_count=len(report.warnings),
        )

        return report

    def _detect_cycles(self, graph: dict[str, set[str]]) -> list[list[str]]:
        """Detect all cycles in the graph using DFS.

        Args:
            graph: Dictionary mapping task IDs to their dependencies

        Returns:
            List of cycles, where each cycle is a list of task IDs forming the cycle
        """
        if not graph:
            return []

        # Reset state
        self._visited = set()
        self._rec_stack = set()
        self._path = []
        cycles = []

        # Get all nodes (including dependencies that aren't explicit tasks)
        all_nodes = set(graph.keys())
        for deps in graph.values():
            all_nodes.update(deps)

        # Try starting DFS from each unvisited node
        for node in all_nodes:
            if node not in self._visited:
                cycle = self._dfs_cycle_detect(node, graph, all_nodes)
                if cycle:
                    cycles.append(cycle)

        return cycles

    def _dfs_cycle_detect(
        self, node: str, graph: dict[str, set[str]], all_nodes: set[str],
    ) -> list[str] | None:
        """DFS-based cycle detection that returns the cycle path.

        Args:
            node: Current node being visited
            graph: The dependency graph
            all_nodes: Set of all nodes in the graph

        Returns:
            List representing the cycle path if found, None otherwise
        """
        self._visited.add(node)
        self._rec_stack.add(node)
        self._path.append(node)

        # Get dependencies for this node (empty set if node is not in graph)
        dependencies = graph.get(node, set())

        for dep in dependencies:
            if dep not in self._visited:
                cycle = self._dfs_cycle_detect(dep, graph, all_nodes)
                if cycle:
                    return cycle
            elif dep in self._rec_stack:
                # Found a cycle - extract the cycle path
                cycle_start_idx = self._path.index(dep)
                return [*self._path[cycle_start_idx:], dep]

        # Backtrack
        self._rec_stack.remove(node)
        self._path.pop()
        return None

    def _check_missing_refs(self, graph: dict[str, set[str]]) -> set[str]:
        """Check for task IDs referenced as dependencies but not defined as tasks.

        Args:
            graph: Dictionary mapping task IDs to their dependencies

        Returns:
            Set of task IDs that are referenced but not defined
        """
        defined_tasks = set(graph.keys())
        referenced_tasks = set()

        for deps in graph.values():
            referenced_tasks.update(deps)

        missing = referenced_tasks - defined_tasks

        if missing:
            logger.debug("missing_references_found", count=len(missing), tasks=list(missing))

        return missing

    def _check_orphaned_tasks(self, graph: dict[str, set[str]]) -> set[str]:
        """Check for tasks that have no path to completion.

        A task is orphaned if:
        1. It has dependencies on tasks that don't exist (handled by missing refs)
        2. It's part of a disconnected subgraph with no end nodes
        3. All paths from it lead to cycles (handled by cycle detection)

        Args:
            graph: Dictionary mapping task IDs to their dependencies

        Returns:
            Set of orphaned task IDs
        """
        if not graph:
            return set()

        # Build reverse dependency map (who depends on whom)
        reverse_deps: dict[str, set[str]] = {}
        for task, deps in graph.items():
            if task not in reverse_deps:
                reverse_deps[task] = set()
            for dep in deps:
                if dep not in reverse_deps:
                    reverse_deps[dep] = set()
                reverse_deps[dep].add(task)

        # Find end nodes (tasks that no one depends on)
        all_tasks = set(graph.keys())
        end_nodes = {task for task in all_tasks if not reverse_deps.get(task, set())}

        if not end_nodes:
            # If there are no end nodes, all tasks are part of cycles or isolated
            # This case is handled by cycle detection
            return set()

        # BFS from end nodes backwards to find all reachable tasks
        reachable = set()
        queue = list(end_nodes)

        while queue:
            current = queue.pop(0)
            if current in reachable:
                continue

            reachable.add(current)

            # Add all tasks that this task depends on
            for dep in graph.get(current, set()):
                if dep not in reachable:
                    queue.append(dep)

        # Orphaned tasks are those not reachable from end nodes
        orphaned = all_tasks - reachable

        if orphaned:
            logger.debug("orphaned_tasks_found", count=len(orphaned), tasks=list(orphaned))

        return orphaned

    def generate_visualization(
        self, graph: "DependencyGraph", output_format: str = "mermaid",
    ) -> str:
        """Generate a visual representation of the dependency graph.

        Args:
            graph: The DependencyGraph to visualize
            output_format: Output format ('mermaid' or 'dot')

        Returns:
            String representation of the graph in the requested format

        Raises:
            ValueError: If an unsupported format is requested
        """
        if output_format == "mermaid":
            return self._generate_mermaid(graph.graph)
        if output_format == "dot":
            return self._generate_graphviz(graph.graph)
        error_msg = f"Unsupported format: {output_format}. Use 'mermaid' or 'dot'."
        raise ValueError(error_msg)

    def _generate_mermaid(self, graph: dict[str, set[str]]) -> str:
        """Generate a Mermaid flowchart representation.

        Args:
            graph: Dictionary mapping task IDs to their dependencies

        Returns:
            Mermaid flowchart syntax
        """
        lines = ["graph TD"]

        if not graph:
            lines.append("    Empty[Empty Graph]")
            return "\n".join(lines)

        # Add all nodes
        for task_id in sorted(graph.keys()):
            # Sanitize task ID for Mermaid (replace special characters)
            sanitized_id = task_id.replace("-", "_").replace(".", "_")
            lines.append(f"    {sanitized_id}[{task_id}]")

        # Add edges (dependencies)
        for task_id, deps in sorted(graph.items()):
            sanitized_task = task_id.replace("-", "_").replace(".", "_")
            for dep in sorted(deps):
                sanitized_dep = dep.replace("-", "_").replace(".", "_")
                # Arrow points from dependency to dependent task
                lines.append(f"    {sanitized_dep} --> {sanitized_task}")

        return "\n".join(lines)

    def _generate_graphviz(self, graph: dict[str, set[str]]) -> str:
        """Generate a Graphviz DOT representation.

        Args:
            graph: Dictionary mapping task IDs to their dependencies

        Returns:
            Graphviz DOT syntax
        """
        lines = ["digraph DependencyGraph {"]
        lines.append("    rankdir=LR;")
        lines.append("    node [shape=box, style=rounded];")

        if not graph:
            lines.append('    Empty [label="Empty Graph"];')
        else:
            # Add nodes
            lines.extend(f'    "{task_id}";' for task_id in sorted(graph.keys()))

            # Add edges
            for task_id, deps in sorted(graph.items()):
                lines.extend(
                    f'    "{dep}" -> "{task_id}";' for dep in sorted(deps)
                )

        lines.append("}")
        return "\n".join(lines)
