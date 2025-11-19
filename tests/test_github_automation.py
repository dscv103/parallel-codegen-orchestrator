"""Unit tests for GitHub Automation Handler.

Tests cover result formatting, comment posting, label management,
auto-merge functionality, and error handling.
"""

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from github import GithubException
from src.agents.codegen_executor import TaskResult, TaskStatus
from src.automation.github_automation import (
    AutomationConfig,
    GitHubAutomationHandler,
)
from src.github.rest_api import GitHubIntegration


@pytest.fixture
def automation_config():
    """Create a test automation configuration."""
    return AutomationConfig(
        auto_merge_on_success=False,
        post_results_as_comment=True,
        update_issue_status=True,
        status_label_prefix="status:",
    )


@pytest.fixture
def mock_github_integration():
    """Create a mock GitHub integration instance."""
    github = Mock(spec=GitHubIntegration)
    github.post_comment = Mock()
    github.update_issue_status = Mock()
    github._get_repository = Mock()
    return github


@pytest.fixture
def automation_handler(automation_config, mock_github_integration):
    """Create a GitHubAutomationHandler instance with mocked dependencies."""
    return GitHubAutomationHandler(
        config=automation_config,
        github_integration=mock_github_integration,
        repo_name="test-org/test-repo",
    )


@pytest.fixture
def sample_task_results():
    """Create sample task results for testing."""
    return [
        TaskResult(
            task_id="task-1",
            status=TaskStatus.COMPLETED,
            start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
            end_time=datetime(2024, 1, 1, 10, 1, 30, tzinfo=UTC),
            duration_seconds=90.0,
            result={"output": "success"},
            error=None,
        ),
        TaskResult(
            task_id="task-2",
            status=TaskStatus.COMPLETED,
            start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
            end_time=datetime(2024, 1, 1, 10, 2, 0, tzinfo=UTC),
            duration_seconds=120.0,
            result={"output": "success"},
            error=None,
        ),
    ]


@pytest.fixture
def failed_task_results():
    """Create sample task results with failures."""
    return [
        TaskResult(
            task_id="task-1",
            status=TaskStatus.COMPLETED,
            start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
            end_time=datetime(2024, 1, 1, 10, 1, 0, tzinfo=UTC),
            duration_seconds=60.0,
            result={"output": "success"},
            error=None,
        ),
        TaskResult(
            task_id="task-2",
            status=TaskStatus.FAILED,
            start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
            end_time=datetime(2024, 1, 1, 10, 0, 30, tzinfo=UTC),
            duration_seconds=30.0,
            result=None,
            error="Connection timeout",
        ),
    ]


class TestAutomationHandlerInit:
    """Tests for GitHubAutomationHandler initialization."""

    def test_init_stores_config_and_dependencies(
        self,
        automation_config,
        mock_github_integration,
    ):
        """Test that handler stores configuration and dependencies."""
        handler = GitHubAutomationHandler(
            config=automation_config,
            github_integration=mock_github_integration,
            repo_name="test-org/test-repo",
        )

        assert handler.config == automation_config
        assert handler.github == mock_github_integration
        assert handler.repo_name == "test-org/test-repo"


