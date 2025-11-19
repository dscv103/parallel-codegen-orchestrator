#!/usr/bin/env python3
"""Main Entry Point and CLI Integration.

This module provides the main async entry point and CLI interface for the
parallel Codegen orchestrator. It initializes all components, loads configuration,
fetches tasks, builds dependency graph, and executes the orchestration loop.
"""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Any

import structlog

from src.agents.agent_pool import AgentPool
from src.config import OrchestratorConfig
from src.github.dependency_parser import DependencyParser
from src.github.rest_api import GitHubIntegration
from src.graph.dependency_graph import DependencyGraph
from src.orchestrator.orchestrator import TaskOrchestrator
from src.orchestrator.result_manager import ResultManager
from src.orchestrator.task_executor import TaskExecutor

# Initialize logger (will be configured after loading config)
logger = structlog.get_logger(__name__)

# Global flag for graceful shutdown
shutdown_requested = False


def configure_logging(level: str = "INFO") -> None:
    """Configure structured logging with the specified level.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if level == "DEBUG"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO),
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def signal_handler(signum: int, _frame: object) -> None:
    """Handle shutdown signals (SIGINT, SIGTERM).

    Args:
        signum: Signal number
        _frame: Current stack frame (unused)
    """
    global shutdown_requested  # noqa: PLW0603
    signal_name = signal.Signals(signum).name
    logger.warning("shutdown_signal_received", signal=signal_name)
    shutdown_requested = True


async def fetch_tasks_from_github(
    github: GitHubIntegration,
    config: OrchestratorConfig,
) -> dict[str, dict[str, Any]]:
    """Fetch tasks from GitHub issues.

    Args:
        github: GitHub integration instance
        config: Orchestrator configuration

    Returns:
        Dictionary mapping task IDs to task data dictionaries
    """
    logger.info("fetching_tasks_from_github", repository=config.github.repository)

    # Fetch open issues from GitHub
    issues = github.fetch_issues(
        repo_name=config.github.repository,
        state="open",
    )

    # Parse dependencies from issue bodies
    parser = DependencyParser()
    tasks = {}

    for issue in issues:
        task_id = f"issue-{issue.number}"
        dependencies = parser.parse_dependencies(
            issue_body=issue.body or "",
            labels=[label.name for label in issue.labels],
        )

        tasks[task_id] = {
            "id": task_id,
            "issue_number": issue.number,
            "title": issue.title,
            "body": issue.body or "",
            "labels": [label.name for label in issue.labels],
            "dependencies": dependencies,
            "repo_id": config.github.repository,
            "prompt": f"Work on issue #{issue.number}: {issue.title}\n\n{issue.body or ''}",
        }

    logger.info("tasks_fetched", count=len(tasks), repository=config.github.repository)
    return tasks


def build_dependency_graph(tasks: dict[str, dict[str, Any]]) -> DependencyGraph:
    """Build dependency graph from tasks.

    Args:
        tasks: Dictionary of task data

    Returns:
        Initialized and prepared DependencyGraph

    Raises:
        ValueError: If dependency graph has cycles
    """
    logger.info("building_dependency_graph", total_tasks=len(tasks))

    dep_graph = DependencyGraph()

    # Add all tasks to the graph
    for task_id, task_data in tasks.items():
        dependencies = task_data.get("dependencies", set())
        dep_graph.add_task(task_id, dependencies)

    # Build and validate the graph
    try:
        dep_graph.build()
    except ValueError as e:
        logger.exception("dependency_graph_cycle_detected", error=str(e))
        raise
    else:
        logger.info(
            "dependency_graph_built",
            total_tasks=len(tasks),
            has_dependencies=any(task_data.get("dependencies") for task_data in tasks.values()),
        )
        return dep_graph


async def post_results_to_github(
    github: GitHubIntegration,
    results: list[dict[str, Any]],
    config: OrchestratorConfig,
) -> None:
    """Post orchestration results back to GitHub as comments.

    Args:
        github: GitHub integration instance
        results: List of task results
        config: Orchestrator configuration
    """
    logger.info("posting_results_to_github", total_results=len(results))

    # Group results by status
    successful = [r for r in results if r.get("status") == "completed"]
    failed = [r for r in results if r.get("status") == "failed"]
    cancelled = [r for r in results if r.get("status") == "cancelled"]

    # Create summary comment
    summary_lines = [
        "## 🤖 Orchestration Results",
        "",
        f"**Total Tasks:** {len(results)}",
        f"✅ **Successful:** {len(successful)}",
        f"❌ **Failed:** {len(failed)}",
        f"🚫 **Cancelled:** {len(cancelled)}",
        "",
    ]

    # Add successful tasks
    if successful:
        summary_lines.append("### ✅ Successful Tasks")
        for result in successful:
            issue_num = result.get("issue_number", "unknown")
            task_title = result.get("title", "Unknown task")
            duration = result.get("duration_seconds", 0)
            summary_lines.append(f"- #{issue_num}: {task_title} ({duration:.1f}s)")
        summary_lines.append("")

    # Add failed tasks
    if failed:
        summary_lines.append("### ❌ Failed Tasks")
        for result in failed:
            issue_num = result.get("issue_number", "unknown")
            task_title = result.get("title", "Unknown task")
            error = result.get("error", "Unknown error")
            summary_lines.append(f"- #{issue_num}: {task_title}")
            summary_lines.append(f"  Error: `{error}`")
        summary_lines.append("")

    # Add cancelled tasks
    if cancelled:
        summary_lines.append("### 🚫 Cancelled Tasks")
        for result in cancelled:
            issue_num = result.get("issue_number", "unknown")
            task_title = result.get("title", "Unknown task")
            summary_lines.append(f"- #{issue_num}: {task_title}")
        summary_lines.append("")

    # Post comment to each issue (or to a central tracking issue)
    # For now, we'll post to each individual issue
    for result in results:
        issue_number = result.get("issue_number")
        if issue_number:
            status_emoji = {
                "completed": "✅",
                "failed": "❌",
                "cancelled": "🚫",
            }.get(result.get("status"), "❓")

            issue_comment = [
                f"{status_emoji} **Orchestration Result**",
                "",
                f"**Status:** {result.get('status', 'unknown')}",
                f"**Duration:** {result.get('duration_seconds', 0):.1f}s",
            ]

            if result.get("error"):
                issue_comment.append(f"**Error:** `{result.get('error')}`")

            if result.get("result"):
                issue_comment.append("")
                issue_comment.append("**Result:**")
                issue_comment.append(f"```\n{result.get('result')}\n```")

            try:
                github.post_comment(
                    repo_name=config.github.repository,
                    issue_number=issue_number,
                    comment="\n".join(issue_comment),
                )
                logger.info(
                    "result_posted_to_issue",
                    issue_number=issue_number,
                    status=result.get("status"),
                )
            except (ValueError, RuntimeError) as e:
                logger.exception(
                    "failed_to_post_result",
                    issue_number=issue_number,
                    error=str(e),
                )

    logger.info("results_posted_to_github", total_posted=len(results))


async def main_async(args: argparse.Namespace) -> int:
    """Main async orchestration entry point.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    exit_code = 0

    # Configure logging
    configure_logging(args.log_level)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Load configuration
        logger.info("loading_configuration", config_file=args.config)
        config = OrchestratorConfig.from_yaml(args.config)

        # Override logging level if specified via CLI
        if args.log_level != "INFO":
            config.logging_level = args.log_level
            configure_logging(config.logging_level)

        # Print configuration warnings
        warnings = config.validate_config()
        for warning in warnings:
            logger.warning("configuration_warning", message=warning)

        # Dry run mode - validate and exit
        if args.dry_run:
            logger.info("dry_run_mode_complete", config_valid=True)
            return exit_code

        # Initialize GitHub integration
        logger.info("initializing_github_integration", organization=config.github.organization)
        github = GitHubIntegration(
            token=config.github.token,
            org_id=config.github.organization,
        )

        # Fetch tasks from GitHub
        tasks = await fetch_tasks_from_github(github, config)

        if not tasks:
            logger.warning("no_tasks_found", repository=config.github.repository)
            return exit_code

        # Build dependency graph
        dep_graph = build_dependency_graph(tasks)

        # Initialize agent pool
        logger.info(
            "initializing_agent_pool",
            max_agents=config.agent.max_concurrent_agents,
        )
        agent_pool = AgentPool(
            org_id=config.codegen.org_id,
            api_token=config.codegen.api_token,
            max_agents=config.agent.max_concurrent_agents,
        )

        # Initialize result manager
        result_manager = ResultManager()

        # Create executor and orchestrator
        logger.info("starting_orchestration")
        executor = TaskExecutor(
            agent_pool=agent_pool,
            dep_graph=dep_graph,
            result_manager=result_manager,
            timeout_seconds=config.agent.task_timeout_seconds,
        )
        orchestrator = TaskOrchestrator(executor=executor)

        # Execute orchestration loop
        results = await orchestrator.orchestrate(tasks)

        # Check for shutdown
        if shutdown_requested:
            logger.warning("orchestration_interrupted_by_signal")
            exit_code = 1
        else:
            # Log summary
            summary = result_manager.get_summary()
            logger.info(
                "orchestration_complete",
                total=summary.get("total_tasks", 0),
                successful=summary.get("successful", 0),
                failed=summary.get("failed", 0),
                duration=summary.get("total_duration_seconds", 0),
            )

            # Post results back to GitHub
            if config.automation.post_results_as_comment and not args.no_post_results:
                # Convert TaskResult objects to dicts with task metadata
                results_dicts = []
                for task_result in results:
                    task_data = tasks.get(task_result.task_id, {})
                    result_dict = {
                        "task_id": task_result.task_id,
                        "issue_number": task_data.get("issue_number"),
                        "title": task_data.get("title", "Unknown task"),
                        "status": task_result.status.value,  # Convert enum to string
                        "duration_seconds": task_result.duration_seconds,
                        "result": task_result.result,
                        "error": task_result.error,
                    }
                    results_dicts.append(result_dict)
                
                await post_results_to_github(github, results_dicts, config)

            # Set exit code based on results
            if summary.get("failed", 0) > 0:
                logger.warning("orchestration_had_failures", failed_count=summary.get("failed"))
                exit_code = 1

    except KeyboardInterrupt:
        logger.warning("orchestration_interrupted")
        exit_code = 1

    except FileNotFoundError as e:
        logger.exception("configuration_file_not_found", error=str(e))
        exit_code = 1

    except ValueError as e:
        logger.exception("configuration_validation_error", error=str(e))
        exit_code = 1

    except Exception as e:
        logger.exception("orchestration_failed", error=str(e))
        exit_code = 1

    return exit_code


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Parallel Codegen Orchestrator - Concurrent task execution with dependency management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python main.py --config config.yaml

  # Verbose mode
  python main.py --config config.yaml --verbose

  # Debug mode with detailed logging
  python main.py --config config.yaml --debug

  # Dry run (validate configuration without executing)
  python main.py --config config.yaml --dry-run

  # Disable posting results to GitHub
  python main.py --config config.yaml --no-post-results
        """,
    )

    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default="config.yaml",
        help="Path to configuration YAML file (default: config.yaml)",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output (INFO level)",
    )

    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Enable debug output (DEBUG level)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration without executing tasks",
    )

    parser.add_argument(
        "--no-post-results",
        action="store_true",
        help="Do not post results back to GitHub",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set logging level (default: INFO)",
    )

    args = parser.parse_args()

    # Handle verbose/debug flags
    if args.debug:
        args.log_level = "DEBUG"
    elif args.verbose:
        args.log_level = "INFO"

    return args


def main() -> None:
    """Main entry point for the orchestrator.

    This function parses arguments, runs the async main function,
    and exits with the appropriate code.
    """
    args = parse_args()

    # Check if config file exists
    if not Path(args.config).exists() and not args.dry_run:
        sys.exit(1)

    # Run async main
    try:
        exit_code = asyncio.run(main_async(args))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        sys.exit(1)


if __name__ == "__main__":
    main()
