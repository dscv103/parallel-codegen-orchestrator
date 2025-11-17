# CI/CD Pipeline Guide

This document explains the CI/CD pipeline and code quality tools configured for the Parallel Codegen Orchestrator project.

## Overview

The CI/CD pipeline automatically runs on every push and pull request to `main` and `develop` branches. It performs comprehensive code quality checks, security scanning, testing, and validation to ensure code meets project standards.

## Pipeline Jobs

### 1. Code Quality Checks
**What it does:**
- Runs Ruff linter with all CodeRabbit rules
- Checks code formatting (Ruff format, Black)
- Validates import sorting (isort)
- Performs type checking (MyPy)

**Key checks:**
- PEP 8 compliance
- Type hints on all functions
- Proper async/await patterns
- Security best practices (Bandit rules)
- Code complexity (max 15)

**Fails on:** Critical linting errors, formatting issues, import order problems

### 2. Security Scanning
**What it does:**
- Scans code for security vulnerabilities (Bandit)
- Checks dependencies for known CVEs (pip-audit)
- Generates security reports

**Key checks:**
- No hardcoded secrets
- Safe API usage
- Dependency vulnerabilities
- SQL injection prevention
- Command injection prevention

**Fails on:** High-severity security issues

### 3. YAML Validation
**What it does:**
- Validates YAML syntax
- Checks YAML formatting and structure
- Ensures consistent style

**Fails on:** Invalid YAML, syntax errors

### 4. Markdown Linting
**What it does:**
- Validates Markdown documentation
- Checks formatting consistency
- Ensures proper structure

**Fails on:** Major documentation issues (optional)

### 5. Shell Script Validation
**What it does:**
- Runs ShellCheck on all shell scripts
- Validates bash/sh syntax
- Checks for common scripting errors

**Fails on:** Critical script errors (optional)

### 6. Test Suite
**What it does:**
- Runs all unit and integration tests
- Generates coverage reports (target: 80%+)
- Uploads coverage to Codecov

**Key checks:**
- All tests pass
- Coverage meets threshold
- Async tests work correctly
- Mocking is proper

**Fails on:** Test failures, insufficient coverage

### 7. Code Complexity Analysis
**What it does:**
- Calculates cyclomatic complexity
- Generates maintainability index
- Identifies complex functions

**Key checks:**
- Functions with complexity > 10
- Overall maintainability score
- Code quality metrics

**Fails on:** (Optional - informational only)

### 8. Dependency Validation
**What it does:**
- Verifies Python 3.13+ compatibility
- Checks for dependency conflicts
- Validates requirements

**Fails on:** (Optional - informational only)

## Configuration Files

### `.github/workflows/ci.yml`
Main GitHub Actions workflow file that orchestrates all checks.

### `ruff.toml`
Ruff linter configuration matching CodeRabbit rules:
- Python 3.13+ target
- Line length: 100 characters
- All rule categories enabled (E, F, W, C90, I, N, D, UP, etc.)
- Google-style docstrings
- Max complexity: 15

### `mypy.ini`
MyPy type checker configuration:
- Strict mode enabled
- Python 3.13+ syntax
- Ignore missing imports for third-party libs
- Pretty output with error codes

### `pyproject.toml`
Combined configuration for:
- **Black**: Line length 100, Python 3.13
- **isort**: Black-compatible profile
- **pytest**: Coverage settings, test markers
- **coverage**: 80%+ target, branch coverage

### `.yamllint.yaml`
YAML linting rules:
- Max line length: 120
- 2-space indentation
- Truthy values allowed

### `.markdownlint.json`
Markdown style rules:
- Line length: 120
- Fenced code blocks
- Consistent styling

### `.pre-commit-config.yaml`
Pre-commit hooks for local development (see below)

## Running Checks Locally

### Install Tools
```bash
# Install Python tools
pip install ruff mypy black isort pytest pytest-cov pytest-asyncio
pip install bandit yamllint radon

# Install pre-commit hooks (recommended)
pip install pre-commit
pre-commit install
```

### Run Individual Checks

**Ruff linter:**
```bash
ruff check .
ruff check . --fix  # Auto-fix issues
```

**Ruff formatter:**
```bash
ruff format .
ruff format --check .  # Check only, no changes
```

**Black formatter:**
```bash
black .
black --check .  # Check only
```

**Import sorting:**
```bash
isort .
isort --check-only .  # Check only
```

**Type checking:**
```bash
mypy src/
```