class TestFormatResultsComment:
    """Tests for result comment formatting."""

    def test_format_results_comment_all_successful(
        self,
        automation_handler,
        sample_task_results,
    ):
        """Test comment formatting with all successful tasks."""
        comment = automation_handler._format_results_comment(sample_task_results)

        # Check header and summary
        assert "## 🤖 Orchestration Results" in comment
        assert "✅" in comment
        assert "All tasks completed successfully" in comment

        # Check statistics
        assert "**Total Tasks:** 2" in comment
        assert "**Successful:** 2 ✅" in comment
        assert "**Failed:** 0 ❌" in comment
        assert "**Total Duration:** 210.00s ⏱️" in comment

        # Check task details
        assert "`task-1`" in comment
        assert "`task-2`" in comment
        assert "Completed successfully" in comment

    def test_format_results_comment_with_failures(
        self,
        automation_handler,
        failed_task_results,
    ):
        """Test comment formatting with failed tasks."""
        comment = automation_handler._format_results_comment(failed_task_results)

        # Check mixed status indicator
        assert "⚠️" in comment
        assert "Partial success" in comment

        # Check statistics
        assert "**Total Tasks:** 2" in comment
        assert "**Successful:** 1 ✅" in comment
        assert "**Failed:** 1 ❌" in comment

        # Check error message included
        assert "Connection timeout" in comment
        assert "❌" in comment  # Failed status emoji

    def test_format_results_comment_all_failed(self, automation_handler):
        """Test comment formatting when all tasks fail."""
        all_failed = [
            TaskResult(
                task_id="task-1",
                status=TaskStatus.FAILED,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                duration_seconds=10.0,

                result=None,
                error="Error 1",
            ),
            TaskResult(
                task_id="task-2",
                status=TaskStatus.FAILED,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                duration_seconds=15.0,

                result=None,
                error="Error 2",
            ),
        ]

        comment = automation_handler._format_results_comment(all_failed)

        assert "❌" in comment
        assert "All tasks failed" in comment
        assert "**Successful:** 0 ✅" in comment
        assert "**Failed:** 2 ❌" in comment

    def test_format_results_comment_truncates_long_errors(
        self,
        automation_handler,
    ):
        """Test that long error messages are truncated in comments."""
        long_error = "A" * 200  # 200 character error

        results = [
            TaskResult(
                task_id="task-1",
                status=TaskStatus.FAILED,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                duration_seconds=10.0,

                result=None,
                error=long_error,
            ),
        ]

        comment = automation_handler._format_results_comment(results)

        # Check that error is truncated to 100 chars + "..."
        assert long_error not in comment
        assert "A" * 100 + "..." in comment

    def test_format_results_comment_includes_timestamp(
        self,
        automation_handler,
        sample_task_results,
    ):
        """Test that comment includes generation timestamp."""
        comment = automation_handler._format_results_comment(sample_task_results)

        assert "Generated by Parallel Codegen Orchestrator" in comment
        assert "UTC" in comment


class TestDetermineStatusLabel:
    """Tests for status label determination."""

    def test_determine_status_label_all_successful(
        self,
        automation_handler,
        sample_task_results,
    ):
        """Test label for all successful tasks."""
        label = automation_handler._determine_status_label(sample_task_results)
        assert label == "completed"

    def test_determine_status_label_all_failed(self, automation_handler):
        """Test label for all failed tasks."""
        all_failed = [
            TaskResult(
                task_id="task-1",
                status=TaskStatus.FAILED,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                duration_seconds=10.0,

                result=None,
                error="Error",
            ),
            TaskResult(
                task_id="task-2",
                status=TaskStatus.FAILED,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                duration_seconds=10.0,

                result=None,
                error="Error",
            ),
        ]

        label = automation_handler._determine_status_label(all_failed)
        assert label == "failed"

    def test_determine_status_label_partial(
        self,
        automation_handler,
        failed_task_results,
    ):
        """Test label for mixed success/failure."""
        label = automation_handler._determine_status_label(failed_task_results)
        assert label == "partial"

    def test_determine_status_label_empty_results(self, automation_handler):
        """Test label for empty results list."""
        label = automation_handler._determine_status_label([])
        assert label == "in-progress"


class TestShouldRunAutomation:
    """Tests for automation feature toggle checking."""

    def test_should_run_automation_enabled(self, automation_handler):
        """Test that enabled features return True."""
        assert automation_handler._should_run_automation("post_results_as_comment")
        assert automation_handler._should_run_automation("update_issue_status")

    def test_should_run_automation_disabled(self, automation_handler):
        """Test that disabled features return False."""
        assert not automation_handler._should_run_automation("auto_merge_on_success")

    def test_should_run_automation_unknown_feature(self, automation_handler):
        """Test that unknown features return False."""
        assert not automation_handler._should_run_automation("nonexistent_feature")


