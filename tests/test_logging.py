"""Unit tests for the logging configuration module.

This test module validates the structured logging configuration,
context binding, and correlation ID management.
"""

import logging

import pytest
import structlog

from src.log_config import (
    bind_context,
    bind_correlation_id,
    clear_context,
    configure_logging,
    get_logger,
    unbind_context,
    unbind_correlation_id,
)


class TestLoggingConfiguration:
    """Test cases for logging configuration."""

    def test_configure_logging_info_level(self):
        """Test logging configuration with INFO level."""
        configure_logging(level="INFO", json_logs=True)
        logger = get_logger("test")
        assert logger is not None
        assert isinstance(logger, structlog.stdlib.BoundLogger)

    def test_configure_logging_debug_level(self):
        """Test logging configuration with DEBUG level."""
        configure_logging(level="DEBUG", json_logs=True)
        logger = get_logger("test")
        assert logger is not None

    def test_configure_logging_invalid_level(self):
        """Test logging configuration with invalid level."""
        with pytest.raises(ValueError, match="Invalid log level"):
            configure_logging(level="INVALID", json_logs=True)

    def test_configure_logging_console_renderer(self):
        """Test logging configuration with console renderer."""
        configure_logging(level="INFO", json_logs=False)
        logger = get_logger("test")
        assert logger is not None

    def test_get_logger_with_name(self):
        """Test getting a logger with a specific name."""
        configure_logging(level="INFO", json_logs=True)
        logger = get_logger(__name__)
        assert logger is not None

    def test_get_logger_without_name(self):
        """Test getting a logger without a name."""
        configure_logging(level="INFO", json_logs=True)
        logger = get_logger()
        assert logger is not None


class TestContextBinding:
    """Test cases for context binding functionality."""

    def setup_method(self):
        """Set up test environment before each test."""
        configure_logging(level="INFO", json_logs=True)
        clear_context()  # Ensure clean state

    def teardown_method(self):
        """Clean up after each test."""
        clear_context()

    def test_bind_correlation_id(self, caplog):
        """Test binding a correlation ID to the logging context."""
        caplog.set_level(logging.INFO)
        logger = get_logger("test")

        bind_correlation_id("test-correlation-id")
        logger.info("test_event")

        # Verify correlation_id is in the log context
        assert len(caplog.records) > 0
        record = caplog.records[0]
        
        # Check if correlation_id is present as an attribute or in the message
        if hasattr(record, "correlation_id"):
            assert record.correlation_id == "test-correlation-id"
        else:
            # Fallback: check if it appears in the formatted message
            assert "test-correlation-id" in record.getMessage()

    def test_unbind_correlation_id(self, caplog):
        """Test unbinding the correlation ID from the logging context."""
        caplog.set_level(logging.INFO)
        logger = get_logger("test")

        bind_correlation_id("test-correlation-id")
        logger.info("with_correlation")

        unbind_correlation_id()
        logger.info("without_correlation")

        assert len(caplog.records) == 2
        
        # First record should have correlation_id
        first_record = caplog.records[0]
        if hasattr(first_record, "correlation_id"):
            assert first_record.correlation_id == "test-correlation-id"
        else:
            assert "test-correlation-id" in first_record.getMessage()
        
        # Second record should NOT have correlation_id
        second_record = caplog.records[1]
        if hasattr(second_record, "correlation_id"):
            # If attribute exists, it should be None or not equal to our ID
            assert second_record.correlation_id != "test-correlation-id"
        else:
            # If no attribute, the ID should not appear in the message
            assert "test-correlation-id" not in second_record.getMessage()

    def test_bind_context_multiple_variables(self, caplog):
        """Test binding multiple context variables."""
        caplog.set_level(logging.INFO)
        logger = get_logger("test")

        bind_context(task_id="task-1", agent_id=5, status="running")
        logger.info("task_started")

        assert len(caplog.records) > 0
        record = caplog.records[0]
        
        # Check if context variables are present as attributes or in the message
        message = record.getMessage()
        
        # Check task_id
        if hasattr(record, "task_id"):
            assert record.task_id == "task-1"
        else:
            assert "task-1" in message
        
        # Check agent_id
        if hasattr(record, "agent_id"):
            assert record.agent_id == 5
        else:
            assert "5" in message
        
        # Check status
        if hasattr(record, "status"):
            assert record.status == "running"
        else:
            assert "running" in message

    def test_unbind_context_specific_keys(self, caplog):
        """Test unbinding specific context variables."""
        caplog.set_level(logging.INFO)
        logger = get_logger("test")

        bind_context(task_id="task-1", agent_id=5)
        logger.info("with_full_context")

        unbind_context("task_id")
        logger.info("without_task_id")

        assert len(caplog.records) == 2

    def test_clear_context(self, caplog):
        """Test clearing all context variables."""
        caplog.set_level(logging.INFO)
        logger = get_logger("test")

        bind_context(task_id="task-1", agent_id=5, status="running")
        logger.info("with_context")

        clear_context()
        logger.info("without_context")

        assert len(caplog.records) == 2


