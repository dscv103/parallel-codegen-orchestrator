"""Configuration Management with Pydantic.

This module implements configuration models using Pydantic for parsing and
validation of YAML/JSON configuration files with environment variable overrides.
"""

import json
from pathlib import Path

import structlog
import yaml
from pydantic import BaseModel, Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings

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
        project_number: Optional Projects v2 number
        default_branch: Default branch for creating new branches
    """

    token: SecretStr = Field(
        description="GitHub personal access token",
        min_length=1,
    )
    organization: str = Field(
        description="GitHub organization name",
        min_length=1,
    )
    repository: str = Field(
        description="Repository in format 'owner/repo'",
    )
    project_number: int | None = Field(
        default=None,
        description="GitHub Projects v2 number",
        gt=0,
    )
    default_branch: str = Field(
        default="main",
        description="Default branch for new branches",
    )

    @field_validator("token")
    @classmethod
    def validate_token(cls, v: SecretStr) -> SecretStr:
        """Validate that the token is not a placeholder.

        Args:
            v: The token value to validate

        Returns:
            The validated token

        Raises:
            ValueError: If token is a placeholder
        """
        token_str = v.get_secret_value()
        if "your_" in token_str or token_str == "":
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
    api_token: SecretStr = Field(
        description="Codegen API token",
        min_length=1,
    )
    base_url: str | None = Field(
        default=None,
        description="Custom Codegen API base URL",
    )

    @field_validator("org_id")
    @classmethod
    def validate_org_id(cls, v: str) -> str:
        """Validate that org_id is not a placeholder.

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

    @field_validator("api_token")
    @classmethod
    def validate_api_token(cls, v: SecretStr) -> SecretStr:
        """Validate that api_token is not a placeholder.

        Args:
            v: The value to validate

        Returns:
            The validated value

        Raises:
            ValueError: If value is a placeholder
        """
        token_str = v.get_secret_value()
        if "your-" in token_str or "your_" in token_str or token_str == "":
            msg = "Codegen configuration must be set (not a placeholder)"
            raise ValueError(msg)
        return v

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str | None) -> str | None:
        """Validate and normalize base URL.

        Args:
            v: The base URL to validate

        Returns:
            The validated and normalized base URL

        Raises:
            ValueError: If URL scheme is invalid
        """
        if v is None:
            return v

        # Strip trailing slash
        v = v.rstrip("/")

        # Validate scheme
        if not v.startswith(("http://", "https://")):
            msg = "Base URL must start with http:// or https://"
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


class OrchestratorConfig(BaseSettings):
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
    )

    model_config = {
        "env_nested_delimiter": "__",
        "env_prefix": "",
        "case_sensitive": False,
    }

    @field_validator("logging_level")
    @classmethod
    def validate_logging_level(cls, v: str) -> str:
        """Validate and normalize logging level."""
        if not isinstance(v, str):
            msg = "Logging level must be a string"
            raise TypeError(msg)

        # Convert to uppercase for case-insensitive validation
        level = v.upper()
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

        if level not in valid_levels:
            msg = f"logging_level must be one of {valid_levels}, got: {v}"
            raise ValueError(msg)

        return level

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

            # Parse and validate configuration (env vars handled by BaseSettings)
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



    def validate_config(self) -> list[str]:
        """Validate configuration and return list of warnings.

        Returns:
            List of validation warning messages (empty if no warnings)
        """
        warnings = []

        # Check for development/example tokens
        if self.github.token.get_secret_value().startswith("ghp_example"):
            warnings.append("GitHub token appears to be an example/placeholder")

        if self.codegen.api_token.get_secret_value().startswith("example_"):
            warnings.append("Codegen API token appears to be an example/placeholder")

        # Warn about security settings
        if self.automation.auto_merge_on_success:
            warnings.append(
                "Auto-merge is enabled - ensure proper testing and review processes",
            )

        # Warn about resource usage
        if self.agent.max_concurrent_agents == MAX_CONCURRENT_AGENTS:
            warnings.append(
                f"Using maximum concurrent agents ({MAX_CONCURRENT_AGENTS}) - monitor resource usage",
            )

        if self.agent.task_timeout_seconds > HIGH_TIMEOUT_THRESHOLD:  # 30 minutes
            warnings.append(
                f"Task timeout is high ({self.agent.task_timeout_seconds}s) - "
                "tasks may run for extended periods",
            )

        return warnings


# Global singleton instance
_config_instance: OrchestratorConfig | None = None


def load_config(config_path: str | Path | None = None) -> OrchestratorConfig:
    """Load configuration from file with environment variable overrides.

    Args:
        config_path: Path to configuration file (YAML or JSON). If None, searches for
                    config.yaml, config.yml, or config.json in current directory.

    Returns:
        Loaded and validated configuration with env var overrides

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If YAML parsing fails
        json.JSONDecodeError: If JSON parsing fails
        ValueError: If file format is unsupported or validation fails
    """
    # Search for default config file if none specified
    if config_path is None:
        default_paths = [
            Path("config.yaml"),
            Path("config.yml"),
            Path("config.json"),
        ]

        for path in default_paths:
            if path.exists():
                config_path = path
                break
        else:
            raise FileNotFoundError(
                "No configuration file found. Searched for: " +
                ", ".join(str(p) for p in default_paths),
            )
    else:
        config_path = Path(config_path)

        if not config_path.exists():
            msg = f"Configuration file not found: {config_path}"
            raise FileNotFoundError(msg)

    # Determine file format and parse
    suffix = config_path.suffix.lower()

    if suffix in {".yaml", ".yml"}:
        with config_path.open("r") as f:
            config_data = yaml.safe_load(f)
    elif suffix == ".json":
        with config_path.open("r") as f:
            config_data = json.load(f)
    else:
        msg = f"Unsupported config file format: {suffix}"
        raise ValueError(msg)

    # Create configuration with validation
    try:
        return OrchestratorConfig(**config_data)
    except ValidationError as e:
        msg = f"Configuration validation failed: {e}"
        raise ValueError(msg) from e


def get_config(config_path: str | Path | None = None, *, reload: bool = False) -> OrchestratorConfig:
    """Get configuration instance (singleton pattern).

    Args:
        config_path: Path to configuration file. If None, uses default locations.
        reload: If True, force reload from file even if cached

    Returns:
        Configuration instance

    Raises:
        FileNotFoundError: If no config file found in default locations
    """
    global _config_instance  # noqa: PLW0603

    # Return cached instance if available and not reloading
    if _config_instance is not None and not reload:
        return _config_instance

    # Determine config path
    if config_path is None:
        # Try default locations
        default_paths = [
            Path("config.yaml"),
            Path("config.yml"),
            Path("config.json"),
        ]

        config_path = None
        for path in default_paths:
            if path.exists():
                config_path = path
                break

        if config_path is None:
            msg = "No configuration file found in default locations"
            raise FileNotFoundError(msg)

    # Load and cache configuration
    _config_instance = load_config(config_path)
    return _config_instance


def reset_config() -> None:
    """Reset cached configuration instance."""
    global _config_instance  # noqa: PLW0603
    _config_instance = None


# Export main configuration class and functions
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