class TestPostResults:
    """Tests for result posting functionality."""

    @pytest.mark.asyncio
    async def test_post_results_to_issue(
        self,
        automation_handler,
        sample_task_results,
        mock_github_integration,
    ):
        """Test posting results to a GitHub issue."""
        context = {"issue_number": 123}
        summary = {"comments_posted": 0, "errors": []}

        await automation_handler._post_results(
            sample_task_results,
            context,
            summary,
        )

        # Verify comment was posted
        mock_github_integration.post_comment.assert_called_once()
        call_args = mock_github_integration.post_comment.call_args

        assert call_args[1]["repo_name"] == "test-org/test-repo"
        assert call_args[1]["issue_number"] == 123
        assert "Orchestration Results" in call_args[1]["comment"]

        # Verify summary updated
        assert summary["comments_posted"] == 1
        assert len(summary["errors"]) == 0

    @pytest.mark.asyncio
    async def test_post_results_to_pr(
        self,
        automation_handler,
        sample_task_results,
        mock_github_integration,
    ):
        """Test posting results to a pull request."""
        context = {"pr_number": 456}
        summary = {"comments_posted": 0, "errors": []}

        await automation_handler._post_results(
            sample_task_results,
            context,
            summary,
        )

        # Verify comment was posted (PRs use issue comment API)
        mock_github_integration.post_comment.assert_called_once()
        call_args = mock_github_integration.post_comment.call_args

        assert call_args[1]["issue_number"] == 456

        # Verify summary updated
        assert summary["comments_posted"] == 1

    @pytest.mark.asyncio
    async def test_post_results_to_both_issue_and_pr(
        self,
        automation_handler,
        sample_task_results,
        mock_github_integration,
    ):
        """Test posting results to both issue and PR."""
        context = {"issue_number": 123, "pr_number": 456}
        summary = {"comments_posted": 0, "errors": []}

        await automation_handler._post_results(
            sample_task_results,
            context,
            summary,
        )

        # Verify both comments were posted
        assert mock_github_integration.post_comment.call_count == 2
        assert summary["comments_posted"] == 2

    @pytest.mark.asyncio
    async def test_post_results_handles_github_exception(
        self,
        automation_handler,
        sample_task_results,
        mock_github_integration,
    ):
        """Test that GitHub API exceptions are handled gracefully."""
        context = {"issue_number": 123}
        summary = {"comments_posted": 0, "errors": []}

        # Simulate GitHub API error
        mock_github_integration.post_comment.side_effect = GithubException(
            status=403,
            data={"message": "Forbidden"},
        )

        # Should not raise exception
        await automation_handler._post_results(
            sample_task_results,
            context,
            summary,
        )

        # Verify error was logged
        assert summary["comments_posted"] == 0
        assert len(summary["errors"]) == 1
        assert "Failed to post comment" in summary["errors"][0]

    @pytest.mark.asyncio
    async def test_post_results_batch_to_multiple_issues(
        self,
        automation_handler,
        sample_task_results,
        mock_github_integration,
    ):
        """Test batch posting to multiple issues."""
        context = {"issue_numbers": [123, 456, 789]}
        summary = {"comments_posted": 0, "errors": []}

        await automation_handler._post_results(
            sample_task_results,
            context,
            summary,
        )

        # Verify all comments were posted
        assert mock_github_integration.post_comment.call_count == 3
        assert summary["comments_posted"] == 3


