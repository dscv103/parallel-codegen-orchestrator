"""Configuration Management with Pydantic.

This module implements configuration models using Pydantic for parsing and
validation of YAML/JSON configuration files with environment variable overrides.
"""

import os
import threading
from pathlib import Path

import structlog
import yaml
from pydantic import BaseModel, Field, field_validator

# Initialize logger
logger = structlog.get_logger(__name__)

# Constants
REPO_PARTS_COUNT = 2
MAX_CONCURRENT_AGENTS = 10
HIGH_TIMEOUT_THRESHOLD = 1800  # 30 minutes


class GitHubConfig(BaseModel):
    """GitHub API configuration settings.

    Attributes:
        token: GitHub personal access token or OAuth token
        organization: GitHub organization name
        repository: Repository name in format 'owner/repo'
        project_id: Optional Projects v2 ID (format: PVT_...)
        default_branch: Default branch for creating new branches
    """

    token: str = Field(
        description="GitHub personal access token",
        min_length=1,
    )
    organization: str = Field(
        description="GitHub organization name",
        min_length=1,
    )
    repository: str = Field(
        description="Repository in format 'owner/repo'",
        pattern=r"^[\w.-]+/[\w.-]+$",
    )
    project_id: str | None = Field(
        default=None,
        description="GitHub Projects v2 ID",
    )
    default_branch: str = Field(
        default="main",
        description="Default branch for new branches",
    )

    @field_validator("token")
    @classmethod
    def validate_token(cls, v: str) -> str:
        """Validate that the token is not a placeholder.

        Args:
            v: The token value to validate

        Returns:
            The validated token

        Raises:
            ValueError: If token is a placeholder
        """
        if "your_" in v or v == "":
            msg = "GitHub token must be set (not a placeholder)"
            raise ValueError(msg)
        return v

    @field_validator("repository")
    @classmethod
    def validate_repository(cls, v: str) -> str:
        """Validate repository format.

        Args:
            v: The repository string to validate

        Returns:
            The validated repository string

        Raises:
            ValueError: If repository format is invalid
        """
        parts = v.split("/")
        if len(parts) != REPO_PARTS_COUNT or not all(parts):
            msg = "Repository must be in format 'owner/repo'"
            raise ValueError(msg)
        return v

    model_config = {"str_strip_whitespace": True}


class CodegenConfig(BaseModel):
    """Codegen API configuration settings.

    Attributes:
        org_id: Codegen organization ID
        api_token: Codegen API authentication token
        base_url: Optional custom Codegen API base URL
    """

    org_id: str = Field(
        description="Codegen organization ID",
        min_length=1,
    )
    api_token: str = Field(
        description="Codegen API token",
        min_length=1,
    )
    base_url: str | None = Field(
        default=None,
        description="Custom Codegen API base URL",
    )

    @field_validator("org_id", "api_token")
    @classmethod
    def validate_not_placeholder(cls, v: str) -> str:
        """Validate that configuration values are not placeholders.

        Args:
            v: The value to validate

        Returns:
            The validated value

        Raises:
            ValueError: If value is a placeholder
        """
        if "your-" in v or "your_" in v or v == "":
            msg = "Codegen configuration must be set (not a placeholder)"
            raise ValueError(msg)
        return v

    model_config = {"str_strip_whitespace": True}


class AgentConfig(BaseModel):
    """Agent pool configuration settings.

    Attributes:
        max_concurrent_agents: Maximum number of concurrent agents (1-10)
        task_timeout_seconds: Task execution timeout in seconds
        retry_attempts: Number of retry attempts for failed tasks
        retry_delay_seconds: Delay between retry attempts in seconds
    """

    max_concurrent_agents: int = Field(
        default=10,
        ge=1,
        le=10,
        description="Maximum concurrent agents",
    )
    task_timeout_seconds: int = Field(
        default=600,
        ge=60,
        description="Task timeout in seconds",
    )
    retry_attempts: int = Field(
        default=3,
        ge=0,
        description="Number of retry attempts",
    )
    retry_delay_seconds: int = Field(
        default=30,
        ge=5,
        description="Delay between retries in seconds",
    )


class AutomationConfig(BaseModel):
    """GitHub automation configuration settings.

    Attributes:
        auto_merge_on_success: Automatically merge PRs on success
        post_results_as_comment: Post orchestration results as comments
        update_issue_status: Automatically update issue status/labels
        status_label_prefix: Prefix for status labels (e.g., "status:")
    """

    auto_merge_on_success: bool = Field(
        default=False,
        description="Auto-merge PRs on success",
    )
    post_results_as_comment: bool = Field(
        default=True,
        description="Post results as comments",
    )
    update_issue_status: bool = Field(
        default=True,
        description="Auto-update issue status",
    )
    status_label_prefix: str = Field(
        default="status:",
        description="Prefix for status labels",
    )


