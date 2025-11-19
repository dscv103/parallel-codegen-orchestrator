"""Retry Logic with Exponential Backoff for Task Execution.

This module provides retry functionality for failed agent tasks and API calls with
configurable exponential backoff. It handles transient failures while maintaining
detailed logging of all retry attempts.
"""

import asyncio
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeVar

from src.log_config import get_logger

if TYPE_CHECKING:
    from src.config import AgentConfig

# Initialize logger
logger = get_logger(__name__)

# Type variable for generic return type
T = TypeVar("T")


class FailureType(Enum):
    """Classification of failure types for retry decisions.

    Attributes:
        TRANSIENT: Temporary failures that may succeed on retry (network, timeout)
        PERMANENT: Permanent failures that won't succeed on retry (invalid input)
        UNKNOWN: Failures with unknown cause (default to transient handling)
    """

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    UNKNOWN = "unknown"


class RetryableError(Exception):
    """Exception that indicates a retryable failure.

    Attributes:
        message: Error description
        failure_type: Classification of the failure
        original_error: The original exception that was raised
    """

    def __init__(
        self,
        message: str,
        failure_type: FailureType = FailureType.UNKNOWN,
        original_error: Exception | None = None,
    ):
        """Initialize a retryable error.

        Args:
            message: Description of the error
            failure_type: Type of failure for retry decisions
            original_error: Original exception that was raised
        """
        super().__init__(message)
        self.failure_type = failure_type
        self.original_error = original_error


def classify_error(error: Exception) -> FailureType:
    """Classify an exception to determine if it's retryable.

    Args:
        error: The exception to classify

    Returns:
        FailureType indicating whether the error is retryable

    Example:
        >>> error = TimeoutError("Request timed out")
        >>> classify_error(error)
        <FailureType.TRANSIENT: 'transient'>
    """
    # Transient errors that are worth retrying
    transient_errors = (
        TimeoutError,
        asyncio.TimeoutError,
        ConnectionError,
        ConnectionResetError,
        ConnectionRefusedError,
        ConnectionAbortedError,
    )

    # Check for retryable error with explicit classification
    if isinstance(error, RetryableError):
        return error.failure_type

    # Check for known transient error types
    if isinstance(error, transient_errors):
        return FailureType.TRANSIENT

    # Check error message for common transient patterns
    error_message = str(error).lower()
    transient_patterns = [
        "timeout",
        "connection",
        "network",
        "temporary",
        "rate limit",
        "service unavailable",
        "try again",
        "502",
        "503",
        "504",
    ]

    if any(pattern in error_message for pattern in transient_patterns):
        return FailureType.TRANSIENT

    # Check for permanent errors
    permanent_patterns = [
        "invalid",
        "unauthorized",
        "forbidden",
        "not found",
        "bad request",
        "400",
        "401",
        "403",
        "404",
    ]

    if any(pattern in error_message for pattern in permanent_patterns):
        return FailureType.PERMANENT

    # Default to unknown (treated as transient with logging)
    return FailureType.UNKNOWN


