# Contributing to MCP Audit

Thank you for your interest in contributing to MCP Audit! This guide covers everything you need to know to add features, fix bugs, or extend platform support.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Development Setup](#development-setup)
3. [Adding Platform Adapters](#adding-platform-adapters)
4. [Plugin System](#plugin-system)
5. [Testing Requirements](#testing-requirements)
6. [Pull Request Workflow](#pull-request-workflow)
7. [Code Style](#code-style)
8. [Documentation](#documentation)
9. [Releasing](#releasing)

---

## Getting Started

### Prerequisites

- Python 3.8+
- Git
- A GitHub account

### Quick Setup

```bash
# Clone the repository
git clone https://github.com/littlebearapps/mcp-audit.git
cd mcp-audit

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode with all dependencies
pip install -e ".[dev]"

# Run tests to verify setup
pytest
```

---

## Development Setup

### Project Structure

```
mcp-audit/
├── src/mcp_audit/
│   ├── __init__.py
│   ├── cli.py                  # Command-line interface
│   ├── base_tracker.py         # BaseTracker abstract class
│   ├── claude_code_adapter.py  # Claude Code platform adapter
│   ├── codex_cli_adapter.py    # Codex CLI platform adapter
│   ├── gemini_cli_adapter.py   # Gemini CLI platform adapter
│   ├── token_estimator.py      # Token estimation for Codex/Gemini
│   ├── session_manager.py      # Session management
│   ├── storage.py              # Session storage and indexing
│   ├── pricing_config.py       # Pricing configuration
│   ├── pricing_api.py          # LiteLLM dynamic pricing (v0.6.0)
│   ├── schema_analyzer.py      # MCP schema analysis (v0.6.0)
│   ├── normalization.py        # Data normalization
│   ├── privacy.py              # Privacy utilities
│   ├── smells.py               # Smell detection engine (v0.5.0)
│   ├── zombie_detector.py      # Zombie tool detection (v0.5.0)
│   └── display/                # TUI components
│       ├── __init__.py
│       ├── rich_display.py     # Rich terminal display
│       ├── themes.py           # Color themes
│       └── snapshot.py         # Display snapshots
├── tests/
│   ├── __init__.py
│   ├── test_storage.py
│   ├── test_claude_code_adapter.py
│   ├── test_codex_cli_adapter.py
│   ├── test_gemini_cli_adapter.py
│   ├── test_token_estimator.py
│   ├── test_smells.py              # Smell detection tests (v0.5.0)
│   ├── test_zombie_detector.py     # Zombie detection tests (v0.5.0)
│   └── fixtures/                   # Test data
├── docs/
└── pyproject.toml
```

### Development Dependencies

```bash
# Install development dependencies
pip install -e ".[dev]"

# This includes:
# - pytest (testing)
# - pytest-cov (coverage)
# - mypy (type checking)
# - black (formatting)
# - ruff (linting)
```

---

## Adding Platform Adapters

The most common contribution is adding support for a new AI coding assistant platform.

### Step 1: Understand the BaseTracker Interface

All platform adapters inherit from `BaseTracker`:

```python
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Iterator
from dataclasses import dataclass

@dataclass
class TrackerEvent:
    """Normalized event from any platform."""
    timestamp: str
    event_type: str  # "token_usage", "tool_call", "session_start", "session_end"
    data: Dict[str, Any]

class BaseTracker(ABC):
    """Abstract base class for platform-specific trackers."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform identifier (e.g., 'claude_code', 'codex_cli')."""
        pass

    @abstractmethod
    def discover_sessions(self) -> Iterator[str]:
        """
        Discover active sessions to track.
        Yields session identifiers (paths, PIDs, etc.).
        """
        pass

    @abstractmethod
    def attach(self, session_id: str) -> bool:
        """
        Attach to an active session.
        Returns True if successful.
        """
        pass

    @abstractmethod
    def read_events(self) -> Iterator[TrackerEvent]:
        """
        Read events from the attached session.
        Yields normalized TrackerEvent objects.
        """
        pass

    @abstractmethod
    def detach(self) -> None:
        """Clean up when tracking ends."""
        pass

    def normalize_tool_name(self, raw_name: str) -> str:
        """
        Normalize tool names for consistency.
        Override if platform has non-standard naming.
        Default: return as-is.
        """
        return raw_name
```

### Step 2: Create Your Adapter

Create a new file in `src/mcp_audit/trackers/`:

```python
# src/mcp_audit/trackers/gemini_cli.py

from typing import Iterator, Optional
from .base import BaseTracker, TrackerEvent

class GeminiCLITracker(BaseTracker):
    """Tracker for Google's Gemini CLI."""

    @property
    def platform_name(self) -> str:
        return "gemini_cli"

    def discover_sessions(self) -> Iterator[str]:
        """
        Discover active Gemini CLI sessions.
        Implementation depends on how Gemini CLI exposes sessions.
        """
        # Example: Check for running processes
        import subprocess
        result = subprocess.run(
            ["pgrep", "-f", "gemini"],
            capture_output=True,
            text=True
        )
        for pid in result.stdout.strip().split('\n'):
            if pid:
                yield pid

    def attach(self, session_id: str) -> bool:
        """Attach to a Gemini CLI session by PID."""
        self._pid = session_id
        # Set up monitoring (log file, API hook, etc.)
        return True

    def read_events(self) -> Iterator[TrackerEvent]:
        """Read events from Gemini CLI."""
        # Implementation depends on how Gemini exposes data
        # Could be: log files, API responses, stdout capture
        pass

    def detach(self) -> None:
        """Clean up Gemini tracking."""
        self._pid = None
```

### Step 3: Register the Adapter

Add to `src/mcp_audit/trackers/__init__.py`:

```python
from .base import BaseTracker, TrackerEvent
from .claude_code import ClaudeCodeTracker
from .codex_cli import CodexCLITracker
from .gemini_cli import GeminiCLITracker  # Add this

PLATFORM_TRACKERS = {
    "claude_code": ClaudeCodeTracker,
    "codex_cli": CodexCLITracker,
    "gemini_cli": GeminiCLITracker,  # Add this
}

def get_tracker(platform: str) -> BaseTracker:
    """Get tracker instance for platform."""
    if platform not in PLATFORM_TRACKERS:
        raise ValueError(f"Unknown platform: {platform}")
    return PLATFORM_TRACKERS[platform]()
```

### Step 4: Add Platform Documentation

Create `docs/platforms/gemini-cli.md` following the existing guides as templates.

### Step 5: Add Tests

Create `tests/test_trackers/test_gemini_cli.py`:

```python
import pytest
from mcp_audit.trackers.gemini_cli import GeminiCLITracker

class TestGeminiCLITracker:
    def test_platform_name(self):
        tracker = GeminiCLITracker()
        assert tracker.platform_name == "gemini_cli"

    def test_normalize_tool_name(self):
        tracker = GeminiCLITracker()
        # Add platform-specific normalization tests
        pass

    # Add more tests for discover, attach, read_events
```

---

## Plugin System

MCP Audit supports plugins for extending functionality without modifying core code.

### Plugin Types

1. **Platform Adapters** - Add new AI assistant support
2. **Analyzers** - Custom analysis algorithms
3. **Exporters** - New output formats
4. **Hooks** - Pre/post processing of events

### Creating a Plugin

#### 1. Platform Plugin

```python
# my_plugin/my_platform.py

from mcp_audit.trackers.base import BaseTracker, TrackerEvent

class MyPlatformTracker(BaseTracker):
    """Custom platform tracker."""

    @property
    def platform_name(self) -> str:
        return "my_platform"

    # Implement required methods...
```

#### 2. Analyzer Plugin

```python
# my_plugin/my_analyzer.py

from mcp_audit.analyzers.base import BaseAnalyzer

class MyAnalyzer(BaseAnalyzer):
    """Custom analysis plugin."""

    def analyze(self, sessions: list) -> dict:
        """
        Perform custom analysis on sessions.

        Args:
            sessions: List of session data dicts

        Returns:
            Analysis results dict
        """
        results = {}
        for session in sessions:
            # Custom analysis logic
            pass
        return results
```

#### 3. Exporter Plugin

```python
# my_plugin/my_exporter.py

from mcp_audit.exporters.base import BaseExporter

class MyExporter(BaseExporter):
    """Custom export format plugin."""

    @property
    def format_name(self) -> str:
        return "my_format"

    def export(self, data: dict, output_path: str) -> None:
        """Export data in custom format."""
        with open(output_path, 'w') as f:
            # Write in custom format
            pass
```

### Registering Plugins

#### Entry Points (Recommended)

In your plugin's `pyproject.toml`:

```toml
[project.entry-points."mcp_audit.trackers"]
my_platform = "my_plugin.my_platform:MyPlatformTracker"

[project.entry-points."mcp_audit.analyzers"]
my_analyzer = "my_plugin.my_analyzer:MyAnalyzer"

[project.entry-points."mcp_audit.exporters"]
my_format = "my_plugin.my_exporter:MyExporter"
```

#### Configuration File

Alternatively, in `~/.mcp-audit/config/plugins.toml`:

```toml
[plugins]
# Local plugin paths
paths = [
    "~/my-plugins/",
]

# Specific plugins to load
enabled = [
    "my_plugin.my_platform",
    "my_plugin.my_analyzer",
]

# Plugins to disable (even if installed)
disabled = []
```

### Plugin Discovery

MCP Audit discovers plugins at startup:

1. Check entry points (installed packages)
2. Check configured plugin paths
3. Load enabled plugins
4. Skip disabled plugins

---

## Testing Requirements

All contributions must include tests. We use pytest with the following requirements:

### Minimum Coverage

- **New features**: 80% coverage minimum
- **Bug fixes**: Test that reproduces the bug + fix
- **Platform adapters**: Full test suite for all methods

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=mcp_audit --cov-report=html

# Run specific test file
pytest tests/test_storage.py

# Run specific test
pytest tests/test_storage.py::TestStorageManager::test_write_session

# Run with verbose output
pytest -v
```

### Test Categories

#### Unit Tests

Test individual functions and classes in isolation:

```python
def test_session_id_generation():
    """Test that session IDs follow the correct format."""
    session_id = generate_session_id()
    assert session_id.startswith("session-")
    assert len(session_id) == 30  # session-YYYYMMDDTHHMMSS-6hex
```

#### Integration Tests

Test component interactions:

```python
def test_tracker_to_storage_flow(tmp_path):
    """Test events flow from tracker to storage."""
    storage = StorageManager(base_dir=tmp_path)
    tracker = MockTracker()

    # Simulate tracking session
    events = list(tracker.read_events())
    session_id = storage.write_session("test_platform", events)

    # Verify stored data
    loaded = storage.read_session("test_platform", session_id)
    assert len(loaded) == len(events)
```

#### Fixture Tests

Use pytest fixtures for common setup:

```python
@pytest.fixture
def sample_session():
    """Provide sample session data for tests."""
    return {
        "session_id": "session-20251125T103045-abc123",
        "platform": "claude_code",
        "token_usage": {
            "input_tokens": 1000,
            "output_tokens": 500,
        }
    }

def test_session_processing(sample_session):
    """Test processing a sample session."""
    result = process_session(sample_session)
    assert result["total_tokens"] == 1500
```

### Test Data

- Use `tests/fixtures/` for test data files
- Sanitize any real session data (no API keys, prompts, or PII)
- Include both valid and invalid data for edge case testing

---

## Pull Request Workflow

### Before You Start

1. **Bug fixes**: Check if an [Issue](https://github.com/littlebearapps/mcp-audit/issues) already exists
2. **New features**: Start a [Discussion](https://github.com/littlebearapps/mcp-audit/discussions/new?category=ideas) first
3. **Questions**: Use [Q&A Discussions](https://github.com/littlebearapps/mcp-audit/discussions/categories/q-a)
4. **Fork the repository** - Work in your own fork

### Development Flow

```bash
# 1. Fork and clone
git clone https://github.com/YOUR_USERNAME/mcp-audit.git
cd mcp-audit

# 2. Create feature branch
git checkout -b feature/my-feature

# 3. Make changes
# ... edit files ...

# 4. Run tests
pytest

# 5. Run linting
ruff check .
black --check .
mypy src/

# 6. Commit with conventional commits
git commit -m "feat: add Gemini CLI platform support"

# 7. Push to your fork
git push origin feature/my-feature

# 8. Open PR on GitHub
```

> **Note:** Your PR will be reviewed by a maintainer. Once approved and merged, your changes will be included in the next release and published to PyPI.

### Commit Messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add new feature
fix: resolve bug
docs: update documentation
test: add or update tests
refactor: code restructuring (no behavior change)
chore: maintenance tasks
```

Examples:
```
feat: add Gemini CLI platform adapter
fix: handle empty session files gracefully
docs: add contributing guide
test: add coverage for storage module
refactor: extract common tracker logic to base class
```

### PR Requirements

Your PR will be reviewed for:

1. **Tests pass** - All CI checks green
2. **Coverage maintained** - No significant coverage drop
3. **Lint clean** - No ruff or mypy errors
4. **Documentation** - New features documented
5. **Conventional commits** - Proper commit messages
6. **Single purpose** - One feature/fix per PR

### Review Process

1. **Automated checks** - CI runs tests, lint, type checking
2. **Code review** - Maintainer reviews code quality
3. **Feedback** - Address any requested changes
4. **Approval** - Maintainer approves
5. **Merge** - Squash and merge to main

---

## Code Style

### Python Style

We follow PEP 8 with some modifications:

- **Line length**: 100 characters (black default)
- **Imports**: Sorted by isort (integrated with ruff)
- **Docstrings**: Google style
- **Type hints**: Required for public APIs

### Formatting

```bash
# Format code
black .

# Check formatting
black --check .

# Sort imports
ruff check --fix .
```

### Type Checking

```bash
# Run mypy
mypy src/

# With strict mode
mypy src/ --strict
```

### Docstring Example

```python
def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    model: str,
    pricing: Optional[Dict[str, float]] = None
) -> float:
    """
    Calculate the estimated cost for token usage.

    Args:
        input_tokens: Number of input tokens consumed.
        output_tokens: Number of output tokens generated.
        model: Model identifier (e.g., "claude-sonnet-4").
        pricing: Optional custom pricing dict. Uses defaults if None.

    Returns:
        Estimated cost in USD.

    Raises:
        ValueError: If model is not found in pricing config.

    Example:
        >>> calculate_cost(1000, 500, "claude-sonnet-4")
        0.0105
    """
    pass
```

---

## Documentation

### When to Update Docs

- **New feature**: Add to relevant docs
- **API change**: Update API reference
- **Bug fix**: Update if behavior changes
- **New platform**: Create platform guide

### Documentation Structure

```
docs/
├── architecture.md      # System design
├── data-contract.md     # Compatibility guarantees
├── contributing.md      # This file
├── privacy-security.md  # Data handling
├── platforms/
│   ├── claude-code.md   # Platform guides
│   └── codex-cli.md
└── api/                 # API reference (generated)
```

### Documentation Style

- **Markdown** - All docs in Markdown format
- **Clear headings** - Use hierarchy (H1 > H2 > H3)
- **Code examples** - Include runnable examples
- **Links** - Cross-reference related docs

---

## Releasing

MCP Audit uses automated releases via GitHub Actions. When a version bump is merged to main, a new release is automatically published to PyPI.

### Release Process

1. **Bump version** in `pyproject.toml`:
   - Update `version = "X.Y.Z"` (single source of truth)
   - `src/mcp_audit/__init__.py` reads version automatically via `importlib.metadata`

2. **Update CHANGELOG.md**:
   - Add new section: `## [X.Y.Z] - YYYY-MM-DD`
   - Document changes under Added/Changed/Fixed/Removed

3. **Create PR** with version bump and changelog

4. **Merge PR** to main

5. **Automatic publishing**:
   - `auto-tag.yml` detects version change in `pyproject.toml`
   - Creates git tag `vX.Y.Z`
   - Maintainer triggers `release-both.yml` workflow with the tag
   - Workflow syncs to public repo and publishes to PyPI

### Version Numbering

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (X.0.0): Breaking changes
- **MINOR** (0.X.0): New features, backward compatible
- **PATCH** (0.0.X): Bug fixes, backward compatible

### Manual Release (Emergency)

If auto-tagging fails, you can manually create a tag:

```bash
git tag -a v0.3.2 -m "Release v0.3.2"
git push origin v0.3.2
```

This triggers the publish workflow.

### Verifying a Release

After merging a version bump:

1. Check [GitHub Actions](https://github.com/littlebearapps/mcp-audit/actions) for workflow runs
2. Verify tag was created: `git fetch --tags && git tag -l "v*"`
3. Check [PyPI](https://pypi.org/project/mcp-audit/) for new version

---

## Getting Help

- **Questions**: Open a [Discussion](https://github.com/littlebearapps/mcp-audit/discussions)
- **Bugs**: Open an [Issue](https://github.com/littlebearapps/mcp-audit/issues)
- **Feature ideas**: Open a Discussion first

---

## License

By contributing to MCP Audit, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to MCP Audit!
