"""Unit tests for ResultManager and TaskResult."""

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.orchestrator.result_manager import ResultManager, TaskResult


@pytest.fixture
def result_manager():
    """Create a fresh ResultManager instance for each test."""
    return ResultManager()


@pytest.fixture
def sample_task_result():
    """Create a sample successful task result."""
    start = datetime.now()
    end = start + timedelta(seconds=10)
    return TaskResult(
        task_id="task-1",
        status="completed",
        start_time=start,
        end_time=end,
        duration_seconds=10.0,
        agent_id=1,
        result={"output": "success"},
        error=None,
    )


@pytest.fixture
def sample_failed_result():
    """Create a sample failed task result."""
    start = datetime.now()
    end = start + timedelta(seconds=5)
    return TaskResult(
        task_id="task-2",
        status="failed",
        start_time=start,
        end_time=end,
        duration_seconds=5.0,
        agent_id=2,
        result=None,
        error="Task execution failed",
    )


class TestTaskResult:
    """Tests for TaskResult dataclass."""

    def test_task_result_creation(self):
        """Test creating a TaskResult instance."""
        start = datetime.now()
        end = start + timedelta(seconds=15)

        result = TaskResult(
            task_id="test-1",
            status="completed",
            start_time=start,
            end_time=end,
            duration_seconds=15.0,
            agent_id=3,
            result={"data": "test"},
            error=None,
        )

        assert result.task_id == "test-1"
        assert result.status == "completed"
        assert result.duration_seconds == 15.0
        assert result.agent_id == 3
        assert result.result == {"data": "test"}
        assert result.error is None

    def test_task_result_with_error(self):
        """Test creating a TaskResult with error."""
        start = datetime.now()
        end = start + timedelta(seconds=2)

        result = TaskResult(
            task_id="test-2",
            status="failed",
            start_time=start,
            end_time=end,
            duration_seconds=2.0,
            agent_id=1,
            result=None,
            error="Connection timeout",
        )

        assert result.status == "failed"
        assert result.error == "Connection timeout"
        assert result.result is None


