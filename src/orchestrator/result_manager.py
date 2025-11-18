"""Task result collection and management module.

This module provides centralized storage, aggregation, and reporting
of task execution results with structured metadata tracking.
"""

import csv
import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class TaskResult:
    """Structured result data for a task execution.

    Attributes:
        task_id: Unique identifier for the task
        status: Task execution status (completed, failed, etc.)
        start_time: When task execution began
        end_time: When task execution finished
        duration_seconds: Total execution time in seconds
        agent_id: ID of the agent that executed the task
        result: Optional result data from successful execution
        error: Optional error message from failed execution
    """

    task_id: str
    status: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    agent_id: int
    result: dict | None = None
    error: str | None = None


class ResultManager:
    """Centralized manager for task result storage and reporting.

    Provides thread-safe result collection with statistics tracking,
    aggregation, and export capabilities for analysis.
    """

    def __init__(self) -> None:
        """Initialize result manager with empty storage."""
        self.results: dict[str, TaskResult] = {}
        self.success_count: int = 0
        self.failure_count: int = 0
        self._lock = threading.Lock()

    def add_result(self, result: TaskResult) -> None:
        """Add a task result to storage and update statistics.

        Args:
            result: TaskResult to store
        """
        with self._lock:
            self.results[result.task_id] = result

            if result.status == "completed":
                self.success_count += 1
            elif result.status == "failed":
                self.failure_count += 1

    def get_result(self, task_id: str) -> TaskResult | None:
        """Retrieve a specific task result by ID.

        Args:
            task_id: ID of task to retrieve

        Returns:
            TaskResult if found, None otherwise
        """
        return self.results.get(task_id)

    def get_all_results(self) -> list[TaskResult]:
        """Get all stored results.

        Returns:
            List of all TaskResult objects
        """
        return list(self.results.values())

    def get_results_by_status(self, status: str) -> list[TaskResult]:
        """Get all results matching a specific status.

        Args:
            status: Status to filter by (e.g., 'completed', 'failed')

        Returns:
            List of TaskResult objects with matching status
        """
        return [result for result in self.results.values() if result.status == status]

    def get_failed_tasks(self) -> list[TaskResult]:
        """Get all failed task results.

        Returns:
            List of TaskResult objects with failed status
        """
        return [result for result in self.results.values() if result.status == "failed"]

    def get_successful_tasks(self) -> list[TaskResult]:
        """Get all successful task results.

        Returns:
            List of TaskResult objects with completed status
        """
        return [result for result in self.results.values() if result.status == "completed"]

    def get_summary(self) -> dict:
        """Generate execution summary with statistics.

        Returns:
            Dictionary containing:
                - total_tasks: Total number of tasks
                - successful: Count of successful tasks
                - failed: Count of failed tasks
                - total_duration_seconds: Sum of all task durations
                - average_duration_seconds: Mean task duration
        """
        total_duration = sum(r.duration_seconds for r in self.results.values())

        return {
            "total_tasks": len(self.results),
            "successful": self.success_count,
            "failed": self.failure_count,
            "total_duration_seconds": total_duration,
            "average_duration_seconds": (
                total_duration / len(self.results) if self.results else 0.0
            ),
        }

    def export_json(self, filepath: str | Path) -> None:
        """Export results to JSON file.

        Exports both summary statistics and detailed results in JSON format
        with proper datetime serialization.

        Args:
            filepath: Path to output JSON file
        """
        filepath = Path(filepath)

        data = {
            "summary": self.get_summary(),
            "results": [asdict(r) for r in self.results.values()],
        }

        # Ensure parent directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with filepath.open("w") as f:
            json.dump(data, f, indent=2, default=str)

    def export_csv(self, filepath: str | Path) -> None:
        """Export results to CSV file.

        Exports detailed task results in CSV format for spreadsheet analysis.

        Args:
            filepath: Path to output CSV file
        """
        filepath = Path(filepath)

        if not self.results:
            return

        # Ensure parent directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # Get field names from dataclass
        fieldnames = [
            "task_id",
            "status",
            "start_time",
            "end_time",
            "duration_seconds",
            "agent_id",
            "error",
        ]

        with filepath.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for result in self.results.values():
                row = {
                    "task_id": result.task_id,
                    "status": result.status,
                    "start_time": result.start_time.isoformat(),
                    "end_time": result.end_time.isoformat(),
                    "duration_seconds": result.duration_seconds,
                    "agent_id": result.agent_id,
                    "error": result.error or "",
                }
                writer.writerow(row)

    def clear(self) -> None:
        """Clear all stored results and reset statistics."""
        self.results.clear()
        self.success_count = 0
        self.failure_count = 0

    def get_statistics(self) -> dict[str, Any]:
        """Get detailed statistics about task execution.

        Returns:
            Dictionary with comprehensive statistics including:
                - Basic counts (total, success, failed)
                - Duration statistics (total, average, min, max)
                - Agent utilization
                - Status breakdown
        """
        if not self.results:
            return {
                "total_tasks": 0,
                "successful": 0,
                "failed": 0,
                "total_duration_seconds": 0.0,
                "average_duration_seconds": 0.0,
                "min_duration_seconds": 0.0,
                "max_duration_seconds": 0.0,
                "agent_utilization": {},
                "status_breakdown": {},
            }

        durations = [r.duration_seconds for r in self.results.values()]

        # Calculate agent utilization
        agent_task_counts: dict[int, int] = {}
        for result in self.results.values():
            agent_task_counts[result.agent_id] = agent_task_counts.get(result.agent_id, 0) + 1

        # Calculate status breakdown
        status_breakdown: dict[str, int] = {}
        for result in self.results.values():
            status_breakdown[result.status] = status_breakdown.get(result.status, 0) + 1

        return {
            "total_tasks": len(self.results),
            "successful": self.success_count,
            "failed": self.failure_count,
            "total_duration_seconds": sum(durations),
            "average_duration_seconds": sum(durations) / len(durations),
            "min_duration_seconds": min(durations),
            "max_duration_seconds": max(durations),
            "agent_utilization": agent_task_counts,
            "status_breakdown": status_breakdown,
        }
