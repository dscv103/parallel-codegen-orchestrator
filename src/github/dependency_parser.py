"""Dependency parser for extracting task dependencies from GitHub issues.

This module provides functionality to parse dependency markers from:
- Issue body text (e.g., "Depends on #123", "Blocked by #456")
- Issue labels (e.g., "depends:issue-123")
"""

import re
from typing import ClassVar

import structlog

logger = structlog.get_logger(__name__)


class DependencyParser:
    """Parser for extracting dependencies from GitHub issues.

    Supports multiple dependency patterns and label-based dependencies.
    """

    # Regex patterns for dependency markers in issue body
    DEPENDENCY_PATTERNS: ClassVar[list[str]] = [
        r"Depends on #(\d+)",
        r"Blocked by #(\d+)",
        r"Requires #(\d+)",
    ]

    def __init__(self):
        """Initialize the dependency parser."""
        self.compiled_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.DEPENDENCY_PATTERNS
        ]

    def parse_dependencies(
        self,
        issue_body: str | None,
        labels: list[str],
    ) -> set[str]:
        """Extract dependencies from issue body and labels.

        Args:
            issue_body: The issue body text (can be None or empty)
            labels: List of label names from the issue

        Returns:
            Set of dependency identifiers in format "issue-{number}"

        Examples:
            >>> parser = DependencyParser()
            >>> parser.parse_dependencies("Depends on #123", [])
            {'issue-123'}
            >>> parser.parse_dependencies("", ["depends:issue-456"])
            {'issue-456'}
        """
        dependencies = set()

        # Parse body text for dependency markers
        if issue_body:
            dependencies.update(self._parse_body(issue_body))

        # Parse labels for dependency markers
        dependencies.update(self._parse_labels(labels))

        logger.debug(
            "dependencies_parsed",
            count=len(dependencies),
            dependencies=list(dependencies),
        )

        return dependencies

    def _parse_body(self, body: str) -> set[str]:
        """Parse issue body for dependency markers.

        Args:
            body: The issue body text

        Returns:
            Set of dependency identifiers
        """
        dependencies = set()

        for pattern in self.compiled_patterns:
            matches = pattern.findall(body)
            dependencies.update(f"issue-{num}" for num in matches)

        return dependencies

    def _parse_labels(self, labels: list[str]) -> set[str]:
        """Parse labels for dependency markers.

        Expected label format: "depends:issue-{number}"

        Args:
            labels: List of label names

        Returns:
            Set of dependency identifiers
        """
        dependencies = set()

        for label in labels:
            if label.startswith("depends:"):
                dep = label.split(":", 1)[1]  # Use maxsplit=1 to handle edge cases
                if dep:  # Only add non-empty dependencies
                    dependencies.add(dep)

        return dependencies

    def validate_dependencies(
        self,
        dependencies: set[str],
        valid_issue_numbers: set[str],
    ) -> tuple[set[str], set[str]]:
        """Validate that dependency references point to existing issues.

        Args:
            dependencies: Set of dependency identifiers to validate
            valid_issue_numbers: Set of valid issue identifiers

        Returns:
            Tuple of (valid_deps, invalid_deps)
        """
        valid_deps = set()
        invalid_deps = set()

        for dep in dependencies:
            if dep in valid_issue_numbers:
                valid_deps.add(dep)
            else:
                invalid_deps.add(dep)
                logger.warning(
                    "invalid_dependency_reference",
                    dependency=dep,
                    reason="issue_not_found",
                )

        return valid_deps, invalid_deps

    def parse_and_validate(
        self,
        issue_body: str | None,
        labels: list[str],
        valid_issue_numbers: set[str],
    ) -> dict:
        """Parse and validate dependencies in one step.

        Args:
            issue_body: The issue body text
            labels: List of label names
            valid_issue_numbers: Set of valid issue identifiers

        Returns:
            Dictionary with:
                - 'valid': Set of valid dependencies
                - 'invalid': Set of invalid dependencies
                - 'all': Set of all parsed dependencies
        """
        all_deps = self.parse_dependencies(issue_body, labels)
        valid_deps, invalid_deps = self.validate_dependencies(
            all_deps,
            valid_issue_numbers,
        )

        return {
            "valid": valid_deps,
            "invalid": invalid_deps,
            "all": all_deps,
        }
