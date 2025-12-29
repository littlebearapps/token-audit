#!/usr/bin/env python3
"""Bucket Configuration Module (task-247.12).

Loads and manages bucket classification configuration from token-audit.toml.
Provides pattern validation, threshold management, and config persistence.

Config search path (in priority order):
    1. ./token-audit.toml (CWD - project override)
    2. ~/.token-audit/token-audit.toml (user config)
    3. Package root token-audit.toml (bundled default)
    4. DEFAULT_BUCKET_PATTERNS (hardcoded fallback)
"""

from __future__ import annotations

import logging
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Try Python 3.11+ built-in tomllib, fall back to toml package
try:
    import tomllib

    HAS_TOMLLIB = True
except ImportError:
    try:
        import toml as tomllib  # type: ignore

        HAS_TOMLLIB = True
    except ImportError:
        HAS_TOMLLIB = False
        warnings.warn(
            "TOML support not available. Install 'toml' package: pip install toml",
            RuntimeWarning,
            stacklevel=2,
        )

# For writing TOML (tomllib is read-only)
try:
    import toml as toml_writer

    HAS_TOML_WRITER = True
except ImportError:
    HAS_TOML_WRITER = False


# =============================================================================
# Default Patterns (matches DEFAULT_BUCKET_PATTERNS in buckets.py)
# =============================================================================

DEFAULT_PATTERNS: dict[str, list[str]] = {
    "state_serialization": [
        r".*_get_.*",
        r".*_get$",
        r".*_list_.*",
        r".*_list$",
        r".*_snapshot.*",
        r".*_export.*",
        r".*_read.*",
        r".*_view.*",
        r".*_view$",
        r".*_fetch.*",
    ],
    "tool_discovery": [
        r".*_introspect.*",
        r".*_search_tools.*",
        r".*_describe.*",
        r".*_list_tools.*",
        r".*_schema.*",
        r".*_capabilities.*",
    ],
    # redundant: detected via content_hash, no patterns needed
    # drift: default bucket, no patterns needed
}

DEFAULT_THRESHOLDS: dict[str, int] = {
    "large_payload_threshold": 5000,
    "redundant_min_occurrences": 2,
}

# Standard locations to search for config (in priority order)
CONFIG_SEARCH_PATHS = [
    Path("token-audit.toml"),  # CWD (project-specific override)
    Path.home() / ".token-audit" / "token-audit.toml",  # User config
    Path(__file__).parent.parent.parent / "token-audit.toml",  # Package root
]


# =============================================================================
# Configuration Dataclass
# =============================================================================


