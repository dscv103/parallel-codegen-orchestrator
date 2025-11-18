"""Tests for the Codegen Executor module.

Tests cover:
- Task execution with various outcomes
- Timeout handling
- Retry logic for transient failures
- Status polling and tracking
- Error handling
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.agents.codegen_executor import (
    CodegenExecutor,
    TaskResult,
    TaskStatus,
)

# Test constants
DEFAULT_TIMEOUT = 600
DEFAULT_POLL_INTERVAL = 2
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_DELAY = 30
CUSTOM_TIMEOUT = 300
CUSTOM_POLL_INTERVAL = 5
CUSTOM_RETRY_ATTEMPTS = 5
CUSTOM_RETRY_DELAY = 15
SHORT_TIMEOUT = 120
RETRY_DELAY_10 = 10
RETRY_DELAY_20 = 20


class TestCodegenExecutor:
    """Test suite for CodegenExecutor class."""

    def test_init_with_defaults(self):
        """Test executor initialization with default parameters."""
        mock_agent = Mock()
        executor = CodegenExecutor(mock_agent)

        assert executor.agent == mock_agent
        assert executor.timeout_seconds == DEFAULT_TIMEOUT
        assert executor.poll_interval_seconds == DEFAULT_POLL_INTERVAL
        assert executor.retry_attempts == DEFAULT_RETRY_ATTEMPTS
        assert executor.retry_delay_seconds == DEFAULT_RETRY_DELAY

    def test_init_with_custom_params(self):
        """Test executor initialization with custom parameters."""
        mock_agent = Mock()
        executor = CodegenExecutor(
            mock_agent,
            timeout_seconds=CUSTOM_TIMEOUT,
            poll_interval_seconds=CUSTOM_POLL_INTERVAL,
            retry_attempts=CUSTOM_RETRY_ATTEMPTS,
            retry_delay_seconds=CUSTOM_RETRY_DELAY,
        )

        assert executor.timeout_seconds == CUSTOM_TIMEOUT
        assert executor.poll_interval_seconds == CUSTOM_POLL_INTERVAL
        assert executor.retry_attempts == CUSTOM_RETRY_ATTEMPTS
        assert executor.retry_delay_seconds == CUSTOM_RETRY_DELAY

    def test_init_with_invalid_timeout(self):
        """Test that initialization fails with timeout below minimum."""
        mock_agent = Mock()

        with pytest.raises(ValueError, match="timeout_seconds must be at least 60"):
            CodegenExecutor(mock_agent, timeout_seconds=30)

    def test_init_with_invalid_poll_interval(self):
        """Test that initialization fails with poll_interval below minimum."""
        mock_agent = Mock()

        with pytest.raises(
            ValueError,
            match="poll_interval_seconds must be at least 1",
        ):
            CodegenExecutor(mock_agent, poll_interval_seconds=0)

    def test_init_with_invalid_retry_delay(self):
        """Test that initialization fails with retry_delay below minimum."""
        mock_agent = Mock()

        with pytest.raises(ValueError, match="retry_delay_seconds must be at least 5"):
            CodegenExecutor(mock_agent, retry_delay_seconds=2)


class TestTaskExecution:
    """Tests for task execution functionality."""

    @pytest.mark.asyncio
    async def test_execute_task_success(self):
        """Test successful task execution."""
        # Setup mock agent and task
        mock_agent = Mock()
        mock_task = Mock()
        mock_task.status = "completed"
        mock_task.result = "Task completed successfully"
        mock_task.refresh = Mock()
        mock_agent.run = Mock(return_value=mock_task)

        executor = CodegenExecutor(mock_agent, poll_interval_seconds=1)

        task_data = {
            "task_id": "test-task-1",
            "prompt": "Implement feature X",
            "repo_id": "org/repo",
        }

        result = await executor.execute_task(task_data)

        # Assertions
        assert result.task_id == "test-task-1"
        assert result.status == TaskStatus.COMPLETED
        assert result.result is not None
        assert result.error is None
        assert result.duration_seconds >= 0
        mock_agent.run.assert_called_once_with(
            prompt="Implement feature X",
        )

    @pytest.mark.asyncio
    async def test_execute_task_with_polling(self):
        """Test task execution that requires polling."""
        # Setup mock agent and task
        mock_agent = Mock()
        mock_task = Mock()

        # Simulate task that starts as running, then completes
        status_sequence = ["running", "running", "completed"]
        mock_task.status = status_sequence[0]

        call_count = [0]

        def refresh_side_effect():
            call_count[0] += 1
            if call_count[0] < len(status_sequence):
                mock_task.status = status_sequence[call_count[0]]

        mock_task.refresh = Mock(side_effect=refresh_side_effect)
        mock_task.result = "Task completed"
        mock_agent.run = Mock(return_value=mock_task)

        executor = CodegenExecutor(mock_agent, poll_interval_seconds=1)

        task_data = {
            "task_id": "test-task-2",
            "prompt": "Fix bug Y",
        }

        result = await executor.execute_task(task_data)

        # Assertions
        assert result.status == TaskStatus.COMPLETED
        assert mock_task.refresh.call_count >= 1

    @pytest.mark.asyncio
    async def test_execute_task_failure(self):
        """Test task execution that fails."""
        # Setup mock agent and task
        mock_agent = Mock()
        mock_task = Mock()
        mock_task.status = "failed"
        mock_task.error = "Task execution failed"
        mock_task.refresh = Mock()
        mock_agent.run = Mock(return_value=mock_task)

        executor = CodegenExecutor(mock_agent)

        task_data = {
            "task_id": "test-task-3",
            "prompt": "Implement feature Z",
        }

        result = await executor.execute_task(task_data)

        # Assertions
        assert result.task_id == "test-task-3"
        assert result.status == TaskStatus.FAILED
        assert result.error == "Task execution failed"
        assert result.result is None

    @pytest.mark.asyncio
    async def test_execute_task_timeout(self):
        """Test task execution timeout."""
        # Setup mock agent and task that never completes
        mock_agent = Mock()
        mock_task = Mock()
        mock_task.status = "running"  # Always running
        mock_task.refresh = Mock()
        mock_agent.run = Mock(return_value=mock_task)

        # Use very short timeout for testing
        executor = CodegenExecutor(mock_agent, timeout_seconds=60, poll_interval_seconds=1)

        task_data = {
            "task_id": "test-task-4",
            "prompt": "Long running task",
        }

        # Patch asyncio.sleep to speed up the test
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # Make sleep instant to avoid actual waiting
            mock_sleep.return_value = None

            result = await executor.execute_task(task_data)

        # Assertions
        assert result.status == TaskStatus.FAILED
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_task_missing_prompt(self):
        """Test task execution with missing prompt."""
        mock_agent = Mock()
        executor = CodegenExecutor(mock_agent)

        task_data = {
            "task_id": "test-task-5",
            # Missing prompt
        }

        result = await executor.execute_task(task_data)

        # Should fail due to missing prompt
        assert result.status == TaskStatus.FAILED
        assert "prompt" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_task_exception_handling(self):
        """Test task execution handles exceptions gracefully."""
        # Setup mock agent that raises exception
        mock_agent = Mock()
        mock_agent.run = Mock(side_effect=RuntimeError("Agent connection failed"))

        executor = CodegenExecutor(mock_agent)

        task_data = {
            "task_id": "test-task-6",
            "prompt": "Test task",
        }

        result = await executor.execute_task(task_data)

        # Assertions
        assert result.status == TaskStatus.FAILED
        assert "Agent connection failed" in result.error


class TestRetryLogic:
    """Tests for retry logic functionality."""

    @pytest.mark.asyncio
    async def test_retry_on_transient_error(self):
        """Test that transient errors trigger retry."""
        mock_agent = Mock()

        # First call fails with transient error, second succeeds
        call_count = [0]

        def run_side_effect(*_args, **_kwargs):
            call_count[0] += 1
            mock_task = Mock()
            if call_count[0] == 1:
                mock_task.status = "failed"
                mock_task.error = "Network timeout occurred"
            else:
                mock_task.status = "completed"
                mock_task.result = "Success"
            mock_task.refresh = Mock()
            return mock_task

        mock_agent.run = Mock(side_effect=run_side_effect)

        executor = CodegenExecutor(
            mock_agent,
            retry_attempts=3,
            retry_delay_seconds=5,
        )

        task_data = {
            "task_id": "test-task-7",
            "prompt": "Test retry",
        }

        # Patch asyncio.sleep to avoid actual delays
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await executor.execute_task(task_data)

        # Should succeed on second attempt
        expected_call_count = 2
        assert result.status == TaskStatus.COMPLETED
        assert mock_agent.run.call_count == expected_call_count

    @pytest.mark.asyncio
    async def test_no_retry_on_permanent_error(self):
        """Test that permanent errors do not trigger retry."""
        mock_agent = Mock()
        mock_task = Mock()
        mock_task.status = "failed"
        mock_task.error = "Invalid input: missing required field"
        mock_task.refresh = Mock()
        mock_agent.run = Mock(return_value=mock_task)

        executor = CodegenExecutor(mock_agent, retry_attempts=3)

        task_data = {
            "task_id": "test-task-8",
            "prompt": "Test no retry",
        }

        result = await executor.execute_task(task_data)

        # Should not retry on permanent error
        assert result.status == TaskStatus.FAILED
        assert mock_agent.run.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_exhaustion(self):
        """Test behavior when all retry attempts are exhausted."""
        mock_agent = Mock()

        # Always fail with transient error
        mock_task = Mock()
        mock_task.status = "failed"
        mock_task.error = "Service temporarily unavailable"
        mock_task.refresh = Mock()
        mock_agent.run = Mock(return_value=mock_task)

        executor = CodegenExecutor(
            mock_agent,
            retry_attempts=3,
            retry_delay_seconds=5,
        )

        task_data = {
            "task_id": "test-task-9",
            "prompt": "Test retry exhaustion",
        }

        # Patch asyncio.sleep to avoid actual delays
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await executor.execute_task(task_data)

        # Should fail after all retries
        expected_retry_count = 3
        assert result.status == TaskStatus.FAILED
        assert "retry attempts exhausted" in result.error.lower()
        assert mock_agent.run.call_count == expected_retry_count
        assert result.retry_count == expected_retry_count

    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """Test that retry delays use exponential backoff."""
        mock_agent = Mock()

        # Always fail with transient error
        mock_task = Mock()
        mock_task.status = "failed"
        mock_task.error = "Connection timeout"
        mock_task.refresh = Mock()
        mock_agent.run = Mock(return_value=mock_task)

        executor = CodegenExecutor(
            mock_agent,
            retry_attempts=3,
            retry_delay_seconds=10,
        )

        task_data = {
            "task_id": "test-task-10",
            "prompt": "Test exponential backoff",
        }

        sleep_calls = []

        async def mock_sleep(duration):
            sleep_calls.append(duration)

        # Patch asyncio.sleep to capture delay durations
        with patch("asyncio.sleep", new_callable=AsyncMock, side_effect=mock_sleep):
            await executor.execute_task(task_data)

        # Verify exponential backoff: 10, 20 (10 * 2^1)
        expected_sleep_count = 2
        assert len(sleep_calls) == expected_sleep_count  # Two delays (between 3 attempts)
        assert sleep_calls[0] == RETRY_DELAY_10  # First retry delay
        assert sleep_calls[1] == RETRY_DELAY_20  # Second retry delay (exponential)


class TestTransientErrorDetection:
    """Tests for transient error detection."""

    def test_is_transient_error_timeout(self):
        """Test detection of timeout errors as transient."""
        mock_agent = Mock()
        executor = CodegenExecutor(mock_agent)

        assert executor._is_transient_error("Request timeout")  # noqa: SLF001
        assert executor._is_transient_error("Connection timeout occurred")  # noqa: SLF001

    def test_is_transient_error_network(self):
        """Test detection of network errors as transient."""
        mock_agent = Mock()
        executor = CodegenExecutor(mock_agent)

        assert executor._is_transient_error("Network connection failed")  # noqa: SLF001
        assert executor._is_transient_error("Connection refused")  # noqa: SLF001

    def test_is_transient_error_rate_limit(self):
        """Test detection of rate limit errors as transient."""
        mock_agent = Mock()
        executor = CodegenExecutor(mock_agent)

        assert executor._is_transient_error("Rate limit exceeded")  # noqa: SLF001

    def test_is_transient_error_http_codes(self):
        """Test detection of transient HTTP error codes."""
        mock_agent = Mock()
        executor = CodegenExecutor(mock_agent)

        assert executor._is_transient_error("503 Service Unavailable")  # noqa: SLF001
        assert executor._is_transient_error("502 Bad Gateway")  # noqa: SLF001
        assert executor._is_transient_error("504 Gateway Timeout")  # noqa: SLF001

    def test_is_not_transient_error(self):
        """Test that permanent errors are not detected as transient."""
        mock_agent = Mock()
        executor = CodegenExecutor(mock_agent)

        assert not executor._is_transient_error("Invalid input")  # noqa: SLF001
        assert not executor._is_transient_error("Authentication failed")  # noqa: SLF001
        assert not executor._is_transient_error("Resource not found")  # noqa: SLF001
        assert not executor._is_transient_error(None)  # noqa: SLF001


class TestTaskResult:
    """Tests for TaskResult dataclass."""

    def test_task_result_success(self):
        """Test TaskResult for successful execution."""
        start = datetime.now(UTC)
        end = datetime.now(UTC)

        result = TaskResult(
            task_id="task-1",
            status=TaskStatus.COMPLETED,
            start_time=start,
            end_time=end,
            duration_seconds=10.5,
            result={"data": "result"},
        )

        assert result.task_id == "task-1"
        assert result.status == TaskStatus.COMPLETED
        assert result.result == {"data": "result"}
        assert result.error is None
        assert result.retry_count == 0

    def test_task_result_failure(self):
        """Test TaskResult for failed execution."""
        start = datetime.now(UTC)
        end = datetime.now(UTC)

        result = TaskResult(
            task_id="task-2",
            status=TaskStatus.FAILED,
            start_time=start,
            end_time=end,
            duration_seconds=5.0,
            error="Task failed",
            retry_count=2,
        )

        assert result.task_id == "task-2"
        assert result.status == TaskStatus.FAILED
        assert result.error == "Task failed"
        assert result.result is None
        expected_retry_count_2 = 2
        assert result.retry_count == expected_retry_count_2
