"""Progress Monitoring and Metrics Module.

This module provides real-time tracking of task orchestration progress,
including task states, throughput metrics, and performance statistics.
"""

import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

# Initialize logger
logger = structlog.get_logger(__name__)


@dataclass
class ProgressSnapshot:
    """Immutable snapshot of progress at a point in time.

    Attributes:
        timestamp: When this snapshot was taken
        total: Total number of tasks
        completed: Number of completed tasks
        failed: Number of failed tasks
        in_progress: Number of tasks currently executing
        remaining: Number of tasks not yet started
        throughput: Tasks completed per second since tracking started
        average_duration: Average task duration in seconds
    """

    timestamp: datetime
    total: int
    completed: int
    failed: int
    in_progress: int
    remaining: int
    throughput: float
    average_duration: float


class ProgressMonitor:
    """Real-time progress and performance monitoring for task orchestration.

    Provides thread-safe tracking of task states, metrics calculation,
    and reporting capabilities for dashboards and CLI output.

    Key Features:
        - Thread-safe state updates
        - Real-time metrics calculation (throughput, remaining tasks)
        - Snapshot-based reporting for consistent data views
        - Automatic logging at configurable intervals
        - Performance statistics (average duration, throughput)

    Example:
        >>> monitor = ProgressMonitor(total_tasks=10)
        >>> monitor.update('completed')
        >>> monitor.update('failed')
        >>> report = monitor.report()
        >>> print(f"Progress: {report['completed']}/{report['total']}")

    Attributes:
        total_tasks: Total number of tasks to execute
        completed: Number of successfully completed tasks
        failed: Number of failed tasks
        in_progress: Number of tasks currently being executed
        start_time: When tracking started
        task_durations: List of completed task durations for statistics
    """

    def __init__(self, total_tasks: int, log_interval_seconds: float = 30.0):
        """Initialize progress monitor with total task count.

        Args:
            total_tasks: Total number of tasks in the orchestration
            log_interval_seconds: How often to log progress snapshots (default: 30s)

        Raises:
            ValueError: If total_tasks is not positive

        Example:
            >>> monitor = ProgressMonitor(total_tasks=100)
        """
        if total_tasks <= 0:
            msg = "total_tasks must be positive"
            raise ValueError(msg)

        self.total_tasks = total_tasks
        self.completed = 0
        self.failed = 0
        self.in_progress = 0
        self.start_time = time.time()
        self.task_durations: list[float] = []

        self._lock = threading.Lock()
        self._last_log_time = self.start_time
        self._log_interval = log_interval_seconds

        logger.info(
            "progress_monitor_initialized",
            total_tasks=total_tasks,
            log_interval_seconds=log_interval_seconds,
        )

    def update(self, status: str, duration_seconds: float | None = None) -> None:
        """Update progress based on task status change.

        Thread-safe method to record task status transitions. Automatically
        logs progress snapshots at configured intervals.

        Args:
            status: Task status - one of 'in_progress', 'completed', 'failed'
            duration_seconds: Optional task duration for completed/failed tasks

        Raises:
            ValueError: If status is not recognized

        Example:
            >>> monitor.update('in_progress')
            >>> monitor.update('completed', duration_seconds=5.2)
            >>> monitor.update('failed', duration_seconds=1.5)
        """
        with self._lock:
            if status == "in_progress":
                self.in_progress += 1
            elif status == "completed":
                self.completed += 1
                if self.in_progress > 0:
                    self.in_progress -= 1
                if duration_seconds is not None:
                    self.task_durations.append(duration_seconds)
            elif status == "failed":
                self.failed += 1
                if self.in_progress > 0:
                    self.in_progress -= 1
                if duration_seconds is not None:
                    self.task_durations.append(duration_seconds)
            else:
                msg = f"Unknown status: {status}"
                raise ValueError(msg)

            # Log progress at regular intervals
            current_time = time.time()
            if current_time - self._last_log_time >= self._log_interval:
                self._log_progress_snapshot()
                self._last_log_time = current_time

    def report(self) -> dict[str, Any]:
        """Generate real-time progress report with metrics.

        Returns a snapshot of current progress with calculated metrics.
        Thread-safe and returns consistent data view.

        Returns:
            Dictionary containing:
                - total: Total tasks
                - completed: Successfully completed tasks
                - failed: Failed tasks
                - in_progress: Currently executing tasks
                - remaining: Tasks not yet started (total - completed - failed - in_progress)
                - throughput: Tasks per second since start
                - average_duration_seconds: Mean task duration
                - elapsed_seconds: Time since tracking started
                - completion_percentage: Percentage of tasks completed (0-100)
                - estimated_time_remaining_seconds: Estimated seconds until completion

        Example:
            >>> report = monitor.report()
            >>> print(f"{report['completion_percentage']:.1f}% complete")
            >>> print(f"ETA: {report['estimated_time_remaining_seconds']:.0f}s")
        """
        with self._lock:
            snapshot = self._create_snapshot()

        return {
            "total": snapshot.total,
            "completed": snapshot.completed,
            "failed": snapshot.failed,
            "in_progress": snapshot.in_progress,
            "remaining": snapshot.remaining,
            "throughput": snapshot.throughput,
            "average_duration_seconds": snapshot.average_duration,
            "elapsed_seconds": time.time() - self.start_time,
            "completion_percentage": self._calculate_completion_percentage(),
            "estimated_time_remaining_seconds": self._estimate_time_remaining(snapshot),
        }

    def get_snapshot(self) -> ProgressSnapshot:
        """Get an immutable snapshot of current progress.

        Returns:
            ProgressSnapshot with current state and metrics

        Example:
            >>> snapshot = monitor.get_snapshot()
            >>> print(f"Throughput: {snapshot.throughput:.2f} tasks/sec")
        """
        with self._lock:
            return self._create_snapshot()

    def _create_snapshot(self) -> ProgressSnapshot:
        """Create progress snapshot from current state.

        Must be called with lock held.

        Returns:
            ProgressSnapshot with current metrics
        """
        elapsed = time.time() - self.start_time
        throughput = self.completed / elapsed if elapsed > 0 else 0.0
        avg_duration = (
            sum(self.task_durations) / len(self.task_durations) if self.task_durations else 0.0
        )
        remaining = self.total_tasks - self.completed - self.failed - self.in_progress

        return ProgressSnapshot(
            timestamp=datetime.now(UTC),
            total=self.total_tasks,
            completed=self.completed,
            failed=self.failed,
            in_progress=self.in_progress,
            remaining=remaining,
            throughput=throughput,
            average_duration=avg_duration,
        )

    def _calculate_completion_percentage(self) -> float:
        """Calculate percentage of completed work (completed + failed).

        Returns:
            Completion percentage (0-100)
        """
        if self.total_tasks == 0:
            return 0.0
        return ((self.completed + self.failed) / self.total_tasks) * 100.0

    def _estimate_time_remaining(self, snapshot: ProgressSnapshot) -> float:
        """Estimate time until all tasks complete based on current throughput.

        Args:
            snapshot: Current progress snapshot

        Returns:
            Estimated seconds until completion, or 0 if throughput is zero
        """
        if snapshot.throughput == 0:
            return 0.0

        tasks_remaining = snapshot.remaining + snapshot.in_progress
        return tasks_remaining / snapshot.throughput

    def _log_progress_snapshot(self) -> None:
        """Log current progress snapshot to structured logs.

        Must be called with lock held.
        """
        snapshot = self._create_snapshot()
        completion_pct = self._calculate_completion_percentage()
        time_remaining = self._estimate_time_remaining(snapshot)

        logger.info(
            "progress_snapshot",
            total=snapshot.total,
            completed=snapshot.completed,
            failed=snapshot.failed,
            in_progress=snapshot.in_progress,
            remaining=snapshot.remaining,
            completion_percentage=f"{completion_pct:.1f}%",
            throughput=f"{snapshot.throughput:.2f} tasks/sec",
            average_duration_seconds=f"{snapshot.average_duration:.2f}s",
            estimated_time_remaining_seconds=f"{time_remaining:.0f}s",
        )

    def reset(self) -> None:
        """Reset all progress tracking to initial state.

        Useful for reusing the monitor for a new orchestration run.

        Example:
            >>> monitor.reset()
            >>> monitor.update('in_progress')  # Start new tracking
        """
        with self._lock:
            self.completed = 0
            self.failed = 0
            self.in_progress = 0
            self.start_time = time.time()
            self.task_durations.clear()
            self._last_log_time = self.start_time

        logger.info("progress_monitor_reset")

    def is_complete(self) -> bool:
        """Check if all tasks have completed (successfully or failed).

        Returns:
            True if all tasks are done, False otherwise

        Example:
            >>> if monitor.is_complete():
            ...     print("All tasks finished!")
        """
        with self._lock:
            return (self.completed + self.failed) >= self.total_tasks