class OrchestratorConfig(BaseModel):
    """Main orchestrator configuration combining all settings.

    Attributes:
        github: GitHub API configuration
        codegen: Codegen API configuration
        agent: Agent pool configuration
        automation: Automation features configuration
        logging_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """

    github: GitHubConfig
    codegen: CodegenConfig
    agent: AgentConfig
    automation: AutomationConfig
    logging_level: str = Field(
        default="INFO",
        description="Logging level",
        pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "OrchestratorConfig":
        """Load configuration from a YAML file.

        Args:
            path: Path to the YAML configuration file

        Returns:
            Parsed and validated OrchestratorConfig instance

        Raises:
            FileNotFoundError: If configuration file doesn't exist
            ValueError: If configuration is invalid
            yaml.YAMLError: If YAML parsing fails
        """
        config_path = Path(path)

        if not config_path.exists():
            msg = f"Configuration file not found: {config_path}"
            raise FileNotFoundError(msg)

        logger.info("loading_configuration", path=str(config_path))

        try:
            with config_path.open() as f:
                config_data = yaml.safe_load(f)

            if not config_data:
                msg = "Configuration file is empty"
                raise ValueError(msg)

            # Apply environment variable overrides
            config_data = cls._apply_env_overrides(config_data)

            # Parse and validate configuration
            config = cls(**config_data)
        except yaml.YAMLError as e:
            logger.exception("yaml_parse_error", error=str(e), path=str(config_path))
            msg = f"Invalid YAML in configuration file: {e}"
            raise ValueError(msg) from e
        else:
            logger.info(
                "configuration_loaded",
                max_agents=config.agent.max_concurrent_agents,
                logging_level=config.logging_level,
            )

            return config

    @classmethod
    def _apply_env_overrides(cls, config_data: dict) -> dict:
        """Apply environment variable overrides to configuration.

        Environment variables follow the pattern: ORCHESTRATOR_<SECTION>_<KEY>
        Example: ORCHESTRATOR_GITHUB_TOKEN, ORCHESTRATOR_AGENT_MAX_CONCURRENT

        Args:
            config_data: Base configuration dictionary from file

        Returns:
            Configuration dictionary with environment overrides applied
        """
        env_overrides = {
            # GitHub configuration
            ("github", "token"): "ORCHESTRATOR_GITHUB_TOKEN",
            ("github", "organization"): "ORCHESTRATOR_GITHUB_ORGANIZATION",
            ("github", "repository"): "ORCHESTRATOR_GITHUB_REPOSITORY",
            ("github", "project_id"): "ORCHESTRATOR_GITHUB_PROJECT_ID",
            ("github", "default_branch"): "ORCHESTRATOR_GITHUB_DEFAULT_BRANCH",
            # Codegen configuration
            ("codegen", "org_id"): "ORCHESTRATOR_CODEGEN_ORG_ID",
            ("codegen", "api_token"): "ORCHESTRATOR_CODEGEN_API_TOKEN",
            ("codegen", "base_url"): "ORCHESTRATOR_CODEGEN_BASE_URL",
            # Agent configuration
            ("agent", "max_concurrent_agents"): "ORCHESTRATOR_AGENT_MAX_CONCURRENT",
            ("agent", "task_timeout_seconds"): "ORCHESTRATOR_AGENT_TASK_TIMEOUT",
            ("agent", "retry_attempts"): "ORCHESTRATOR_AGENT_RETRY_ATTEMPTS",
            ("agent", "retry_delay_seconds"): "ORCHESTRATOR_AGENT_RETRY_DELAY",
            # Automation configuration
            ("automation", "auto_merge_on_success"): "ORCHESTRATOR_AUTO_MERGE",
            ("automation", "post_results_as_comment"): "ORCHESTRATOR_POST_RESULTS",
            ("automation", "update_issue_status"): "ORCHESTRATOR_UPDATE_STATUS",
            ("automation", "status_label_prefix"): "ORCHESTRATOR_STATUS_PREFIX",
            # Logging
            ("logging_level",): "ORCHESTRATOR_LOGGING_LEVEL",
        }

        for path, env_var in env_overrides.items():
            value = os.environ.get(env_var)
            if value is not None:
                # Navigate to nested config section
                current = config_data
                for key in path[:-1]:
                    if key not in current:
                        current[key] = {}
                    current = current[key]

                # Convert string values to appropriate types
                final_key = path[-1]
                if env_var.endswith(("_TIMEOUT", "_DELAY", "_ATTEMPTS", "_CONCURRENT")):
                    value = int(value)
                elif env_var.endswith(("_MERGE", "_RESULTS", "_STATUS")):
                    value = value.lower() in ("true", "1", "yes")

                current[final_key] = value
                logger.debug(
                    "env_override_applied",
                    env_var=env_var,
                    config_path=".".join(path),
                )

        return config_data

    def validate_config(self) -> list[str]:
        """Validate configuration and return list of warnings.

        Returns:
            List of validation warning messages (empty if no warnings)
        """
        warnings = []

        # Check for development/example tokens
        if self.github.token.startswith("ghp_example"):
            warnings.append("GitHub token appears to be an example/placeholder")

        if self.codegen.api_token.startswith("example_"):
            warnings.append("Codegen API token appears to be an example/placeholder")

        # Warn about security settings
        if self.automation.auto_merge_on_success:
            warnings.append(
                "Auto-merge is enabled - ensure proper testing and review processes",
            )

        # Warn about resource usage
        if self.agent.max_concurrent_agents == MAX_CONCURRENT_AGENTS:
            warnings.append(
                f"Using maximum concurrent agents ({MAX_CONCURRENT_AGENTS}) - "
                "monitor resource usage",
            )

        if self.agent.task_timeout_seconds > HIGH_TIMEOUT_THRESHOLD:  # 30 minutes
            warnings.append(
                f"Task timeout is high ({self.agent.task_timeout_seconds}s) - "
                "tasks may run for extended periods",
            )

        return warnings


class ConfigManager:
    """Configuration manager using singleton pattern."""

    _instance: OrchestratorConfig | None = None
    _init_lock: threading.Lock = threading.Lock()

    @classmethod
    def load_config(cls, config_path: str | Path | None = None) -> OrchestratorConfig:
        """Load configuration from file.

        Args:
            config_path: Path to configuration file. If None, looks for config.yaml or config.json
                        in current directory.

        Returns:
            Loaded OrchestratorConfig instance

        Raises:
            FileNotFoundError: If config file not found
            ValueError: If config file is invalid or unsupported format
        """
        if config_path is None:
            # Look for default config files
            for default_name in ["config.yaml", "config.yml", "config.json"]:
                default_path = Path(default_name)
                if default_path.exists():
                    config_path = default_path
                    break
            else:
                msg = (
                    "No configuration file found. Expected config.yaml, config.yml, or config.json"
                )
                raise FileNotFoundError(msg)

        config_path = Path(config_path)
        if not config_path.exists():
            msg = f"Configuration file not found: {config_path}"
            raise FileNotFoundError(msg)

        return OrchestratorConfig.from_yaml(config_path)

    @classmethod
    def get_config(
        cls,
        config_path: str | Path | None = None,
        reload: bool = False,
    ) -> OrchestratorConfig:
        """Get configuration instance (singleton pattern).

        Uses double-checked locking to prevent TOCTOU race conditions
        where concurrent threads could both call load_config.

        Args:
            config_path: Path to configuration file. Only used on first call or when reload=True.
            reload: If True, force reload configuration from file.

        Returns:
            OrchestratorConfig instance
        """
        # First check (without lock) - fast path for already initialized instance
        if cls._instance is not None and not reload:
            return cls._instance

        # Acquire lock for initialization
        with cls._init_lock:
            # Second check (with lock) - prevent race condition
            if cls._instance is None or reload:
                cls._instance = cls.load_config(config_path)

            return cls._instance

    @classmethod
    def reset_config(cls) -> None:
        """Reset the configuration instance."""
        cls._instance = None


# Convenience functions for backward compatibility
def load_config(config_path: str | Path | None = None) -> OrchestratorConfig:
    """Load configuration from file."""
    return ConfigManager.load_config(config_path)


def get_config(config_path: str | Path | None = None, reload: bool = False) -> OrchestratorConfig:
    """Get configuration instance (singleton pattern)."""
    return ConfigManager.get_config(config_path, reload)


def reset_config() -> None:
    """Reset the configuration instance."""
    ConfigManager.reset_config()


# Export main configuration class
__all__ = [
    "AgentConfig",
    "AutomationConfig",
    "CodegenConfig",
    "GitHubConfig",
    "OrchestratorConfig",
    "get_config",
    "load_config",
    "reset_config",
]