class TestUpdateLabels:
    """Tests for label update functionality."""

    @pytest.mark.asyncio
    async def test_update_labels_successful_tasks(
        self,
        automation_handler,
        sample_task_results,
        mock_github_integration,
    ):
        """Test updating labels for successful tasks."""
        context = {"issue_number": 123}
        summary = {"labels_updated": 0, "errors": []}

        # Mock repository and issue
        mock_repo = Mock()
        mock_issue = Mock()
        mock_label = Mock()
        mock_label.name = "bug"
        mock_issue.labels = [mock_label]

        mock_github_integration._get_repository.return_value = mock_repo
        mock_repo.get_issue.return_value = mock_issue

        await automation_handler._update_labels(
            sample_task_results,
            context,
            summary,
        )

        # Verify labels were updated
        mock_github_integration.update_issue_status.assert_called_once()
        call_args = mock_github_integration.update_issue_status.call_args

        assert call_args[1]["issue_number"] == 123
        assert "status:completed" in call_args[1]["labels"]
        assert "bug" in call_args[1]["labels"]

        # Verify summary updated
        assert summary["labels_updated"] == 1

    @pytest.mark.asyncio
    async def test_update_labels_removes_old_status_labels(
        self,
        automation_handler,
        sample_task_results,
        mock_github_integration,
    ):
        """Test that old status labels are removed."""
        context = {"issue_number": 123}
        summary = {"labels_updated": 0, "errors": []}

        # Mock issue with old status label
        mock_repo = Mock()
        mock_issue = Mock()

        old_status_label = Mock()
        old_status_label.name = "status:in-progress"
        bug_label = Mock()
        bug_label.name = "bug"

        mock_issue.labels = [old_status_label, bug_label]

        mock_github_integration._get_repository.return_value = mock_repo
        mock_repo.get_issue.return_value = mock_issue

        await automation_handler._update_labels(
            sample_task_results,
            context,
            summary,
        )

        # Verify new labels include only new status label
        call_args = mock_github_integration.update_issue_status.call_args
        new_labels = call_args[1]["labels"]

        assert "status:completed" in new_labels
        assert "bug" in new_labels
        assert "status:in-progress" not in new_labels
        assert len([l for l in new_labels if l.startswith("status:")]) == 1

    @pytest.mark.asyncio
    async def test_update_labels_no_issue_number_in_context(
        self,
        automation_handler,
        sample_task_results,
        mock_github_integration,
    ):
        """Test that labels are not updated when no issue number provided."""
        context = {}  # No issue_number
        summary = {"labels_updated": 0, "errors": []}

        await automation_handler._update_labels(
            sample_task_results,
            context,
            summary,
        )

        # Verify no update attempted
        mock_github_integration.update_issue_status.assert_not_called()
        assert summary["labels_updated"] == 0

    @pytest.mark.asyncio
    async def test_update_labels_handles_github_exception(
        self,
        automation_handler,
        sample_task_results,
        mock_github_integration,
    ):
        """Test that label update exceptions are handled gracefully."""
        context = {"issue_number": 123}
        summary = {"labels_updated": 0, "errors": []}

        # Mock repo that raises exception
        mock_github_integration._get_repository.side_effect = GithubException(
            status=404,
            data={"message": "Not Found"},
        )

        # Should not raise exception
        await automation_handler._update_labels(
            sample_task_results,
            context,
            summary,
        )

        # Verify error logged
        assert summary["labels_updated"] == 0
        assert len(summary["errors"]) == 1