class TestResultManager:
    """Tests for ResultManager class."""

    def test_initialization(self, result_manager):
        """Test ResultManager initialization."""
        assert len(result_manager.results) == 0
        assert result_manager.success_count == 0
        assert result_manager.failure_count == 0

    def test_add_successful_result(self, result_manager, sample_task_result):
        """Test adding a successful task result."""
        result_manager.add_result(sample_task_result)

        assert len(result_manager.results) == 1
        assert result_manager.success_count == 1
        assert result_manager.failure_count == 0
        assert "task-1" in result_manager.results

    def test_add_failed_result(self, result_manager, sample_failed_result):
        """Test adding a failed task result."""
        result_manager.add_result(sample_failed_result)

        assert len(result_manager.results) == 1
        assert result_manager.success_count == 0
        assert result_manager.failure_count == 1
        assert "task-2" in result_manager.results

    def test_add_multiple_results(self, result_manager, sample_task_result, sample_failed_result):
        """Test adding multiple results."""
        result_manager.add_result(sample_task_result)
        result_manager.add_result(sample_failed_result)

        assert len(result_manager.results) == 2
        assert result_manager.success_count == 1
        assert result_manager.failure_count == 1

    def test_get_result(self, result_manager, sample_task_result):
        """Test retrieving a specific result by task_id."""
        result_manager.add_result(sample_task_result)

        retrieved = result_manager.get_result("task-1")
        assert retrieved is not None
        assert retrieved.task_id == "task-1"
        assert retrieved.status == "completed"

    def test_get_nonexistent_result(self, result_manager):
        """Test retrieving a result that doesn't exist."""
        result = result_manager.get_result("nonexistent")
        assert result is None

    def test_get_all_results(self, result_manager, sample_task_result, sample_failed_result):
        """Test retrieving all results."""
        result_manager.add_result(sample_task_result)
        result_manager.add_result(sample_failed_result)

        all_results = result_manager.get_all_results()
        assert len(all_results) == 2
        assert sample_task_result in all_results
        assert sample_failed_result in all_results

    def test_get_results_by_status(self, result_manager, sample_task_result, sample_failed_result):
        """Test filtering results by status."""
        result_manager.add_result(sample_task_result)
        result_manager.add_result(sample_failed_result)

        completed = result_manager.get_results_by_status("completed")
        assert len(completed) == 1
        assert completed[0].task_id == "task-1"

        failed = result_manager.get_results_by_status("failed")
        assert len(failed) == 1
        assert failed[0].task_id == "task-2"

    def test_get_failed_tasks(self, result_manager, sample_task_result, sample_failed_result):
        """Test retrieving only failed tasks."""
        result_manager.add_result(sample_task_result)
        result_manager.add_result(sample_failed_result)

        failed = result_manager.get_failed_tasks()
        assert len(failed) == 1
        assert failed[0].status == "failed"
        assert failed[0].error == "Task execution failed"

    def test_get_successful_tasks(self, result_manager, sample_task_result, sample_failed_result):
        """Test retrieving only successful tasks."""
        result_manager.add_result(sample_task_result)
        result_manager.add_result(sample_failed_result)

        successful = result_manager.get_successful_tasks()
        assert len(successful) == 1
        assert successful[0].status == "completed"
        assert successful[0].result == {"output": "success"}

    def test_get_summary_empty(self, result_manager):
        """Test summary generation with no results."""
        summary = result_manager.get_summary()

        assert summary["total_tasks"] == 0
        assert summary["successful"] == 0
        assert summary["failed"] == 0
        assert summary["total_duration_seconds"] == 0.0
        assert summary["average_duration_seconds"] == 0.0

    def test_get_summary_with_results(
        self, result_manager, sample_task_result, sample_failed_result
    ):
        """Test summary generation with results."""
        result_manager.add_result(sample_task_result)
        result_manager.add_result(sample_failed_result)

        summary = result_manager.get_summary()

        assert summary["total_tasks"] == 2
        assert summary["successful"] == 1
        assert summary["failed"] == 1
        assert summary["total_duration_seconds"] == 15.0
        assert summary["average_duration_seconds"] == 7.5

    def test_export_json(self, result_manager, sample_task_result):
        """Test JSON export functionality."""
        result_manager.add_result(sample_task_result)

        with TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "results" / "output.json"
            result_manager.export_json(filepath)

            assert filepath.exists()

            with filepath.open() as f:
                data = json.load(f)

            assert "summary" in data
            assert "results" in data
            assert data["summary"]["total_tasks"] == 1
            assert len(data["results"]) == 1

    def test_export_json_creates_directory(self, result_manager, sample_task_result):
        """Test that export_json creates parent directories."""
        result_manager.add_result(sample_task_result)

        with TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "nested" / "deep" / "output.json"
            result_manager.export_json(filepath)

            assert filepath.exists()
            assert filepath.parent.exists()

    def test_export_csv(self, result_manager, sample_task_result, sample_failed_result):
        """Test CSV export functionality."""
        result_manager.add_result(sample_task_result)
        result_manager.add_result(sample_failed_result)

        with TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "results.csv"
            result_manager.export_csv(filepath)

            assert filepath.exists()

            with filepath.open(newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert len(rows) == 2
            assert rows[0]["task_id"] == "task-1"
            assert rows[0]["status"] == "completed"
            assert rows[1]["task_id"] == "task-2"
            assert rows[1]["status"] == "failed"

    def test_export_csv_empty(self, result_manager):
        """Test CSV export with no results."""
        with TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "empty.csv"
            result_manager.export_csv(filepath)

            # Should not create file when no results
            assert not filepath.exists()

    def test_clear(self, result_manager, sample_task_result, sample_failed_result):
        """Test clearing all results and statistics."""
        result_manager.add_result(sample_task_result)
        result_manager.add_result(sample_failed_result)

        assert len(result_manager.results) == 2
        assert result_manager.success_count == 1
        assert result_manager.failure_count == 1

        result_manager.clear()

        assert len(result_manager.results) == 0
        assert result_manager.success_count == 0
        assert result_manager.failure_count == 0

    def test_get_statistics_empty(self, result_manager):
        """Test statistics with no results."""
        stats = result_manager.get_statistics()

        assert stats["total_tasks"] == 0
        assert stats["successful"] == 0
        assert stats["failed"] == 0
        assert stats["agent_utilization"] == {}
        assert stats["status_breakdown"] == {}

    def test_get_statistics_with_results(
        self,
        result_manager,
        sample_task_result,
        sample_failed_result,
    ):
        """Test comprehensive statistics with multiple results."""
        # Add multiple results with different durations and agents
        start = datetime.now()

        results = [
            TaskResult("task-1", "completed", start, start + timedelta(seconds=10), 10.0, 1),
            TaskResult("task-2", "failed", start, start + timedelta(seconds=5), 5.0, 2),
            TaskResult("task-3", "completed", start, start + timedelta(seconds=20), 20.0, 1),
        ]

        for result in results:
            result_manager.add_result(result)

        stats = result_manager.get_statistics()

        assert stats["total_tasks"] == 3
        assert stats["successful"] == 2
        assert stats["failed"] == 1
        assert stats["total_duration_seconds"] == 35.0
        assert stats["average_duration_seconds"] == pytest.approx(11.67, rel=0.01)
        assert stats["min_duration_seconds"] == 5.0
        assert stats["max_duration_seconds"] == 20.0
        assert stats["agent_utilization"] == {1: 2, 2: 1}
        assert stats["status_breakdown"] == {"completed": 2, "failed": 1}

    def test_concurrent_updates(self, result_manager):
        """Test handling multiple status updates in sequence."""
        start = datetime.now()

        # Add 5 completed and 3 failed tasks
        for i in range(5):
            result = TaskResult(
                task_id=f"completed-{i}",
                status="completed",
                start_time=start,
                end_time=start + timedelta(seconds=10),
                duration_seconds=10.0,
                agent_id=1,
            )
            result_manager.add_result(result)

        for i in range(3):
            result = TaskResult(
                task_id=f"failed-{i}",
                status="failed",
                start_time=start,
                end_time=start + timedelta(seconds=5),
                duration_seconds=5.0,
                agent_id=2,
                error=f"Error {i}",
            )
            result_manager.add_result(result)

        assert len(result_manager.results) == 8
        assert result_manager.success_count == 5
        assert result_manager.failure_count == 3

        summary = result_manager.get_summary()
        assert summary["total_tasks"] == 8
        assert summary["successful"] == 5
        assert summary["failed"] == 3
