"""Unit tests for configuration management module."""

import json
import os
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from src.config import (
    AgentConfig,
    AutomationConfig,
    CodegenConfig,
    GitHubConfig,
    OrchestratorConfig,
    get_config,
    load_config,
    reset_config,
)


@pytest.fixture
def valid_config_dict() -> dict[str, Any]:
    """Fixture providing valid configuration dictionary."""
    return {
        "github": {
            "token": "ghp_test_token_123",
            "organization": "test-org",
            "repository": "test-org/test-repo",
            "project_number": 42,
            "default_branch": "main",
        },
        "codegen": {
            "org_id": "codegen-org-123",
            "api_token": "codegen_token_456",
            "base_url": "https://api.codegen.com",
        },
        "agent": {
            "max_concurrent_agents": 5,
            "task_timeout_seconds": 300,
            "retry_attempts": 2,
            "retry_delay_seconds": 10,
        },
        "automation": {
            "auto_merge_on_success": True,
            "post_results_as_comment": False,
            "update_issue_status": True,
            "status_label_prefix": "status:",
        },
        "logging_level": "DEBUG",
    }


@pytest.fixture
def temp_config_file(tmp_path: Path, valid_config_dict: dict[str, Any]) -> Path:
    """Fixture providing temporary YAML config file."""
    config_path = tmp_path / "config.yaml"
    with config_path.open("w") as f:
        yaml.dump(valid_config_dict, f)
    return config_path


@pytest.fixture
def temp_json_config_file(tmp_path: Path, valid_config_dict: dict[str, Any]) -> Path:
    """Fixture providing temporary JSON config file."""
    config_path = tmp_path / "config.json"
    with config_path.open("w") as f:
        json.dump(valid_config_dict, f)
    return config_path


@pytest.fixture(autouse=True)
def reset_config_singleton():
    """Reset configuration singleton before and after each test."""
    reset_config()
    yield
    reset_config()


@pytest.fixture(autouse=True)
def clean_env_vars(monkeypatch):
    """Clean environment variables before each test."""
    env_prefixes = ["GITHUB__", "CODEGEN__", "AGENT__", "AUTOMATION__"]
    for key in list(os.environ.keys()):
        for prefix in env_prefixes:
            if key.startswith(prefix):
                monkeypatch.delenv(key, raising=False)


class TestGitHubConfig:
    """Tests for GitHubConfig model."""

    def test_valid_github_config(self):
        """Test creating valid GitHubConfig."""
        config = GitHubConfig(
            token="ghp_test_token",
            organization="test-org",
            repository="owner/repo",
        )
        assert config.organization == "test-org"
        assert config.repository == "owner/repo"
        assert config.default_branch == "main"
        assert config.project_number is None

    def test_github_config_with_project_number(self):
        """Test GitHubConfig with project number."""
        config = GitHubConfig(
            token="ghp_test_token",
            organization="test-org",
            repository="owner/repo",
            project_number=123,
        )
        assert config.project_number == 123

    def test_invalid_repository_format(self):
        """Test GitHubConfig rejects invalid repository format."""
        with pytest.raises(ValidationError, match="Repository must be in format"):
            GitHubConfig(token="ghp_test_token", organization="test-org", repository="invalid-repo")

    def test_invalid_repository_format_multiple_slashes(self):
        """Test GitHubConfig rejects repository with multiple slashes."""
        with pytest.raises(ValidationError, match="Repository must be in format"):
            GitHubConfig(
                token="ghp_test_token",
                organization="test-org",
                repository="owner/repo/extra",
            )

    def test_missing_required_field(self):
        """Test GitHubConfig requires token."""
        with pytest.raises(ValidationError, match="token"):
            GitHubConfig(organization="test-org", repository="owner/repo")

    def test_project_number_validation(self):
        """Test project_number must be positive."""
        with pytest.raises(ValidationError):
            GitHubConfig(
                token="ghp_test_token",
                organization="test-org",
                repository="owner/repo",
                project_number=0,
            )

    def test_secret_str_masking(self):
        """Test that token is masked in repr."""
        config = GitHubConfig(
            token="ghp_secret_token",
            organization="test-org",
            repository="owner/repo",
        )
        repr_str = repr(config)
        assert "ghp_secret_token" not in repr_str
        assert "token" in repr_str


