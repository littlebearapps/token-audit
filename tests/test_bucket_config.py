"""
Tests for the Bucket Configuration Module (v1.0.4 - task-247.15).

Tests cover:
- Configuration loading from TOML
- Default patterns and thresholds
- Pattern validation (valid/invalid regex)
- Pattern add/remove operations
- Threshold setting and validation
- Configuration persistence (save/reload)
- Merge behavior with defaults
"""

from pathlib import Path

import pytest

from token_audit.bucket_config import (
    HAS_TOML_WRITER,
    BucketConfig,
    DEFAULT_PATTERNS,
    DEFAULT_THRESHOLDS,
    add_pattern,
    get_default_config,
    load_config,
    remove_pattern,
    reset_to_defaults,
    save_config,
    set_threshold,
    validate_all_patterns,
    validate_pattern,
)


# ============================================================================
# Test: Pattern Validation
# ============================================================================


class TestPatternValidation:
    """Tests for regex pattern validation."""

    def test_validate_pattern_valid_simple(self) -> None:
        """Test valid simple regex patterns."""
        is_valid, error = validate_pattern(r".*_get_.*")
        assert is_valid is True
        assert error is None

    def test_validate_pattern_valid_complex(self) -> None:
        """Test valid complex regex patterns."""
        is_valid, error = validate_pattern(r"^mcp__[a-z]+__\w+$")
        assert is_valid is True
        assert error is None

    def test_validate_pattern_invalid_regex(self) -> None:
        """Test invalid regex pattern with unmatched brackets."""
        is_valid, error = validate_pattern(r"[unclosed")
        assert is_valid is False
        assert error is not None
        assert "unterminated" in error.lower() or "bracket" in error.lower()

    def test_validate_pattern_invalid_quantifier(self) -> None:
        """Test invalid regex pattern with bad quantifier."""
        is_valid, error = validate_pattern(r"**invalid")
        assert is_valid is False
        assert error is not None

    def test_validate_all_patterns_valid(self) -> None:
        """Test validating all patterns returns empty list for valid patterns."""
        patterns = {
            "state_serialization": [r".*_get_.*", r".*_list_.*"],
            "tool_discovery": [r".*_introspect.*"],
        }
        errors = validate_all_patterns(patterns)
        assert errors == []

    def test_validate_all_patterns_with_errors(self) -> None:
        """Test validating patterns returns errors for invalid ones."""
        patterns = {
            "state_serialization": [r".*_get_.*", r"[invalid"],
            "tool_discovery": [r"++bad"],
        }
        errors = validate_all_patterns(patterns)
        assert len(errors) == 2
        # Each error is (bucket, pattern, error_message)
        buckets = [e[0] for e in errors]
        assert "state_serialization" in buckets
        assert "tool_discovery" in buckets


# ============================================================================
# Test: Configuration Loading
# ============================================================================


class TestBucketConfigLoading:
    """Tests for loading bucket configuration."""

    def test_default_patterns_when_no_file(self) -> None:
        """Test that defaults are used when no config file exists."""
        config = load_config(Path("/nonexistent/path/token-audit.toml"))
        assert config.patterns == DEFAULT_PATTERNS
        assert config.large_payload_threshold == DEFAULT_THRESHOLDS["large_payload_threshold"]
        assert config.redundant_min_occurrences == DEFAULT_THRESHOLDS["redundant_min_occurrences"]

    def test_get_default_config(self) -> None:
        """Test get_default_config returns fresh defaults."""
        config = get_default_config()
        assert config.patterns == DEFAULT_PATTERNS
        assert config.large_payload_threshold == 5000
        assert config.redundant_min_occurrences == 2
        assert config.config_path is None

    def test_load_from_toml(self, tmp_path: Path) -> None:
        """Test loading config from TOML file."""
        toml_content = """
[buckets]
large_payload_threshold = 10000
redundant_min_occurrences = 3

[buckets.patterns]
state_serialization = ["custom_.*"]
tool_discovery = ["discover_.*"]
"""
        config_file = tmp_path / "token-audit.toml"
        config_file.write_text(toml_content)

        config = load_config(config_file)
        assert config.large_payload_threshold == 10000
        assert config.redundant_min_occurrences == 3
        assert config.patterns["state_serialization"] == ["custom_.*"]
        assert config.patterns["tool_discovery"] == ["discover_.*"]
        assert config.config_path == config_file

    def test_load_invalid_regex_raises(self, tmp_path: Path) -> None:
        """Test that loading config with invalid regex raises ValueError."""
        toml_content = """
[buckets.patterns]
state_serialization = ["[invalid"]
"""
        config_file = tmp_path / "token-audit.toml"
        config_file.write_text(toml_content)

        with pytest.raises(ValueError) as exc_info:
            load_config(config_file)
        assert "Invalid regex pattern" in str(exc_info.value)

    def test_load_preserves_other_sections(self, tmp_path: Path) -> None:
        """Test that loading only reads [buckets] section."""
        toml_content = """
[pricing]
model = "claude-3-5-sonnet"

[buckets]
large_payload_threshold = 7500
"""
        config_file = tmp_path / "token-audit.toml"
        config_file.write_text(toml_content)

        config = load_config(config_file)
        assert config.large_payload_threshold == 7500
        # Patterns should be defaults since not specified
        assert "state_serialization" in config.patterns


