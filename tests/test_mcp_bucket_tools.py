"""
Tests for MCP Bucket Configuration Tools (v1.0.4 - task-247.15).

Tests cover:
- config_list_patterns tool
- config_add_pattern tool
- config_remove_pattern tool
- config_set_threshold tool
- bucket_analyze tool

These tests verify the MCP tool implementations in server/tools.py.
Note: Tests use mocked/isolated config paths to avoid modifying real configs.
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from token_audit.bucket_config import HAS_TOML_WRITER, get_default_config, save_config

# Skip entire module if MCP server dependencies not installed
try:
    from token_audit.server import tools as _  # noqa: F401

    HAS_SERVER_DEPS = True
except ImportError:
    HAS_SERVER_DEPS = False

pytestmark = pytest.mark.skipif(
    not HAS_SERVER_DEPS or not HAS_TOML_WRITER,
    reason="MCP server dependencies not installed or toml package missing",
)


# ============================================================================
# Test: config_list_patterns
# ============================================================================


class TestConfigListPatterns:
    """Tests for config_list_patterns MCP tool."""

    def test_returns_all_patterns(self, tmp_path: Path) -> None:
        """Test listing all patterns and thresholds."""
        from token_audit.server.tools import config_list_patterns

        # Create a config file
        config = get_default_config()
        config_file = tmp_path / "token-audit.toml"
        save_config(config, config_file)

        with patch("token_audit.bucket_config.CONFIG_SEARCH_PATHS", [config_file]):
            result = config_list_patterns()

        assert "state_serialization" in result.patterns
        assert "tool_discovery" in result.patterns
        assert result.thresholds["large_payload_threshold"] == 5000
        assert result.thresholds["redundant_min_occurrences"] == 2

    def test_filters_by_bucket(self, tmp_path: Path) -> None:
        """Test filtering patterns by bucket name."""
        from token_audit.server.tools import config_list_patterns

        config = get_default_config()
        config_file = tmp_path / "token-audit.toml"
        save_config(config, config_file)

        with patch("token_audit.bucket_config.CONFIG_SEARCH_PATHS", [config_file]):
            result = config_list_patterns(bucket="state_serialization")

        assert "state_serialization" in result.patterns
        assert "tool_discovery" not in result.patterns

    def test_unknown_bucket_returns_empty(self, tmp_path: Path) -> None:
        """Test filtering by unknown bucket returns empty patterns."""
        from token_audit.server.tools import config_list_patterns

        config = get_default_config()
        config_file = tmp_path / "token-audit.toml"
        save_config(config, config_file)

        with patch("token_audit.bucket_config.CONFIG_SEARCH_PATHS", [config_file]):
            result = config_list_patterns(bucket="nonexistent")

        assert result.patterns == {}


# ============================================================================
# Test: config_add_pattern
# ============================================================================


class TestConfigAddPattern:
    """Tests for config_add_pattern MCP tool."""

    def test_adds_valid_pattern(self, tmp_path: Path) -> None:
        """Test adding a valid pattern."""
        from token_audit.server.tools import config_add_pattern

        config = get_default_config()
        config_file = tmp_path / "token-audit.toml"
        save_config(config, config_file)

        with patch("token_audit.bucket_config.CONFIG_SEARCH_PATHS", [config_file]):
            with patch("token_audit.bucket_config._find_config", return_value=config_file):
                result = config_add_pattern(
                    bucket="state_serialization",
                    pattern=r"my_custom_.*",
                )

        assert result.success is True
        assert "my_custom_.*" in result.patterns
        assert result.bucket == "state_serialization"

    def test_rejects_invalid_regex(self, tmp_path: Path) -> None:
        """Test rejecting invalid regex pattern."""
        from token_audit.server.tools import config_add_pattern

        config = get_default_config()
        config_file = tmp_path / "token-audit.toml"
        save_config(config, config_file)

        with patch("token_audit.bucket_config.CONFIG_SEARCH_PATHS", [config_file]):
            result = config_add_pattern(
                bucket="state_serialization",
                pattern=r"[invalid",
            )

        assert result.success is False
        assert "Invalid regex" in result.message

    def test_rejects_invalid_bucket(self, tmp_path: Path) -> None:
        """Test rejecting unknown bucket name."""
        from token_audit.server.tools import config_add_pattern

        config = get_default_config()
        config_file = tmp_path / "token-audit.toml"
        save_config(config, config_file)

        with patch("token_audit.bucket_config.CONFIG_SEARCH_PATHS", [config_file]):
            result = config_add_pattern(
                bucket="unknown_bucket",
                pattern=r".*pattern.*",
            )

        assert result.success is False
        assert "Invalid bucket" in result.message


# ============================================================================
# Test: config_remove_pattern
# ============================================================================


class TestConfigRemovePattern:
    """Tests for config_remove_pattern MCP tool."""

    def test_removes_existing_pattern(self, tmp_path: Path) -> None:
        """Test removing an existing pattern."""
        from token_audit.server.tools import config_remove_pattern

        config = get_default_config()
        config_file = tmp_path / "token-audit.toml"
        save_config(config, config_file)

        pattern_to_remove = r".*_get_.*"

        with patch("token_audit.bucket_config.CONFIG_SEARCH_PATHS", [config_file]):
            with patch("token_audit.bucket_config._find_config", return_value=config_file):
                result = config_remove_pattern(
                    bucket="state_serialization",
                    pattern=pattern_to_remove,
                )

        assert result.success is True
        assert pattern_to_remove not in result.patterns

    def test_handles_missing_pattern(self, tmp_path: Path) -> None:
        """Test handling removal of non-existent pattern."""
        from token_audit.server.tools import config_remove_pattern

        config = get_default_config()
        config_file = tmp_path / "token-audit.toml"
        save_config(config, config_file)

        with patch("token_audit.bucket_config.CONFIG_SEARCH_PATHS", [config_file]):
            result = config_remove_pattern(
                bucket="state_serialization",
                pattern="nonexistent_pattern",
            )

        assert result.success is False
        assert "not found" in result.message.lower()

    def test_handles_unknown_bucket(self, tmp_path: Path) -> None:
        """Test handling removal from unknown bucket."""
        from token_audit.server.tools import config_remove_pattern

        config = get_default_config()
        config_file = tmp_path / "token-audit.toml"
        save_config(config, config_file)

        with patch("token_audit.bucket_config.CONFIG_SEARCH_PATHS", [config_file]):
            result = config_remove_pattern(
                bucket="unknown_bucket",
                pattern=r".*pattern.*",
            )

        assert result.success is False
        assert "Unknown bucket" in result.message


# ============================================================================
# Test: config_set_threshold
# ============================================================================


class TestConfigSetThreshold:
    """Tests for config_set_threshold MCP tool."""

    def test_sets_valid_threshold(self, tmp_path: Path) -> None:
        """Test setting a valid threshold."""
        from token_audit.server.tools import config_set_threshold

        config = get_default_config()
        config_file = tmp_path / "token-audit.toml"
        save_config(config, config_file)

        with patch("token_audit.bucket_config.CONFIG_SEARCH_PATHS", [config_file]):
            with patch("token_audit.bucket_config._find_config", return_value=config_file):
                result = config_set_threshold(
                    name="large_payload_threshold",
                    value=10000,
                )

        assert result.success is True
        assert result.thresholds["large_payload_threshold"] == 10000

    def test_rejects_invalid_threshold_name(self, tmp_path: Path) -> None:
        """Test rejecting unknown threshold name."""
        from token_audit.server.tools import config_set_threshold

        config = get_default_config()
        config_file = tmp_path / "token-audit.toml"
        save_config(config, config_file)

        with patch("token_audit.bucket_config.CONFIG_SEARCH_PATHS", [config_file]):
            result = config_set_threshold(
                name="unknown_threshold",
                value=100,
            )

        assert result.success is False
        assert "Invalid threshold" in result.message


# ============================================================================
# Test: bucket_analyze
# ============================================================================


class TestBucketAnalyze:
    """Tests for bucket_analyze MCP tool."""

    def test_no_sessions_returns_error(self, tmp_path: Path) -> None:
        """Test analyzing when no sessions exist."""
        from token_audit.server.tools import bucket_analyze

        # Create empty storage directory
        storage_dir = tmp_path / "sessions"
        storage_dir.mkdir(parents=True)

        with patch("token_audit.storage.get_default_base_dir", return_value=storage_dir):
            result = bucket_analyze()

        assert result.success is False
        assert "No sessions" in result.message or "No sessions" in result.summary

    def test_session_not_found(self, tmp_path: Path) -> None:
        """Test analyzing non-existent session."""
        from token_audit.server.tools import bucket_analyze

        # Create empty storage directory
        storage_dir = tmp_path / "sessions"
        storage_dir.mkdir(parents=True)

        with patch("token_audit.storage.get_default_base_dir", return_value=storage_dir):
            result = bucket_analyze(session_id="nonexistent-session-id")

        assert result.success is False
        assert "not found" in result.message.lower()


# ============================================================================
# Test: Output Schema Compliance
# ============================================================================


class TestOutputSchemas:
    """Tests for Pydantic output schema compliance."""

    def test_config_list_patterns_schema(self) -> None:
        """Test ConfigListPatternsOutput schema fields."""
        from token_audit.server.schemas import ConfigListPatternsOutput

        output = ConfigListPatternsOutput(
            patterns={"test": [".*"]},
            thresholds={"large_payload_threshold": 5000},
            config_path="/path/to/config.toml",
        )
        data = output.model_dump()

        assert "patterns" in data
        assert "thresholds" in data
        assert "config_path" in data

    def test_config_add_pattern_schema(self) -> None:
        """Test ConfigAddPatternOutput schema fields."""
        from token_audit.server.schemas import ConfigAddPatternOutput

        output = ConfigAddPatternOutput(
            success=True,
            message="Added pattern",
            bucket="state_serialization",
            patterns=[".*_get_.*"],
        )
        data = output.model_dump()

        assert data["success"] is True
        assert "message" in data
        assert "bucket" in data
        assert "patterns" in data

    def test_bucket_analyze_schema(self) -> None:
        """Test BucketAnalyzeOutput schema fields."""
        from token_audit.server.schemas import BucketAnalyzeOutput, BucketStats

        output = BucketAnalyzeOutput(
            success=True,
            session_id="test-123",
            buckets={
                "state_serialization": BucketStats(
                    count=5,
                    tokens=1000,
                    percentage=50.0,
                    tools=["get_data", "list_items"],
                )
            },
            total_tokens=2000,
            total_calls=10,
            summary="state_serialization: 50.0%",
            message=None,
        )
        data = output.model_dump()

        assert data["success"] is True
        assert data["session_id"] == "test-123"
        assert "state_serialization" in data["buckets"]
        assert data["total_tokens"] == 2000
        assert data["total_calls"] == 10
