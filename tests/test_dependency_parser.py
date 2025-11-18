"""
Tests for the dependency parser module.
"""

import pytest

from src.github.dependency_parser import DependencyParser


class TestDependencyParser:
    """Test suite for DependencyParser class."""

    @pytest.fixture
    def parser(self):
        """Fixture to create a DependencyParser instance."""
        return DependencyParser()

    # Test basic dependency parsing from body

    def test_parse_single_dependency_uppercase(self, parser):
        """Test parsing single dependency with uppercase pattern."""
        body = "Depends on #123"
        result = parser.parse_dependencies(body, [])
        assert result == {"issue-123"}

    def test_parse_single_dependency_lowercase(self, parser):
        """Test parsing single dependency with lowercase pattern."""
        body = "depends on #456"
        result = parser.parse_dependencies(body, [])
        assert result == {"issue-456"}

    def test_parse_blocked_by_pattern(self, parser):
        """Test parsing 'Blocked by' pattern."""
        body = "Blocked by #789"
        result = parser.parse_dependencies(body, [])
        assert result == {"issue-789"}

    def test_parse_requires_pattern(self, parser):
        """Test parsing 'Requires' pattern."""
        body = "Requires #321"
        result = parser.parse_dependencies(body, [])
        assert result == {"issue-321"}

    def test_parse_multiple_dependencies(self, parser):
        """Test parsing multiple dependencies from body."""
        body = """
        This issue depends on several others:
        - Depends on #100
        - Blocked by #200
        - Requires #300
        """
        result = parser.parse_dependencies(body, [])
        assert result == {"issue-100", "issue-200", "issue-300"}

    def test_parse_duplicate_dependencies(self, parser):
        """Test that duplicate dependencies are deduplicated."""
        body = "Depends on #123, also depends on #123"
        result = parser.parse_dependencies(body, [])
        assert result == {"issue-123"}

    # Test edge cases for body parsing

    def test_parse_empty_body(self, parser):
        """Test parsing with empty body."""
        result = parser.parse_dependencies("", [])
        assert result == set()

    def test_parse_none_body(self, parser):
        """Test parsing with None body."""
        result = parser.parse_dependencies(None, [])
        assert result == set()

    def test_parse_body_no_dependencies(self, parser):
        """Test parsing body with no dependency markers."""
        body = "This is a regular issue with no dependencies mentioned."
        result = parser.parse_dependencies(body, [])
        assert result == set()

    def test_parse_malformed_dependency_no_hash(self, parser):
        """Test that malformed dependencies (no #) are ignored."""
        body = "Depends on 123"  # Missing #
        result = parser.parse_dependencies(body, [])
        assert result == set()

    def test_parse_mixed_case_patterns(self, parser):
        """Test parsing with mixed case patterns."""
        body = "DePeNdS oN #123"
        result = parser.parse_dependencies(body, [])
        assert result == {"issue-123"}

    # Test label-based dependency parsing

    def test_parse_label_dependency(self, parser):
        """Test parsing dependency from label."""
        labels = ["depends:issue-123"]
        result = parser.parse_dependencies(None, labels)
        assert result == {"issue-123"}

    def test_parse_multiple_label_dependencies(self, parser):
        """Test parsing multiple dependencies from labels."""
        labels = ["depends:issue-100", "depends:issue-200", "bug"]
        result = parser.parse_dependencies(None, labels)
        assert result == {"issue-100", "issue-200"}

    def test_parse_label_with_non_dependency_labels(self, parser):
        """Test that non-dependency labels are ignored."""
        labels = ["bug", "enhancement", "depends:issue-123"]
        result = parser.parse_dependencies(None, labels)
        assert result == {"issue-123"}

    def test_parse_empty_labels(self, parser):
        """Test parsing with empty labels list."""
        result = parser.parse_dependencies(None, [])
        assert result == set()

    def test_parse_malformed_label_no_issue_number(self, parser):
        """Test handling of malformed label (no issue number)."""
        labels = ["depends:"]
        result = parser.parse_dependencies(None, labels)
        assert result == set()

    # Test combined body and label parsing

    def test_parse_body_and_labels_combined(self, parser):
        """Test parsing dependencies from both body and labels."""
        body = "Depends on #100"
        labels = ["depends:issue-200"]
        result = parser.parse_dependencies(body, labels)
        assert result == {"issue-100", "issue-200"}

    def test_parse_duplicate_in_body_and_labels(self, parser):
        """Test deduplication when same dependency in body and labels."""
        body = "Depends on #123"
        labels = ["depends:issue-123"]
        result = parser.parse_dependencies(body, labels)
        assert result == {"issue-123"}

    # Test dependency validation

    def test_validate_all_valid_dependencies(self, parser):
        """Test validation with all valid dependencies."""
        dependencies = {"issue-100", "issue-200"}
        valid_issues = {"issue-100", "issue-200", "issue-300"}

        valid, invalid = parser.validate_dependencies(dependencies, valid_issues)

        assert valid == {"issue-100", "issue-200"}
        assert invalid == set()

    def test_validate_all_invalid_dependencies(self, parser):
        """Test validation with all invalid dependencies."""
        dependencies = {"issue-999", "issue-888"}
        valid_issues = {"issue-100", "issue-200"}

        valid, invalid = parser.validate_dependencies(dependencies, valid_issues)

        assert valid == set()
        assert invalid == {"issue-999", "issue-888"}

    def test_validate_mixed_valid_invalid_dependencies(self, parser):
        """Test validation with mix of valid and invalid dependencies."""
        dependencies = {"issue-100", "issue-999"}
        valid_issues = {"issue-100", "issue-200"}

        valid, invalid = parser.validate_dependencies(dependencies, valid_issues)

        assert valid == {"issue-100"}
        assert invalid == {"issue-999"}

    def test_validate_empty_dependencies(self, parser):
        """Test validation with no dependencies."""
        valid, invalid = parser.validate_dependencies(set(), {"issue-100"})

        assert valid == set()
        assert invalid == set()

    # Test parse_and_validate combined method

    def test_parse_and_validate_all_valid(self, parser):
        """Test combined parse and validate with all valid."""
        body = "Depends on #100"
        labels = ["depends:issue-200"]
        valid_issues = {"issue-100", "issue-200", "issue-300"}

        result = parser.parse_and_validate(body, labels, valid_issues)

        assert result["all"] == {"issue-100", "issue-200"}
        assert result["valid"] == {"issue-100", "issue-200"}
        assert result["invalid"] == set()

    def test_parse_and_validate_with_invalid(self, parser):
        """Test combined parse and validate with some invalid."""
        body = "Depends on #100\nBlocked by #999"
        labels = ["depends:issue-200"]
        valid_issues = {"issue-100", "issue-200"}

        result = parser.parse_and_validate(body, labels, valid_issues)

        assert result["all"] == {"issue-100", "issue-200", "issue-999"}
        assert result["valid"] == {"issue-100", "issue-200"}
        assert result["invalid"] == {"issue-999"}

    def test_parse_and_validate_empty_input(self, parser):
        """Test combined parse and validate with empty input."""
        result = parser.parse_and_validate(None, [], {"issue-100"})

        assert result["all"] == set()
        assert result["valid"] == set()
        assert result["invalid"] == set()

    # Test real-world scenarios

    def test_realistic_issue_body(self, parser):
        """Test parsing a realistic issue body."""
        body = """
        ## Overview
        Implement dependency extraction from issue descriptions.

        ## Dependencies
        - Depends on #1
        - Blocked by #2

        ## Implementation Details
        This will use regex patterns to find dependencies.
        """
        result = parser.parse_dependencies(body, [])
        assert result == {"issue-1", "issue-2"}

    def test_complex_scenario(self, parser):
        """Test complex scenario with multiple patterns and formats."""
        body = """
        This feature requires several prerequisites:
        - Depends on #10 (authentication)
        - Requires #20 (database setup)
        - blocked by #30 (API integration)

        Also see #40 for related work (not a dependency).
        """
        labels = ["depends:issue-50", "enhancement", "priority:high"]
        valid_issues = {
            "issue-10",
            "issue-20",
            "issue-30",
            "issue-50",
            "issue-100",
        }

        result = parser.parse_and_validate(body, labels, valid_issues)

        # Should find dependencies from body and labels
        assert "issue-10" in result["all"]
        assert "issue-20" in result["all"]
        assert "issue-30" in result["all"]
        assert "issue-50" in result["all"]

        # #40 should NOT be found (not in dependency pattern)
        assert "issue-40" not in result["all"]

        # All should be valid
        assert result["invalid"] == set()