# ============================================================================
# Test: Pattern Operations
# ============================================================================


class TestBucketConfigPatterns:
    """Tests for pattern add/remove operations."""

    def test_add_pattern_valid(self) -> None:
        """Test adding a valid pattern."""
        config = get_default_config()
        original_count = len(config.patterns["state_serialization"])

        add_pattern(config, "state_serialization", r"wpnav_get_.*")

        assert len(config.patterns["state_serialization"]) == original_count + 1
        assert r"wpnav_get_.*" in config.patterns["state_serialization"]

    def test_add_pattern_invalid_regex(self) -> None:
        """Test adding an invalid regex pattern raises ValueError."""
        config = get_default_config()

        with pytest.raises(ValueError) as exc_info:
            add_pattern(config, "state_serialization", r"[invalid")
        assert "Invalid regex pattern" in str(exc_info.value)

    def test_add_pattern_unknown_bucket(self) -> None:
        """Test adding pattern to unknown bucket raises ValueError."""
        config = get_default_config()

        with pytest.raises(ValueError) as exc_info:
            add_pattern(config, "unknown_bucket", r".*pattern.*")
        assert "Invalid bucket" in str(exc_info.value)

    def test_add_pattern_duplicate(self) -> None:
        """Test adding duplicate pattern doesn't add it again."""
        config = get_default_config()
        pattern = r".*_get_.*"  # Already in defaults

        original_count = len(config.patterns["state_serialization"])
        add_pattern(config, "state_serialization", pattern)

        # Should not add duplicate
        assert len(config.patterns["state_serialization"]) == original_count

    def test_remove_pattern(self) -> None:
        """Test removing an existing pattern."""
        config = get_default_config()
        pattern = r".*_get_.*"
        assert pattern in config.patterns["state_serialization"]

        remove_pattern(config, "state_serialization", pattern)

        assert pattern not in config.patterns["state_serialization"]

    def test_remove_pattern_not_found(self) -> None:
        """Test removing non-existent pattern is a no-op."""
        config = get_default_config()
        original = config.patterns["state_serialization"].copy()

        remove_pattern(config, "state_serialization", "nonexistent_pattern")

        assert config.patterns["state_serialization"] == original


# ============================================================================
# Test: Threshold Operations
# ============================================================================


class TestBucketConfigThresholds:
    """Tests for threshold setting operations."""

    def test_set_threshold_valid_large_payload(self) -> None:
        """Test setting large_payload_threshold."""
        config = get_default_config()

        set_threshold(config, "large_payload_threshold", 10000)

        assert config.large_payload_threshold == 10000

    def test_set_threshold_valid_redundant_min(self) -> None:
        """Test setting redundant_min_occurrences."""
        config = get_default_config()

        set_threshold(config, "redundant_min_occurrences", 5)

        assert config.redundant_min_occurrences == 5

    def test_set_threshold_invalid_name(self) -> None:
        """Test setting unknown threshold raises ValueError."""
        config = get_default_config()

        with pytest.raises(ValueError) as exc_info:
            set_threshold(config, "unknown_threshold", 100)
        assert "Invalid threshold" in str(exc_info.value)

    def test_set_threshold_invalid_value_negative(self) -> None:
        """Test setting negative threshold raises ValueError."""
        config = get_default_config()

        with pytest.raises(ValueError) as exc_info:
            set_threshold(config, "large_payload_threshold", -100)
        assert "positive" in str(exc_info.value).lower()

    def test_set_threshold_invalid_value_zero(self) -> None:
        """Test setting zero threshold raises ValueError for large_payload."""
        config = get_default_config()

        with pytest.raises(ValueError) as exc_info:
            set_threshold(config, "large_payload_threshold", 0)
        assert "positive" in str(exc_info.value).lower()

    def test_set_threshold_invalid_type(self) -> None:
        """Test setting non-integer threshold raises ValueError."""
        config = get_default_config()

        with pytest.raises(ValueError) as exc_info:
            set_threshold(config, "large_payload_threshold", "not_an_int")  # type: ignore
        assert "integer" in str(exc_info.value).lower()


