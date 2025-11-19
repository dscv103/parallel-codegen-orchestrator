"""Demonstration of structured logging with the orchestrator system.

This example shows how to use the centralized logging configuration
with correlation IDs, context binding, and structured events.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.log_config import (
    bind_context,
    bind_correlation_id,
    clear_context,
    configure_logging,
    get_logger,
    unbind_correlation_id,
)


async def simulate_task_execution(task_id: str, agent_id: int) -> None:
    """Simulate task execution with structured logging.

    Args:
        task_id: Unique identifier for the task
        agent_id: ID of the agent executing the task
    """
    logger = get_logger(__name__)

    # Bind task context
    bind_context(task_id=task_id, agent_id=agent_id)

    logger.info("task_started", status="pending")

    # Simulate work
    await asyncio.sleep(0.5)
    logger.debug("task_processing", progress=50)

    await asyncio.sleep(0.5)
    logger.info("task_completed", status="success", duration_seconds=1.0)

    # Clear context after task completion
    clear_context()


async def simulate_orchestration() -> None:
    """Simulate orchestration with multiple tasks and correlation IDs."""
    logger = get_logger(__name__)

    # Generate a correlation ID for this orchestration run
    correlation_id = "orch-12345"
    bind_correlation_id(correlation_id)

    logger.info("orchestration_started", total_tasks=3)

    try:
        # Simulate multiple tasks
        tasks = [
            simulate_task_execution("task-1", agent_id=1),
            simulate_task_execution("task-2", agent_id=2),
            simulate_task_execution("task-3", agent_id=3),
        ]

        await asyncio.gather(*tasks)

        logger.info(
            "orchestration_completed",
            status="success",
            completed_tasks=3,
            failed_tasks=0,
        )
    except Exception as e:
        logger.exception("orchestration_failed", error=str(e))
        raise
    finally:
        unbind_correlation_id()


def demonstrate_error_logging() -> None:
    """Demonstrate error logging with exception information."""
    logger = get_logger(__name__)

    try:
        # Simulate an error
        result = 10 / 0
    except ZeroDivisionError:
        logger.exception(
            "division_error",
            operation="calculate",
            numerator=10,
            denominator=0,
        )


def demonstrate_log_levels() -> None:
    """Demonstrate different log levels."""
    logger = get_logger(__name__)

    logger.debug("debug_message", detail="This is a debug message")
    logger.info("info_message", detail="This is an info message")
    logger.warning("warning_message", detail="This is a warning")
    logger.error("error_message", detail="This is an error")


def main() -> None:
    """Main demonstration function."""
    # Configure logging for JSON output
    print("=== JSON Logging Output ===\n")
    configure_logging(level="INFO", json_logs=True)

    # Demonstrate basic logging
    logger = get_logger(__name__)
    logger.info("demo_started", version="1.0")

    # Demonstrate log levels
    demonstrate_log_levels()

    # Demonstrate error logging
    demonstrate_error_logging()

    # Demonstrate async orchestration with correlation IDs
    asyncio.run(simulate_orchestration())

    logger.info("demo_completed")

    # Reconfigure for console output (human-readable)
    print("\n=== Console Logging Output (Human-Readable) ===\n")
    configure_logging(level="DEBUG", json_logs=False)

    logger = get_logger(__name__)
    logger.info("console_demo_started", mode="development")

    # Show context binding
    bind_context(user_id="user-123", session="session-456")
    logger.info("user_action", action="login")
    logger.debug("session_details", ip="192.168.1.1")
    clear_context()

    logger.info("console_demo_completed")


if __name__ == "__main__":
    main()
