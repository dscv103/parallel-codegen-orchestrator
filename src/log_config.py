"""Centralized structured logging configuration using structlog.

This module provides a centralized logging configuration for the entire
orchestrator system. It configures structlog with JSON output, timestamps,
correlation IDs, and contextual logging support.

Example:
    >>> from src.log_config import configure_logging, get_logger
    >>> configure_logging(level="INFO")
    >>> logger = get_logger(__name__)
    >>> logger.info("task_dispatched", task_id="task-1", agent_id=5)
"""

import logging
import sys
from typing import Any

import structlog


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    """Configure structlog for the orchestrator system.

    Sets up structlog with processors for timestamps, log levels, stack info,
    and JSON rendering. Also configures the standard library logging to work
    with structlog.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_logs: If True, use JSONRenderer; if False, use ConsoleRenderer for development

    Raises:
        ValueError: If an invalid log level is provided
    """
    # Validate log level
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        msg = f"Invalid log level: {level}"
        raise TypeError(msg)

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
    )

    # Define structlog processors
    processors: list[Any] = [
        # Add the log level to the event dict
        structlog.stdlib.add_log_level,
        # Add a timestamp in ISO 8601 format
        structlog.processors.TimeStamper(fmt="iso"),
        # Add caller information (module, function, line number)
        structlog.processors.CallsiteParameterAdder(
            parameters=[
                structlog.processors.CallsiteParameter.MODULE,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ],
        ),
        # Add exception info if present
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        # Add any context variables
        structlog.contextvars.merge_contextvars,
    ]

    # Add the appropriate renderer based on configuration
    if json_logs:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            ),
        )

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a configured structlog logger.

    Args:
        name: Logger name (typically __name__ of the calling module)

    Returns:
        A configured structlog BoundLogger instance

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("operation_started", operation="data_fetch")
    """
    return structlog.get_logger(name)


def bind_correlation_id(correlation_id: str) -> None:
    """Bind a correlation ID to the logging context.

    This adds a correlation_id to all subsequent log messages in the current
    context, making it easier to trace related operations.

    Args:
        correlation_id: Unique identifier for correlating related log entries

    Example:
        >>> bind_correlation_id("req-12345")
        >>> logger.info("request_received")  # Will include correlation_id
    """
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)


def unbind_correlation_id() -> None:
    """Remove the correlation ID from the logging context.

    Example:
        >>> unbind_correlation_id()
    """
    structlog.contextvars.unbind_contextvars("correlation_id")


def bind_context(**kwargs: Any) -> None:
    """Bind arbitrary context variables to the logging context.

    Args:
        **kwargs: Key-value pairs to add to the logging context

    Example:
        >>> bind_context(task_id="task-1", agent_id=5)
        >>> logger.info("task_started")  # Will include task_id and agent_id
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def unbind_context(*keys: str) -> None:
    """Remove specific context variables from the logging context.

    Args:
        *keys: Names of context variables to remove

    Example:
        >>> unbind_context("task_id", "agent_id")
    """
    structlog.contextvars.unbind_contextvars(*keys)


def clear_context() -> None:
    """Clear all context variables from the logging context.

    Example:
        >>> clear_context()
    """
    structlog.contextvars.clear_contextvars()