class TestCodegenConfig:
    """Tests for CodegenConfig model."""

    def test_valid_codegen_config(self):
        """Test creating valid CodegenConfig."""
        config = CodegenConfig(org_id="org123", api_token="token456")
        assert config.org_id == "org123"
        assert config.base_url is None

    def test_codegen_config_with_base_url(self):
        """Test CodegenConfig with custom base URL."""
        config = CodegenConfig(
            org_id="org123",
            api_token="token456",
            base_url="https://custom.api.com",
        )
        assert config.base_url == "https://custom.api.com"

    def test_base_url_strips_trailing_slash(self):
        """Test base_url strips trailing slash."""
        config = CodegenConfig(org_id="org123", api_token="token456", base_url="https://api.com/")
        assert config.base_url == "https://api.com"

    def test_invalid_base_url_scheme(self):
        """Test CodegenConfig rejects invalid base URL scheme."""
        with pytest.raises(ValidationError, match="must start with http"):
            CodegenConfig(org_id="org123", api_token="token456", base_url="ftp://invalid.com")

    def test_missing_required_fields(self):
        """Test CodegenConfig requires org_id and api_token."""
        with pytest.raises(ValidationError):
            CodegenConfig(org_id="org123")


class TestAgentConfig:
    """Tests for AgentConfig model."""

    def test_valid_agent_config(self):
        """Test creating valid AgentConfig with defaults."""
        config = AgentConfig()
        assert config.max_concurrent_agents == 10
        assert config.task_timeout_seconds == 600
        assert config.retry_attempts == 3
        assert config.retry_delay_seconds == 30

    def test_agent_config_custom_values(self):
        """Test AgentConfig with custom values."""
        config = AgentConfig(
            max_concurrent_agents=5,
            task_timeout_seconds=300,
            retry_attempts=5,
            retry_delay_seconds=60,
        )
        assert config.max_concurrent_agents == 5
        assert config.task_timeout_seconds == 300
        assert config.retry_attempts == 5
        assert config.retry_delay_seconds == 60

    def test_max_concurrent_agents_bounds(self):
        """Test max_concurrent_agents must be between 1 and 10."""
        with pytest.raises(ValidationError):
            AgentConfig(max_concurrent_agents=0)

        with pytest.raises(ValidationError):
            AgentConfig(max_concurrent_agents=11)

        # Valid boundaries
        config1 = AgentConfig(max_concurrent_agents=1)
        assert config1.max_concurrent_agents == 1

        config10 = AgentConfig(max_concurrent_agents=10)
        assert config10.max_concurrent_agents == 10

    def test_task_timeout_minimum(self):
        """Test task_timeout_seconds must be at least 60."""
        with pytest.raises(ValidationError):
            AgentConfig(task_timeout_seconds=59)

        config = AgentConfig(task_timeout_seconds=60)
        assert config.task_timeout_seconds == 60

    def test_retry_attempts_non_negative(self):
        """Test retry_attempts must be non-negative."""
        with pytest.raises(ValidationError):
            AgentConfig(retry_attempts=-1)

        config = AgentConfig(retry_attempts=0)
        assert config.retry_attempts == 0

    def test_retry_delay_minimum(self):
        """Test retry_delay_seconds must be at least 5."""
        with pytest.raises(ValidationError):
            AgentConfig(retry_delay_seconds=4)

        config = AgentConfig(retry_delay_seconds=5)
        assert config.retry_delay_seconds == 5


class TestAutomationConfig:
    """Tests for AutomationConfig model."""

    def test_valid_automation_config(self):
        """Test creating valid AutomationConfig with defaults."""
        config = AutomationConfig()
        assert config.auto_merge_on_success is False
        assert config.post_results_as_comment is True
        assert config.update_issue_status is True
        assert config.status_label_prefix == "status:"

    def test_automation_config_custom_values(self):
        """Test AutomationConfig with custom values."""
        config = AutomationConfig(
            auto_merge_on_success=True,
            post_results_as_comment=False,
            update_issue_status=False,
            status_label_prefix="state:",
        )
        assert config.auto_merge_on_success is True
        assert config.post_results_as_comment is False
        assert config.update_issue_status is False
        assert config.status_label_prefix == "state:"