**Security scan:**
```bash
bandit -r src/
```

**YAML validation:**
```bash
yamllint .
```

**Run all tests:**
```bash
pytest tests/ --cov=src --cov-report=html
```

**Code complexity:**
```bash
radon cc src/ -a  # Average complexity
radon cc src/ -n C  # Functions with complexity > 10
radon mi src/  # Maintainability index
```

### Run All Checks
```bash
# Using pre-commit (runs all configured hooks)
pre-commit run --all-files
```

## Pre-commit Hooks

Pre-commit hooks run automatically before each commit to catch issues early.

**Setup:**
```bash
pip install pre-commit
pre-commit install
```

**Configured hooks:**
1. Ruff (linter + formatter)
2. Black (formatter)
3. isort (import sorting)
4. MyPy (type checking)
5. yamllint (YAML validation)
6. markdownlint (Markdown validation)
7. Bandit (security)
8. Standard checks (trailing whitespace, file endings, etc.)
9. ShellCheck (shell scripts)

**Skip hooks temporarily:**
```bash
git commit --no-verify
```

## CI/CD Status Badges

Add to README.md:
```markdown
![CI/CD Pipeline](https://github.com/dscv101/parallel-codegen-orchestrator/actions/workflows/ci.yml/badge.svg)
```

## Fixing Common Issues

### Ruff Errors
```bash
# Auto-fix most issues
ruff check . --fix

# Format code
ruff format .
```

### Import Order Issues
```bash
# Fix import sorting
isort .
```

### Type Errors
Review MyPy output and add type hints:
```python
# Bad
def process_task(task_id, config):
    ...

# Good
def process_task(task_id: str, config: dict[str, Any]) -> TaskResult:
    ...
```

### Test Failures
```bash
# Run tests with verbose output
pytest tests/ -vv

# Run specific test
pytest tests/test_dependency_graph.py::test_cycle_detection -vv

# Run with debugger
pytest tests/ --pdb
```

### Coverage Issues
```bash
# See what's not covered
pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html
```

## Matching CodeRabbit Configuration

The CI/CD pipeline is configured to match CodeRabbit's review settings:

| Tool | CodeRabbit | CI/CD |
|------|------------|-------|
| Ruff | ✅ All rules | ✅ Same rules |
| Type checking | ✅ Strict | ✅ MyPy strict |
| Formatting | ✅ Black-style | ✅ Black + Ruff |
| Security | ✅ Bandit rules | ✅ Bandit scan |
| YAML | ✅ yamllint | ✅ yamllint |
| Markdown | ✅ markdownlint | ✅ markdownlint |
| Complexity | ✅ Max 15 | ✅ Radon |
| Python version | ✅ 3.13+ | ✅ 3.13+ |

## Workflow Triggers

The pipeline runs on:
- **Push** to `main` or `develop`
- **Pull requests** to `main` or `develop`
- **Manual trigger** (workflow_dispatch)

## Artifacts

The pipeline generates artifacts:
- **Security Report**: Bandit JSON report
- **Coverage Report**: HTML coverage report
- **Test Results**: XML test results

Access artifacts from the Actions tab in GitHub.

## Required Status Checks

Configure branch protection rules to require:
- ✅ Code Quality Checks (critical)
- ✅ YAML Validation (critical)
- ⚠️ Security Scan (warning)
- ⚠️ Test Suite (warning)

## Performance

Typical run times:
- Code Quality: ~2-3 minutes
- Security Scan: ~1-2 minutes
- Tests: ~3-5 minutes
- **Total**: ~8-12 minutes

## Troubleshooting

### Pipeline Fails on First Run
Normal - no source code yet. Pipeline will pass once code is added.

### MyPy Errors on Third-party Libraries
Already configured to ignore missing imports. If issues persist, add to `mypy.ini`:
```ini
[mypy-library_name.*]
ignore_missing_imports = True
```

### Pre-commit is Slow
```bash
# Skip slow hooks during development
SKIP=mypy git commit -m "message"

# Or disable temporarily
pre-commit uninstall
```

### False Positives in Security Scan
Add `# nosec` comment with justification:
```python
password = os.getenv("PASSWORD")  # nosec - from secure env var
```

## Resources

- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [MyPy Documentation](https://mypy.readthedocs.io/)
- [pytest Documentation](https://docs.pytest.org/)
- [pre-commit Documentation](https://pre-commit.com/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)

---

**Questions?** Check AGENTS.md for architecture details or CODERABBIT.md for review guidelines.