"""GitHub REST API Integration using PyGithub.

Provides methods for repository, issue, and PR management.
"""

import time
from collections.abc import Iterator

from github import Github, GithubException, RateLimitExceededException
from github.Issue import Issue
from github.PullRequest import PullRequest
from github.Repository import Repository

from src.log_config import get_logger

# Initialize logger
logger = get_logger(__name__)

# Constants
BRANCH_EXISTS_STATUS_CODE = 422
RATE_LIMIT_THRESHOLD = 100


class GitHubIntegration:
    """GitHub REST API integration class using PyGithub.

    Handles authentication, issue/PR fetching, branch creation,
    and automated posting of results with rate limit management.
    """

    def __init__(self, token: str, org_id: str):
        """Initialize GitHub integration with authentication.

        Args:
            token: GitHub personal access token or OAuth token
            org_id: GitHub organization ID
        """
        self.github = Github(token)
        self.org_id = org_id
        logger.info("github_integration_initializing", org_id=org_id)
        self._verify_authentication()
        logger.info("github_integration_initialized", org_id=org_id)

    def _verify_authentication(self) -> None:
        """Verify GitHub token is valid."""
        try:
            # Verify token by fetching user (but don't log PII)
            _ = self.github.get_user().login
            logger.info("github_authentication_verified")
        except GithubException as e:
            logger.exception("github_authentication_failed", error=str(e))
            msg = f"Invalid GitHub token: {e}"
            raise ValueError(msg) from e

    def _get_repository(self, repo_name: str) -> Repository:
        """Get repository object with error handling.

        Args:
            repo_name: Repository name in format 'owner/repo'

        Returns:
            Repository object

        Raises:
            GithubException: If repository not found or access denied
        """
        try:
            return self.github.get_repo(repo_name)
        except GithubException as e:
            raise GithubException(
                e.status,
                f"Failed to access repository '{repo_name}': {e.data}",
            ) from e

    def get_repository(self, repo_name: str) -> Repository:
        """Get repository object with error handling.

        Args:
            repo_name: Repository name in format 'owner/repo'

        Returns:
            Repository object

        Raises:
            GithubException: If repository not found or access denied
        """
        return self._get_repository(repo_name)

    def fetch_issues(
        self,
        repo_name: str,
        state: str = "open",
        labels: list[str] | None = None,
        max_retries: int = 3,
    ) -> Iterator[Issue]:
        """Fetch issues from repository with filtering and pagination support.

        Args:
            repo_name: Repository name in format 'owner/repo'
            state: Issue state filter ('open', 'closed', 'all')
            labels: Optional list of label names to filter by
            max_retries: Maximum number of retry attempts for rate limit errors

        Returns:
            Iterator of Issue objects

        Raises:
            GithubException: If repository access fails
            RateLimitExceededException: If rate limit exceeded after retries
        """
        repo = self._get_repository(repo_name)

        # Prepare parameters
        kwargs = {"state": state}
        if labels:
            kwargs["labels"] = labels

        # Retry loop with exponential backoff
        for attempt in range(max_retries):
            try:
                issues = repo.get_issues(**kwargs)
                # Filter out pull requests (GitHub API returns PRs as issues)
                for issue in issues:
                    if not issue.pull_request:
                        yield issue
            except RateLimitExceededException:
                if attempt < max_retries - 1:
                    # Wait for rate limit reset before retrying
                    self._handle_rate_limit()
                    # Optional exponential backoff (additional wait)
                    time.sleep(2**attempt)
                else:
                    # Exhausted retries, raise the exception
                    raise
            else:
                return  # Success, exit retry loop

    def fetch_pull_requests(
        self,
        repo_name: str,
        state: str = "open",
        max_retries: int = 3,
    ) -> Iterator[PullRequest]:
        """Fetch pull requests with metadata from repository.

        Args:
            repo_name: Repository name in format 'owner/repo'
            state: PR state filter ('open', 'closed', 'all')
            max_retries: Maximum number of retry attempts for rate limit errors

        Returns:
            Iterator of PullRequest objects with full metadata

        Raises:
            GithubException: If repository access fails
            RateLimitExceededException: If rate limit exceeded after retries
        """
        repo = self._get_repository(repo_name)

        # Retry loop with exponential backoff
        for attempt in range(max_retries):
            try:
                pulls = repo.get_pulls(state=state)
                yield from pulls
            except RateLimitExceededException:
                if attempt < max_retries - 1:
                    # Wait for rate limit reset before retrying
                    self._handle_rate_limit()
                    # Optional exponential backoff (additional wait)
                    time.sleep(2**attempt)
                else:
                    # Exhausted retries, raise the exception
                    raise
            else:
                return  # Success, exit retry loop

    def update_issue_status(
        self,
        repo_name: str,
        issue_number: int,
        state: str | None = None,
        labels: list[str] | None = None,
    ) -> None:
        """Update issue status and labels.

        Args:
            repo_name: Repository name in format 'owner/repo'
            issue_number: Issue number to update
            state: New state ('open' or 'closed'), optional
            labels: New list of labels, optional

        Raises:
            GithubException: If update fails
        """
        repo = self._get_repository(repo_name)
        issue = repo.get_issue(issue_number)

        # Build update parameters
        update_params = {}
        if state:
            update_params["state"] = state
        if labels is not None:
            update_params["labels"] = labels

        if update_params:
            issue.edit(**update_params)

    def create_branch(
        self,
        repo_name: str,
        branch_name: str,
        from_branch: str = "main",
    ) -> bool:
        """Create a new branch from an existing branch.

        Args:
            repo_name: Repository name in format 'owner/repo'
            branch_name: Name for the new branch
            from_branch: Source branch name (default: 'main')

        Returns:
            True if branch created successfully

        Raises:
            GithubException: If branch creation fails
        """
        repo = self._get_repository(repo_name)

        try:
            # Get the SHA of the source branch
            source_ref = repo.get_git_ref(f"heads/{from_branch}")
            source_sha = source_ref.object.sha

            # Create new branch reference
            repo.create_git_ref(
                ref=f"refs/heads/{branch_name}",
                sha=source_sha,
            )
        except GithubException as e:
            if e.status == BRANCH_EXISTS_STATUS_CODE:
                raise GithubException(
                    e.status,
                    f"Branch '{branch_name}' already exists or invalid",
                ) from e
            raise
        else:
            return True

    def post_comment(
        self,
        repo_name: str,
        issue_number: int,
        comment: str,
    ) -> None:
        """Post a comment to an issue or pull request.

        Args:
            repo_name: Repository name in format 'owner/repo'
            issue_number: Issue or PR number to comment on
            comment: Comment text (supports Markdown)

        Raises:
            GithubException: If comment posting fails
        """
        repo = self._get_repository(repo_name)
        issue = repo.get_issue(issue_number)
        issue.create_comment(comment)

    def get_rate_limit(self) -> dict:
        """Get current rate limit information.

        Returns:
            Dictionary with rate limit info:
                - limit: Total rate limit
                - remaining: Remaining requests
                - reset: Unix timestamp when limit resets
        """
        rate_limit = self.github.get_rate_limit()
        return {
            "limit": rate_limit.core.limit,
            "remaining": rate_limit.core.remaining,
            "reset": int(rate_limit.core.reset.timestamp()),
        }

    def _handle_rate_limit(self) -> None:
        """Handle rate limit by checking status and waiting if necessary.

        Logs warning when approaching limit.
        """
        rate_info = self.get_rate_limit()

        if rate_info["remaining"] < RATE_LIMIT_THRESHOLD:
            reset_time = rate_info["reset"]
            wait_time = max(0, reset_time - int(time.time()))

            if wait_time > 0:
                time.sleep(wait_time + 1)

    def close(self) -> None:
        """Close the GitHub client connection."""
        self.github.close()
