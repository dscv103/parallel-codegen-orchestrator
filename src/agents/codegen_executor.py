"""Codegen Executor for agent task execution.

This module implements the CodegenExecutor class that wraps Codegen Agent
execution with async polling, timeout handling, and retry logic.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import structlog
from codegen import Agent

# Initialize logger
logger = structlog.get_logger()

# Constants
DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_POLL_INTERVAL_SECONDS = 2
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SECONDS = 30
MIN_TIMEOUT = 60
MIN_POLL_INTERVAL = 1
MIN_RETRY_DELAY = 5


class TaskStatus(Enum):
    """Task execution status enumeration.

    Represents the current state of a Codegen task execution.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskResult:
    """Result of a Codegen task execution.

    Contains all information about a completed task execution,
    including status, timing, and results or errors.

    Attributes:
        task_id: Unique identifier for the task
        status: Final status of the task execution
        start_time: When the task execution began
        end_time: When the task execution completed
        duration_seconds: Total execution time in seconds
        result: Task result data if successful (None if failed)
        error: Error message if failed (None if successful)
        retry_count: Number of retry attempts made
    """

    task_id: str
    status: TaskStatus
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    result: dict[str, Any] | None = None
    error: str | None = None
    retry_count: int = 0


class CodegenExecutor:
    """Executor for Codegen agent tasks.

    Handles execution of Codegen tasks with async polling for completion,
    configurable timeouts, and automatic retry logic for transient failures.

    The executor polls the Codegen API at regular intervals to check task
    status and handles the complete lifecycle of task execution.

    Example:
        >>> executor = CodegenExecutor(agent, timeout_seconds=300)
        >>> task_data = {
        ...     'task_id': 'task-1',
        ...     'prompt': 'Implement user authentication',
        ...     'repo_id': 'org/repo'
        ... }
        >>> result = await executor.execute_task(task_data)
        >>> print(result.status)

    Attributes:
        agent: The Codegen Agent instance to use for execution
        timeout_seconds: Maximum time to wait for task completion
        poll_interval_seconds: Time to wait between status checks
        retry_attempts: Maximum number of retry attempts for transient failures
        retry_delay_seconds: Base delay between retry attempts (with exponential backoff)
    """

    def __init__(
        self,
        agent: Agent,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
        retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
        retry_delay_seconds: int = DEFAULT_RETRY_DELAY_SECONDS,
    ):
        """Initialize the Codegen executor.

        Args:
            agent: Codegen Agent instance
            timeout_seconds: Task execution timeout (default: 600, min: 60)
            poll_interval_seconds: Polling interval for status checks (default: 2, min: 1)
            retry_attempts: Maximum retry attempts for transient failures (default: 3)
            retry_delay_seconds: Base delay between retries (default: 30, min: 5)

        Raises:
            ValueError: If timeout or poll_interval are below minimum values
        """
        if timeout_seconds < MIN_TIMEOUT:
            msg = f"timeout_seconds must be at least {MIN_TIMEOUT}, got {timeout_seconds}"
            raise ValueError(msg)

        if poll_interval_seconds < MIN_POLL_INTERVAL:
            msg = f"poll_interval_seconds must be at least {MIN_POLL_INTERVAL}, got {poll_interval_seconds}"
            raise ValueError(msg)

        if retry_delay_seconds < MIN_RETRY_DELAY:
            msg = f"retry_delay_seconds must be at least {MIN_RETRY_DELAY}, got {retry_delay_seconds}"
            raise ValueError(msg)

        self.agent = agent
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.retry_attempts = retry_attempts
        self.retry_delay_seconds = retry_delay_seconds

        logger.info(
            "codegen_executor_initialized",
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            retry_attempts=retry_attempts,
        )

    async def execute_task(self, task_data: dict[str, Any]) -> TaskResult:
        """Execute a Codegen task with retry logic.

        Runs the task using the Codegen agent with automatic retries for
        transient failures. Each retry uses exponential backoff.

        Args:
            task_data: Task configuration containing:
                - task_id: Unique task identifier
                - prompt: Task prompt/description
                - repo_id: Repository identifier (optional)
                - Additional task-specific parameters

        Returns:
            TaskResult with execution details and outcome

        Raises:
            Exception: If all retry attempts are exhausted

        Example:
            >>> task_data = {
            ...     'task_id': 'task-1',
            ...     'prompt': 'Fix bug in authentication',
            ...     'repo_id': 'org/repo'
            ... }
            >>> result = await executor.execute_task(task_data)
        """
        task_id = task_data.get("task_id", "unknown")
        last_error = None

        for attempt in range(self.retry_attempts):
            try:
                logger.info(
                    "task_execution_attempt",
                    task_id=task_id,
                    attempt=attempt + 1,
                    max_attempts=self.retry_attempts,
                )

                result = await self._execute_single_attempt(task_data)

                # If completed successfully, return immediately
                if result.status == TaskStatus.COMPLETED:
                    logger.info(
                        "task_execution_succeeded",
                        task_id=task_id,
                        attempt=attempt + 1,
                    )
                    return result

                # If failed but not a transient error, don't retry
                if result.status == TaskStatus.FAILED:
                    if not self._is_transient_error(result.error):
                        logger.warning(
                            "task_execution_failed_permanent",
                            task_id=task_id,
                            error=result.error,
                        )
                        return result

                    last_error = result.error
                    logger.warning(
                        "task_execution_failed_transient",
                        task_id=task_id,
                        attempt=attempt + 1,
                        error=result.error,
                    )

            except Exception as e:
                last_error = str(e)
                logger.exception(
                    "task_execution_exception",
                    task_id=task_id,
                    attempt=attempt + 1,
                    error=str(e),
                )

            # If not the last attempt, wait before retrying with exponential backoff
            if attempt < self.retry_attempts - 1:
                delay = self.retry_delay_seconds * (2**attempt)
                logger.info(
                    "task_execution_retry_delay",
                    task_id=task_id,
                    delay_seconds=delay,
                    next_attempt=attempt + 2,
                )
                await asyncio.sleep(delay)

        # All retries exhausted
        logger.error(
            "task_execution_retry_exhausted",
            task_id=task_id,
            attempts=self.retry_attempts,
            last_error=last_error,
        )

        # Return a failed result with the last error
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=0,
            error=f"All retry attempts exhausted. Last error: {last_error}",
            retry_count=self.retry_attempts,
        )

    async def _execute_single_attempt(self, task_data: dict[str, Any]) -> TaskResult:
        """Execute a single task attempt without retries.

        Runs the Codegen agent task and polls for completion.

        Args:
            task_data: Task configuration dictionary

        Returns:
            TaskResult with execution outcome

        Raises:
            TimeoutError: If task exceeds timeout duration
            Exception: For other execution errors
        """
        task_id = task_data.get("task_id", "unknown")
        prompt = task_data.get("prompt")
        repo_id = task_data.get("repo_id")

        if not prompt:
            msg = "Task data must include 'prompt'"
            raise ValueError(msg)

        start_time = datetime.now()

        logger.info(
            "task_started",
            task_id=task_id,
            prompt=prompt[:100] if prompt else None,  # Log first 100 chars
            repo_id=repo_id,
        )

        try:
            # Run the agent
            task = self.agent.run(prompt=prompt, repo_id=repo_id)

            logger.debug(
                "agent_task_submitted",
                task_id=task_id,
                codegen_task_status=task.status,
            )

            # Poll for completion with timeout
            elapsed_time = 0
            while task.status not in ["completed", "failed"]:
                if elapsed_time >= self.timeout_seconds:
                    error_msg = f"Task exceeded timeout of {self.timeout_seconds}s"
                    logger.error(
                        "task_timeout",
                        task_id=task_id,
                        elapsed_seconds=elapsed_time,
                        timeout_seconds=self.timeout_seconds,
                    )

                    end_time = datetime.now()
                    return TaskResult(
                        task_id=task_id,
                        status=TaskStatus.FAILED,
                        start_time=start_time,
                        end_time=end_time,
                        duration_seconds=(end_time - start_time).total_seconds(),
                        error=error_msg,
                    )

                await asyncio.sleep(self.poll_interval_seconds)
                elapsed_time += self.poll_interval_seconds

                # Refresh task status
                task.refresh()

                logger.debug(
                    "task_status_polled",
                    task_id=task_id,
                    status=task.status,
                    elapsed_seconds=elapsed_time,
                )

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            # Build result based on final status
            if task.status == "completed":
                logger.info(
                    "task_completed",
                    task_id=task_id,
                    duration_seconds=duration,
                )

                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.COMPLETED,
                    start_time=start_time,
                    end_time=end_time,
                    duration_seconds=duration,
                    result={"data": task.result} if hasattr(task, "result") else None,
                )
            else:  # task.status == "failed"
                error_msg = task.error if hasattr(task, "error") else "Unknown error"

                logger.error(
                    "task_failed",
                    task_id=task_id,
                    duration_seconds=duration,
                    error=error_msg,
                )

                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    start_time=start_time,
                    end_time=end_time,
                    duration_seconds=duration,
                    error=error_msg,
                )

        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            logger.exception(
                "task_execution_error",
                task_id=task_id,
                duration_seconds=duration,
                error=str(e),
            )

            return TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration,
                error=str(e),
            )

    def _is_transient_error(self, error: str | None) -> bool:
        """Determine if an error is transient and should be retried.

        Args:
            error: Error message or None

        Returns:
            True if error appears to be transient, False otherwise
        """
        if not error:
            return False

        # List of error patterns that indicate transient failures
        transient_patterns = [
            "timeout",
            "connection",
            "network",
            "rate limit",
            "503",
            "502",
            "504",
            "temporary",
            "unavailable",
        ]

        error_lower = error.lower()
        is_transient = any(pattern in error_lower for pattern in transient_patterns)

        if is_transient:
            logger.debug("transient_error_detected", error=error)

        return is_transient