class TestOrchestratorConfig:
    """Tests for OrchestratorConfig model."""

    def test_valid_orchestrator_config(self, valid_config_dict):
        """Test creating valid OrchestratorConfig."""
        config = OrchestratorConfig(**valid_config_dict)
        assert config.github.organization == "test-org"
        assert config.codegen.org_id == "codegen-org-123"
        assert config.agent.max_concurrent_agents == 5
        assert config.automation.auto_merge_on_success is True
        assert config.logging_level == "DEBUG"

    def test_logging_level_validation(self, valid_config_dict):
        """Test logging_level validation."""
        # Valid levels
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            config_dict = valid_config_dict.copy()
            config_dict["logging_level"] = level
            config = OrchestratorConfig(**config_dict)
            assert config.logging_level == level

        # Case insensitive
        config_dict = valid_config_dict.copy()
        config_dict["logging_level"] = "debug"
        config = OrchestratorConfig(**config_dict)
        assert config.logging_level == "DEBUG"

        # Invalid level
        config_dict = valid_config_dict.copy()
        config_dict["logging_level"] = "INVALID"
        with pytest.raises(ValidationError, match="logging_level must be one of"):
            OrchestratorConfig(**config_dict)

    def test_default_logging_level(self, valid_config_dict):
        """Test default logging level."""
        config_dict = valid_config_dict.copy()
        del config_dict["logging_level"]
        config = OrchestratorConfig(**config_dict)
        assert config.logging_level == "INFO"

    def test_nested_validation_errors(self, valid_config_dict):
        """Test that nested validation errors are properly reported."""
        config_dict = valid_config_dict.copy()
        config_dict["agent"]["max_concurrent_agents"] = 20  # Invalid: > 10

        with pytest.raises(ValidationError) as exc_info:
            OrchestratorConfig(**config_dict)

        error_str = str(exc_info.value)
        assert "max_concurrent_agents" in error_str


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_yaml_config(self, temp_config_file):
        """Test loading configuration from YAML file."""
        config = load_config(temp_config_file)
        assert isinstance(config, OrchestratorConfig)
        assert config.github.organization == "test-org"
        assert config.codegen.org_id == "codegen-org-123"

    def test_load_json_config(self, temp_json_config_file):
        """Test loading configuration from JSON file."""
        config = load_config(temp_json_config_file)
        assert isinstance(config, OrchestratorConfig)
        assert config.github.organization == "test-org"
        assert config.codegen.org_id == "codegen-org-123"

    def test_load_config_not_found(self, tmp_path):
        """Test load_config raises FileNotFoundError for missing file."""
        non_existent = tmp_path / "nonexistent.yaml"
        with pytest.raises(FileNotFoundError):
            load_config(non_existent)

    def test_load_config_invalid_yaml(self, tmp_path):
        """Test load_config raises YAMLError for invalid YAML."""
        config_path = tmp_path / "invalid.yaml"
        with open(config_path, "w") as f:
            f.write("invalid: yaml: content: [")

        with pytest.raises(yaml.YAMLError):
            load_config(config_path)

    def test_load_config_invalid_json(self, tmp_path):
        """Test load_config raises JSONDecodeError for invalid JSON."""
        config_path = tmp_path / "invalid.json"
        with open(config_path, "w") as f:
            f.write('{"invalid": json}')

        with pytest.raises(json.JSONDecodeError):
            load_config(config_path)

    def test_load_config_unsupported_format(self, tmp_path):
        """Test load_config raises ValueError for unsupported format."""
        config_path = tmp_path / "config.txt"
        with open(config_path, "w") as f:
            f.write("some text")

        with pytest.raises(ValueError, match="Unsupported config file format"):
            load_config(config_path)

    def test_load_config_validation_error(self, tmp_path):
        """Test load_config raises ValueError for invalid configuration."""
        config_path = tmp_path / "config.yaml"
        invalid_config = {
            "github": {
                "token": "token",
                "organization": "org",
                "repository": "invalid-repo",  # Missing slash
            },
            "codegen": {"org_id": "org", "api_token": "token"},
            "agent": {},
            "automation": {},
        }
        with open(config_path, "w") as f:
            yaml.dump(invalid_config, f)

        with pytest.raises(ValueError, match="Configuration validation failed"):
            load_config(config_path)

    def test_load_config_default_location(self, tmp_path, valid_config_dict, monkeypatch):
        """Test load_config finds config in default location."""
        # Change to temp directory
        monkeypatch.chdir(tmp_path)

        # Create config.yaml in current directory
        config_path = Path("config.yaml")
        with open(config_path, "w") as f:
            yaml.dump(valid_config_dict, f)

        # Should find it without explicit path
        config = load_config()
        assert config.github.organization == "test-org"

    def test_load_config_default_location_not_found(self, tmp_path, monkeypatch):
        """Test load_config raises FileNotFoundError when no default found."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(FileNotFoundError, match="No configuration file found"):
            load_config()


class TestEnvironmentVariableOverrides:
    """Tests for environment variable override support."""

    def test_github_token_override(self, temp_config_file, monkeypatch):
        """Test GITHUB__TOKEN overrides file value."""
        monkeypatch.setenv("GITHUB__TOKEN", "env_override_token")

        config = load_config(temp_config_file)
        assert config.github.token.get_secret_value() == "env_override_token"

    def test_agent_max_concurrent_override(self, temp_config_file, monkeypatch):
        """Test AGENT__MAX_CONCURRENT_AGENTS overrides file value."""
        monkeypatch.setenv("AGENT__MAX_CONCURRENT_AGENTS", "7")

        config = load_config(temp_config_file)
        assert config.agent.max_concurrent_agents == 7

    def test_automation_bool_override(self, temp_config_file, monkeypatch):
        """Test boolean environment variable override."""
        monkeypatch.setenv("AUTOMATION__AUTO_MERGE_ON_SUCCESS", "false")

        config = load_config(temp_config_file)
        assert config.automation.auto_merge_on_success is False

    def test_multiple_overrides(self, temp_config_file, monkeypatch):
        """Test multiple environment variable overrides."""
        monkeypatch.setenv("GITHUB__ORGANIZATION", "env-org")
        monkeypatch.setenv("CODEGEN__ORG_ID", "env-codegen-org")
        monkeypatch.setenv("AGENT__RETRY_ATTEMPTS", "5")

        config = load_config(temp_config_file)
        assert config.github.organization == "env-org"
        assert config.codegen.org_id == "env-codegen-org"
        assert config.agent.retry_attempts == 5


class TestGetConfig:
    """Tests for get_config singleton function."""

    def test_get_config_singleton(self, temp_config_file):
        """Test get_config returns same instance."""
        config1 = get_config(temp_config_file)
        config2 = get_config()

        assert config1 is config2

    def test_get_config_reload(self, temp_config_file, tmp_path, valid_config_dict):
        """Test get_config with reload parameter."""
        config1 = get_config(temp_config_file)
        original_org = config1.github.organization

        # Modify config file
        modified_config = valid_config_dict.copy()
        modified_config["github"]["organization"] = "modified-org"

        modified_path = tmp_path / "modified.yaml"
        with open(modified_path, "w") as f:
            yaml.dump(modified_config, f)

        # Reload with new path
        config2 = get_config(modified_path, reload=True)
        assert config2.github.organization == "modified-org"
        assert config2.github.organization != original_org

    def test_reset_config(self, temp_config_file):
        """Test reset_config clears cached instance."""
        config1 = get_config(temp_config_file)
        reset_config()
        config2 = get_config(temp_config_file)

        assert config1 is not config2


class TestConfigIntegration:
    """Integration tests for complete configuration workflows."""

    def test_full_workflow_yaml(self, temp_config_file):
        """Test complete workflow with YAML configuration."""
        # Load config
        config = load_config(temp_config_file)

        # Verify all sections loaded correctly
        assert config.github.token.get_secret_value() == "ghp_test_token_123"
        assert config.github.repository == "test-org/test-repo"
        assert config.codegen.base_url == "https://api.codegen.com"
        assert config.agent.max_concurrent_agents == 5
        assert config.automation.status_label_prefix == "status:"
        assert config.logging_level == "DEBUG"

    def test_full_workflow_with_env_overrides(self, temp_config_file, monkeypatch):
        """Test complete workflow with environment variable overrides."""
        # Set environment overrides
        monkeypatch.setenv("GITHUB__TOKEN", "env_token")
        monkeypatch.setenv("AGENT__MAX_CONCURRENT_AGENTS", "8")
        monkeypatch.setenv("AUTOMATION__AUTO_MERGE_ON_SUCCESS", "true")

        config = load_config(temp_config_file)

        # Verify overrides applied
        assert config.github.token.get_secret_value() == "env_token"
        assert config.agent.max_concurrent_agents == 8
        assert config.automation.auto_merge_on_success is True

        # Verify non-overridden values from file
        assert config.github.organization == "test-org"
        assert config.codegen.org_id == "codegen-org-123"

    def test_minimal_config(self, tmp_path):
        """Test configuration with only required fields and defaults."""
        minimal_config = {
            "github": {"token": "token", "organization": "org", "repository": "owner/repo"},
            "codegen": {"org_id": "codegen-org", "api_token": "token"},
            "agent": {},
            "automation": {},
        }

        config_path = tmp_path / "minimal.yaml"
        with open(config_path, "w") as f:
            yaml.dump(minimal_config, f)

        config = load_config(config_path)

        # Verify defaults applied
        assert config.github.default_branch == "main"
        assert config.agent.max_concurrent_agents == 10
        assert config.agent.task_timeout_seconds == 600
        assert config.automation.post_results_as_comment is True
        assert config.logging_level == "INFO"
