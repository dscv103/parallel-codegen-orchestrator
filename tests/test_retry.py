"""Tests for Retry Logic with Exponential Backoff.

This module tests the retry logic implementation including:
- Retry attempts with exponential backoff
- Error classification (transient vs permanent)
- Retry configuration management
- Integration with task executor
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.config import AgentConfig
from src.orchestrator.retry import (
    FailureType,
    RetryableError,
    RetryConfig,
    classify_error,
    execute_with_retry,
)


class TestErrorClassification:
    """Test cases for error classification logic."""

    def test_classify_timeout_error(self):
        """Test that TimeoutError is classified as transient."""
        error = TimeoutError("Request timed out")
        assert classify_error(error) == FailureType.TRANSIENT

    def test_classify_connection_error(self):
        """Test that connection errors are classified as transient."""
        errors = [
            ConnectionError("Connection failed"),
            ConnectionResetError("Connection reset"),
            ConnectionRefusedError("Connection refused"),
            ConnectionAbortedError("Connection aborted"),
        ]
        for error in errors:
            assert classify_error(error) == FailureType.TRANSIENT

    def test_classify_retryable_error_explicit(self):
        """Test that RetryableError respects explicit classification."""
        error = RetryableError("Temporary failure", FailureType.TRANSIENT)
        assert classify_error(error) == FailureType.TRANSIENT

        error = RetryableError("Permanent failure", FailureType.PERMANENT)
        assert classify_error(error) == FailureType.PERMANENT

    def test_classify_error_by_message_transient(self):
        """Test transient error detection by message patterns."""
        transient_messages = [
            "Network timeout occurred",
            "Connection temporarily unavailable",
            "Service unavailable, please try again",
            "Rate limit exceeded",
            "HTTP 502 Bad Gateway",
            "HTTP 503 Service Unavailable",
            "HTTP 504 Gateway Timeout",
        ]
        for msg in transient_messages:
            error = Exception(msg)
            assert classify_error(error) == FailureType.TRANSIENT

    def test_classify_error_by_message_permanent(self):
        """Test permanent error detection by message patterns."""
        permanent_messages = [
            "Invalid input provided",
            "Unauthorized access",
            "Forbidden resource",
            "Not found",
            "Bad request format",
            "HTTP 400 Bad Request",
            "HTTP 401 Unauthorized",
            "HTTP 403 Forbidden",
            "HTTP 404 Not Found",
        ]
        for msg in permanent_messages:
            error = Exception(msg)
            assert classify_error(error) == FailureType.PERMANENT

    def test_classify_unknown_error(self):
        """Test that unknown errors are classified as unknown (treated as transient)."""
        error = ValueError("Some unexpected error")
        assert classify_error(error) == FailureType.UNKNOWN


class TestExecuteWithRetry:
    """Test cases for execute_with_retry function."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        """Test that successful execution on first attempt requires no retries."""
        mock_func = AsyncMock(return_value={"status": "success"})

        result = await execute_with_retry(
            task_id="test-task",
            func=mock_func,
            max_attempts=3,
            base_delay_seconds=1,
        )

        assert result == {"status": "success"}
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_success_after_retry(self):
        """Test that function succeeds after transient failures."""
        # Fail twice, then succeed
        mock_func = AsyncMock(
            side_effect=[
                TimeoutError("Timeout 1"),
                TimeoutError("Timeout 2"),
                {"status": "success"},
            ],
        )

        result = await execute_with_retry(
            task_id="test-task",
            func=mock_func,
            max_attempts=3,
            base_delay_seconds=0.1,  # Short delay for tests
        )

        assert result == {"status": "success"}
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_permanent_failure_no_retry(self):
        """Test that permanent failures are not retried."""
        permanent_error = ValueError("Invalid input provided")
        mock_func = AsyncMock(side_effect=permanent_error)

        with pytest.raises(ValueError, match="Invalid input"):
            await execute_with_retry(
                task_id="test-task",
                func=mock_func,
                max_attempts=3,
                base_delay_seconds=0.1,
            )

        # Should only be called once (no retries for permanent failure)
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_exhaustion(self):
        """Test that retries are exhausted after max_attempts."""
        transient_error = TimeoutError("Persistent timeout")
        mock_func = AsyncMock(side_effect=transient_error)

        with pytest.raises(TimeoutError, match="Persistent timeout"):
            await execute_with_retry(
                task_id="test-task",
                func=mock_func,
                max_attempts=3,
                base_delay_seconds=0.1,
            )

        # Should be called max_attempts times
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self):
        """Test that exponential backoff delays are calculated correctly."""
        mock_func = AsyncMock(side_effect=TimeoutError("Timeout"))
        base_delay = 0.1

        start_time = asyncio.get_event_loop().time()

        with pytest.raises(TimeoutError):
            await execute_with_retry(
                task_id="test-task",
                func=mock_func,
                max_attempts=3,
                base_delay_seconds=base_delay,
            )

        elapsed = asyncio.get_event_loop().time() - start_time

        # Expected delays: base_delay * 1 + base_delay * 2 = 0.3s
        # Allow some tolerance for execution overhead
        expected_min_delay = base_delay * (1 + 2)  # 0.3s
        assert elapsed >= expected_min_delay

    @pytest.mark.asyncio
    async def test_retry_with_function_arguments(self):
        """Test that function arguments are passed correctly through retries."""
        mock_func = AsyncMock(return_value="result")

        await execute_with_retry(
            task_id="test-task",
            func=mock_func,
            max_attempts=3,
            base_delay_seconds=0.1,
            arg1="value1",
            arg2="value2",
        )

        # Verify arguments were passed
        mock_func.assert_called_once_with(arg1="value1", arg2="value2")

    @pytest.mark.asyncio
    async def test_retry_with_retryable_error(self):
        """Test explicit RetryableError handling."""
        # Create explicit retryable error
        transient_error = RetryableError(
            "Temporary API failure",
            failure_type=FailureType.TRANSIENT,
        )

        mock_func = AsyncMock(side_effect=[transient_error, {"status": "success"}])

        result = await execute_with_retry(
            task_id="test-task",
            func=mock_func,
            max_attempts=3,
            base_delay_seconds=0.1,
        )

        assert result == {"status": "success"}
        assert mock_func.call_count == 2


class TestRetryConfig:
    """Test cases for RetryConfig class."""

    def test_default_configuration(self):
        """Test default retry configuration."""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.base_delay_seconds == 30
        assert config.enabled is True

    def test_custom_configuration(self):
        """Test custom retry configuration."""
        config = RetryConfig(max_attempts=5, base_delay_seconds=60, enabled=True)
        assert config.max_attempts == 5
        assert config.base_delay_seconds == 60
        assert config.enabled is True

    def test_disabled_configuration(self):
        """Test disabled retry configuration."""
        config = RetryConfig(max_attempts=0, enabled=False)
        assert config.max_attempts == 0
        assert config.enabled is False

    def test_invalid_max_attempts(self):
        """Test that negative max_attempts raises ValueError."""
        with pytest.raises(ValueError, match="max_attempts must be non-negative"):
            RetryConfig(max_attempts=-1)

    def test_invalid_base_delay(self):
        """Test that negative base_delay_seconds raises ValueError."""
        with pytest.raises(ValueError, match="base_delay_seconds must be non-negative"):
            RetryConfig(base_delay_seconds=-1)

    def test_invalid_enabled_with_zero_attempts(self):
        """Test that enabled=True with max_attempts=0 raises ValueError."""
        with pytest.raises(ValueError, match="enabled cannot be True when max_attempts is 0"):
            RetryConfig(max_attempts=0, enabled=True)

    def test_from_agent_config(self):
        """Test creating RetryConfig from AgentConfig."""
        agent_config = AgentConfig(
            max_concurrent_agents=5,
            task_timeout_seconds=300,
            retry_attempts=5,
            retry_delay_seconds=45,
        )

        retry_config = RetryConfig.from_agent_config(agent_config)

        assert retry_config.max_attempts == 5
        assert retry_config.base_delay_seconds == 45
        assert retry_config.enabled is True

    def test_from_agent_config_disabled(self):
        """Test creating disabled RetryConfig from AgentConfig."""
        agent_config = AgentConfig(
            max_concurrent_agents=5,
            task_timeout_seconds=300,
            retry_attempts=0,
            retry_delay_seconds=30,
        )

        retry_config = RetryConfig.from_agent_config(agent_config)

        assert retry_config.max_attempts == 0
        assert retry_config.enabled is False


class TestRetryableError:
    """Test cases for RetryableError exception class."""

    def test_retryable_error_creation(self):
        """Test creating RetryableError with default values."""
        error = RetryableError("Test error")
        assert str(error) == "Test error"
        assert error.failure_type == FailureType.UNKNOWN
        assert error.original_error is None

    def test_retryable_error_with_failure_type(self):
        """Test creating RetryableError with explicit failure type."""
        error = RetryableError("Test error", FailureType.TRANSIENT)
        assert error.failure_type == FailureType.TRANSIENT

    def test_retryable_error_with_original_error(self):
        """Test creating RetryableError wrapping another exception."""
        original = ValueError("Original error")
        error = RetryableError("Wrapped error", original_error=original)
        assert error.original_error is original


class TestRetryIntegration:
    """Integration tests for retry logic with realistic scenarios."""

    @pytest.mark.asyncio
    async def test_api_call_simulation_with_retry(self):
        """Simulate API call with network issues requiring retry."""

        async def simulate_api_call():
            """Simulate API call that may fail transiently."""
            # This would be a real API call in production
            await asyncio.sleep(0.01)
            return {"data": "success"}

        # Create a mock that fails twice then succeeds
        call_count = 0

        async def flaky_api_call():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                msg = "Network timeout"
                raise TimeoutError(msg)
            return await simulate_api_call()

        result = await execute_with_retry(
            task_id="api-call-task",
            func=flaky_api_call,
            max_attempts=5,
            base_delay_seconds=0.1,
        )

        assert result == {"data": "success"}
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_mixed_error_types(self):
        """Test handling of mixed transient and permanent errors."""
        errors = [
            TimeoutError("Transient 1"),
            ConnectionError("Transient 2"),
            ValueError("Invalid input - permanent"),
        ]

        call_count = 0

        async def failing_func():
            nonlocal call_count
            error = errors[call_count]
            call_count += 1
            raise error

        # Should fail after encountering permanent error
        with pytest.raises(ValueError, match="Invalid input"):
            await execute_with_retry(
                task_id="mixed-errors-task",
                func=failing_func,
                max_attempts=5,
                base_delay_seconds=0.1,
            )

        # Should have tried twice (transient) then hit permanent error
        assert call_count == 3