class TestCheckMergeEligibility:
    """Tests for PR merge eligibility checking."""

    def test_check_merge_eligibility_all_conditions_met(
        self,
        automation_handler,
        sample_task_results,
    ):
        """Test eligibility when all conditions are met."""
        mock_pr = Mock()
        mock_pr.state = "open"
        mock_pr.mergeable = True
        mock_pr.merged = False

        eligible, reason = automation_handler._check_merge_eligibility(
            mock_pr,
            sample_task_results,
        )

        assert eligible is True
        assert reason == "All checks passed"

    def test_check_merge_eligibility_has_failed_tasks(
        self,
        automation_handler,
        failed_task_results,
    ):
        """Test eligibility when tasks have failures."""
        mock_pr = Mock()
        mock_pr.state = "open"
        mock_pr.mergeable = True
        mock_pr.merged = False

        eligible, reason = automation_handler._check_merge_eligibility(
            mock_pr,
            failed_task_results,
        )

        assert eligible is False
        assert "task(s) failed" in reason

    def test_check_merge_eligibility_pr_not_open(
        self,
        automation_handler,
        sample_task_results,
    ):
        """Test eligibility when PR is not open."""
        mock_pr = Mock()
        mock_pr.state = "closed"
        mock_pr.mergeable = True
        mock_pr.merged = False

        eligible, reason = automation_handler._check_merge_eligibility(
            mock_pr,
            sample_task_results,
        )

        assert eligible is False
        assert "PR is closed" in reason

    def test_check_merge_eligibility_pr_not_mergeable(
        self,
        automation_handler,
        sample_task_results,
    ):
        """Test eligibility when PR has merge conflicts."""
        mock_pr = Mock()
        mock_pr.state = "open"
        mock_pr.mergeable = False
        mock_pr.merged = False

        eligible, reason = automation_handler._check_merge_eligibility(
            mock_pr,
            sample_task_results,
        )

        assert eligible is False
        assert "merge conflicts" in reason

    def test_check_merge_eligibility_pr_already_merged(
        self,
        automation_handler,
        sample_task_results,
    ):
        """Test eligibility when PR is already merged."""
        mock_pr = Mock()
        mock_pr.state = "open"
        mock_pr.mergeable = True
        mock_pr.merged = True

        eligible, reason = automation_handler._check_merge_eligibility(
            mock_pr,
            sample_task_results,
        )

        assert eligible is False
        assert "already merged" in reason


class TestAutoMergePrs:
    """Tests for auto-merge functionality."""

    @pytest.mark.asyncio
    async def test_auto_merge_prs_successful(
        self,
        automation_handler,
        sample_task_results,
        mock_github_integration,
    ):
        """Test successful PR auto-merge."""
        context = {"pr_number": 456}
        summary = {"prs_merged": 0, "errors": []}

        # Mock eligible PR
        mock_repo = Mock()
        mock_pr = Mock()
        mock_pr.state = "open"
        mock_pr.mergeable = True
        mock_pr.merged = False

        mock_merge_result = Mock()
        mock_merge_result.merged = True
        mock_merge_result.sha = "abc123"
        mock_pr.merge.return_value = mock_merge_result

        mock_github_integration._get_repository.return_value = mock_repo
        mock_repo.get_pull.return_value = mock_pr

        await automation_handler._auto_merge_prs(
            sample_task_results,
            context,
            summary,
        )

        # Verify merge was attempted
        mock_pr.merge.assert_called_once()
        assert summary["prs_merged"] == 1
        assert len(summary["errors"]) == 0

    @pytest.mark.asyncio
    async def test_auto_merge_prs_not_eligible(
        self,
        automation_handler,
        failed_task_results,
        mock_github_integration,
    ):
        """Test that ineligible PRs are not merged."""
        context = {"pr_number": 456}
        summary = {"prs_merged": 0, "errors": []}

        # Mock PR with failures
        mock_repo = Mock()
        mock_pr = Mock()
        mock_pr.state = "open"
        mock_pr.mergeable = True
        mock_pr.merged = False

        mock_github_integration._get_repository.return_value = mock_repo
        mock_repo.get_pull.return_value = mock_pr

        await automation_handler._auto_merge_prs(
            failed_task_results,
            context,
            summary,
        )

        # Verify merge was not attempted
        mock_pr.merge.assert_not_called()
        assert summary["prs_merged"] == 0

    @pytest.mark.asyncio
    async def test_auto_merge_prs_no_pr_number(
        self,
        automation_handler,
        sample_task_results,
        mock_github_integration,
    ):
        """Test that merge is skipped when no PR number provided."""
        context = {}  # No pr_number
        summary = {"prs_merged": 0, "errors": []}

        await automation_handler._auto_merge_prs(
            sample_task_results,
            context,
            summary,
        )

        # Verify no merge attempted
        mock_github_integration._get_repository.assert_not_called()
        assert summary["prs_merged"] == 0

    @pytest.mark.asyncio
    async def test_auto_merge_prs_handles_exception(
        self,
        automation_handler,
        sample_task_results,
        mock_github_integration,
    ):
        """Test that merge exceptions are handled gracefully."""
        context = {"pr_number": 456}
        summary = {"prs_merged": 0, "errors": []}

        # Mock exception during merge
        mock_github_integration._get_repository.side_effect = GithubException(
            status=500,
            data={"message": "Internal Error"},
        )

        # Should not raise exception
        await automation_handler._auto_merge_prs(
            sample_task_results,
            context,
            summary,
        )

        # Verify error logged
        assert summary["prs_merged"] == 0
        assert len(summary["errors"]) == 1


