"""
Unit tests for GitHub REST API Integration
Tests follow TDD principles - written before implementation
"""

from unittest.mock import Mock, patch

import pytest
from github.Issue import Issue
from github.PullRequest import PullRequest
from github.Repository import Repository

from github import Github, GithubException, RateLimitExceededException
from src.github.rest_api import GitHubIntegration


class TestGitHubIntegration:
    """Test suite for GitHubIntegration class"""

    @pytest.fixture
    def mock_github(self):
        """Create a mocked Github instance"""
        return Mock(spec=Github)

    @pytest.fixture
    def github_integration(self, mock_github):
        """Create GitHubIntegration instance with mocked Github"""
        with patch("src.github.rest_api.Github", return_value=mock_github):
            return GitHubIntegration(token="test_token", org_id="test_org")

    def test_initialization(self, github_integration):
        """Test GitHubIntegration initialization"""
        assert github_integration is not None
        assert github_integration.org_id == "test_org"

    def test_fetch_issues_open(self, github_integration, mock_github):
        """Test fetching open issues"""
        # Setup mock
        mock_repo = Mock(spec=Repository)
        mock_issue1 = Mock(spec=Issue)
        mock_issue1.number = 1
        mock_issue1.title = "Test Issue 1"
        mock_issue1.state = "open"
        mock_issue1.pull_request = None  # Not a PR

        mock_issue2 = Mock(spec=Issue)
        mock_issue2.number = 2
        mock_issue2.title = "Test Issue 2"
        mock_issue2.state = "open"
        mock_issue2.pull_request = None  # Not a PR

        mock_repo.get_issues.return_value = [mock_issue1, mock_issue2]
        mock_github.get_repo.return_value = mock_repo

        # Execute
        issues = github_integration.fetch_issues("test_org/test_repo", state="open")

        # Assert
        assert len(list(issues)) == 2
        mock_github.get_repo.assert_called_once_with("test_org/test_repo")
        mock_repo.get_issues.assert_called_once()

    def test_fetch_issues_closed(self, github_integration, mock_github):
        """Test fetching closed issues"""
        mock_repo = Mock(spec=Repository)
        mock_issue = Mock(spec=Issue)
        mock_issue.number = 3
        mock_issue.title = "Closed Issue"
        mock_issue.state = "closed"
        mock_issue.pull_request = None  # Not a PR

        mock_repo.get_issues.return_value = [mock_issue]
        mock_github.get_repo.return_value = mock_repo

        # Execute
        issues = github_integration.fetch_issues("test_org/test_repo", state="closed")

        # Assert
        issues_list = list(issues)
        assert len(issues_list) == 1
        assert issues_list[0].state == "closed"

    def test_fetch_issues_pagination(self, github_integration, mock_github):
        """Test issue fetching handles pagination"""
        mock_repo = Mock(spec=Repository)
        # Create 25 mock issues to simulate pagination
        mock_issues = [Mock(spec=Issue, number=i, title=f"Issue {i}", pull_request=None) for i in range(25)]
        mock_repo.get_issues.return_value = mock_issues
        mock_github.get_repo.return_value = mock_repo

        # Execute
        issues = list(github_integration.fetch_issues("test_org/test_repo"))

        # Assert
        assert len(issues) == 25

    def test_fetch_pull_requests(self, github_integration, mock_github):
        """Test fetching pull requests with metadata"""
        mock_repo = Mock(spec=Repository)
        mock_pr = Mock(spec=PullRequest)
        mock_pr.number = 100
        mock_pr.title = "Test PR"
        mock_pr.state = "open"
        mock_pr.head.ref = "feature-branch"
        mock_pr.base.ref = "main"

        mock_repo.get_pulls.return_value = [mock_pr]
        mock_github.get_repo.return_value = mock_repo

        # Execute
        prs = github_integration.fetch_pull_requests("test_org/test_repo", state="open")

        # Assert
        prs_list = list(prs)
        assert len(prs_list) == 1
        assert prs_list[0].number == 100
        assert prs_list[0].head.ref == "feature-branch"

    def test_update_issue_status(self, github_integration, mock_github):
        """Test updating issue status and labels"""
        mock_repo = Mock(spec=Repository)
        mock_issue = Mock(spec=Issue)
        mock_repo.get_issue.return_value = mock_issue
        mock_github.get_repo.return_value = mock_repo

        # Execute
        github_integration.update_issue_status(
            "test_org/test_repo",
            issue_number=1,
            state="closed",
            labels=["bug", "fixed"],
        )

        # Assert
        mock_issue.edit.assert_called_once_with(state="closed", labels=["bug", "fixed"])

    def test_create_branch(self, github_integration, mock_github):
        """Test creating a new branch"""
        mock_repo = Mock(spec=Repository)
        mock_ref = Mock()
        mock_ref.ref = "refs/heads/main"
        mock_ref.object.sha = "abc123"

        mock_repo.get_git_ref.return_value = mock_ref
        mock_github.get_repo.return_value = mock_repo

        # Execute
        result = github_integration.create_branch(
            "test_org/test_repo",
            branch_name="feature/new-feature",
            from_branch="main",
        )

        # Assert
        assert result is True
        mock_repo.create_git_ref.assert_called_once_with(
            ref="refs/heads/feature/new-feature",
            sha="abc123",
        )

    def test_post_comment(self, github_integration, mock_github):
        """Test posting a comment to an issue"""
        mock_repo = Mock(spec=Repository)
        mock_issue = Mock(spec=Issue)
        mock_repo.get_issue.return_value = mock_issue
        mock_github.get_repo.return_value = mock_repo

        # Execute
        github_integration.post_comment(
            "test_org/test_repo",
            issue_number=1,
            comment="Test comment",
        )

        # Assert
        mock_issue.create_comment.assert_called_once_with("Test comment")

    def test_rate_limit_handling(self, github_integration, mock_github):
        """Test rate limit checking"""
        # Setup mock rate limiting
        mock_rate_limit = Mock()
        mock_rate_limit.core.remaining = 100
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.reset.timestamp.return_value = 1234567890
        mock_github.get_rate_limit.return_value = mock_rate_limit

        # Execute
        rate_info = github_integration.get_rate_limit()

        # Assert
        assert rate_info["remaining"] == 100
        assert rate_info["limit"] == 5000
        assert rate_info["reset"] == 1234567890

    def test_error_handling_invalid_repo(self, github_integration, mock_github):
        """Test error handling for invalid repository"""
        # Must happen after initialization, so we need to set it on github_integration.github
        github_integration.github.get_repo.side_effect = GithubException(404, {"message": "Not Found"})

        # Execute and Assert
        with pytest.raises(GithubException):
            list(github_integration.fetch_issues("invalid/repo"))

    def test_error_handling_rate_limit_exceeded(self, github_integration, mock_github):
        """Test handling when rate limit is exceeded"""
        mock_repo = Mock(spec=Repository)
        mock_repo.get_issues.side_effect = RateLimitExceededException(
            403,
            {"message": "Rate limit exceeded"},
        )
        github_integration.github.get_repo.return_value = mock_repo

        # Mock rate limit for _handle_rate_limit call
        mock_rate_limit = Mock()
        mock_rate_limit.core.remaining = 0
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.reset.timestamp.return_value = 1234567890
        github_integration.github.get_rate_limit.return_value = mock_rate_limit

        # Execute and Assert
        with pytest.raises(RateLimitExceededException):
            list(github_integration.fetch_issues("test_org/test_repo"))

    def test_fetch_issues_with_labels_filter(self, github_integration, mock_github):
        """Test fetching issues with label filtering"""
        mock_repo = Mock(spec=Repository)
        mock_issue = Mock(spec=Issue)
        mock_issue.number = 1
        mock_issue.labels = [Mock(name="bug")]
        mock_issue.pull_request = None  # Not a PR

        mock_repo.get_issues.return_value = [mock_issue]
        github_integration.github.get_repo.return_value = mock_repo

        # Execute
        issues = github_integration.fetch_issues(
            "test_org/test_repo",
            state="open",
            labels=["bug"],
        )

        # Assert
        assert len(list(issues)) == 1
