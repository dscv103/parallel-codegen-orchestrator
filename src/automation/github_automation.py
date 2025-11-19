"""GitHub Automation Handler for Orchestration Results.

This module provides automated GitHub integration after task orchestration
completes, including result posting, label management, and auto-merge capabilities.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

from github import GithubException, PullRequest
from src.agents.codegen_executor import TaskResult, TaskStatus
from src.github.rest_api import GitHubIntegration

# Initialize structured logger
logger = structlog.get_logger(__name__)

# Constants for status indicators
STATUS_EMOJI = {
    TaskStatus.COMPLETED: "✅",
    TaskStatus.FAILED: "❌",
    TaskStatus.PENDING: "⏳",
    TaskStatus.RUNNING: "🔄",
}

# Default status labels
DEFAULT_STATUS_LABELS = {
    "all_success": "completed",
    "all_failed": "failed",
    "partial": "partial",
    "in_progress": "in-progress",
}


@dataclass
class AutomationConfig:
    """Configuration for GitHub automation features.

    Attributes:
        auto_merge_on_success: Enable automatic PR merging on all tasks success
        post_results_as_comment: Post orchestration results as GitHub comments
        update_issue_status: Automatically update issue labels based on outcomes
        status_label_prefix: Prefix for status labels (e.g., "status:")
    """

    auto_merge_on_success: bool = False
    post_results_as_comment: bool = True
    update_issue_status: bool = True
    status_label_prefix: str = "status:"


class GitHubAutomationHandler:
    """Handler for GitHub automation features post-orchestration.

    This class coordinates automated GitHub actions after task orchestration
    completes, including posting results, managing labels, and merging PRs.
    All operations are fail-safe and won't disrupt the main orchestration flow.

    Example:
        >>> config = AutomationConfig(
        ...     post_results_as_comment=True,
        ...     update_issue_status=True,
        ...     auto_merge_on_success=False
        ... )
        >>> github = GitHubIntegration(token="ghp_...", org_id="my-org")
        >>> handler = GitHubAutomationHandler(
        ...     config=config,
        ...     github_integration=github,
        ...     repo_name="my-org/my-repo"
        ... )
        >>> 
        >>> # After orchestration completes
        >>> results = [...]  # List of TaskResult objects
        >>> context = {"issue_number": 123, "pr_number": 456}
        >>> await handler.execute_automation(results, context)

    Attributes:
        config: Automation configuration settings
        github: GitHub REST API integration instance
        repo_name: Repository name in 'owner/repo' format
    """

    def __init__(
        self,
        config: AutomationConfig,
        github_integration: GitHubIntegration,
        repo_name: str,
    ):
        """Initialize GitHub automation handler.

        Args:
            config: Automation configuration with feature toggles
            github_integration: Authenticated GitHub API client
            repo_name: Repository name in 'owner/repo' format

        Example:
            >>> config = AutomationConfig(post_results_as_comment=True)
            >>> github = GitHubIntegration("token", "org-id")
            >>> handler = GitHubAutomationHandler(config, github, "org/repo")
        """
        self.config = config
        self.github = github_integration
        self.repo_name = repo_name

        logger.info(
            "github_automation_handler_initialized",
            repo_name=repo_name,
            auto_merge_enabled=config.auto_merge_on_success,
            post_comments_enabled=config.post_results_as_comment,
            update_labels_enabled=config.update_issue_status,
            label_prefix=config.status_label_prefix,
        )

    async def execute_automation(
        self,
        results: Sequence[TaskResult],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute all enabled automation features.

        This is the main entry point for post-orchestration automation. It
        coordinates all automation actions based on configuration and returns
        a summary of what was executed.

        Args:
            results: List of TaskResult objects from orchestration
            context: Optional context with GitHub metadata:
                - issue_number: GitHub issue number to update
                - pr_number: GitHub pull request number to update
                - issue_numbers: List of issue numbers for batch updates
                - pr_numbers: List of PR numbers for batch updates

        Returns:
            Dictionary with automation execution summary:
                - comments_posted: Number of comments successfully posted
                - labels_updated: Number of labels successfully updated
                - prs_merged: Number of PRs successfully merged
                - errors: List of errors encountered (non-fatal)

        Example:
            >>> results = [TaskResult(...), TaskResult(...)]
            >>> context = {"issue_number": 123, "pr_number": 456}
            >>> summary = await handler.execute_automation(results, context)
            >>> print(f"Posted {summary['comments_posted']} comments")
        """
        if not results:
            logger.warning("execute_automation_called_with_empty_results")
            return {
                "comments_posted": 0,
                "labels_updated": 0,
                "prs_merged": 0,
                "errors": [],
            }

        context = context or {}
        summary = {
            "comments_posted": 0,
            "labels_updated": 0,
            "prs_merged": 0,
            "errors": [],
        }

        logger.info(
            "automation_execution_started",
            total_results=len(results),
            context=context,
        )

        # Post results as comments
        if self._should_run_automation("post_results_as_comment"):
            await self._post_results(results, context, summary)

        # Update issue/PR labels
        if self._should_run_automation("update_issue_status"):
            await self._update_labels(results, context, summary)

        # Auto-merge successful PRs
        if self._should_run_automation("auto_merge_on_success"):
            await self._auto_merge_prs(results, context, summary)

        logger.info(
            "automation_execution_completed",
            comments_posted=summary["comments_posted"],
            labels_updated=summary["labels_updated"],
            prs_merged=summary["prs_merged"],
            error_count=len(summary["errors"]),
        )

        return summary

    def _should_run_automation(self, feature_name: str) -> bool:
        """Check if a specific automation feature is enabled.

        Args:
            feature_name: Name of the configuration attribute to check

        Returns:
            True if the feature is enabled in configuration

        Example:
            >>> handler._should_run_automation("post_results_as_comment")
            True
        """
        enabled = getattr(self.config, feature_name, False)

        if not enabled:
            logger.debug(
                "automation_feature_disabled",
                feature=feature_name,
            )

        return enabled

    def _format_results_comment(self, results: Sequence[TaskResult]) -> str:
        """Format task results into a markdown comment.

        Creates a well-formatted markdown comment with:
        - Summary statistics (total, success, failed)
        - Execution time information
        - Detailed per-task results with status indicators
        - Error messages for failed tasks

        Args:
            results: List of TaskResult objects to format

        Returns:
            Formatted markdown string ready for GitHub comment

        Example:
            >>> results = [TaskResult(...), TaskResult(...)]
            >>> comment = handler._format_results_comment(results)
            >>> print(comment)
            ## 🤖 Orchestration Results
            ...
        """
        # Calculate summary statistics
        total_tasks = len(results)
        successful = sum(1 for r in results if r.status == TaskStatus.COMPLETED)
        failed = sum(1 for r in results if r.status == TaskStatus.FAILED)
        total_duration = sum(r.duration_seconds for r in results if r.duration_seconds)

        # Determine overall status emoji
        if failed == 0:
            overall_emoji = "✅"
            overall_status = "All tasks completed successfully"
        elif successful == 0:
            overall_emoji = "❌"
            overall_status = "All tasks failed"
        else:
            overall_emoji = "⚠️"
            overall_status = "Partial success"

        # Build comment header
        comment_lines = [
            "## 🤖 Orchestration Results",
            "",
            f"{overall_emoji} **{overall_status}**",
            "",
            "### 📊 Summary",
            "",
            f"- **Total Tasks:** {total_tasks}",
            f"- **Successful:** {successful} ✅",
            f"- **Failed:** {failed} ❌",
            f"- **Total Duration:** {total_duration:.2f}s ⏱️",
            "",
        ]

        # Add detailed results if there are any
        if results:
            comment_lines.extend([
                "### 📝 Detailed Results",
                "",
                "| Task ID | Status | Duration | Details |",
                "|---------|--------|----------|---------|",
            ])

            for result in results:
                status_emoji = STATUS_EMOJI.get(result.status, "❓")
                status_text = result.status.value if hasattr(result.status, "value") else str(result.status)
                duration_text = f"{result.duration_seconds:.2f}s" if result.duration_seconds else "N/A"

                # Create details column
                if result.status == TaskStatus.FAILED and result.error:
                    # Truncate long error messages
                    error_msg = result.error[:100] + "..." if len(result.error) > 100 else result.error
                    details = f"`{error_msg}`"
                elif result.status == TaskStatus.COMPLETED and result.result:
                    details = "Completed successfully"
                else:
                    details = "-"

                comment_lines.append(
                    f"| `{result.task_id}` | {status_emoji} {status_text} | {duration_text} | {details} |",
                )

        # Add footer with timestamp
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        comment_lines.extend([
            "",
            "---",
            f"*Generated by Parallel Codegen Orchestrator at {timestamp}*",
        ])

        return "\n".join(comment_lines)

    async def _post_results(
        self,
        results: Sequence[TaskResult],
        context: dict[str, Any],
        summary: dict[str, Any],
    ) -> None:
        """Post formatted results as comments to GitHub issues/PRs.

        Args:
            results: List of TaskResult objects
            context: Context with issue_number and/or pr_number
            summary: Summary dictionary to update with results
        """
        comment_text = self._format_results_comment(results)

        # Post to issue if issue_number provided
        if "issue_number" in context:
            try:
                issue_number = context["issue_number"]
                logger.info(
                    "posting_comment_to_issue",
                    issue_number=issue_number,
                    repo_name=self.repo_name,
                )

                self.github.post_comment(
                    repo_name=self.repo_name,
                    issue_number=issue_number,
                    comment=comment_text,
                )

                summary["comments_posted"] += 1
                logger.info(
                    "comment_posted_to_issue_success",
                    issue_number=issue_number,
                )

            except GithubException as e:
                error_msg = f"Failed to post comment to issue #{issue_number}: {e}"
                logger.error(
                    "comment_posting_failed",
                    issue_number=issue_number,
                    error=str(e),
                    status_code=e.status,
                )
                summary["errors"].append(error_msg)

            except Exception as e:
                error_msg = f"Unexpected error posting to issue #{issue_number}: {e}"
                logger.exception(
                    "comment_posting_unexpected_error",
                    issue_number=issue_number,
                    error=str(e),
                )
                summary["errors"].append(error_msg)

        # Post to PR if pr_number provided
        if "pr_number" in context:
            try:
                pr_number = context["pr_number"]
                logger.info(
                    "posting_comment_to_pr",
                    pr_number=pr_number,
                    repo_name=self.repo_name,
                )

                self.github.post_comment(
                    repo_name=self.repo_name,
                    issue_number=pr_number,  # PRs use issue comment API
                    comment=comment_text,
                )

                summary["comments_posted"] += 1
                logger.info(
                    "comment_posted_to_pr_success",
                    pr_number=pr_number,
                )

            except GithubException as e:
                error_msg = f"Failed to post comment to PR #{pr_number}: {e}"
                logger.error(
                    "comment_posting_failed",
                    pr_number=pr_number,
                    error=str(e),
                    status_code=e.status,
                )
                summary["errors"].append(error_msg)

            except Exception as e:
                error_msg = f"Unexpected error posting to PR #{pr_number}: {e}"
                logger.exception(
                    "comment_posting_unexpected_error",
                    pr_number=pr_number,
                    error=str(e),
                )
                summary["errors"].append(error_msg)

        # Batch posting to multiple issues
        if "issue_numbers" in context:
            for issue_number in context["issue_numbers"]:
                try:
                    self.github.post_comment(
                        repo_name=self.repo_name,
                        issue_number=issue_number,
                        comment=comment_text,
                    )
                    summary["comments_posted"] += 1

                except Exception as e:
                    error_msg = f"Failed to post to issue #{issue_number}: {e}"
                    logger.error("batch_comment_posting_failed", issue_number=issue_number, error=str(e))
                    summary["errors"].append(error_msg)

    def _determine_status_label(self, results: Sequence[TaskResult]) -> str:
        """Determine the appropriate status label based on task results.

        Args:
            results: List of TaskResult objects

        Returns:
            Status label name (without prefix)

        Example:
            >>> results = [TaskResult(status=TaskStatus.COMPLETED), ...]
            >>> label = handler._determine_status_label(results)
            >>> print(label)  # "completed"
        """
        if not results:
            return DEFAULT_STATUS_LABELS["in_progress"]

        total = len(results)
        successful = sum(1 for r in results if r.status == TaskStatus.COMPLETED)
        failed = sum(1 for r in results if r.status == TaskStatus.FAILED)

        if successful == total:
            return DEFAULT_STATUS_LABELS["all_success"]
        if failed == total:
            return DEFAULT_STATUS_LABELS["all_failed"]
        return DEFAULT_STATUS_LABELS["partial"]

    async def _update_labels(
        self,
        results: Sequence[TaskResult],
        context: dict[str, Any],
        summary: dict[str, Any],
    ) -> None:
        """Update issue labels based on task execution outcomes.

        Args:
            results: List of TaskResult objects
            context: Context with issue_number
            summary: Summary dictionary to update with results
        """
        if "issue_number" not in context:
            logger.debug("no_issue_number_in_context_skipping_label_update")
            return

        issue_number = context["issue_number"]
        status_label_name = self._determine_status_label(results)
        full_label = f"{self.config.status_label_prefix}{status_label_name}"

        try:
            logger.info(
                "updating_issue_labels",
                issue_number=issue_number,
                new_label=full_label,
                repo_name=self.repo_name,
            )

            # Get current labels
            repo = self.github._get_repository(self.repo_name)
            issue = repo.get_issue(issue_number)
            current_labels = [label.name for label in issue.labels]

            # Remove old status labels with same prefix
            new_labels = [
                label for label in current_labels
                if not label.startswith(self.config.status_label_prefix)
            ]

            # Add new status label
            new_labels.append(full_label)

            # Update labels
            self.github.update_issue_status(
                repo_name=self.repo_name,
                issue_number=issue_number,
                labels=new_labels,
            )

            summary["labels_updated"] += 1
            logger.info(
                "issue_labels_updated_success",
                issue_number=issue_number,
                new_label=full_label,
                removed_labels=[l for l in current_labels if l.startswith(self.config.status_label_prefix)],
            )

        except GithubException as e:
            error_msg = f"Failed to update labels for issue #{issue_number}: {e}"
            logger.error(
                "label_update_failed",
                issue_number=issue_number,
                error=str(e),
                status_code=e.status,
            )
            summary["errors"].append(error_msg)

        except Exception as e:
            error_msg = f"Unexpected error updating labels for issue #{issue_number}: {e}"
            logger.exception(
                "label_update_unexpected_error",
                issue_number=issue_number,
                error=str(e),
            )
            summary["errors"].append(error_msg)

    def _check_merge_eligibility(
        self,
        pr: PullRequest.PullRequest,
        results: Sequence[TaskResult],
    ) -> tuple[bool, str]:
        """Check if a PR is eligible for auto-merge.

        Args:
            pr: GitHub PullRequest object
            results: List of TaskResult objects

        Returns:
            Tuple of (eligible: bool, reason: str)

        Example:
            >>> pr = repo.get_pull(123)
            >>> results = [TaskResult(...)]
            >>> eligible, reason = handler._check_merge_eligibility(pr, results)
            >>> if not eligible:
            ...     print(f"Cannot merge: {reason}")
        """
        # Check all tasks succeeded
        failed_tasks = [r for r in results if r.status != TaskStatus.COMPLETED]
        if failed_tasks:
            return False, f"{len(failed_tasks)} task(s) failed"

        # Check PR is open
        if pr.state != "open":
            return False, f"PR is {pr.state}, not open"

        # Check PR is mergeable
        if not pr.mergeable:
            return False, "PR has merge conflicts"

        # Check PR is not merged already
        if pr.merged:
            return False, "PR is already merged"

        # All checks passed
        return True, "All checks passed"

    async def _auto_merge_prs(
        self,
        results: Sequence[TaskResult],
        context: dict[str, Any],
        summary: dict[str, Any],
    ) -> None:
        """Automatically merge pull requests if eligible.

        Args:
            results: List of TaskResult objects
            context: Context with pr_number
            summary: Summary dictionary to update with results
        """
        if "pr_number" not in context:
            logger.debug("no_pr_number_in_context_skipping_auto_merge")
            return

        pr_number = context["pr_number"]

        try:
            logger.info(
                "checking_pr_merge_eligibility",
                pr_number=pr_number,
                repo_name=self.repo_name,
            )

            # Get PR object
            repo = self.github._get_repository(self.repo_name)
            pr = repo.get_pull(pr_number)

            # Check eligibility
            eligible, reason = self._check_merge_eligibility(pr, results)

            if not eligible:
                logger.info(
                    "pr_not_eligible_for_auto_merge",
                    pr_number=pr_number,
                    reason=reason,
                )
                return

            # Attempt merge
            logger.info(
                "attempting_pr_auto_merge",
                pr_number=pr_number,
                repo_name=self.repo_name,
            )

            merge_result = pr.merge(
                commit_message="Auto-merge: All orchestration tasks completed successfully",
                merge_method="squash",  # Use squash merge by default
            )

            if merge_result.merged:
                summary["prs_merged"] += 1
                logger.info(
                    "pr_auto_merged_success",
                    pr_number=pr_number,
                    sha=merge_result.sha,
                )
            else:
                error_msg = f"PR #{pr_number} merge returned False: {merge_result.message}"
                logger.warning(
                    "pr_merge_returned_false",
                    pr_number=pr_number,
                    message=merge_result.message,
                )
                summary["errors"].append(error_msg)

        except GithubException as e:
            error_msg = f"Failed to auto-merge PR #{pr_number}: {e}"
            logger.error(
                "pr_auto_merge_failed",
                pr_number=pr_number,
                error=str(e),
                status_code=e.status,
            )
            summary["errors"].append(error_msg)

        except Exception as e:
            error_msg = f"Unexpected error during PR auto-merge #{pr_number}: {e}"
            logger.exception(
                "pr_auto_merge_unexpected_error",
                pr_number=pr_number,
                error=str(e),
            )
            summary["errors"].append(error_msg)