async def execute_with_retry[T](
    task_id: str,
    func: Callable[..., Awaitable[T]],
    max_attempts: int = 3,
    base_delay_seconds: int = 30,
    *args: Any,
    **kwargs: Any,
) -> T:
    """Execute an async function with exponential backoff retry logic.

    Attempts to execute the given async function up to max_attempts times,
    with exponential backoff between retries. Only retries transient failures.

    Args:
        task_id: Identifier for the task (for logging)
        func: Async function to execute
        max_attempts: Maximum number of execution attempts (default: 3)
        base_delay_seconds: Base delay for exponential backoff (default: 30)
        *args: Positional arguments to pass to func
        **kwargs: Keyword arguments to pass to func

    Returns:
        Result from successful function execution

    Raises:
        Exception: The last exception if all retry attempts fail

    Example:
        >>> async def fetch_data():
        ...     # Simulate API call
        ...     return {"status": "success"}
        >>>
        >>> result = await execute_with_retry(
        ...     task_id="task-1",
        ...     func=fetch_data,
        ...     max_attempts=3,
        ...     base_delay_seconds=30
        ... )
    """
    last_error = None
    attempt = 0

    logger.info(
        "retry_execution_started",
        task_id=task_id,
        max_attempts=max_attempts,
        base_delay=base_delay_seconds,
    )

    for attempt in range(1, max_attempts + 1):
        try:
            logger.debug(
                "retry_attempt_started",
                task_id=task_id,
                attempt=attempt,
                max_attempts=max_attempts,
            )

            # Execute the function
            result = await func(*args, **kwargs)

            # Success - log and return
            if attempt > 1:
                logger.info(
                    "retry_succeeded",
                    task_id=task_id,
                    attempt=attempt,
                    total_attempts=attempt,
                )
            else:
                # First attempt succeeded, no retry needed
                pass

            return result

        except Exception as e:
            last_error = e
            failure_type = classify_error(e)

            logger.warning(
                "retry_attempt_failed",
                task_id=task_id,
                attempt=attempt,
                max_attempts=max_attempts,
                error=str(e),
                error_type=type(e).__name__,
                failure_type=failure_type.value,
            )

            # Don't retry permanent failures
            if failure_type == FailureType.PERMANENT:
                logger.exception(
                    "retry_aborted_permanent_failure",
                    task_id=task_id,
                    attempt=attempt,
                    error=str(e),
                )
                raise

            # If this was the last attempt, raise the error
            if attempt >= max_attempts:
                logger.exception(
                    "retry_exhausted",
                    task_id=task_id,
                    total_attempts=attempt,
                    final_error=str(e),
                )
                raise

            # Calculate exponential backoff delay: base_delay * 2^(attempt-1)
            # attempt=1: base_delay * 1 = base_delay
            # attempt=2: base_delay * 2 = 2 * base_delay
            # attempt=3: base_delay * 4 = 4 * base_delay
            delay = base_delay_seconds * (2 ** (attempt - 1))

            logger.info(
                "retry_backoff_delay",
                task_id=task_id,
                attempt=attempt,
                delay_seconds=delay,
                next_attempt=attempt + 1,
            )

            # Wait before next retry
            await asyncio.sleep(delay)

    # This should never be reached, but just in case
    if last_error:
        raise last_error
    error_msg = f"Retry logic failed unexpectedly for task {task_id}"
    raise RuntimeError(error_msg)


class RetryConfig:
    """Configuration for retry behavior.

    Attributes:
        max_attempts: Maximum number of retry attempts
        base_delay_seconds: Base delay for exponential backoff
        enabled: Whether retry logic is enabled
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay_seconds: int = 30,
        enabled: bool = True,
    ):
        """Initialize retry configuration.

        Args:
            max_attempts: Maximum retry attempts (default: 3)
            base_delay_seconds: Base backoff delay (default: 30)
            enabled: Enable retry logic (default: True)

        Raises:
            ValueError: If parameters are invalid
        """
        if max_attempts < 0:
            msg = "max_attempts must be non-negative"
            raise ValueError(msg)
        if base_delay_seconds < 0:
            msg = "base_delay_seconds must be non-negative"
            raise ValueError(msg)

        self.max_attempts = max_attempts
        self.base_delay_seconds = base_delay_seconds
        self.enabled = enabled

    @classmethod
    def from_agent_config(cls, agent_config: "AgentConfig") -> "RetryConfig":
        """Create RetryConfig from AgentConfig.

        Args:
            agent_config: AgentConfig instance with retry settings

        Returns:
            RetryConfig instance

        Example:
            >>> from src.config import AgentConfig
            >>> agent_config = AgentConfig(
            ...     retry_attempts=3,
            ...     retry_delay_seconds=30
            ... )
            >>> retry_config = RetryConfig.from_agent_config(agent_config)
        """
        return cls(
            max_attempts=agent_config.retry_attempts,
            base_delay_seconds=agent_config.retry_delay_seconds,
            enabled=agent_config.retry_attempts > 0,
        )