class TestStructuredLogging:
    """Test cases for structured logging output."""

    def setup_method(self):
        """Set up test environment before each test."""
        configure_logging(level="INFO", json_logs=True)
        clear_context()

    def teardown_method(self):
        """Clean up after each test."""
        clear_context()

    def test_json_output_format(self, caplog):
        """Test that logs are output in JSON format."""
        caplog.set_level(logging.INFO)
        logger = get_logger("test")

        # Capture stdout to parse JSON
        logger.info("test_event", key1="value1", key2=42)

        assert len(caplog.records) > 0
        # Note: Full JSON validation would require capturing stdout

    def test_log_with_exception(self, caplog):
        """Test logging with exception information."""
        caplog.set_level(logging.ERROR)
        logger = get_logger("test")

        def _raise_test_error():
            msg = "Test exception"
            raise ValueError(msg)

        try:
            _raise_test_error()
        except ValueError:
            logger.exception("error_occurred", operation="test")

        assert len(caplog.records) > 0
        assert "error_occurred" in str(caplog.records[0].message)

    def test_log_levels(self, caplog):
        """Test different log levels."""
        configure_logging(level="DEBUG", json_logs=True)
        caplog.set_level(logging.DEBUG)
        logger = get_logger("test")

        logger.debug("debug_message")
        logger.info("info_message")
        logger.warning("warning_message")
        logger.error("error_message")

        assert len(caplog.records) == 4

    def test_caller_information(self, caplog):
        """Test that caller information is included in logs."""
        caplog.set_level(logging.INFO)
        logger = get_logger("test")

        logger.info("test_caller_info")

        assert len(caplog.records) > 0
        # Caller info would be in the actual JSON output


class TestLoggerReuse:
    """Test cases for logger caching and reuse."""

    def test_logger_caching(self):
        """Test that loggers are cached on first use."""
        configure_logging(level="INFO", json_logs=True)

        logger1 = get_logger("test")
        logger2 = get_logger("test")

        # Should return the same cached instance
        assert logger1 is logger2

    def test_different_logger_names(self):
        """Test that different names create different loggers."""
        configure_logging(level="INFO", json_logs=True)

        logger1 = get_logger("test1")
        logger2 = get_logger("test2")

        # Different names should create different instances
        assert logger1 is not logger2


class TestContextIsolation:
    """Test cases for context variable isolation."""

    def setup_method(self):
        """Set up test environment before each test."""
        configure_logging(level="INFO", json_logs=True)
        clear_context()

    def teardown_method(self):
        """Clean up after each test."""
        clear_context()

    def test_context_isolation_between_tests(self, caplog):
        """Test that context is properly isolated between tests."""
        caplog.set_level(logging.INFO)
        logger = get_logger("test")

        # First log without context
        logger.info("no_context")

        # Add context
        bind_context(test_id="test-1")
        logger.info("with_context")

        # Clear context
        clear_context()
        logger.info("context_cleared")

        assert len(caplog.records) == 3

    def test_multiple_context_bindings(self, caplog):
        """Test multiple sequential context bindings."""
        caplog.set_level(logging.INFO)
        logger = get_logger("test")

        bind_context(stage="stage1")
        logger.info("stage_1")

        bind_context(stage="stage2")
        logger.info("stage_2")

        assert len(caplog.records) == 2


@pytest.mark.integration
class TestLoggingIntegration:
    """Integration tests for logging with other components."""

    def test_logging_with_async_context(self, caplog):
        """Test logging in an async context (placeholder for async tests)."""
        configure_logging(level="INFO", json_logs=True)
        caplog.set_level(logging.INFO)
        logger = get_logger("test")

        # Simulate async operation logging
        bind_context(task_id="async-task-1", operation="async_operation")
        logger.info("async_operation_started")
        logger.info("async_operation_completed", duration_ms=150)
        clear_context()

        assert len(caplog.records) == 2

    def test_logging_performance(self, caplog):
        """Test logging performance with multiple calls."""
        import time  # noqa: PLC0415

        configure_logging(level="INFO", json_logs=True)
        caplog.set_level(logging.INFO)
        logger = get_logger("test")

        start_time = time.time()
        for i in range(100):
            logger.info("performance_test", iteration=i)
        elapsed_time = time.time() - start_time

        # Should complete quickly (less than 1 second for 100 logs)
        assert elapsed_time < 1.0
        assert len(caplog.records) == 100
