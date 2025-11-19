"""GitHub automation module for parallel-codegen-orchestrator.

This module provides automated GitHub integration features including:
- Posting orchestration results as comments to issues/PRs
- Auto-merging successful pull requests
- Updating issue status labels based on execution outcomes
- Configurable automation features with fail-safe error handling

All automation features are configuration-driven and designed to fail
gracefully without disrupting the main orchestration flow.
"""

from src.automation.github_automation import GitHubAutomationHandler

__all__ = ["GitHubAutomationHandler"]