# ============================================================================
# Test: Configuration Persistence
# ============================================================================


@pytest.mark.skipif(not HAS_TOML_WRITER, reason="toml package not installed for writing")
class TestBucketConfigPersistence:
    """Tests for saving and reloading configuration."""

    def test_save_and_reload(self, tmp_path: Path) -> None:
        """Test saving config and reloading it."""
        config = get_default_config()
        add_pattern(config, "state_serialization", r"custom_pattern_.*")
        set_threshold(config, "large_payload_threshold", 8000)

        save_path = tmp_path / "token-audit.toml"
        saved = save_config(config, save_path)
        assert saved == save_path

        reloaded = load_config(save_path)
        assert r"custom_pattern_.*" in reloaded.patterns["state_serialization"]
        assert reloaded.large_payload_threshold == 8000

    def test_save_preserves_other_sections(self, tmp_path: Path) -> None:
        """Test that saving preserves non-bucket sections."""
        # Create initial file with other sections
        toml_content = """
[pricing]
model = "claude-3-5-sonnet"
input_cost = 3.0

[other]
key = "value"
"""
        config_file = tmp_path / "token-audit.toml"
        config_file.write_text(toml_content)

        # Load, modify, save
        config = load_config(config_file)
        set_threshold(config, "large_payload_threshold", 9999)
        save_config(config, config_file)

        # Verify other sections preserved
        saved_content = config_file.read_text()
        assert "[pricing]" in saved_content
        assert "claude-3-5-sonnet" in saved_content
        assert "[other]" in saved_content
        assert 'key = "value"' in saved_content

    def test_to_dict(self) -> None:
        """Test BucketConfig.to_dict() returns TOML-compatible dict."""
        config = get_default_config()
        data = config.to_dict()

        assert "buckets" in data
        assert "large_payload_threshold" in data["buckets"]
        assert "redundant_min_occurrences" in data["buckets"]
        assert "patterns" in data["buckets"]


# ============================================================================
# Test: Reset to Defaults
# ============================================================================


class TestBucketConfigReset:
    """Tests for resetting configuration to defaults."""

    def test_reset_to_defaults(self) -> None:
        """Test reset_to_defaults restores default values."""
        config = get_default_config()

        # Modify config
        add_pattern(config, "state_serialization", r"custom_.*")
        set_threshold(config, "large_payload_threshold", 999)

        # Reset
        reset_to_defaults(config)

        assert config.patterns == DEFAULT_PATTERNS
        assert config.large_payload_threshold == 5000
        assert config.redundant_min_occurrences == 2


# ============================================================================
# Test: Integration with BucketClassifier
# ============================================================================


class TestBucketConfigIntegration:
    """Tests for integration with BucketClassifier."""

    def test_classifier_uses_config_patterns(self) -> None:
        """Test that BucketClassifier can use loaded config patterns."""
        from token_audit.buckets import BucketClassifier

        config = get_default_config()
        add_pattern(config, "state_serialization", r"my_custom_get_.*")

        classifier = BucketClassifier(
            patterns=config.patterns,
            thresholds={
                "large_payload_threshold": config.large_payload_threshold,
                "redundant_min_occurrences": config.redundant_min_occurrences,
            },
        )

        # Verify custom pattern matches
        assert classifier._matches_patterns("my_custom_get_data", "state_serialization")

    def test_classifier_uses_config_thresholds(self) -> None:
        """Test that BucketClassifier uses configured thresholds."""
        from token_audit.buckets import BucketClassifier, BucketThresholds

        config = get_default_config()
        set_threshold(config, "large_payload_threshold", 100)  # Very low threshold

        classifier = BucketClassifier(
            patterns=config.patterns,
            thresholds=BucketThresholds(
                large_payload_threshold=config.large_payload_threshold,
                redundant_min_occurrences=config.redundant_min_occurrences,
            ),
        )

        # Verify low threshold is used
        assert classifier.thresholds.large_payload_threshold == 100
