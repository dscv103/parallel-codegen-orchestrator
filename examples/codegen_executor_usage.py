"""Example usage of CodegenExecutor.

This script demonstrates how to use the CodegenExecutor class
to execute Codegen agent tasks with proper error handling and retry logic.
"""

import asyncio
import logging
import os

from codegen import Agent

from src.agents.codegen_executor import CodegenExecutor, TaskStatus

# Configure logging for examples
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def example_basic_usage():
    """Demonstrate basic CodegenExecutor usage."""
    logger.info("=== Basic CodegenExecutor Usage ===")

    # Initialize Codegen Agent
    # In production, get these from environment variables or config
    org_id = os.getenv("CODEGEN_ORG_ID", "YOUR_ORG_ID")
    api_token = os.getenv("CODEGEN_API_TOKEN", "YOUR_API_TOKEN")

    agent = Agent(org_id=int(org_id), token=api_token)

    # Create executor with default settings
    executor = CodegenExecutor(agent)

    # Define a task
    task_data = {
        "task_id": "example-task-1",
        "prompt": "Add input validation to the login form",
        "repo_id": "your-org/your-repo",
    }

    logger.info("Executing task: %s", task_data["task_id"])
    logger.info("Prompt: %s", task_data["prompt"])

    # Execute the task
    result = await executor.execute_task(task_data)

    # Check result
    logger.info("Task ID: %s", result.task_id)
    logger.info("Status: %s", result.status.value)
    logger.info("Duration: %.2f seconds", result.duration_seconds)

    if result.status == TaskStatus.COMPLETED:
        logger.info("Result: %s", result.result)
    else:
        logger.error("Error: %s", result.error)


async def example_custom_configuration():
    """Demonstrate CodegenExecutor with custom configuration."""
    logger.info("=== Custom Configuration Example ===")

    org_id = os.getenv("CODEGEN_ORG_ID", "YOUR_ORG_ID")
    api_token = os.getenv("CODEGEN_API_TOKEN", "YOUR_API_TOKEN")

    agent = Agent(org_id=int(org_id), token=api_token)

    # Constants for configuration
    timeout_seconds = 300  # 5 minute timeout
    poll_interval_seconds = 5  # Check status every 5 seconds
    retry_attempts = 5  # Up to 5 retry attempts
    retry_delay_seconds = 15  # 15 second base delay between retries

    # Create executor with custom settings
    executor = CodegenExecutor(
        agent,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        retry_attempts=retry_attempts,
        retry_delay_seconds=retry_delay_seconds,
    )

    task_data = {
        "task_id": "example-task-2",
        "prompt": "Refactor the authentication module for better testability",
        "repo_id": "your-org/your-repo",
    }

    logger.info("Executing task with custom config: %s", task_data["task_id"])

    result = await executor.execute_task(task_data)

    logger.info("Task completed with status: %s", result.status.value)
    if result.retry_count > 0:
        logger.info("Required %d retry attempts", result.retry_count)


async def example_multiple_tasks():
    """Demonstrate executing multiple tasks concurrently."""
    logger.info("=== Multiple Tasks Example ===")

    org_id = os.getenv("CODEGEN_ORG_ID", "YOUR_ORG_ID")
    api_token = os.getenv("CODEGEN_API_TOKEN", "YOUR_API_TOKEN")

    agent = Agent(org_id=int(org_id), token=api_token)

    poll_interval_seconds = 3
    executor = CodegenExecutor(agent, poll_interval_seconds=poll_interval_seconds)

    # Define multiple tasks
    tasks = [
        {
            "task_id": "task-1",
            "prompt": "Add error logging to the payment service",
            "repo_id": "your-org/your-repo",
        },
        {
            "task_id": "task-2",
            "prompt": "Update API documentation for v2 endpoints",
            "repo_id": "your-org/your-repo",
        },
        {
            "task_id": "task-3",
            "prompt": "Implement rate limiting for API calls",
            "repo_id": "your-org/your-repo",
        },
    ]

    logger.info("Executing %d tasks concurrently...", len(tasks))

    # Execute all tasks concurrently
    results = await asyncio.gather(
        *[executor.execute_task(task) for task in tasks],
        return_exceptions=True,
    )

    # Display results
    for result in results:
        if isinstance(result, Exception):
            logger.error("Task failed with exception: %s", result)
        else:
            logger.info("Task %s: %s", result.task_id, result.status.value)


async def example_error_handling():
    """Demonstrate error handling and retry behavior."""
    logger.info("=== Error Handling Example ===")

    org_id = os.getenv("CODEGEN_ORG_ID", "YOUR_ORG_ID")
    api_token = os.getenv("CODEGEN_API_TOKEN", "YOUR_API_TOKEN")

    agent = Agent(org_id=int(org_id), token=api_token)

    # Constants for configuration
    timeout_seconds = 120  # Short timeout for demo
    retry_attempts = 3
    retry_delay_seconds = 10

    executor = CodegenExecutor(
        agent,
        timeout_seconds=timeout_seconds,
        retry_attempts=retry_attempts,
        retry_delay_seconds=retry_delay_seconds,
    )

    # Task with potentially transient failure
    task_data = {
        "task_id": "example-task-error",
        "prompt": "Complex refactoring that might timeout",
        "repo_id": "your-org/your-repo",
    }

    logger.info("Executing task that may fail: %s", task_data["task_id"])

    try:
        result = await executor.execute_task(task_data)

        if result.status == TaskStatus.FAILED:
            logger.error("Task failed: %s", result.error)
            if result.retry_count > 0:
                logger.info("Failed after %d retry attempts", result.retry_count)
        else:
            logger.info("Task succeeded: %s", result.status.value)

    except Exception:
        logger.exception("Unexpected error occurred")


async def main():
    """Run all examples."""
    # Note: These examples use placeholder credentials
    # Replace with actual credentials to run

    logger.info("CodegenExecutor Examples")
    logger.info("=" * 50)
    logger.info("Note: Update CODEGEN_ORG_ID and CODEGEN_API_TOKEN")
    logger.info("environment variables to run these examples.")

    try:
        await example_basic_usage()
        await example_custom_configuration()
        await example_multiple_tasks()
        await example_error_handling()

    except Exception:
        logger.exception("Error running examples")
        logger.info("Make sure to set valid CODEGEN_ORG_ID and CODEGEN_API_TOKEN")


if __name__ == "__main__":
    asyncio.run(main())