class TestExecuteAutomation:
    """Tests for main automation execution."""

    @pytest.mark.asyncio
    async def test_execute_automation_all_features_enabled(
        self,
        sample_task_results,
        mock_github_integration,
    ):
        """Test execution with all features enabled."""
        config = AutomationConfig(
            auto_merge_on_success=True,
            post_results_as_comment=True,
            update_issue_status=True,
        )

        handler = GitHubAutomationHandler(
            config=config,
            github_integration=mock_github_integration,
            repo_name="test-org/test-repo",
        )

        # Mock all GitHub operations
        mock_repo = Mock()
        mock_issue = Mock()
        mock_issue.labels = []
        mock_pr = Mock()
        mock_pr.state = "open"
        mock_pr.mergeable = True
        mock_pr.merged = False
        mock_merge_result = Mock()
        mock_merge_result.merged = True
        mock_merge_result.sha = "abc123"
        mock_pr.merge.return_value = mock_merge_result

        mock_github_integration._get_repository.return_value = mock_repo
        mock_repo.get_issue.return_value = mock_issue
        mock_repo.get_pull.return_value = mock_pr

        context = {"issue_number": 123, "pr_number": 456}

        summary = await handler.execute_automation(sample_task_results, context)

        # Verify all features executed
        assert summary["comments_posted"] == 2  # Issue and PR
        assert summary["labels_updated"] == 1
        assert summary["prs_merged"] == 1
        assert len(summary["errors"]) == 0

    @pytest.mark.asyncio
    async def test_execute_automation_with_empty_results(
        self,
        automation_handler,
    ):
        """Test that empty results are handled gracefully."""
        summary = await automation_handler.execute_automation([], {})

        assert summary["comments_posted"] == 0
        assert summary["labels_updated"] == 0
        assert summary["prs_merged"] == 0
        assert len(summary["errors"]) == 0

    @pytest.mark.asyncio
    async def test_execute_automation_respects_feature_toggles(
        self,
        mock_github_integration,
        sample_task_results,
    ):
        """Test that feature toggles are respected."""
        config = AutomationConfig(
            auto_merge_on_success=False,
            post_results_as_comment=False,
            update_issue_status=False,
        )

        handler = GitHubAutomationHandler(
            config=config,
            github_integration=mock_github_integration,
            repo_name="test-org/test-repo",
        )

        context = {"issue_number": 123, "pr_number": 456}

        summary = await handler.execute_automation(sample_task_results, context)

        # Verify no features executed
        assert summary["comments_posted"] == 0
        assert summary["labels_updated"] == 0
        assert summary["prs_merged"] == 0
        mock_github_integration.post_comment.assert_not_called()
        mock_github_integration.update_issue_status.assert_not_called()
