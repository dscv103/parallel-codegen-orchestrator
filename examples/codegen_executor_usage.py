"""Example usage of CodegenExecutor.

This script demonstrates how to use the CodegenExecutor class
to execute Codegen agent tasks with proper error handling and retry logic.
"""

import asyncio
import os

from codegen import Agent

from src.agents.codegen_executor import CodegenExecutor, TaskStatus


async def example_basic_usage():
    """Demonstrate basic CodegenExecutor usage."""
    print("=== Basic CodegenExecutor Usage ===\n")

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

    print(f"Executing task: {task_data['task_id']}")
    print(f"Prompt: {task_data['prompt']}\n")

    # Execute the task
    result = await executor.execute_task(task_data)

    # Check result
    print(f"Task ID: {result.task_id}")
    print(f"Status: {result.status.value}")
    print(f"Duration: {result.duration_seconds:.2f} seconds")

    if result.status == TaskStatus.COMPLETED:
        print("Result:", result.result)
    else:
        print("Error:", result.error)


async def example_custom_configuration():
    """Demonstrate CodegenExecutor with custom configuration."""
    print("\n\n=== Custom Configuration Example ===\n")

    org_id = os.getenv("CODEGEN_ORG_ID", "YOUR_ORG_ID")
    api_token = os.getenv("CODEGEN_API_TOKEN", "YOUR_API_TOKEN")

    agent = Agent(org_id=int(org_id), token=api_token)

    # Create executor with custom settings
    executor = CodegenExecutor(
        agent,
        timeout_seconds=300,  # 5 minute timeout
        poll_interval_seconds=5,  # Check status every 5 seconds
        retry_attempts=5,  # Up to 5 retry attempts
        retry_delay_seconds=15,  # 15 second base delay between retries
    )

    task_data = {
        "task_id": "example-task-2",
        "prompt": "Refactor the authentication module for better testability",
        "repo_id": "your-org/your-repo",
    }

    print(f"Executing task with custom config: {task_data['task_id']}\n")

    result = await executor.execute_task(task_data)

    print(f"Task completed with status: {result.status.value}")
    if result.retry_count > 0:
        print(f"Required {result.retry_count} retry attempts")


async def example_multiple_tasks():
    """Demonstrate executing multiple tasks concurrently."""
    print("\n\n=== Multiple Tasks Example ===\n")

    org_id = os.getenv("CODEGEN_ORG_ID", "YOUR_ORG_ID")
    api_token = os.getenv("CODEGEN_API_TOKEN", "YOUR_API_TOKEN")

    agent = Agent(org_id=int(org_id), token=api_token)
    executor = CodegenExecutor(agent, poll_interval_seconds=3)

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

    print(f"Executing {len(tasks)} tasks concurrently...\n")

    # Execute all tasks concurrently
    results = await asyncio.gather(
        *[executor.execute_task(task) for task in tasks], return_exceptions=True
    )

    # Display results
    for result in results:
        if isinstance(result, Exception):
            print(f"Task failed with exception: {result}")
        else:
            print(f"Task {result.task_id}: {result.status.value}")


async def example_error_handling():
    """Demonstrate error handling and retry behavior."""
    print("\n\n=== Error Handling Example ===\n")

    org_id = os.getenv("CODEGEN_ORG_ID", "YOUR_ORG_ID")
    api_token = os.getenv("CODEGEN_API_TOKEN", "YOUR_API_TOKEN")

    agent = Agent(org_id=int(org_id), token=api_token)
    executor = CodegenExecutor(
        agent,
        timeout_seconds=120,  # Short timeout for demo
        retry_attempts=3,
        retry_delay_seconds=10,
    )

    # Task with potentially transient failure
    task_data = {
        "task_id": "example-task-error",
        "prompt": "Complex refactoring that might timeout",
        "repo_id": "your-org/your-repo",
    }

    print(f"Executing task that may fail: {task_data['task_id']}\n")

    try:
        result = await executor.execute_task(task_data)

        if result.status == TaskStatus.FAILED:
            print(f"Task failed: {result.error}")
            if result.retry_count > 0:
                print(f"Failed after {result.retry_count} retry attempts")
        else:
            print(f"Task succeeded: {result.status.value}")

    except Exception as e:
        print(f"Unexpected error: {e}")


async def main():
    """Run all examples."""
    # Note: These examples use placeholder credentials
    # Replace with actual credentials to run

    print("CodegenExecutor Examples")
    print("=" * 50)
    print("\nNote: Update CODEGEN_ORG_ID and CODEGEN_API_TOKEN")
    print("environment variables to run these examples.\n")

    try:
        await example_basic_usage()
        await example_custom_configuration()
        await example_multiple_tasks()
        await example_error_handling()

    except Exception as e:
        print(f"\nError running examples: {e}")
        print("\nMake sure to set valid CODEGEN_ORG_ID and CODEGEN_API_TOKEN")


if __name__ == "__main__":
    asyncio.run(main())

