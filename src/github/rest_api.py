"""
GitHub REST API Integration using PyGithub
Provides methods for repository, issue, and PR management
"""

from typing import Iterator, Optional
import time
from github import Github, GithubException, RateLimitExceededException
from github.Issue import Issue
from github.PullRequest import PullRequest
from github.Repository import Repository


class GitHubIntegration:
    """
    GitHub REST API integration class using PyGithub.
    
    Handles authentication, issue/PR fetching, branch creation,
    and automated posting of results with rate limit management.
    """

    def __init__(self, token: str, org_id: str):
        """
        Initialize GitHub integration with authentication.
        
        Args:
            token: GitHub personal access token or OAuth token
            org_id: GitHub organization ID
        """
        self.github = Github(token)
        self.org_id = org_id
        self._verify_authentication()

    def _verify_authentication(self) -> None:
        """Verify GitHub token is valid"""
        try:
            self.github.get_user().login
        except GithubException as e:
            raise ValueError(f"Invalid GitHub token: {e}")

    def _get_repository(self, repo_name: str) -> Repository:
        """
        Get repository object with error handling.
        
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
                f"Failed to access repository '{repo_name}': {e.data}"
            )

    def fetch_issues(
        self,
        repo_name: str,
        state: str = "open",
        labels: Optional[list[str]] = None
    ) -> Iterator[Issue]:
        """
        Fetch issues from repository with filtering and pagination support.
        
        Args:
            repo_name: Repository name in format 'owner/repo'
            state: Issue state filter ('open', 'closed', 'all')
            labels: Optional list of label names to filter by
            
        Returns:
            Iterator of Issue objects
            
        Raises:
            GithubException: If repository access fails
            RateLimitExceededException: If rate limit exceeded
        """
        repo = self._get_repository(repo_name)
        
        # Prepare parameters
        kwargs = {"state": state}
        if labels:
            kwargs["labels"] = labels
        
        # PyGithub handles pagination automatically
        try:
            issues = repo.get_issues(**kwargs)
            # Filter out pull requests (GitHub API returns PRs as issues)
            for issue in issues:
                if not issue.pull_request:
                    yield issue
        except RateLimitExceededException:
            self._handle_rate_limit()
            raise

    def fetch_pull_requests(
        self,
        repo_name: str,
        state: str = "open"
    ) -> Iterator[PullRequest]:
        """
        Fetch pull requests with metadata from repository.
        
        Args:
            repo_name: Repository name in format 'owner/repo'
            state: PR state filter ('open', 'closed', 'all')
            
        Returns:
            Iterator of PullRequest objects with full metadata
            
        Raises:
            GithubException: If repository access fails
        """
        repo = self._get_repository(repo_name)
        
        try:
            pulls = repo.get_pulls(state=state)
            for pr in pulls:
                yield pr
        except RateLimitExceededException:
            self._handle_rate_limit()
            raise

    def update_issue_status(
        self,
        repo_name: str,
        issue_number: int,
        state: Optional[str] = None,
        labels: Optional[list[str]] = None
    ) -> None:
        """
        Update issue status and labels.
        
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
        from_branch: str = "main"
    ) -> bool:
        """
        Create a new branch from an existing branch.
        
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
                sha=source_sha
            )
            return True
            
        except GithubException as e:
            if e.status == 422:
                raise GithubException(
                    e.status,
                    f"Branch '{branch_name}' already exists or invalid"
                )
            raise

    def post_comment(
        self,
        repo_name: str,
        issue_number: int,
        comment: str
    ) -> None:
        """
        Post a comment to an issue or pull request.
        
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
        """
        Get current rate limit information.
        
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
            "reset": int(rate_limit.core.reset.timestamp())
        }

    def _handle_rate_limit(self) -> None:
        """
        Handle rate limit by checking status and waiting if necessary.
        Logs warning when approaching limit.
        """
        rate_info = self.get_rate_limit()
        
        if rate_info["remaining"] < 100:
            reset_time = rate_info["reset"]
            wait_time = max(0, reset_time - int(time.time()))
            
            if wait_time > 0:
                print(
                    f"Rate limit low ({rate_info['remaining']} remaining). "
                    f"Waiting {wait_time}s until reset..."
                )
                time.sleep(wait_time + 1)

    def close(self) -> None:
        """Close the GitHub client connection"""
        self.github.close()

