"""Unit tests for Progress Monitoring and Metrics.

Tests for the ProgressMonitor class including state tracking,
metrics calculation, and thread-safety.
"""

import time
from datetime import datetime
from unittest.mock import patch

import pytest

from src.orchestrator.progress import ProgressMonitor, ProgressSnapshot


class TestProgressMonitor:
    """Test suite for ProgressMonitor class."""

    def test_init_valid_total(self):
        """Test initialization with valid total tasks."""
        monitor = ProgressMonitor(total_tasks=10)
        assert monitor.total_tasks == 10
        assert monitor.completed == 0
        assert monitor.failed == 0
        assert monitor.in_progress == 0
        assert len(monitor.task_durations) == 0

    def test_init_custom_log_interval(self):
        """Test initialization with custom log interval."""
        monitor = ProgressMonitor(total_tasks=5, log_interval_seconds=60.0)
        assert monitor._log_interval == 60.0

    def test_init_invalid_total_zero(self):
        """Test initialization fails with zero total tasks."""
        with pytest.raises(ValueError, match="total_tasks must be positive"):
            ProgressMonitor(total_tasks=0)

    def test_init_invalid_total_negative(self):
        """Test initialization fails with negative total tasks."""
        with pytest.raises(ValueError, match="total_tasks must be positive"):
            ProgressMonitor(total_tasks=-5)

    def test_update_in_progress(self):
        """Test updating status to in_progress."""
        monitor = ProgressMonitor(total_tasks=10)
        monitor.update("in_progress")

        assert monitor.in_progress == 1
        assert monitor.completed == 0
        assert monitor.failed == 0

    def test_update_completed(self):
        """Test updating status to completed."""
        monitor = ProgressMonitor(total_tasks=10)
        monitor.update("in_progress")
        monitor.update("completed", duration_seconds=5.0)

        assert monitor.completed == 1
        assert monitor.in_progress == 0
        assert monitor.failed == 0
        assert 5.0 in monitor.task_durations

    def test_update_completed_without_in_progress(self):
        """Test completing task that wasn't tracked as in_progress."""
        monitor = ProgressMonitor(total_tasks=10)
        monitor.update("completed", duration_seconds=5.0)

        assert monitor.completed == 1
        assert monitor.in_progress == 0

    def test_update_failed(self):
        """Test updating status to failed."""
        monitor = ProgressMonitor(total_tasks=10)
        monitor.update("in_progress")
        monitor.update("failed", duration_seconds=2.0)

        assert monitor.failed == 1
        assert monitor.in_progress == 0
        assert monitor.completed == 0
        assert 2.0 in monitor.task_durations

    def test_update_multiple_tasks(self):
        """Test updating multiple tasks with various statuses."""
        monitor = ProgressMonitor(total_tasks=10)

        # Start 3 tasks
        monitor.update("in_progress")
        monitor.update("in_progress")
        monitor.update("in_progress")
        assert monitor.in_progress == 3

        # Complete 2 tasks
        monitor.update("completed", duration_seconds=3.0)
        monitor.update("completed", duration_seconds=4.0)
        assert monitor.completed == 2
        assert monitor.in_progress == 1

        # Fail 1 task
        monitor.update("failed", duration_seconds=1.5)
        assert monitor.failed == 1
        assert monitor.in_progress == 0

    def test_update_invalid_status(self):
        """Test updating with invalid status raises ValueError."""
        monitor = ProgressMonitor(total_tasks=10)

        with pytest.raises(ValueError, match="Unknown status"):
            monitor.update("invalid_status")

    def test_report_initial_state(self):
        """Test report() returns correct initial state."""
        monitor = ProgressMonitor(total_tasks=10)
        report = monitor.report()

        assert report["total"] == 10
        assert report["completed"] == 0
        assert report["failed"] == 0
        assert report["in_progress"] == 0
        assert report["remaining"] == 10
        assert report["throughput"] == 0.0
        assert report["average_duration_seconds"] == 0.0
        assert report["completion_percentage"] == 0.0
        assert report["elapsed_seconds"] >= 0.0

    def test_report_with_progress(self):
        """Test report() after some tasks complete."""
        monitor = ProgressMonitor(total_tasks=10)

        monitor.update("completed", duration_seconds=2.0)
        monitor.update("completed", duration_seconds=3.0)
        monitor.update("failed", duration_seconds=1.0)
        monitor.update("in_progress")

        time.sleep(0.1)  # Ensure some time passes for throughput calculation
        report = monitor.report()

        assert report["completed"] == 2
        assert report["failed"] == 1
        assert report["in_progress"] == 1
        assert report["remaining"] == 6
        assert report["throughput"] > 0.0
        assert report["average_duration_seconds"] == pytest.approx(2.0)
        assert report["completion_percentage"] == pytest.approx(30.0)
        assert report["elapsed_seconds"] > 0.0

    def test_report_completion_percentage(self):
        """Test completion percentage calculation."""
        monitor = ProgressMonitor(total_tasks=100)

        # Complete 30 tasks
        for _ in range(30):
            monitor.update("completed", duration_seconds=1.0)

        report = monitor.report()
        assert report["completion_percentage"] == pytest.approx(30.0)

        # Fail 20 more tasks (total 50% done)
        for _ in range(20):
            monitor.update("failed", duration_seconds=1.0)

        report = monitor.report()
        assert report["completion_percentage"] == pytest.approx(50.0)

    def test_report_estimated_time_remaining(self):
        """Test estimated time remaining calculation."""
        monitor = ProgressMonitor(total_tasks=10)

        # Complete tasks with known timing
        time.sleep(0.1)
        for _ in range(5):
            monitor.update("completed", duration_seconds=1.0)

        report = monitor.report()

        # Should estimate based on throughput
        assert report["estimated_time_remaining_seconds"] >= 0.0
        # With 5 completed out of 10, should have estimate for remaining 5

    def test_get_snapshot(self):
        """Test get_snapshot() returns ProgressSnapshot."""
        monitor = ProgressMonitor(total_tasks=10)
        monitor.update("completed", duration_seconds=5.0)
        monitor.update("in_progress")

        time.sleep(0.1)
        snapshot = monitor.get_snapshot()

        assert isinstance(snapshot, ProgressSnapshot)
        assert isinstance(snapshot.timestamp, datetime)
        assert snapshot.total == 10
        assert snapshot.completed == 1
        assert snapshot.failed == 0
        assert snapshot.in_progress == 1
        assert snapshot.remaining == 8
        assert snapshot.throughput > 0.0
        assert snapshot.average_duration == 5.0

    def test_snapshot_immutability(self):
        """Test that snapshot is an immutable dataclass."""
        monitor = ProgressMonitor(total_tasks=10)
        snapshot = monitor.get_snapshot()

        # Dataclasses are not truly immutable by default, but we test
        # that modifications to monitor don't affect existing snapshot
        original_completed = snapshot.completed
        monitor.update("completed")

        assert snapshot.completed == original_completed

    @patch("src.orchestrator.progress.logger")
    def test_automatic_logging_at_interval(self, mock_logger):
        """Test that progress is logged automatically at intervals."""
        monitor = ProgressMonitor(total_tasks=10, log_interval_seconds=0.1)

        # Clear initialization log
        mock_logger.info.reset_mock()

        # Update and wait for log interval
        monitor.update("completed", duration_seconds=1.0)
        time.sleep(0.15)

        # Next update should trigger log
        monitor.update("completed", duration_seconds=1.0)

        # Check that progress_snapshot was logged
        calls = [
            call for call in mock_logger.info.call_args_list if call[0][0] == "progress_snapshot"
        ]
        assert len(calls) > 0

    @patch("src.orchestrator.progress.logger")
    def test_no_logging_before_interval(self, mock_logger):
        """Test that progress is not logged before interval expires."""
        monitor = ProgressMonitor(total_tasks=10, log_interval_seconds=10.0)

        # Clear initialization log
        mock_logger.info.reset_mock()

        # Update multiple times quickly
        monitor.update("completed", duration_seconds=1.0)
        monitor.update("completed", duration_seconds=1.0)
        monitor.update("completed", duration_seconds=1.0)

        # Check that progress_snapshot was NOT logged
        calls = [
            call for call in mock_logger.info.call_args_list if call[0][0] == "progress_snapshot"
        ]
        assert len(calls) == 0

    def test_reset(self):
        """Test reset() clears all progress."""
        monitor = ProgressMonitor(total_tasks=10)

        # Make some progress
        monitor.update("completed", duration_seconds=2.0)
        monitor.update("failed", duration_seconds=1.0)
        monitor.update("in_progress")

        # Reset
        monitor.reset()

        assert monitor.completed == 0
        assert monitor.failed == 0
        assert monitor.in_progress == 0
        assert len(monitor.task_durations) == 0

        report = monitor.report()
        assert report["completed"] == 0
        assert report["failed"] == 0

    def test_is_complete_not_done(self):
        """Test is_complete() returns False when tasks remain."""
        monitor = ProgressMonitor(total_tasks=10)

        monitor.update("completed", duration_seconds=1.0)
        monitor.update("failed", duration_seconds=1.0)

        assert not monitor.is_complete()

    def test_is_complete_all_done(self):
        """Test is_complete() returns True when all tasks complete."""
        monitor = ProgressMonitor(total_tasks=3)

        monitor.update("completed", duration_seconds=1.0)
        monitor.update("completed", duration_seconds=1.0)
        monitor.update("failed", duration_seconds=1.0)

        assert monitor.is_complete()

    def test_is_complete_only_completed(self):
        """Test is_complete() with only successful completions."""
        monitor = ProgressMonitor(total_tasks=5)

        for _ in range(5):
            monitor.update("completed", duration_seconds=1.0)

        assert monitor.is_complete()

    def test_is_complete_only_failed(self):
        """Test is_complete() with only failures."""
        monitor = ProgressMonitor(total_tasks=5)

        for _ in range(5):
            monitor.update("failed", duration_seconds=1.0)

        assert monitor.is_complete()

    def test_thread_safety(self):
        """Test thread-safe operations with concurrent updates."""
        import threading

        monitor = ProgressMonitor(total_tasks=100)

        def complete_tasks(count):
            for _ in range(count):
                monitor.update("completed", duration_seconds=0.1)

        # Create multiple threads updating concurrently
        threads = [threading.Thread(target=complete_tasks, args=(10,)) for _ in range(10)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Should have exactly 100 completed tasks
        assert monitor.completed == 100

    def test_throughput_calculation(self):
        """Test throughput is calculated correctly."""
        monitor = ProgressMonitor(total_tasks=10)

        # Wait a known amount of time
        time.sleep(0.1)

        # Complete 2 tasks
        monitor.update("completed", duration_seconds=1.0)
        monitor.update("completed", duration_seconds=1.0)

        report = monitor.report()

        # Throughput should be roughly 2 tasks / elapsed_seconds
        expected_throughput = 2.0 / report["elapsed_seconds"]
        assert report["throughput"] == pytest.approx(expected_throughput, rel=0.1)

    def test_average_duration_calculation(self):
        """Test average duration is calculated correctly."""
        monitor = ProgressMonitor(total_tasks=10)

        monitor.update("completed", duration_seconds=1.0)
        monitor.update("completed", duration_seconds=2.0)
        monitor.update("completed", duration_seconds=3.0)
        monitor.update("failed", duration_seconds=4.0)

        report = monitor.report()

        # Average of [1.0, 2.0, 3.0, 4.0] = 2.5
        assert report["average_duration_seconds"] == pytest.approx(2.5)

    def test_remaining_tasks_calculation(self):
        """Test remaining tasks calculation."""
        monitor = ProgressMonitor(total_tasks=20)

        monitor.update("completed", duration_seconds=1.0)  # 1 completed
        monitor.update("completed", duration_seconds=1.0)  # 2 completed
        monitor.update("failed", duration_seconds=1.0)  # 1 failed
        monitor.update("in_progress")  # 1 in progress
        monitor.update("in_progress")  # 2 in progress

        report = monitor.report()

        # Remaining = 20 - 2 (completed) - 1 (failed) - 2 (in progress) = 15
        assert report["remaining"] == 15

    def test_zero_throughput_handling(self):
        """Test handling of zero throughput (no tasks completed yet)."""
        monitor = ProgressMonitor(total_tasks=10)

        report = monitor.report()

        assert report["throughput"] == 0.0
        assert report["estimated_time_remaining_seconds"] == 0.0

    @patch("src.orchestrator.progress.logger")
    def test_logging_format(self, mock_logger):
        """Test that logged snapshots contain expected fields."""
        monitor = ProgressMonitor(total_tasks=10, log_interval_seconds=0.1)

        # Clear initialization log
        mock_logger.info.reset_mock()

        monitor.update("completed", duration_seconds=2.0)
        time.sleep(0.15)
        monitor.update("completed", duration_seconds=3.0)

        # Find progress_snapshot log call
        snapshot_calls = [
            call for call in mock_logger.info.call_args_list if call[0][0] == "progress_snapshot"
        ]

        assert len(snapshot_calls) > 0

        # Check that expected fields are present
        call_kwargs = snapshot_calls[0][1]
        assert "total" in call_kwargs
        assert "completed" in call_kwargs
        assert "failed" in call_kwargs
        assert "in_progress" in call_kwargs
        assert "remaining" in call_kwargs
        assert "completion_percentage" in call_kwargs
        assert "throughput" in call_kwargs
        assert "average_duration_seconds" in call_kwargs


class TestProgressSnapshot:
    """Test suite for ProgressSnapshot dataclass."""

    def test_snapshot_creation(self):
        """Test creating a ProgressSnapshot."""
        now = datetime.now()
        snapshot = ProgressSnapshot(
            timestamp=now,
            total=10,
            completed=5,
            failed=1,
            in_progress=2,
            remaining=2,
            throughput=0.5,
            average_duration=2.5,
        )

        assert snapshot.timestamp == now
        assert snapshot.total == 10
        assert snapshot.completed == 5
        assert snapshot.failed == 1
        assert snapshot.in_progress == 2
        assert snapshot.remaining == 2
        assert snapshot.throughput == 0.5
        assert snapshot.average_duration == 2.5

    def test_snapshot_is_dataclass(self):
        """Test that ProgressSnapshot is a dataclass."""
        from dataclasses import is_dataclass

        assert is_dataclass(ProgressSnapshot)


class TestProgressMonitorIntegration:
    """Integration tests for ProgressMonitor with realistic scenarios."""

    def test_full_orchestration_simulation(self):
        """Simulate a full orchestration lifecycle."""
        total = 10
        monitor = ProgressMonitor(total_tasks=total)

        # Simulate tasks being dispatched and executed
        for i in range(total):
            monitor.update("in_progress")
            time.sleep(0.01)  # Simulate work

            if i < 8:  # 8 successes
                monitor.update("completed", duration_seconds=0.5 + (i * 0.1))
            else:  # 2 failures
                monitor.update("failed", duration_seconds=0.2)

        # Check final state
        assert monitor.is_complete()
        report = monitor.report()
        assert report["completed"] == 8
        assert report["failed"] == 2
        assert report["remaining"] == 0
        assert report["completion_percentage"] == 100.0

    def test_concurrent_execution_simulation(self):
        """Simulate concurrent task execution (max 3 at once)."""
        monitor = ProgressMonitor(total_tasks=10)

        # Start first batch
        for _ in range(3):
            monitor.update("in_progress")

        report = monitor.report()
        assert report["in_progress"] == 3
        assert report["remaining"] == 7

        # Complete one, start another
        monitor.update("completed", duration_seconds=1.0)
        monitor.update("in_progress")

        report = monitor.report()
        assert report["in_progress"] == 3
        assert report["completed"] == 1
        assert report["remaining"] == 6

    def test_error_recovery_scenario(self):
        """Test monitoring through error and recovery scenario."""
        monitor = ProgressMonitor(total_tasks=5)

        # Start and fail a task
        monitor.update("in_progress")
        monitor.update("failed", duration_seconds=0.5)

        # Continue with successful tasks
        monitor.update("in_progress")
        monitor.update("completed", duration_seconds=1.0)

        monitor.update("in_progress")
        monitor.update("completed", duration_seconds=1.0)

        report = monitor.report()
        assert report["failed"] == 1
        assert report["completed"] == 2
        assert not monitor.is_complete()