@dataclass
class BucketConfig:
    """Bucket classification configuration.

    Attributes:
        patterns: Mapping of bucket names to lists of regex patterns.
            Only state_serialization and tool_discovery use patterns.
        large_payload_threshold: Token count above which a call is classified
            as state_serialization regardless of pattern match (default: 5000).
        redundant_min_occurrences: Minimum content_hash occurrences to classify
            as redundant. First occurrence is NOT redundant (default: 2).
        config_path: Path to the config file this was loaded from (or None).
    """

    patterns: dict[str, list[str]] = field(default_factory=lambda: DEFAULT_PATTERNS.copy())
    large_payload_threshold: int = 5000
    redundant_min_occurrences: int = 2
    config_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to TOML-compatible dict."""
        return {
            "buckets": {
                "large_payload_threshold": self.large_payload_threshold,
                "redundant_min_occurrences": self.redundant_min_occurrences,
                "patterns": self.patterns,
            }
        }


# =============================================================================
# Pattern Validation
# =============================================================================


def validate_pattern(pattern: str) -> tuple[bool, str | None]:
    """Validate a regex pattern.

    Args:
        pattern: Regex pattern string to validate.

    Returns:
        Tuple of (is_valid, error_message).
        If valid, error_message is None.
    """
    try:
        re.compile(pattern, re.IGNORECASE)
        return True, None
    except re.error as e:
        return False, str(e)


def validate_all_patterns(patterns: dict[str, list[str]]) -> list[tuple[str, str, str]]:
    """Validate all patterns in a configuration.

    Args:
        patterns: Mapping of bucket names to pattern lists.

    Returns:
        List of (bucket, pattern, error_message) for invalid patterns.
    """
    errors = []
    for bucket, pattern_list in patterns.items():
        for pattern in pattern_list:
            is_valid, error = validate_pattern(pattern)
            if not is_valid:
                errors.append((bucket, pattern, error or "Unknown error"))
    return errors


# =============================================================================
# Configuration Loading
# =============================================================================


def _find_config() -> Path | None:
    """Find the first available config file.

    Returns:
        Path to config file, or None if not found.
    """
    for path in CONFIG_SEARCH_PATHS:
        if path.exists() and path.is_file():
            return path
    return None


def load_config(path: Path | None = None) -> BucketConfig:
    """Load bucket configuration from TOML file.

    Args:
        path: Optional explicit path to config file.
            If None, searches standard locations.

    Returns:
        BucketConfig with merged patterns (user patterns extend defaults).

    Raises:
        ValueError: If config file has invalid regex patterns.
    """
    # Start with defaults
    config = BucketConfig(
        patterns={k: v.copy() for k, v in DEFAULT_PATTERNS.items()},
        large_payload_threshold=DEFAULT_THRESHOLDS["large_payload_threshold"],
        redundant_min_occurrences=DEFAULT_THRESHOLDS["redundant_min_occurrences"],
    )

    # Find config file
    config_path = path or _find_config()
    if config_path is None:
        logger.debug("No config file found, using defaults")
        return config

    if not HAS_TOMLLIB:
        logger.warning("TOML support not available, using defaults")
        return config

    # Load TOML
    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        logger.warning(f"Failed to load config from {config_path}: {e}")
        return config

    config.config_path = config_path

    # Extract [buckets] section
    buckets_section = data.get("buckets", {})
    if not buckets_section:
        logger.debug(f"No [buckets] section in {config_path}")
        return config

    # Load thresholds
    if "large_payload_threshold" in buckets_section:
        threshold = buckets_section["large_payload_threshold"]
        if isinstance(threshold, int) and threshold > 0:
            config.large_payload_threshold = threshold
        else:
            logger.warning(
                f"Invalid large_payload_threshold: {threshold} (must be positive integer)"
            )

    if "redundant_min_occurrences" in buckets_section:
        min_occ = buckets_section["redundant_min_occurrences"]
        if isinstance(min_occ, int) and min_occ >= 1:
            config.redundant_min_occurrences = min_occ
        else:
            logger.warning(f"Invalid redundant_min_occurrences: {min_occ} (must be integer >= 1)")

    # Load patterns (merge with defaults)
    patterns_section = buckets_section.get("patterns", {})
    for bucket, pattern_list in patterns_section.items():
        if not isinstance(pattern_list, list):
            logger.warning(f"Invalid patterns for bucket '{bucket}': expected list")
            continue

        # Validate all patterns
        for pattern in pattern_list:
            is_valid, error = validate_pattern(pattern)
            if not is_valid:
                raise ValueError(f"Invalid regex pattern in [{bucket}]: '{pattern}' - {error}")

        # Merge: user patterns completely replace defaults for that bucket
        config.patterns[bucket] = pattern_list

    logger.debug(f"Loaded bucket config from {config_path}")
    return config


# =============================================================================
# Configuration Saving
# =============================================================================


def save_config(config: BucketConfig, path: Path | None = None) -> Path:
    """Save bucket configuration to TOML file.

    Preserves existing non-bucket sections in the file.

    Args:
        config: BucketConfig to save.
        path: Path to save to. If None, uses config.config_path or
            ~/.token-audit/token-audit.toml.

    Returns:
        Path to saved config file.

    Raises:
        RuntimeError: If toml package not available for writing.
        ValueError: If no path specified and config has no config_path.
    """
    if not HAS_TOML_WRITER:
        raise RuntimeError("TOML writing not available. Install 'toml' package: pip install toml")

    # Determine save path
    save_path = path or config.config_path
    if save_path is None:
        save_path = Path.home() / ".token-audit" / "token-audit.toml"

    # Ensure parent directory exists
    save_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing config to preserve other sections
    existing_data: dict[str, Any] = {}
    if save_path.exists():
        try:
            with open(save_path, "rb") as f:
                existing_data = tomllib.load(f)
        except Exception as e:
            logger.warning(f"Failed to read existing config: {e}")

    # Update buckets section
    existing_data["buckets"] = {
        "large_payload_threshold": config.large_payload_threshold,
        "redundant_min_occurrences": config.redundant_min_occurrences,
        "patterns": config.patterns,
    }

    # Write back
    with open(save_path, "w") as f:
        toml_writer.dump(existing_data, f)

    logger.info(f"Saved bucket config to {save_path}")
    return save_path


# =============================================================================
# Configuration Modification Helpers
# =============================================================================


def add_pattern(config: BucketConfig, bucket: str, pattern: str) -> BucketConfig:
    """Add a pattern to a bucket.

    Args:
        config: BucketConfig to modify.
        bucket: Bucket name (state_serialization or tool_discovery).
        pattern: Regex pattern to add.

    Returns:
        Updated BucketConfig (same instance, modified in place).

    Raises:
        ValueError: If pattern is invalid regex or bucket name is invalid.
    """
    # Validate bucket name
    valid_buckets = {"state_serialization", "tool_discovery"}
    if bucket not in valid_buckets:
        raise ValueError(f"Invalid bucket '{bucket}'. Must be one of: {valid_buckets}")

    # Validate pattern
    is_valid, error = validate_pattern(pattern)
    if not is_valid:
        raise ValueError(f"Invalid regex pattern: '{pattern}' - {error}")

    # Add pattern if not already present
    if bucket not in config.patterns:
        config.patterns[bucket] = []

    if pattern not in config.patterns[bucket]:
        config.patterns[bucket].append(pattern)
        logger.debug(f"Added pattern '{pattern}' to bucket '{bucket}'")
    else:
        logger.debug(f"Pattern '{pattern}' already exists in bucket '{bucket}'")

    return config


def remove_pattern(config: BucketConfig, bucket: str, pattern: str) -> BucketConfig:
    """Remove a pattern from a bucket.

    Args:
        config: BucketConfig to modify.
        bucket: Bucket name.
        pattern: Regex pattern to remove.

    Returns:
        Updated BucketConfig (same instance, modified in place).
    """
    if bucket in config.patterns and pattern in config.patterns[bucket]:
        config.patterns[bucket].remove(pattern)
        logger.debug(f"Removed pattern '{pattern}' from bucket '{bucket}'")
    else:
        logger.debug(f"Pattern '{pattern}' not found in bucket '{bucket}'")

    return config


def set_threshold(config: BucketConfig, name: str, value: int) -> BucketConfig:
    """Set a threshold value.

    Args:
        config: BucketConfig to modify.
        name: Threshold name (large_payload_threshold or redundant_min_occurrences).
        value: New threshold value.

    Returns:
        Updated BucketConfig (same instance, modified in place).

    Raises:
        ValueError: If threshold name is invalid or value is invalid.
    """
    valid_thresholds = {"large_payload_threshold", "redundant_min_occurrences"}
    if name not in valid_thresholds:
        raise ValueError(f"Invalid threshold '{name}'. Must be one of: {valid_thresholds}")

    if not isinstance(value, int):
        raise ValueError(f"Threshold value must be integer, got {type(value).__name__}")

    if name == "large_payload_threshold":
        if value <= 0:
            raise ValueError("large_payload_threshold must be positive")
        config.large_payload_threshold = value
    elif name == "redundant_min_occurrences":
        if value < 1:
            raise ValueError("redundant_min_occurrences must be >= 1")
        config.redundant_min_occurrences = value

    logger.debug(f"Set threshold '{name}' to {value}")
    return config


# =============================================================================
# Convenience Functions
# =============================================================================


def get_default_config() -> BucketConfig:
    """Get a BucketConfig with all default values.

    Returns:
        BucketConfig with default patterns and thresholds.
    """
    return BucketConfig(
        patterns={k: v.copy() for k, v in DEFAULT_PATTERNS.items()},
        large_payload_threshold=DEFAULT_THRESHOLDS["large_payload_threshold"],
        redundant_min_occurrences=DEFAULT_THRESHOLDS["redundant_min_occurrences"],
    )


def reset_to_defaults(config: BucketConfig) -> BucketConfig:
    """Reset a config to default values.

    Args:
        config: BucketConfig to reset.

    Returns:
        Same config instance with default values.
    """
    config.patterns = {k: v.copy() for k, v in DEFAULT_PATTERNS.items()}
    config.large_payload_threshold = DEFAULT_THRESHOLDS["large_payload_threshold"]
    config.redundant_min_occurrences = DEFAULT_THRESHOLDS["redundant_min_occurrences"]
    return config
